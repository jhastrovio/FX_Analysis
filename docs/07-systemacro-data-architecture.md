# Systemacro Data Architecture

## Purpose

This document describes how **FX_Analysis** interacts with the Systemacro research platform, the Systemacro website, and the OneDrive data store.

The goal is to clearly define the **division of responsibilities between research production, data storage, and analysis** so that:

- FX_Analysis remains a **lightweight, read-only analytics consumer**
- upstream research systems remain the **source of truth**
- analysis can evolve rapidly without creating hidden data pipelines

This architecture prioritizes **clarity, reproducibility, and separation of concerns**.

---

# System Architecture Overview

FX_Analysis sits in the **analysis layer** of a broader research ecosystem.

```text
Systemacro Research System
  -> structured data exports / daily snapshots
  -> OneDrive Data Store
  -> FX_Analysis
  -> Ephemeral outputs

Systemacro Website
  -> presentation, documentation, and metadata context
  -> not the primary runtime data source
```

Each layer has a clearly defined responsibility.

---

# Systemacro Research System

The **Systemacro Research System** is where the underlying quantitative work is performed.

This includes:

- systematic FX models
- strategy signals
- model returns
- portfolio construction logic
- research methodologies

These models and datasets are **maintained outside the FX_Analysis repository**.

FX_Analysis **does not attempt to recreate or modify this research layer**.  
It consumes outputs produced by this system.

---

# Systemacro Website

The Systemacro website (`systemacro.com`) acts as the **research presentation and documentation layer**.

It provides:

- descriptions of models and strategies
- portfolio documentation
- research context and commentary
- taxonomy of strategies and model families

FX_Analysis may use the website as a **contextual or metadata source**, for example:

- strategy descriptions
- factor classifications
- portfolio definitions
- links to research documentation

However:

> The website is **not the primary runtime data source for analysis**.

Analysis should rely on **structured datasets stored in OneDrive**, not on scraping the live website.

For static reference inputs, a structured workbook in OneDrive is acceptable when it is stable and machine-readable. For example, portfolio allocation weights may be maintained in `_meta/Portfolio_Allocations.xlsx` and normalized in analysis code for minor presentation rounding differences.

---

# OneDrive Data Store

The **OneDrive Data Store** acts as the operational input layer for analysis.

It contains:

### Systemacro datasets

Examples:

- model returns
- strategy signals
- portfolio snapshots
- model metadata
- strategy catalogs

### Internal market data

Examples:

- FX spot rates
- interest rates
- volatility series
- macroeconomic time series
- benchmark indices

These datasets are saved as **daily snapshots or structured exports**.

Example structure:


OneDrive/

systemacro/
returns/
signals/
portfolios/
model_catalog.csv

market_data/
fx/
rates/
vols/

```

FX_Analysis reads these datasets **in a read-only manner**.

---

# FX_Analysis Responsibilities

FX_Analysis is responsible for **analysis and research**, not data production.

Typical activities include:

- model performance analysis
- cross-model comparison
- strategy ranking
- correlation and diversification analysis
- portfolio construction research
- visualization and reporting
- exploratory analysis

Outputs produced by FX_Analysis include:

- summary statistics
- correlation tables
- ranking tables
- charts and dashboards
- portfolio simulations

These outputs are **temporary analytical artifacts**.

They are:

- not authoritative datasets
- not used as upstream inputs
- reproducible from source data

---

# Read-Only Contract

FX_Analysis operates under a **strict read-only contract** with upstream datasets.

This means:

- FX_Analysis **reads datasets from OneDrive**
- FX_Analysis **does not modify or overwrite source datasets**
- FX_Analysis **does not publish canonical datasets**

All authoritative data production occurs **outside this repository**.

This protects:

- data governance
- reproducibility of research
- separation of responsibilities

---

# Data Request Loop

Analysis may reveal the need for additional upstream data.

Examples:

- missing historical data
- new model attributes
- improved dataset structure
- additional market series

When this occurs:

1. The requirement should be documented.
2. The change should be implemented **upstream** in the research system or data preparation layer.
3. The resulting dataset becomes available in **OneDrive**.
4. FX_Analysis then consumes the new dataset.

FX_Analysis should **not implement permanent data engineering pipelines**.

---

# Design Principles

The architecture follows several guiding principles.

### Separation of responsibilities

```

Research system → produces models
Website → documents research
OneDrive → stores datasets
FX_Analysis → performs analysis

```

### Read-only analytics

FX_Analysis is an **analytics consumer**, not a data platform.

### Reproducibility

Analysis results should always be reproducible from source datasets.

### Lightweight structure

The repository should remain easy to understand and modify.

### Clarity over complexity

Avoid unnecessary abstractions or frameworks.

---

# Summary

FX_Analysis is designed to function as a **research and analysis layer** built on top of the Systemacro research platform.

Upstream systems handle:

- model creation
- dataset production
- research documentation

FX_Analysis focuses on:

- evaluating models
- comparing strategies
- exploring portfolios
- generating analytical insight

By maintaining this separation, the repository remains **flexible, safe, and easy to evolve** while respecting the broader research infrastructure.
```
