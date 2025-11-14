from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import permission_required
from django.views.decorators.http import require_POST
from django.contrib.auth.models import User, Group, Permission
from django.contrib import messages
from django.db import IntegrityError
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from collections import defaultdict


@permission_required('auth.view_user')
def manage_users(request):
    """
    Displays the list of users and handles the creation of new users.
    """
    if request.method == 'POST':
        if not request.user.has_perm('auth.add_user'):
            raise PermissionDenied

        username = request.POST.get('username')
        pass1 = request.POST.get('password')
        pass2 = request.POST.get('password_confirm')
        is_staff = request.POST.get('is_staff') == 'on'
        is_superuser = request.POST.get('is_superuser') == 'on'
        group_ids = request.POST.getlist('groups')

        if pass1 != pass2:
            messages.error(request, "كلمتا المرور غير متطابقتين.")
            return redirect('inventory:manage_users')

        if not username or not pass1:
            messages.error(request, "اسم المستخدم وكلمة المرور حقول إلزامية.")
            return redirect('inventory:manage_users')

        try:
            user = User.objects.create_user(username=username, password=pass1)
            user.is_staff = is_staff
            user.is_superuser = is_superuser
            user.save()
            user.groups.set(group_ids)
            messages.success(request, f"تم إنشاء المستخدم '{username}' بنجاح.")
        except IntegrityError:
            messages.error(request, f"اسم المستخدم '{username}' موجود بالفعل.")

        return redirect('inventory:manage_users')

    users = User.objects.prefetch_related('groups').order_by('username')
    groups = Group.objects.all()
    context = {
        'active_page': 'settings',
        'users': users,
        'all_groups': groups,
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/users/users_content.html', context)
    return render(request, 'inventory/users/users.html', context)


@require_POST
@permission_required('auth.change_user')
def edit_user(request, pk):
    """
    Handles editing an existing user's details.
    """
    user_to_edit = get_object_or_404(User, pk=pk)

    username = request.POST.get('username')
    is_staff = request.POST.get('is_staff') == 'on'
    is_superuser = request.POST.get('is_superuser') == 'on'
    group_ids = request.POST.getlist('groups')
    pass1 = request.POST.get('password')
    pass2 = request.POST.get('password_confirm')

    # Prevent non-superusers from escalating privileges
    if not request.user.is_superuser:
        if is_superuser != user_to_edit.is_superuser:
            messages.error(request, "لا يمكنك تغيير صلاحية المستخدم الخارق.")
            return redirect('inventory:manage_users')

    # Check for username collision
    if User.objects.filter(username=username).exclude(pk=pk).exists():
        messages.error(request, f"اسم المستخدم '{username}' مستخدم بالفعل.")
        return redirect('inventory:manage_users')

    user_to_edit.username = username
    user_to_edit.is_staff = is_staff
    user_to_edit.is_superuser = is_superuser

    if pass1:
        if pass1 != pass2:
            messages.error(request, "كلمتا المرور غير متطابقتين عند محاولة التغيير.")
            return redirect('inventory:manage_users')
        user_to_edit.set_password(pass1)

    user_to_edit.save()
    user_to_edit.groups.set(group_ids)

    messages.success(request, f"تم تحديث بيانات المستخدم '{username}' بنجاح.")
    return redirect('inventory:manage_users')


@require_POST
@permission_required('auth.delete_user')
def delete_user(request, pk):
    user_to_delete = get_object_or_404(User, pk=pk)
    if user_to_delete.is_superuser:
        messages.error(request, "لا يمكن حذف المستخدم الخارق.")
        return redirect('inventory:manage_users')
    if user_to_delete == request.user:
        messages.error(request, "لا يمكنك حذف حسابك الخاص.")
        return redirect('inventory:manage_users')
    
    username = user_to_delete.username
    user_to_delete.delete()
    messages.success(request, f"تم حذف المستخدم '{username}' بنجاح.")
    return redirect('inventory:manage_users')


@permission_required('auth.view_group')
def manage_groups(request):
    """
    Displays the list of groups and handles creation of new groups.
    """
    if request.method == 'POST':
        if not request.user.has_perm('auth.add_group'):
            raise PermissionDenied
        name = request.POST.get('name')
        if name:
            try:
                Group.objects.create(name=name)
                messages.success(request, f"تم إنشاء المجموعة '{name}' بنجاح.")
            except IntegrityError:
                messages.error(request, f"المجموعة '{name}' موجودة بالفعل.")
        return redirect('inventory:manage_groups')

    # Prepare permissions for the 'Edit' modal, grouped by app/model
    permissions = Permission.objects.select_related('content_type').filter(
        ~Q(content_type__app_label__in=['admin', 'sessions', 'contenttypes'])
    ).order_by('content_type__app_label', 'content_type__model', 'codename')

    grouped_permissions = defaultdict(list)
    for perm in permissions:
        # Create a readable group name like "Inventory | Product"
        model_verbose_name = perm.content_type.model_class()._meta.verbose_name
        group_key = f"{perm.content_type.app_label.title()} | {model_verbose_name}"
        grouped_permissions[group_key].append(perm)

    context = {
        'active_page': 'settings',
        'groups': Group.objects.prefetch_related('permissions').all(),
        'grouped_permissions': dict(grouped_permissions)
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/users/groups_content.html', context)
    return render(request, 'inventory/users/groups.html', context)


@require_POST
@permission_required('auth.change_group')
def edit_group(request, pk):
    """
    Handles editing a group's name and its associated permissions.
    """
    group = get_object_or_404(Group, pk=pk)
    name = request.POST.get('name')
    permission_ids = request.POST.getlist('permissions')

    if Group.objects.filter(name=name).exclude(pk=pk).exists():
        messages.error(request, f"اسم المجموعة '{name}' مستخدم بالفعل.")
        return redirect('inventory:manage_groups')

    group.name = name
    group.save()
    group.permissions.set(permission_ids)

    messages.success(request, f"تم تحديث المجموعة '{name}' بنجاح.")
    return redirect('inventory:manage_groups')


@require_POST
@permission_required('auth.delete_group')
def delete_group(request, pk):
    """
    Handles deleting a group.
    """
    group = get_object_or_404(Group, pk=pk)
    if group.user_set.exists():
        messages.error(request, f"لا يمكن حذف المجموعة '{group.name}' لأنها مرتبطة بمستخدمين.")
        return redirect('inventory:manage_groups')

    name = group.name
    group.delete()
    messages.success(request, f"تم حذف المجموعة '{name}' بنجاح.")
    return redirect('inventory:manage_groups')
