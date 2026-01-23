# Running FX_Analysis

## Streamlit Dashboard

Launch the interactive dashboard:

```bash
cd /Users/jameshassett/dev/FX_Analysis
source .venv/bin/activate
streamlit run bin/streamlit_app.py
```

The dashboard will open in your default browser at `http://localhost:8501`.

### Dashboard Features

- **Dataset Selection**: Choose datasets from the manifest
- **Model Performance Analysis**: View summary statistics, correlations, and rolling metrics
- **Multi-Period Comparison**: Compare performance across different time ranges
- **Export Capabilities**: Download filtered results and visualizations

### Configuration

Dashboard behavior is controlled by `fx_analysis_config.yaml`. Key settings:

- Default date ranges for analysis
- Performance metrics to calculate
- Visualization options
- Export formats

## Batch / CLI Execution

FX_Analysis provides CLI commands for batch processing and automation.

### Data Consolidation

Consolidate individual model return files into a master matrix:

```bash
python -m lib.data_consolidate [OPTIONS]
```

Or using the bin entry point:
```bash
python bin/consolidate.py [OPTIONS]
```

Options:
- `--output OUTPUT`: Override output location (defaults to outputs/)
- `--preview`: Preview results without writing
- `--verbose`: Enable detailed logging

Example:
```bash
python -m lib.data_consolidate --verbose
```

### Summary Statistics

Calculate performance metrics for models:

```bash
python -m lib.summary_statistics [OPTIONS]
```

Or using the bin entry point:
```bash
python bin/summary_stats.py [OPTIONS]
```

Options:
- `--date-range RANGE`: Time period (full, 1year, 5year, etc.)
- `--preview`: Preview without saving
- `--verbose`: Detailed logging

Example:
```bash
python -m lib.summary_statistics --date-range 1year
```

### All Date Ranges

Calculate statistics for all configured date ranges:

```bash
python -m lib.summary_statistics all-ranges
```

This generates separate output files for each date range in `outputs/`.

## Expected Workflow

A typical analytics workflow:

1. **Select Dataset**: Reference dataset by manifest name, not file path
2. **Consolidate** (if needed): Merge source files into analysis-ready format
3. **Calculate Metrics**: Generate performance statistics
4. **Visualize**: Explore results in Streamlit dashboard
5. **Export**: Save specific results from dashboard or CLI

All outputs are written to `outputs/` and are ephemeral.

## Error Handling

CLI commands will:
- Validate manifest entries before processing
- Check dataset availability and schema compliance
- Provide clear error messages for missing datasets or invalid configurations
- Never attempt to write to `FX_DATA_ROOT`

## Automation

CLI commands are designed for automation:

```bash
# Example: Daily analytics pipeline
python -m lib.data_consolidate
python -m lib.summary_statistics all-ranges
```

Outputs can be consumed by downstream systems or archived as needed.
