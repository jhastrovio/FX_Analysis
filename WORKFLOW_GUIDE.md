# FX Analysis Workflow Guide

This guide explains how to use the FX Analysis codebase to perform end-to-end analysis of FX trading models.

## Table of Contents
1. [Prerequisites](#prerequisites)
2. [Workflow Overview](#workflow-overview)
3. [Step 1: Data Consolidation](#step-1-data-consolidation)
4. [Step 2: Calculate Summary Statistics](#step-2-calculate-summary-statistics)
5. [Step 3: Visualize Results](#step-3-visualize-results)
6. [File Management](#file-management)
7. [Common Workflows](#common-workflows)
8. [Troubleshooting](#troubleshooting)

---

## Prerequisites

Before starting, ensure you have:

1. **Environment Setup** (see README for details):
   ```bash
   # Navigate to project directory
   cd /Users/jameshassett/dev/FX_Analysis
   
   # Create and activate virtual environment
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   
   # Install dependencies
   pip install -r requirements.txt
   ```

2. **OneDrive Configuration**:
   - OneDrive client installed and syncing
   - `.env` file with `OD=/path/to/your/OneDrive/root`
   - Model CSV files in: `{OD}/clean/models_signals_systemacro/`
   - `Model_Index.csv` in the same directory

3. **Verify Setup**:
   ```bash
   # Make sure you're in the project directory
   cd /Users/jameshassett/dev/FX_Analysis
   
   # Verify model count
   python check_model_count.py
   ```
   This should show 100 models found.

---

## Workflow Overview

The typical analysis workflow consists of three main steps:

```
Raw Model Files → [Step 1: Consolidate] → Master Return Matrix
                                              ↓
                                    [Step 2: Calculate Stats]
                                              ↓
                                    Summary Statistics CSV
                                              ↓
                                    [Step 3: Visualize]
                                              ↓
                                    Interactive Dashboard
```

---

## Step 1: Data Consolidation

**Purpose**: Merge individual model CSV files into a single master return matrix.

### Basic Usage

```bash
# Make sure you're in the project directory
cd /Users/jameshassett/dev/FX_Analysis

# Consolidate all models (default behavior)
python Data_Consolidate.py

# Preview results without saving
python Data_Consolidate.py --preview

# Run with verbose output to see progress
python Data_Consolidate.py --verbose
```

### What It Does

1. Reads all model CSV files from the Models directory
2. Matches each file with metadata from `Model_Index.csv`
3. Extracts date and return columns
4. Merges all models into a single DataFrame with:
   - `Date` column (index)
   - One column per model: `{model_id} - {model_name}`

### Output

- **Location**: `{OD}/clean/systemacro_analysis/Processed/Master_Return_Matrix.csv`
- **Format**: CSV with Date column and one column per model
- **Shape**: (number of trading days) × (100 models + 1 date column)

### Example Output

```
Date,1 - G10Carry MM1 2Crosses,6 - PPP Global,12 - LMeanReversion Global,...
2000-01-03,0.0,0.0,0.0,...
2000-01-04,0.12,-0.11,0.05,...
...
```

### Advanced Options

```bash
# Use custom config file
python Data_Consolidate.py --config my_config.yaml

# Specify custom output path
python Data_Consolidate.py --output ./custom/master.csv
```

### Verification

After consolidation, verify the output:
```bash
python file_manager.py list-onedrive-files processed_data --pattern "*Master*.csv"
```

---

## Step 2: Calculate Summary Statistics

**Purpose**: Calculate performance metrics for all models (returns, volatility, Sharpe ratio, max drawdown, etc.).

### Basic Usage

```bash
# Make sure you're in the project directory
cd /Users/jameshassett/dev/FX_Analysis

# Calculate statistics for full period (default)
python summary_statistics.py

# Preview results without saving
python summary_statistics.py --preview

# Run with verbose output
python summary_statistics.py --verbose

# Calculate for specific date range
python summary_statistics.py --date-range 1year
```

### Available Date Ranges

- `full` - All available data (default)
- `10year`, `5year`, `2year`, `1year`
- `6month`, `3month`, `2month`, `1month`
- `1week`, `3day`, `1day`

### What It Calculates

For each model, the script calculates:

1. **Annualized Return** - Compound annual return (%)
2. **Total Return** - Cumulative return over period (%)
3. **Volatility** - Annualized standard deviation (decimal)
4. **Sharpe Ratio** - Annualized Sharpe based on monthly returns
5. **Max Drawdown** - Maximum peak-to-trough decline (decimal)

Plus metadata:
- Model ID and Name
- Category (from Model_Index.csv)
- Family (from Model_Index.csv)

### Output

- **Location**: `{OD}/clean/systemacro_analysis/Processed/{date_range}_Stats_{date}.csv`
- **Format**: CSV with one row per model
- **Columns**: model_id, model_name, category, family, annualized_return, return, volatility, sharpe_ratio, max_drawdown

### Example Output

```
model_id,model_name,category,family,annualized_return,return,volatility,sharpe_ratio,max_drawdown
1,G10Carry MM1 2Crosses,carry,simple carry,5.234567,125.456789,0.123456,0.456789,-0.234567
6,PPP Global,valuation,PPP,3.123456,78.901234,0.098765,0.345678,-0.187654
...
```

### Calculate for All Date Ranges

```bash
# Calculate statistics for ALL available date ranges at once
python summary_statistics.py all-ranges --verbose
```

This creates separate CSV files for each date range, useful for comparing performance across different time periods.

### Test Mode

```bash
# Use test data instead of production data
python summary_statistics.py --test
```

### Advanced Options

```bash
# Use custom config file
python summary_statistics.py --config my_config.yaml

# Combine options
python summary_statistics.py --date-range 5year --verbose --preview
```

---

## Step 3: Visualize Results

**Purpose**: Interactive dashboard for exploring and analyzing model performance.

### Launch Dashboard

```bash
# Make sure you're in the project directory
cd /Users/jameshassett/dev/FX_Analysis

# Launch the dashboard
streamlit run Streamlit.py
```

The dashboard will open in your browser (typically at `http://localhost:8501`).

### Dashboard Features

#### 1. File Selection
- **Single File Mode**: Analyze one summary statistics file
- **Multi-File Comparison**: Compare multiple date ranges side-by-side

#### 2. Filtering & Analysis
- **Model Filter**: Select specific models to analyze
- **Top N Filter**: Show top performers by any metric
- **Category/Family Grouping**: Group models by classification

#### 3. Visualizations
- **Bar Charts**: Compare metrics across models
- **Heatmaps**: Multi-period performance comparison
  - Absolute values
  - Relative to mean
  - Percentile ranks
  - Z-scores
- **Correlation Analysis**: Period-to-period correlations

#### 4. Advanced Features
- **Rank Columns**: Add ranking for each metric
- **Percentiles**: Show percentile positions
- **Z-Scores**: Standardized scores
- **Group Statistics**: Summary by category/family
- **Export Options**: Download filtered data, heatmaps, correlations

### Workflow in Dashboard

1. **Load Files**: Select summary statistics CSV files from Processed directory
2. **Filter Models**: Use sidebar to filter by model name, category, or top performers
3. **Explore Metrics**: Switch between different performance metrics
4. **Compare Periods**: Use multi-file mode to compare different time ranges
5. **Export Results**: Download analysis results for further processing

### Example Workflow

```bash
# 1. Launch dashboard
streamlit run Streamlit.py

# 2. In dashboard:
#    - Select "Multi-File Comparison"
#    - Load: full_period_Stats_*.csv, 1year_Stats_*.csv, 5year_Stats_*.csv
#    - Filter to top 25 models by Sharpe ratio
#    - View heatmap of annualized returns
#    - Export correlation matrix
```

---

## File Management

The `file_manager.py` script provides utilities for managing OneDrive files.

### Common Commands

```bash
# List all CSV files in processed data
python file_manager.py list-onedrive-files processed_data --pattern "*.csv"

# Explore folder structure
python file_manager.py explore-onedrive-folder processed_data --details

# Get folder statistics
python file_manager.py folder-stats processed_data

# Preview a file
python file_manager.py preview-onedrive-file processed_data "Master_Return_Matrix.csv"

# List files modified in last 7 days
python file_manager.py list-onedrive-files processed_data --days-ago 7
```

### Path Keys

Use these path keys with file_manager commands:
- `base` - `clean/systemacro_analysis`
- `raw_data` - `clean/systemacro_analysis/Models`
- `processed_data` - `clean/systemacro_analysis/Processed`
- `logs` - `clean/systemacro_analysis/Logs`

---

## Common Workflows

### Workflow 1: Full Analysis (First Time)

```bash
# Navigate to project directory
cd /Users/jameshassett/dev/FX_Analysis

# 1. Verify setup
python check_model_count.py

# 2. Consolidate data
python Data_Consolidate.py --verbose

# 3. Calculate statistics for all periods
python summary_statistics.py all-ranges --verbose

# 4. Launch dashboard
streamlit run Streamlit.py
```

### Workflow 2: Update Analysis (New Data)

```bash
# Navigate to project directory
cd /Users/jameshassett/dev/FX_Analysis

# 1. Re-consolidate (if new models added)
python Data_Consolidate.py --verbose

# 2. Recalculate statistics
python summary_statistics.py --verbose

# 3. View in dashboard
streamlit run Streamlit.py
```

### Workflow 3: Analyze Specific Time Period

```bash
# Navigate to project directory
cd /Users/jameshassett/dev/FX_Analysis

# 1. Calculate for specific period
python summary_statistics.py --date-range 1year --verbose

# 2. Compare with full period in dashboard
streamlit run Streamlit.py
# Then load both files in multi-file mode
```

### Workflow 4: Quick Preview

```bash
# Navigate to project directory
cd /Users/jameshassett/dev/FX_Analysis

# Preview consolidation
python Data_Consolidate.py --preview

# Preview statistics
python summary_statistics.py --preview --date-range 1year
```

### Workflow 5: Export for External Analysis

```bash
# Navigate to project directory
cd /Users/jameshassett/dev/FX_Analysis

# 1. Generate statistics
python summary_statistics.py all-ranges

# 2. Use file_manager to export
python file_manager.py list-onedrive-files processed_data --pattern "*Stats*.csv"

# 3. Or download via Streamlit dashboard export feature
```

---

## Troubleshooting

### Issue: "OD environment variable not set"

**Solution**: 
```bash
# Check .env file exists and has:
OD=/path/to/your/OneDrive/root

# Restart terminal/IDE after updating .env
```

### Issue: "OneDrive path does not exist"

**Solution**:
- Verify OneDrive is syncing properly
- Check the exact path matches your OneDrive folder structure
- Run: `python check_model_count.py` to verify paths

### Issue: "No model data found"

**Solution**:
- Verify model CSV files are in the Models directory
- Check Model_Index.csv exists and has correct format
- Run: `python file_manager.py list-onedrive-files raw_data`

### Issue: "Failed to load master matrix"

**Solution**:
- Ensure Step 1 (Data_Consolidate.py) completed successfully
- Check Processed directory has Master_Return_Matrix.csv
- Verify file is not corrupted: `python file_manager.py preview-onedrive-file processed_data "Master_Return_Matrix.csv"`

### Issue: Streamlit dashboard shows no files

**Solution**:
- Verify summary statistics files exist in Processed directory
- Check file naming matches expected pattern
- Use file_manager to list files: `python file_manager.py list-onedrive-files processed_data`

### Issue: Import errors

**Solution**:
```bash
# Ensure virtual environment is activated
source .venv/bin/activate

# Reinstall dependencies
pip install -r requirements.txt
```

---

## Configuration

### Customizing Analysis Parameters

Edit `fx_analysis_config.yaml` to customize:

- **Performance Metrics**: Add/remove metrics to calculate
- **Date Ranges**: Modify available analysis periods
- **Annualization Factor**: Change from 260 (trading days) if needed
- **Rolling Windows**: Configure rolling analysis windows
- **File Patterns**: Customize output file naming

### Customizing OneDrive Paths

Edit `onedrive_config.yaml` to change:
- Base paths for different data types
- File naming patterns
- Timestamp formats

---

## Next Steps

After completing the basic workflow:

1. **Explore Different Metrics**: Try different performance metrics in the dashboard
2. **Compare Periods**: Use multi-file comparison to see how models perform over time
3. **Filter by Category**: Analyze specific model categories (carry, valuation, etc.)
4. **Export Results**: Download data for further analysis in Excel/Python/R
5. **Portfolio Construction**: (Coming soon) Use consolidated data for portfolio optimization

---

## Quick Reference

```bash
# Navigate to project directory first
cd /Users/jameshassett/dev/FX_Analysis

# Data Consolidation
python Data_Consolidate.py [--preview] [--verbose]

# Summary Statistics
python summary_statistics.py [--date-range RANGE] [--preview] [--verbose]
python summary_statistics.py all-ranges [--verbose]

# Visualization
streamlit run Streamlit.py

# File Management
python file_manager.py list-onedrive-files PATH_KEY
python file_manager.py explore-onedrive-folder PATH_KEY
python file_manager.py folder-stats PATH_KEY

# Verification
python check_model_count.py
```

---

For more details, see the [README](Readme) for setup instructions and project overview.
