# Data Request

## Title

Expand `models_signals_systemacro` to include per-model currency position breakout

## Analytical problem

Need per-model, per-currency positions so FX_Analysis can aggregate model exposures into strategy-level portfolio attribution.

## Why current data is insufficient

`models_signals_systemacro` currently exposes returns only and does not provide the model position breakout required for position-based attribution.

## Proposed dataset or schema change

Extend `models_signals_systemacro` to publish per-model position data by date and currency/instrument.

## Expected grain / keys

- Grain: one row per `date`, `model_id`, `instrument`
- Keys: `date`, `model_id`, `instrument`

## Required fields

- `date`
- `model_id`
- `instrument`
- `model_position`
- source run or valuation metadata if available

## Example downstream use in FX_Analysis

FX_Analysis will join the expanded model position dataset to portfolio allocation weights on `model_id`, then aggregate weighted model positions into strategy-level end-of-day and daily-change attribution.

## Priority / urgency

High.

## Owner / requester

Requester: FX_Analysis
Owner: Producer system / data platform team responsible for `models_signals_systemacro`
