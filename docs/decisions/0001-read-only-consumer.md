# Read-Only Consumer Boundary

## The Decision

FX_Analysis is read-only with respect to `/FX_Data - General`. It never writes, modifies, or deletes anything in that directory tree.

## Why This Boundary Exists

The FX data estate is governed and maintained by a separate producer system. That system handles all the hard problems: ingestion, normalization, reconciliation, schema management, data quality, and lifecycle. It produces authoritative datasets that other systems depend on.

If FX_Analysis could write to that space, several bad things would happen:

- **Ownership confusion**: Who's responsible for data quality? Who fixes problems?
- **Accidental corruption**: Analytics code could break production datasets
- **Governance violations**: Unauthorized changes bypass review and audit trails
- **Coupling**: Analytics becomes tightly coupled to data storage details

The read-only boundary creates a clean separation. FX_Analysis is a consumer, not a producer. It reads what's there, does analysis, and writes results elsewhere.

## What Doesn't Belong Here

This boundary means certain kinds of work don't belong in FX_Analysis:

**Data Production Work**
- Ingesting raw market data
- Normalizing inconsistent formats
- Reconciling conflicting sources
- Creating new authoritative datasets
- Managing dataset lifecycles (creation, archival, deletion)

**Data Governance Work**
- Defining schemas for permanent storage
- Establishing data quality rules
- Setting up validation pipelines
- Managing access controls

**Infrastructure Work**
- Database setup or migration
- Storage optimization
- Backup and recovery
- Data estate monitoring

If you find yourself wanting to do any of these things, that work belongs in the producer repository, not here.

## What Does Belong

FX_Analysis is for analytics work:

- Reading datasets and performing calculations
- Generating performance metrics and statistics
- Creating visualizations and reports
- Exploring data relationships and patterns
- Building temporary analysis views

All of this happens on read-only copies of the data, and results go to the local `outputs/` directory.

## Practical Implications

When writing code, ask: "Am I trying to write to `/FX_Data - General`?" If yes, stop. That's the producer's job.

When designing workflows, assume you can only read. You can't fix bad data, you can't create new datasets, you can't modify existing ones. If the data isn't right, work with the producer team to fix it at the source.

This constraint keeps FX_Analysis lightweight and focused. It's an analytics tool, not a data platform.
