# Read-Only Contract

FX_Analysis is read-only with respect to `/FX_Data - General`. It must never write, modify, repair, or publish anything into the governed data estate.

## What Read-Only Means

- Read governed datasets for analysis.
- Respect upstream schemas, lifecycle, and dataset ownership.
- Write outputs only to local, ephemeral locations such as `outputs/`.
- Treat derived files as disposable analysis artifacts, not permanent datasets.

## Why This Boundary Exists

The producer system owns ingestion, normalization, reconciliation, schema management, and permanent datasets. Keeping FX_Analysis read-only avoids ownership confusion, accidental corruption, and silent expansion into a second data platform.

## Belongs In FX_Analysis

- Computing new metrics from governed datasets
- Ranking models by Sharpe, drawdown, or related statistics
- Exploratory cross-model comparisons
- Dashboards, charts, and temporary exports
- Temporary derived views used for research

## Does Not Belong In FX_Analysis

- Creating permanent cleaned datasets
- Schema governance or schema migrations
- Data repair or normalization jobs
- Authoritative publishing back into governed storage
- Lifecycle management for upstream datasets

## Acceptable Changes

- Add a new reusable metric in `lib/`
- Add a new analysis script in `bin/`
- Add a dashboard view built from governed inputs
- Export a temporary CSV or chart to `outputs/`

## Unacceptable Changes

- Write transformed files back into `/FX_Data - General`
- Build a pipeline that fixes or reconciles upstream data here
- Introduce new authoritative schemas inside this repo
- Store permanent datasets as if FX_Analysis owns them

## Practical Rule

If a change needs write access to governed storage, permanent dataset ownership, or upstream schema control, it does not belong here. Follow the [data request contract](/Users/jameshassett/dev/FX_Analysis/docs/04-data-request-contract.md) instead.
