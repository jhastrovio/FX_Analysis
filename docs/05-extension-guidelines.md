# Extension Guidelines

Add new analysis work in a way that keeps FX_Analysis lightweight and clearly separate from the producer system.

## Where New Work Should Go

- `bin/`: entrypoints, scripts, and workflow runners
- `lib/`: reusable analytics logic, helpers, and data-access code
- `outputs/`: temporary exports and analysis artifacts only
- `docs/`: short usage or contract notes when a new workflow changes how the repo is used

## Belongs In FX_Analysis

- New performance metrics and comparison logic
- Additional dashboards or visualisations
- Temporary derived views for research
- Reusable helpers that read governed datasets
- Small workflow scripts that automate repeatable analysis

## Does Not Belong In FX_Analysis

- Permanent cleaned datasets
- New authoritative schemas
- Normalization or reconciliation jobs
- Data repair pipelines
- Publishing authoritative outputs for other systems

## Extension Rules

- Select datasets by manifest name, not hard-coded estate paths.
- Keep analytics logic separate from any notion of dataset production.
- Write outputs to local ephemeral locations only.
- Document new metrics or visualisations in plain language.
- If a change needs upstream data ownership, route it through the [data request contract](/Users/jameshassett/dev/FX_Analysis/docs/04-data-request-contract.md).

## Deciding Where A Need Belongs

Ask these questions:

1. Is this a calculation, comparison, or visualisation on top of governed data?
2. Is the output temporary and regenerable?
3. Can the work remain read-only with respect to `/FX_Data - General`?

If the answer to all three is yes, it probably belongs here. If the change needs permanent storage, schema control, or dataset production, it belongs upstream.

## Lightweight By Default

Prefer small scripts, direct functions, and clear docs over new layers of abstraction. This repo should stay easy to reason about months later.
