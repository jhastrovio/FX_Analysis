# Data Contract

## Authoritative vs Non-Authoritative Datasets

### Authoritative Datasets

Authoritative datasets are produced, maintained, and governed by the producer repository. They reside in `/FX_Data - General` and have:

- **Defined Schemas**: Column names, types, and constraints specified in the manifest
- **Lifecycle Management**: Creation dates, update frequencies, archival policies
- **Data Quality Guarantees**: Validation, reconciliation, and normalization applied
- **Version Control**: Change tracking and audit trails

Examples of authoritative datasets:
- `eod_portfolio`: End-of-day portfolio positions
- `market_changes`: Market data change events
- `model_signals`: FX trading model signal outputs

### Non-Authoritative Datasets

FX_Analysis produces non-authoritative, ephemeral analytics artifacts:

- **Derived Data**: Calculated metrics, aggregations, transformations
- **Temporary Results**: Intermediate outputs from multi-step workflows
- **Analysis Views**: Filtered, grouped, or pivoted views of source data
- **Visualization Exports**: Charts, reports, summaries

These outputs are written to `outputs/` and are:
- Not versioned in the data estate
- Not used as inputs by other systems
- Regenerable from source datasets
- Ephemeral and disposable

## Manifest Metadata Consumption

FX_Analysis consumes metadata from the master manifest to:

### Resolve Dataset Paths

```python
# Manifest entry
{
  "name": "model_signals",
  "path": "clean/models_signals_systemacro",
  "schema": {...}
}

# FX_Analysis resolves to absolute path
absolute_path = FX_DATA_ROOT / manifest_entry["path"]
```

### Validate Schemas

```python
# Load dataset with schema validation
dataset = manifest.get_dataset("model_signals")
df = load_with_schema(dataset, validate=True)
```

### Check Lifecycle Status

```python
# Verify dataset is current
if not dataset.is_current():
    raise DatasetStaleError(f"{dataset.name} has not been updated recently")
```

## Commonly Used Datasets

### model_signals

FX trading model daily return signals.

**Manifest Name**: `model_signals`  
**Path**: `clean/models_signals_systemacro`  
**Schema**: 
- `Date`: Trading date
- `{model_id}_{model_name}`: Daily return columns
- `Model_Index.csv`: Metadata (ID, Name, Category, Family)

**Usage in FX_Analysis**:
- Consolidation into master return matrix
- Performance metrics calculation
- Portfolio construction analysis

### eod_portfolio

End-of-day portfolio positions and exposures.

**Manifest Name**: `eod_portfolio`  
**Usage**: Portfolio-level analysis, risk metrics, attribution

### market_changes

Market data change events and updates.

**Manifest Name**: `market_changes`  
**Usage**: Event-driven analysis, market impact studies

## Dataset Access Pattern

FX_Analysis follows a consistent pattern for dataset access:

1. **Resolve from Manifest**: Look up dataset by name
2. **Validate Availability**: Check dataset exists and is current
3. **Load with Schema**: Read data with schema validation
4. **Process Read-Only**: Perform analytics without modification
5. **Write to Outputs**: Save results to local `outputs/` directory

## Schema Compliance

FX_Analysis expects datasets to conform to their manifest-defined schemas:

- **Column Names**: Must match exactly
- **Data Types**: Must be compatible (coercion may occur)
- **Constraints**: Referential integrity, value ranges, etc.
- **Required Fields**: Must be present

Schema violations will raise clear errors indicating the mismatch.

## Lifecycle Awareness

FX_Analysis respects dataset lifecycle metadata:

- **Update Frequencies**: Knows when datasets are expected to refresh
- **Staleness Checks**: Warns if using outdated data
- **Archival Status**: Handles archived datasets appropriately

This ensures analytics are performed on current, valid data.

## Contract Guarantees

FX_Analysis guarantees:

- **Read-Only Access**: Never modifies source datasets
- **Schema Compliance**: Validates and respects manifest schemas
- **Path Resolution**: Uses manifest paths, not hard-coded locations
- **Output Isolation**: All writes go to `outputs/`, never to data estate

The producer repository guarantees:

- **Schema Stability**: Schemas don't change without manifest updates
- **Path Stability**: Dataset paths remain consistent
- **Data Quality**: Authoritative datasets meet quality standards
- **Lifecycle Management**: Datasets are maintained per manifest metadata
