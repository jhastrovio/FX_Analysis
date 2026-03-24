# AGENTS.md

## Purpose
FX_Analysis is a read-only analytics repo for exploratory FX analysis and visualization.

## Strict boundaries
- Never write to `/FX_Data - General` or other governed data stores.
- No ingestion, normalization, reconciliation, or canonical dataset creation here.
- Outputs are temporary analysis artifacts only.
- If work creates a permanent dataset or production pipeline, it belongs upstream.

## Repo shape
- `bin/` = entrypoints
- `lib/` = reusable logic
- Keep notebooks and Streamlit thin; reusable logic belongs in `lib/`.

## Working style
- Prefer small, reversible changes.
- Prefer explicit code over abstraction.
- Reuse existing code before adding new layers.
- Avoid framework-style restructuring.

## Workflow defaults
- Read existing code before writing new code.
- Notebook first for exploration and visual review.
- Streamlit only for repeatable views after the analysis is understood.

## When uncertain
- Do less.
- Do not expand repo scope beyond analytics.
- Preserve read-only assumptions at all times.
