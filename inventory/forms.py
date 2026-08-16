# gipcco_project/inventory/forms.py

from django import forms
from django.forms import inlineformset_factory
from django.utils.translation import gettext_lazy as _
from decimal import Decimal

from .models import JournalEntry, JournalEntryLine, Account

class JournalEntryLineForm(forms.ModelForm):
    class Meta:
        model = JournalEntryLine
        fields = ['account', 'entry_type', 'amount']
        widgets = {
            'account': forms.Select(attrs={'class': 'form-control select2 account-selector'}),
            'entry_type': forms.Select(attrs={'class': 'form-control entry-type-selector'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control amount-input', 'step': '0.001'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # We only want to select leaf accounts (accounts with no children) for journal entries
        self.fields['account'].queryset = Account.objects.filter(children__isnull=True).order_by('code')


class JournalEntryForm(forms.ModelForm):
    class Meta:
        model = JournalEntry
        fields = ['date', 'description', 'notes']
        widgets = {
            'date': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'description': forms.TextInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }


# FormSet for handling multiple lines in a single journal entry
JournalEntryLineFormSet = inlineformset_factory(
    JournalEntry,
    JournalEntryLine,
    form=JournalEntryLineForm,
    extra=2,  # Start with 2 empty lines
    can_delete=True,
    min_num=2, # A valid JE must have at least 2 lines
)

# Custom validation for the FormSet
class BaseJournalEntryLineFormSet(forms.BaseInlineFormSet):
    def clean(self):
        super().clean()
        
        if any(self.errors):
            # Don't bother validating the debit/credit balance if individual forms are invalid
            return

        total_debit = Decimal('0.000')
        total_credit = Decimal('0.000')
        
        lines_count = 0
        for form in self.forms:
            if not form.is_valid() or self.can_delete and self._should_delete_form(form):
                continue

            if form.cleaned_data:
                lines_count += 1
                amount = form.cleaned_data.get('amount', Decimal('0.000'))
                entry_type = form.cleaned_data.get('entry_type')
                
                if entry_type == JournalEntryLine.EntryType.DEBIT:
                    total_debit += amount
                elif entry_type == JournalEntryLine.EntryType.CREDIT:
                    total_credit += amount

        if lines_count < 2:
            raise forms.ValidationError(_('A journal entry must have at least two lines.'))
        
        if total_debit != total_credit:
            raise forms.ValidationError(
                _('Total debits (%(debit)s) must equal total credits (%(credit)s). The difference is %(diff)s.') % {
                    'debit': total_debit,
                    'credit': total_credit,
                    'diff': abs(total_debit - total_credit)
                }
            )

# Re-create the FormSet using our custom base class
JournalEntryLineFormSet = inlineformset_factory(
    JournalEntry,
    JournalEntryLine,
    form=JournalEntryLineForm,
    formset=BaseJournalEntryLineFormSet,
    extra=2,
    can_delete=True,
    min_num=2,
)