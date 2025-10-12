# gipcco_project/inventory/services/accounting/period_end.py

import logging
from decimal import Decimal

from django.db import transaction

from ...models import (
    FinancialPeriod, FixedAsset, DepreciationLog, PeriodCloseChecklist
)
from ._helpers import _check_period_is_open

logger = logging.getLogger(__name__)


def run_monthly_depreciation(period: FinancialPeriod) -> dict:
    """
    Calculates and posts depreciation for all eligible fixed assets for a given period.
    """
    logger.info(f"Starting monthly depreciation run for period '{period.name}'.")
    _check_period_is_open(period.end_date)

    assets_to_depreciate = FixedAsset.objects.filter(
        status=FixedAsset.AssetStatus.IN_SERVICE,
        depreciation_start_date__lte=period.end_date
    )

    existing_logs = DepreciationLog.objects.filter(
        asset__in=assets_to_depreciate,
        period_date=period.end_date
    ).values_list('asset_id', flat=True)

    assets_to_process = assets_to_depreciate.exclude(id__in=existing_logs)

    try:
        checklist, _ = PeriodCloseChecklist.objects.get_or_create(financial_period=period)
        checklist.is_depreciation_run = True
        checklist.save()
        logger.info(f"Updated period close checklist for {period.name}: is_depreciation_run=True.")
    except Exception as e:
        logger.error(f"Could not update period close checklist for '{period.name}': {e}", exc_info=True)

    if not assets_to_process.exists():
        logger.info("No new assets found to depreciate for this period.")
        summary = {
            "status": "success",
            "message": "No new assets found to depreciate for this period.",
            "assets_processed": 0,
            "total_depreciation": Decimal("0.0")
        }
        return summary

    processed_count = 0
    total_depreciation_posted = Decimal("0.0")

    for asset in assets_to_process:
        with transaction.atomic():
            accumulated_dep = asset.accumulated_depreciation
            depreciable_base = asset.depreciable_base

            if accumulated_dep >= depreciable_base:
                logger.info(f"Skipping asset '{asset.asset_tag}' as it is fully depreciated.")
                continue

            monthly_depreciation_amount = (depreciable_base / (asset.useful_life_years * 12)).quantize(Decimal('0.001'))

            if (accumulated_dep + monthly_depreciation_amount) > depreciable_base:
                final_amount = depreciable_base - accumulated_dep
                depreciation_amount = final_amount
            else:
                depreciation_amount = monthly_depreciation_amount

            if depreciation_amount > 0:
                DepreciationLog.objects.create(
                    asset=asset,
                    period_date=period.end_date,
                    amount=depreciation_amount
                )
                processed_count += 1
                total_depreciation_posted += depreciation_amount
                logger.info(f"Posted depreciation of {depreciation_amount} for asset '{asset.asset_tag}'.")

    summary = {
        "status": "success",
        "message": f"Depreciation run completed for period '{period.name}'.",
        "assets_processed": processed_count,
        "total_depreciation": total_depreciation_posted
    }
    logger.info(f"Finished depreciation run. Processed {processed_count} assets with a total value of {total_depreciation_posted}.")
    return summary
