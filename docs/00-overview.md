# FX_Analysis Overview

## What FX_Analysis Is

FX_Analysis is a read-only analytics consumer application that performs exploratory data analysis, performance metrics calculation, and visualization on FX trading model datasets. It provides:

- **Performance Analytics**: Calculation of annualized returns, volatility, Sharpe ratios, and drawdown metrics
- **Data Consolidation**: Merging of individual model return files into consolidated matrices
- **Interactive Visualization**: Streamlit-based dashboards for exploring model performance
- **Portfolio Analysis**: Framework for evaluating portfolio construction techniques

## What FX_Analysis Is Not

FX_Analysis is **not** a data producer. It does not:

- Ingest raw market data
- Normalize or reconcile datasets
- Produce authoritative datasets
- Modify source data in any way
- Write to the governed data estate

## Read-Only Contract

FX_Analysis maintains a strict read-only contract with `/FX_Data - General`:

- **Read Access Only**: All data access is read-only. No write, modify, or delete operations are permitted.
- **No Data Modification**: Source datasets are never altered, transformed in-place, or overwritten.
- **No Schema Changes**: Dataset schemas and structures are treated as immutable.
- **No Lifecycle Management**: Dataset creation, archival, or deletion is handled exclusively by the producer repository.

This contract ensures data governance integrity and prevents analytics workflows from affecting authoritative datasets.

## Role in FX Data Platform

FX_Analysis sits in the analytics layer of the FX data platform:

```
┌─────────────────────────────────────┐
│   Producer Repository               │
│   (Ingestion, Normalization)        │
└──────────────┬──────────────────────┘
               │ writes
               ▼
┌─────────────────────────────────────┐
│   /FX_Data - General                │
│   (Governed Data Estate)            │
└──────────────┬──────────────────────┘
               │ read-only
               ▼
┌─────────────────────────────────────┐
│   FX_Analysis                       │
│   (Analytics Consumer)              │
└──────────────┬──────────────────────┘
               │ writes
               ▼
┌─────────────────────────────────────┐
│   outputs/                          │
│   (Ephemeral Analytics Artifacts)    │
└─────────────────────────────────────┘
```

The platform follows a clear separation of concerns:

1. **Producer Repository**: Handles all data ingestion, normalization, reconciliation, and dataset production
2. **FX_Data - General**: Stores authoritative, governed datasets with defined schemas and lifecycle metadata
3. **FX_Analysis**: Consumes datasets for analytics, producing ephemeral outputs

## Output Location

All analytics outputs are written to the local `outputs/` directory within the FX_Analysis repository:

- **Consolidated Matrices**: Merged return matrices
- **Summary Statistics**: Performance metrics by model and time period
- **Visualization Exports**: Charts, heatmaps, and analysis reports
- **Intermediate Results**: Temporary artifacts from multi-step workflows

Outputs are ephemeral and may be regenerated at any time. They are not versioned or treated as authoritative datasets. The `outputs/` directory is excluded from source control (via `.gitignore`).

## Architecture Principles

- **Manifest-Driven**: Dataset selection and schema information comes from the master manifest, not hard-coded paths
- **Stateless Analytics**: Workflows can be re-run to regenerate outputs from source data
- **Separation of Concerns**: Analytics logic is independent of data production logic
- **Contract Compliance**: Strict adherence to the read-only contract with the data estate
