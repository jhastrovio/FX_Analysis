# Configuration

## fx_analysis_config.yaml

The `fx_analysis_config.yaml` file controls analysis parameters, metrics, and output formatting. It does **not** define dataset paths or schemas—those come from the master manifest.

## Key Sections

### Analysis Parameters

```yaml
analysis:
  annualization_factor: 260  # Trading days per year
  performance_metrics:
    - "annualized_return"
    - "volatility"
    - "sharpe_ratio"
    - "max_drawdown"
  date_ranges:
    full: "2000-01-01 to present"
    1year: "1 year"
    5year: "5 years"
```

### Output Configuration

```yaml
output_formats:
  csv:
    encoding: "utf-8"
    date_format: "%Y-%m-%d"
    float_format: "%.6f"
  excel:
    sheet_name: "FX_Analysis"
    engine: "openpyxl"
```

### Model Classification

```yaml
model_classification:
  categories:
    - "carry"
    - "valuation"
    - "cross asset"
  families:
    - "simple carry"
    - "PPP"
    - "moving average"
```

## Dataset Selection via Manifest

**Critical**: FX_Analysis selects datasets by manifest name, not hard-coded paths.

### Correct Approach

```python
# Reference dataset by manifest name
dataset = manifest.get_dataset("model_signals")
data = load_dataset(dataset)
```

### Incorrect Approach

```python
# ❌ DO NOT hard-code paths
data = pd.read_csv("/FX_Data - General/clean/models_signals_systemacro/...")
```

## Manifest Integration

The configuration file works in conjunction with the manifest:

1. **Manifest Defines**: Dataset names, paths, schemas, lifecycle
2. **Config Defines**: Analysis parameters, metrics, output formats

Example workflow:

```yaml
# User selects dataset from manifest
manifest_name: "model_signals"

# Config provides analysis parameters
analysis:
  date_ranges:
    1year: "1 year"
  performance_metrics:
    - "annualized_return"
```

The system resolves:
- Dataset path from manifest entry for `model_signals`
- Analysis parameters from config
- Output location: `outputs/` (always local)

## Configuration Overrides

Some parameters can be overridden via CLI:

```bash
# Override date range
python bin/summary_stats.py --date-range 5year

# Override output location
python bin/consolidate.py --output ./custom/output.csv
```

However, dataset selection must always reference the manifest.

## Validation

The configuration is validated on load:

- Required sections must be present
- Date range formats must be valid
- Performance metrics must be supported
- Output formats must have valid settings

Invalid configurations will fail fast with clear error messages.

## Best Practices

1. **Keep Config Focused**: Only analysis parameters, not data paths
2. **Version Control**: Config changes should be reviewed and versioned
3. **Environment-Specific**: Use environment variables for paths, not config
4. **Manifest-Driven**: Always reference datasets by manifest name
