# FX_Analysis Overview

FX_Analysis is a read-only analytics consumer. It reads governed FX datasets from the OneDrive Data Store, performs exploratory and repeatable analysis, and produces temporary outputs for research and review.

## What It Is

- A place for analysis, metrics, comparisons, and visualisation
- A consumer of governed datasets owned elsewhere
- A lightweight repo for repeatable research workflows

## What It Is Not

- Not a producer system
- Not an ingestion or normalization pipeline
- Not a canonical dataset layer
- Not a place to publish permanent datasets back into `/FX_Data - General`

## Where It Sits

In the current Systemacro architecture, the Systemacro Research System produces research outputs upstream, the Systemacro Website acts as a presentation and metadata layer, and the OneDrive Data Store provides the operational input datasets consumed by FX_Analysis.

```
┌─────────────────────────────────────┐
│ Producer system                     │
│ Ingestion, normalization, schemas   │
└──────────────┬──────────────────────┘
               │ writes governed data
               ▼
┌─────────────────────────────────────┐
│ /FX_Data - General                  │
│ Authoritative datasets              │
└──────────────┬──────────────────────┘
               │ read-only
               ▼
┌─────────────────────────────────────┐
│ FX_Analysis                         │
│ Analysis, metrics, dashboards       │
└──────────────┬──────────────────────┘
               │ writes temporary files
               ▼
┌─────────────────────────────────────┐
│ outputs/                            │
│ Ephemeral analysis artifacts        │
└─────────────────────────────────────┘
```

## Outputs

FX_Analysis can create consolidated views, summary statistics, charts, reports, and other temporary analysis artifacts. These outputs are local, regenerable, and non-authoritative.

## Key Rule

When analysis reveals a need for new or improved upstream data, document that requirement as a data request and have it implemented in the producer system, not inside FX_Analysis.

See [07-systemacro-data-architecture.md](/Users/jameshassett/dev/FX_Analysis/docs/07-systemacro-data-architecture.md), [03-read-only-contract.md](/Users/jameshassett/dev/FX_Analysis/docs/03-read-only-contract.md), and [04-data-request-contract.md](/Users/jameshassett/dev/FX_Analysis/docs/04-data-request-contract.md).
