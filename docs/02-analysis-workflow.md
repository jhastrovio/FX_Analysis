# Analysis Workflow

Use this workflow for normal analysis work in FX_Analysis.

## Default Flow

1. Select governed data by manifest name.
2. Consolidate it for analysis if needed.
3. Compute metrics, rankings, or comparisons.
4. Visualise and explore the results.
5. Export temporary results to `outputs/`.
6. Raise an upstream data request if missing data blocks the analysis.

## What This Looks Like In Practice

- Consolidation: merge source files into an analysis-ready matrix.
- Metrics: calculate returns, volatility, Sharpe, drawdown, and related statistics.
- Exploration: use scripts, notebooks, or dashboards to compare models and time periods.
- Export: save charts, tables, and intermediate views locally when they help the analysis.

## Operating Rules

- Treat `/FX_Data - General` as read-only at all times.
- Reference datasets through the manifest rather than hard-coded estate paths.
- Keep all outputs temporary and local to this repo.
- Do not create ad hoc upstream substitutes inside FX_Analysis.

## When Data Is Missing

If analysis reveals that an upstream field, grain, key, or dataset is missing:

1. Describe the analytical problem.
2. Document the required upstream change.
3. Hand the request back to the producer system.
4. Resume the analysis when the governed dataset is available.

Use [04-data-request-contract.md](/Users/jameshassett/dev/FX_Analysis/docs/04-data-request-contract.md) and [data_request_template.md](/Users/jameshassett/dev/FX_Analysis/docs/templates/data_request_template.md).
