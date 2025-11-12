# gipcco_project/inventory/services/accounting/correction_transactions.py

import logging
from typing import Optional

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError, PermissionDenied

from ...models import (
    JournalEntry, JournalEntryLine, TransactionCorrection, ExpenseRequest
)
from ._helpers import _check_period_is_open
from ._builder import JournalEntryBuilder

logger = logging.getLogger(__name__)


def correct_approved_expense(request_id: int, user, justification: str) -> TransactionCorrection:
    """
    Finds an approved expense request and its resulting transaction, and creates
    a reversing journal entry and an audit record for the correction.
    """
    with transaction.atomic():
        try:
            request = ExpenseRequest.objects.select_for_update().get(id=request_id)
        except ExpenseRequest.DoesNotExist:
            raise ValidationError(f"ExpenseRequest with ID {request_id} not found.")

        if request.status != ExpenseRequest.Status.APPROVED:
            raise PermissionDenied(f"Cannot correct a request with status '{request.status}'. Only approved requests can be corrected.")

        original_object = None
        if request.request_type == ExpenseRequest.RequestType.DIRECT_EXPENSE:
            original_object = request.final_expense_logs.first()
        elif request.request_type in [
            ExpenseRequest.RequestType.INVENTORY_EXPENSE,
            ExpenseRequest.RequestType.INVENTORY_CAPITALIZE,
            ExpenseRequest.RequestType.INVENTORY_PREPAID
        ]:
            original_object = request.final_consumption

        if not original_object:
            raise ValidationError("Could not find the original transaction linked to this expense request.")

        reversing_je = create_reversing_je_for_correction(
            original_object=original_object,
            justification=justification,
            user=user,
            correction_date=timezone.now()
        )

        correction_record = TransactionCorrection.objects.get(adjusting_journal_entry=reversing_je)

        request.notes = f"{request.notes or ''}\n\nCORRECTION: This request was reversed on {timezone.now().date()} by {user.username}. Justification: {justification}. See JE-{reversing_je.id}."
        request.save(update_fields=['notes'])

        logger.info(f"User '{user.username}' corrected ExpenseRequest ID {request.id}. Reversing JE-{reversing_je.id} created.")

        return correction_record


def create_reversing_je_for_correction(
    original_object,
    justification: str,
    user,
    correction_date: Optional[timezone.datetime] = None
) -> JournalEntry:
    """
    Creates a new journal entry in the current open period that exactly reverses
    the financial impact of an original transaction's journal entry.
    """
    content_type = ContentType.objects.get_for_model(original_object)
    original_je = JournalEntry.objects.filter(
        content_type=content_type, object_id=original_object.pk
    ).first()

    if not original_je:
        raise ValueError(f"Cannot create correction: No original journal entry found for {original_object}.")

    if TransactionCorrection.objects.filter(content_type=content_type, object_id=original_object.pk).exists():
        raise PermissionError(f"This transaction ({original_object}) has already been corrected and cannot be adjusted again.")

    correction_date = correction_date or timezone.now()
    _check_period_is_open(correction_date)

    with transaction.atomic():
        # FIX: The logic is to create the JE first, then the correction record that links to it.
        # The builder cannot be used here because its source (the correction record) doesn't exist yet.
        # We revert to a manual, explicit creation which is clearer for this complex case.
        
        description = _("Reversal of JE-%(original_je_id)s for: %(original_desc)s") % {
            'original_je_id': original_je.id,
            'original_desc': original_je.description
        }

        # 1. Create the JE header. The source is temporary.
        adjusting_je = JournalEntry.objects.create(
            date=correction_date,
            description=description,
            notes=justification,
            status=JournalEntry.Status.POSTED,
            source_object=original_object # Temporary source
        )

        # 2. Create the reversed lines.
        for line in original_je.lines.all():
            JournalEntryLine.objects.create(
                journal_entry=adjusting_je,
                account=line.account,
                amount=line.amount,
                entry_type=JournalEntryLine.EntryType.CREDIT if line.entry_type == JournalEntryLine.EntryType.DEBIT else JournalEntryLine.EntryType.DEBIT,
                sub_ledger_object=line.sub_ledger_object
            )
        
        adjusting_je.validate_balance()

        # 3. Now create the correction record, linking the JE we just made.
        correction_record = TransactionCorrection.objects.create(
            source_object=original_object,
            adjusting_journal_entry=adjusting_je,
            justification=justification,
            corrected_by=user
        )

        # 4. Finally, update the JE's source to point to the correction record for a clean audit trail.
        adjusting_je.source_object = correction_record
        adjusting_je.save(update_fields=['content_type', 'object_id'])

        logger.info(f"Successfully created reversing JE-{adjusting_je.id} to correct {original_object}.")

    return adjusting_je