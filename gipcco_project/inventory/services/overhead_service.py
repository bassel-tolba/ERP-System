# gipcco_project/inventory/services/overhead_service.py

import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import List

from django.db.models import Sum, Q, F, ExpressionWrapper, DecimalField
from django.utils import timezone
from django.db import transaction

from ..models import (
    FinancialPeriod, CostPool, AllocationDriver, OverheadAllocationRun,
    ExpenseLog, Batch, FinishedProductReceipt, PeriodCloseChecklist
)

logger = logging.getLogger(__name__)


def calculate_cost_pool_total(cost_pool: CostPool, period: FinancialPeriod) -> Decimal:
    """
    Calculates the total amount of expenses assigned to a specific cost pool
    (and all of its sub-pools) for a given financial period.
    """
    # Find all descendants of the given cost pool, including itself
    all_pools = [cost_pool]
    descendants = cost_pool.children.all()
    while descendants:
        all_pools.extend(descendants)
        descendants = CostPool.objects.filter(parent__in=descendants)

    total = ExpenseLog.objects.filter(
        expense_date__gte=period.start_date,
        expense_date__lte=period.end_date,
        cost_pool__in=all_pools
    ).aggregate(total_amount=Sum('amount'))['total_amount'] or Decimal('0.0')
    
    return total.quantize(Decimal('0.001'))


def calculate_driver_units_total(driver: AllocationDriver, period: FinancialPeriod) -> float:
    """
    Calculates the total number of driver units recorded for a given period,
    based on the finished goods produced in that period.
    """
    total_units = 0.0
    
    # Base query for receipts within the period for consistency
    receipts_in_period = FinishedProductReceipt.objects.filter(
        receipt_date__gte=period.start_date,
        receipt_date__lte=period.end_date
    )
    
    if driver.name == AllocationDriver.DriverChoices.MACHINE_HOURS:
        # Sum machine hours from batches linked to receipts in the period
        total_units = receipts_in_period.filter(
            batch__machine_hours_consumed__isnull=False
        ).aggregate(total=Sum('batch__machine_hours_consumed'))['total'] or 0.0
        
    elif driver.name == AllocationDriver.DriverChoices.LABOR_HOURS:
        # Sum labor hours from batches linked to receipts in the period
        total_units = receipts_in_period.filter(
            batch__labor_hours_consumed__isnull=False
        ).aggregate(total=Sum('batch__labor_hours_consumed'))['total'] or 0.0

    elif driver.name == AllocationDriver.DriverChoices.BOTTLE_UNITS:
        # Sum the quantity produced from the receipts themselves
        total_units = receipts_in_period.filter(
            total_quantity_produced__isnull=False
        ).aggregate(total=Sum('total_quantity_produced'))['total'] or 0.0

    elif driver.name == AllocationDriver.DriverChoices.LITERS_VOLUME:
        # Calculate total volume based on quantity and bottle size from the template
        total_volume_ml = receipts_in_period.filter(
            total_quantity_produced__isnull=False,
            batch__template__bottle_size_ml__isnull=False
        ).annotate(
            total_ml=ExpressionWrapper(
                F('total_quantity_produced') * F('batch__template__bottle_size_ml'), 
                output_field=DecimalField()
            )
        ).aggregate(total=Sum('total_ml'))['total'] or Decimal('0.0')
        
        total_units = float(total_volume_ml / Decimal('1000.0')) if total_volume_ml else 0.0
        
    return total_units


def execute_overhead_allocation_run(run: OverheadAllocationRun) -> OverheadAllocationRun:
    """
    Executes the calculations for a given allocation run.
    It calculates the pool total, driver total, and the final overhead rate,
    then saves the results to the run object.
    """
    logger.info(f"Executing overhead allocation run for {run.cost_pool.name} in {run.financial_period.name}")
    
    # 1. Calculate the total amount in the cost pool for the period
    pool_total = calculate_cost_pool_total(run.cost_pool, run.financial_period)
    logger.debug(f"Calculated pool total: {pool_total}")
    
    # 2. Calculate the total driver units for the period
    driver_total = calculate_driver_units_total(run.allocation_driver, run.financial_period)
    logger.debug(f"Calculated driver total: {driver_total}")
    
    # 3. Calculate the overhead rate
    if driver_total > 0:
        calculated_rate = (pool_total / Decimal(str(driver_total))).quantize(Decimal('0.00001'))
    else:
        calculated_rate = Decimal('0.00000')
    logger.debug(f"Calculated overhead rate: {calculated_rate}")

    # 4. Update and save the run object
    run.total_pool_amount = pool_total
    run.total_driver_units = driver_total
    run.calculated_rate = calculated_rate
    run.status = OverheadAllocationRun.Status.CALCULATED
    run.save()
    
    logger.info(f"Successfully executed allocation run {run.id}. Status set to CALCULATED.")
    return run


def apply_overhead_to_finished_goods(run: OverheadAllocationRun) -> Decimal:
    """
    Applies the calculated overhead rate from a run to all finished goods
    receipts within the run's financial period.

    This function is now responsible for setting the 'is_overhead_posted' flag
    on the period's closing checklist.
    """
    period = run.financial_period
    driver_name = run.allocation_driver.name
    rate = run.calculated_rate

    # --- FIX: Ensure the checklist exists before trying to update it ---
    checklist, _ = PeriodCloseChecklist.objects.get_or_create(financial_period=period)

    # Find all FG receipts in the period that have a batch with the relevant driver data
    receipts_in_period = FinishedProductReceipt.objects.filter(
        receipt_date__gte=period.start_date,
        receipt_date__lte=period.end_date
    ).select_related('batch__template') # Eager load for efficiency

    if not receipts_in_period.exists():
        logger.warning(f"Overhead run {run.id} found no finished goods receipts in period {period.name}. No overhead will be applied.")
        # Even if no receipts, the process is complete. Mark as applied.
        # The checklist should be updated to reflect that the process ran.
        # FIX: Always use the 'checklist' object fetched at the start of the function
        # to avoid using a potentially stale 'period.checklist' prefetched object.
        checklist.is_overhead_posted = True
        checklist.save()
        return Decimal('0.0')

    # 3. Apply the overhead cost to each receipt
    total_applied_cost = Decimal('0.0')
    receipts_to_update = []

    for receipt in receipts_in_period:
        driver_units_for_receipt = 0.0
        if driver_name == AllocationDriver.DriverChoices.MACHINE_HOURS:
            driver_units_for_receipt = receipt.batch.machine_hours_consumed or 0.0
        elif driver_name == AllocationDriver.DriverChoices.LABOR_HOURS:
            driver_units_for_receipt = receipt.batch.labor_hours_consumed or 0.0
        elif driver_name == AllocationDriver.DriverChoices.BOTTLE_UNITS:
            driver_units_for_receipt = receipt.total_quantity_produced or 0.0
        elif driver_name == AllocationDriver.DriverChoices.LITERS_VOLUME:
            bottle_size_ml = receipt.batch.template.bottle_size_ml
            quantity_produced = receipt.total_quantity_produced
            if bottle_size_ml and quantity_produced:
                driver_units_for_receipt = (float(quantity_produced) * float(bottle_size_ml)) / 1000.0

        if driver_units_for_receipt > 0:
            applied_cost = (Decimal(str(driver_units_for_receipt)) * rate).quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)
            
            # Update the receipt instance in memory
            receipt.allocated_overhead_cost = applied_cost
            # Also update the total_cost using an F() expression to ensure correct atomic update.
            receipt.total_cost = F('total_cost') + applied_cost
            receipts_to_update.append(receipt)
            total_applied_cost += applied_cost

    with transaction.atomic():
        # Add 'total_cost' to the list of fields to be updated.
        FinishedProductReceipt.objects.bulk_update(receipts_to_update, ['allocated_overhead_cost', 'total_cost'])
        logger.info(f"Applied overhead of {total_applied_cost} to {len(receipts_to_update)} finished product receipts for run {run.id}.")

        # --- NEW: Update the period close checklist ---
        checklist.is_overhead_posted = True
        checklist.save()
        logger.info(f"Updated period close checklist for {period.name}: is_overhead_posted=True.")

    # Return the total cost that was applied, to be used in the JE
    return total_applied_cost