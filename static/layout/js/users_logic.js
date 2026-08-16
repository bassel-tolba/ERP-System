function initUsersLogic(container) {
    const groupSelects = container.querySelectorAll('.user-groups-select');
    if (groupSelects.length > 0 && !container.dataset.usersLogicInitialized) {
        console.log("[DEBUG] Initializing User Management logic...");
        container.dataset.usersLogicInitialized = 'true';

        groupSelects.forEach(select => {
            new TomSelect(select, { plugins: ['remove_button'], placeholder: 'اختر المجموعات...' });
        });
    }
}

function initGroupsLogic(container) {
    const permissionsContainers = container.querySelectorAll('.permissions-container');
    if (permissionsContainers.length > 0 && !container.dataset.groupsLogicInitialized) {
        console.log("[DEBUG] Initializing Group Management permissions accordion logic...");
        container.dataset.groupsLogicInitialized = 'true';

        permissionsContainers.forEach(pContainer => {
            const groupToggles = pContainer.querySelectorAll('.permission-group-toggle');
            
            groupToggles.forEach(toggle => {
                const targetId = toggle.dataset.groupTarget;
                const targetCollapse = document.querySelector(targetId);
                if (!targetCollapse) return;

                const permissionCheckboxes = targetCollapse.querySelectorAll('.permission-checkbox');

                const updateToggleState = () => {
                    if (permissionCheckboxes.length === 0) return;
                    const total = permissionCheckboxes.length;
                    const checkedCount = targetCollapse.querySelectorAll('.permission-checkbox:checked').length;

                    if (checkedCount === 0) {
                        toggle.checked = false;
                        toggle.indeterminate = false;
                    } else if (checkedCount === total) {
                        toggle.checked = true;
                        toggle.indeterminate = false;
                    } else {
                        toggle.checked = false;
                        toggle.indeterminate = true;
                    }
                };

                toggle.addEventListener('change', (e) => {
                    permissionCheckboxes.forEach(checkbox => {
                        checkbox.checked = e.target.checked;
                    });
                    toggle.indeterminate = false;
                });

                permissionCheckboxes.forEach(checkbox => {
                    checkbox.addEventListener('change', updateToggleState);
                });

                updateToggleState();
            });
        });
    }
}
