from decimal import Decimal
from django.db import models
from django.db.models import Sum, F, Subquery, OuterRef, DecimalField
from django.db.models.functions import Coalesce


class InventoryLogQuerySet(models.QuerySet):
    """Custom QuerySet for the InventoryLog model."""

    def with_remaining_quantity(self):
        """
        Annotates the queryset with the calculated remaining quantity for each log,
        using subqueries to prevent join multiplication bugs. This is the single
        source of truth for raw material/MRO stock availability.
        """
        from .inventory_management import BatchItem, InventoryConsumption, ProductionReturn, Batch
        from .inventory_counts import InventoryAdjustment

        # Subquery for consumption in production batches (non-cancelled)
        consumed_prod_subquery = BatchItem.objects.filter(
            source_log_id=OuterRef('pk')
        ).exclude(
            batch__status=Batch.Status.CANCELLED
        ).values('source_log_id').annotate(total=Sum('actual_quantity')).values('total')

        # Subquery for internal/expense consumptions
        consumed_internal_subquery = InventoryConsumption.objects.filter(
            source_log_id=OuterRef('pk')
        ).values('source_log_id').annotate(total=Sum('quantity_consumed')).values('total')

        # Subquery for returns from production (adds back to stock)
        returned_subquery = ProductionReturn.objects.filter(
            source_log_id=OuterRef('pk')
        ).values('source_log_id').annotate(total=Sum('quantity')).values('total')

        # Subquery for inventory adjustments (can be positive or negative)
        adjusted_subquery = InventoryAdjustment.objects.filter(
            source_log_id=OuterRef('pk')
        ).values('source_log_id').annotate(total=Sum('adjustment_quantity')).values('total')

        return self.annotate(
            total_used_in_prod=Coalesce(Subquery(consumed_prod_subquery, output_field=DecimalField()), Decimal('0.0')),
            total_used_in_consumption=Coalesce(Subquery(consumed_internal_subquery, output_field=DecimalField()), Decimal('0.0')),
            total_returned=Coalesce(Subquery(returned_subquery, output_field=DecimalField()), Decimal('0.0')),
            total_adjusted=Coalesce(Subquery(adjusted_subquery, output_field=DecimalField()), Decimal('0.0'))
        ).annotate(
            remaining_quantity=F('quantity') - F('total_used_in_prod') - F('total_used_in_consumption') + F('total_returned') + F('total_adjusted')
        )


class FinishedProductReceiptQuerySet(models.QuerySet):
    """Custom QuerySet for the FinishedProductReceipt model."""

    def with_remaining_quantity(self):
        """
        Annotates the queryset with the calculated remaining quantity for each receipt,
        using subqueries. This is the single source of truth for finished good availability.
        """
        from .inventory_management import FinishedProductDispatch
        from .inventory_counts import InventoryAdjustment

        dispatched_subquery = FinishedProductDispatch.objects.filter(finished_product_id=OuterRef('pk')).values('finished_product_id').annotate(total=Sum('quantity')).values('total')
        adjusted_subquery = InventoryAdjustment.objects.filter(source_finished_product_id=OuterRef('pk')).values('source_finished_product_id').annotate(total=Sum('adjustment_quantity')).values('total')

        return self.annotate(
            total_dispatched=Coalesce(Subquery(dispatched_subquery, output_field=DecimalField()), Decimal('0.0')),
            total_adjusted=Coalesce(Subquery(adjusted_subquery, output_field=DecimalField()), Decimal('0.0'))
        ).annotate(
            remaining_quantity=F('total_quantity_produced') - F('total_dispatched') + F('total_adjusted')
        )
