# gipcco_project/inventory/services/accounting/_builder.py

import logging
from decimal import Decimal
from typing import Optional, List, Dict, Any

from django.db import transaction
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError

from ...models import JournalEntry, JournalEntryLine, Account
from ._helpers import _check_period_is_open

logger = logging.getLogger(__name__)

class JournalEntryBuilder:
    """
    A fluent builder for creating JournalEntry objects and their lines.
    This class encapsulates the boilerplate logic of:
    - Checking for existing JEs.
    - Checking financial periods.
    - Transaction management.
    - Creating JE and JELs.
    - Validating balance.
    - Linking the JE back to the source object.
    """

    def __init__(self, source_object: Any):
        self._source_object = source_object
        self._content_type = ContentType.objects.get_for_model(self._source_object)
        
        self._date = getattr(source_object, 'date', None) or \
                     getattr(source_object, 'period_date', None) or \
                     getattr(source_object, 'financial_period', None) or \
                     getattr(source_object, 'creation_date', None) or \
                     getattr(source_object, 'release_timestamp', None) or \
                     getattr(source_object, 'receipt_date', None) or \
                     getattr(source_object, 'dispatch_date', None) or \
                     getattr(source_object, 'return_date', None) or \
                     timezone.now()
        if hasattr(self._date, 'end_date'): # Handle FinancialPeriod object
            self._date = self._date.end_date

        self._description: str = ""
        self._notes: str = ""
        self._status: str = JournalEntry.Status.POSTED
        self._lines: List[Dict[str, Any]] = []

    def set_date(self, date) -> 'JournalEntryBuilder':
        self._date = date
        return self
    
    def set_description(self, description: str) -> 'JournalEntryBuilder':
        self._description = description
        return self

    def set_notes(self, notes: str) -> 'JournalEntryBuilder':
        self._notes = notes
        return self

    def debit(self, amount: Decimal, account: Account, sub_ledger_object: Optional[Any] = None) -> 'JournalEntryBuilder':
        if amount and amount > 0:
            self._lines.append({
                'entry_type': JournalEntryLine.EntryType.DEBIT,
                'amount': amount,
                'account': account,
                'sub_ledger_object': sub_ledger_object
            })
        return self

    def credit(self, amount: Decimal, account: Account, sub_ledger_object: Optional[Any] = None) -> 'JournalEntryBuilder':
        if amount and amount > 0:
            self._lines.append({
                'entry_type': JournalEntryLine.EntryType.CREDIT,
                'amount': amount,
                'account': account,
                'sub_ledger_object': sub_ledger_object
            })
        return self

    def post(self, link_to_source_field: Optional[str] = 'journal_entry') -> Optional[JournalEntry]:
        """
        Validates the builder state and creates the JournalEntry in a transaction.
        Returns the created JournalEntry or None if it already exists or if the total amount is zero.
        
        :param link_to_source_field: The name of the ForeignKey field on the source object
                                     to link this JE to. If None, no linking is performed.
        """
        if JournalEntry.objects.filter(
            content_type=self._content_type, object_id=self._source_object.id
        ).exists():
            logger.debug(f"Journal entry for {self._source_object.__class__.__name__} ID {self._source_object.id} already exists. Aborting.")
            return None

        _check_period_is_open(self._date)

        total_debits = sum(line['amount'] for line in self._lines if line['entry_type'] == JournalEntryLine.EntryType.DEBIT)
        
        if total_debits <= 0:
            logger.info(f"Total transaction amount for {self._source_object.__class__.__name__} ID {self._source_object.id} is zero. No JE created.")
            return None

        with transaction.atomic():
            je = JournalEntry.objects.create(
                date=self._date,
                description=self._description,
                notes=self._notes,
                source_object=self._source_object,
                status=self._status
            )

            for line_data in self._lines:
                JournalEntryLine.objects.create(journal_entry=je, **line_data)
            
            je.validate_balance()

            if link_to_source_field and hasattr(self._source_object, link_to_source_field):
                setattr(self._source_object, link_to_source_field, je)
                self._source_object.save(update_fields=[link_to_source_field])

            logger.info(f"Successfully created JE-{je.id} for {self._source_object.__class__.__name__} ID {self._source_object.id}.")
        
        return je
# gipcco_project/inventory/services/accounting/_builder.py

import logging
from decimal import Decimal
from typing import Optional, List, Dict, Any

from django.db import transaction
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError

from ...models import JournalEntry, JournalEntryLine, Account
from ._helpers import _check_period_is_open

logger = logging.getLogger(__name__)

class JournalEntryBuilder:
    """
    A fluent builder for creating JournalEntry objects and their lines.
    This class encapsulates the boilerplate logic of:
    - Checking for existing JEs.
    - Checking financial periods.
    - Transaction management.
    - Creating JE and JELs.
    - Validating balance.
    - Linking the JE back to the source object.
    """

    def __init__(self, source_object: Any):
        self._source_object = source_object
        self._content_type = ContentType.objects.get_for_model(self._source_object)
        
        self._date = getattr(source_object, 'date', None) or \
                     getattr(source_object, 'period_date', None) or \
                     getattr(source_object, 'financial_period', None) or \
                     getattr(source_object, 'creation_date', None) or \
                     getattr(source_object, 'release_timestamp', None) or \
                     getattr(source_object, 'receipt_date', None) or \
                     getattr(source_object, 'dispatch_date', None) or \
                     getattr(source_object, 'return_date', None) or \
                     timezone.now()
        if hasattr(self._date, 'end_date'): # Handle FinancialPeriod object
            self._date = self._date.end_date

        self._description: str = ""
        self._notes: str = ""
        self._status: str = JournalEntry.Status.POSTED
        self._lines: List[Dict[str, Any]] = []

    def set_date(self, date) -> 'JournalEntryBuilder':
        self._date = date
        return self
    
    def set_description(self, description: str) -> 'JournalEntryBuilder':
        self._description = description
        return self

    def set_notes(self, notes: str) -> 'JournalEntryBuilder':
        self._notes = notes
        return self

    def debit(self, amount: Decimal, account: Account, sub_ledger_object: Optional[Any] = None) -> 'JournalEntryBuilder':
        if amount and amount > 0:
            self._lines.append({
                'entry_type': JournalEntryLine.EntryType.DEBIT,
                'amount': amount,
                'account': account,
                'sub_ledger_object': sub_ledger_object
            })
        return self

    def credit(self, amount: Decimal, account: Account, sub_ledger_object: Optional[Any] = None) -> 'JournalEntryBuilder':
        if amount and amount > 0:
            self._lines.append({
                'entry_type': JournalEntryLine.EntryType.CREDIT,
                'amount': amount,
                'account': account,
                'sub_ledger_object': sub_ledger_object
            })
        return self

    def post(self, link_to_source_field: Optional[str] = 'journal_entry') -> Optional[JournalEntry]:
        """
        Validates the builder state and creates the JournalEntry in a transaction.
        Returns the created JournalEntry or None if it already exists or if the total amount is zero.
        
        :param link_to_source_field: The name of the ForeignKey field on the source object
                                     to link this JE to. If None, no linking is performed.
        """
        if JournalEntry.objects.filter(
            content_type=self._content_type, object_id=self._source_object.id
        ).exists():
            logger.debug(f"Journal entry for {self._source_object.__class__.__name__} ID {self._source_object.id} already exists. Aborting.")
            return None

        _check_period_is_open(self._date)

        total_debits = sum(line['amount'] for line in self._lines if line['entry_type'] == JournalEntryLine.EntryType.DEBIT)
        
        if total_debits <= 0:
            logger.info(f"Total transaction amount for {self._source_object.__class__.__name__} ID {self._source_object.id} is zero. No JE created.")
            return None

        with transaction.atomic():
            je = JournalEntry.objects.create(
                date=self._date,
                description=self._description,
                notes=self._notes,
                source_object=self._source_object,
                status=self._status
            )

            for line_data in self._lines:
                JournalEntryLine.objects.create(journal_entry=je, **line_data)
            
            je.validate_balance()

            if link_to_source_field and hasattr(self._source_object, link_to_source_field):
                setattr(self._source_object, link_to_source_field, je)
                self._source_object.save(update_fields=[link_to_source_field])

            logger.info(f"Successfully created JE-{je.id} for {self._source_object.__class__.__name__} ID {self._source_object.id}.")
        
        return je