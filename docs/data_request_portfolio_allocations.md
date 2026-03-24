# Portfolio Allocation Reference

## Current Source

Portfolio allocation weights are currently maintained in the static workbook:

`_meta/Portfolio_Allocations.xlsx`

This workbook is now structured enough to be used as the reference source for static portfolio allocation weights.

## Workbook Shape

- `INDEX` sheet with `portfolio_name`, `portfolio_id`, `sheet_name`
- One sheet per portfolio
- Portfolio sheets with:
  `portfolio_id`, `model_id`, `strategy_name`, `risk_alloc`, `category`, `family`

## Parsing Notes

- `risk_alloc` should be treated as numeric
- minor sheet-level sum differences are presentation rounding artifacts and should be normalized in code
- `portfolio_id` is explicit on every allocation row, so consumers should not rely on sheet names for joins

## Downstream Use

FX_Analysis can use this workbook, or a local CSV extracted from it, as the source for static-by-portfolio allocation weights in local portfolio research workflows.

## When A Dataset Request Is Needed

Only raise a separate governed dataset request if the workbook stops being stable, needs history/versioning, or must be consumed by other systems as a formal data contract.
