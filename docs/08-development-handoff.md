# FX_Analysis Development Handoff

## Purpose

This document is a practical overview of the repository for an IT professional and an agentic AI expert who may extend it.

The repo is designed as a **read-only analytics layer** on top of governed FX datasets stored outside the repository. Its role is to support analysis, comparison, portfolio research, and reporting without becoming a data production system.

## Core Objective

The main objective of `FX_Analysis` is to let a researcher or analyst:

- read governed FX model and portfolio datasets from the OneDrive data estate
- create temporary analysis-ready views
- calculate repeatable performance and risk metrics
- inspect portfolio construction and approximate attribution outputs
- export local, reproducible, non-authoritative analysis artifacts

The repo is intentionally **not** meant to own ingestion, canonical storage, schema design, or upstream data repair.

## Architectural Position

The intended system boundary is:

```text
Systemacro Research System
  -> produces governed datasets
  -> OneDrive Data Store
  -> FX_Analysis
  -> local ephemeral outputs

Systemacro Website
  -> context, documentation, and metadata
  -> not the primary runtime data source
```

In practice:

- upstream systems produce the authoritative data
- OneDrive is the operational input store
- this repo consumes those datasets in read-only mode
- analysis outputs are written only to local `outputs/`

This boundary is a recurring design rule across the docs and codebase.

## Current Functional Scope

The repository currently supports five main workflow areas.

### 1. Data consolidation

`lib/data_consolidate.py` reads individual model CSV files plus `Model_Index.csv` and builds a temporary consolidated return matrix.

Primary output:

- `outputs/consolidated/Master_Return_Matrix.csv`

### 2. Summary statistics

`lib/summary_statistics.py` calculates model-level metrics including:

- annualized return
- total return
- volatility
- Sharpe ratio
- max drawdown

Primary output:

- `outputs/summary_stats/*.csv`

### 3. Volatility analysis

`lib/volatility_analysis.py` and [`bin/run_volatility_analysis.py`](/Users/jameshassett/dev/FX_Analysis/bin/run_volatility_analysis.py) provide simple annualized volatility summaries for:

- model returns
- currency returns
- portfolio returns

### 4. Portfolio construction research

[`lib/portfolio/construction.py`](/Users/jameshassett/dev/FX_Analysis/lib/portfolio/construction.py) supports:

- loading portfolio allocation workbooks or CSVs
- converting model return matrices into long-form model return series
- estimating trailing 42-day model volatility
- converting `risk_alloc` inputs into derived portfolio weights
- constructing portfolio daily returns

This is analytical portfolio simulation logic, not order-generation or production portfolio management.

## Operating Model

The repo follows a simple operating model:

1. Read governed input datasets from OneDrive.
2. Resolve files via config and, increasingly, manifest-style references.
3. Transform the data into temporary analysis tables.
4. Run metrics, portfolio, or attribution logic.
5. Save outputs locally under `outputs/`.
6. If required data is missing, write a data request for upstream implementation.

This is important: when analysis exposes a missing field, missing grain, or missing dataset, the intended solution is to change the upstream producer system, not to build a shadow data pipeline here.

## Repo Structure

The codebase is organized in a straightforward way.

- [`bin/`](/Users/jameshassett/dev/FX_Analysis/bin): CLI entry points and workflow runners
- [`lib/`](/Users/jameshassett/dev/FX_Analysis/lib): reusable analytics logic
- [`docs/`](/Users/jameshassett/dev/FX_Analysis/docs): architecture, contracts, workflow guidance
- [`outputs/`](/Users/jameshassett/dev/FX_Analysis/outputs): local ephemeral artifacts
- [`tests/`](/Users/jameshassett/dev/FX_Analysis/tests): unit tests for newer analytics modules

Notable modules:

- [`lib/config_manager.py`](/Users/jameshassett/dev/FX_Analysis/lib/config_manager.py): config loading and path resolution
- [`lib/onedrive_storage.py`](/Users/jameshassett/dev/FX_Analysis/lib/onedrive_storage.py): local filesystem adapter for read-only OneDrive access
- [`bin/streamlit_app.py`](/Users/jameshassett/dev/FX_Analysis/bin/streamlit_app.py): lightweight dashboard over local analysis outputs

## Important Constraints

Anyone extending the repo should preserve these constraints:

- upstream data is authoritative; this repo is not
- OneDrive inputs are read-only
- outputs must remain local and regenerable
- analytics should stay lightweight and scriptable
- permanent data engineering work should be pushed upstream

These constraints are not incidental. They are the main mechanism preventing this repository from drifting into an ungoverned data platform.

## Current State Of The Codebase

The repo has a clear direction, but it is in transition.

Observed characteristics:

- the documentation strongly defines a read-only analytics-consumer model
- newer modules and tests align well with that model
- there is a mix of legacy path-based conventions and newer manifest-driven ideas
- some top-level legacy scripts still exist beside the `bin/` and `lib/` layout
- `README.md` and `Makefile` are effectively empty, so the best onboarding material currently lives in `docs/`

This means the repo is usable, but the developer experience is not yet fully consolidated.

## Best Opportunities For Further Development

The highest-value next steps appear to be:

### 1. Standardize the execution surface

Unify around the `bin/` plus `lib/` pattern and retire or wrap legacy top-level scripts so there is one obvious way to run each workflow.

### 2. Complete the manifest-driven input model

Some docs state that datasets should be selected by manifest name rather than hard-coded paths. That principle should be applied consistently across all analysis workflows.

### 3. Strengthen input contracts

The newer portfolio and attribution flows already normalize multiple source column names. That should evolve into explicit, versioned input contracts with better validation and clearer failure messages.

### 4. Improve reproducibility and run metadata

Outputs are ephemeral, but each run should still be traceable. Useful additions would be:

- run manifests
- source file provenance
- config snapshots
- target date and portfolio metadata

### 5. Expand test coverage around boundary behavior

Tests exist for volatility and portfolio construction. The next priority should be:

- config/path resolution
- manifest dataset resolution
- malformed input handling
- reconciliation edge cases

### 6. Add a more deliberate orchestration layer

There is a good foundation for agentic orchestration because the workflows are already scriptable and mostly side-effect constrained. The missing piece is a thin planner/executor pattern for repeatable analysis runs.

## Agentic AI Fit

This repo is a good candidate for agentic augmentation because:

- workflows are mostly deterministic
- the system boundary is well defined
- outputs are local and disposable
- the repo already depends on small CLI-style tasks
- many development tasks are about validation, orchestration, and documentation rather than opaque model behavior

Good agentic use cases:

- selecting the correct workflow from a user intent
- validating required inputs before execution
- resolving manifest datasets for a requested date or portfolio
- running analysis pipelines end-to-end
- generating structured summaries from output CSVs
- raising upstream data requests when inputs are missing
- checking whether a requested change violates the read-only contract

Risk areas for agentic work:

- silently inferring dataset semantics from inconsistent file formats
- introducing local “temporary” fixes that become de facto upstream logic
- mixing exploratory heuristics with supposedly repeatable analytics
- writing outputs outside the local ephemeral boundary

An agent working on this repo should be constrained to respect the architecture first and optimize second.

## Recommended Handoff Framing

If this repo is being handed to a technical collaborator, the most accurate summary is:

`FX_Analysis` is a lightweight research analytics repository for Systemacro FX datasets. It reads governed upstream data from OneDrive, performs repeatable analysis and portfolio research locally, and produces only temporary outputs. The main development challenge is not adding more analytics complexity; it is preserving the repo’s read-only, manifest-driven, non-authoritative role while improving workflow consistency, validation, and orchestration.

## Suggested Immediate Priorities

If the goal is to enable efficient further development, start here:

1. Create a real top-level `README.md` that points to the correct workflows.
2. Choose a single canonical CLI surface for each workflow.
3. Audit all remaining hard-coded data path assumptions.
4. Define explicit input contracts for allocations, returns, model positions, and final positions.
5. Add a thin orchestration layer for repeatable end-to-end runs.
6. Expand tests around manifest resolution and failure modes.

## Key References

- [`docs/00-overview.md`](/Users/jameshassett/dev/FX_Analysis/docs/00-overview.md)
- [`docs/01-working-model.md`](/Users/jameshassett/dev/FX_Analysis/docs/01-working-model.md)
- [`docs/02-analysis-workflow.md`](/Users/jameshassett/dev/FX_Analysis/docs/02-analysis-workflow.md)
- [`docs/03-read-only-contract.md`](/Users/jameshassett/dev/FX_Analysis/docs/03-read-only-contract.md)
- [`docs/04-data-request-contract.md`](/Users/jameshassett/dev/FX_Analysis/docs/04-data-request-contract.md)
- [`docs/05-extension-guidelines.md`](/Users/jameshassett/dev/FX_Analysis/docs/05-extension-guidelines.md)
- [`docs/07-systemacro-data-architecture.md`](/Users/jameshassett/dev/FX_Analysis/docs/07-systemacro-data-architecture.md)
