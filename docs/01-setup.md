# Setup Guide

## Python Environment

FX_Analysis requires Python 3.9 or higher. Set up a virtual environment:

```bash
cd /Users/jameshassett/dev/FX_Analysis
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

## Installing Dependencies

Install required packages from `requirements.txt`:

```bash
pip install -r requirements.txt
```

Core dependencies include:
- `pandas` - Data manipulation and analysis
- `streamlit` - Interactive dashboard framework
- `typer` - CLI interface
- `pyyaml` - Configuration file parsing
- `python-dotenv` - Environment variable management

## Environment Variables

FX_Analysis requires the following environment variables, configured via `.env` file:

### FX_DATA_ROOT

Path to the root of the FX data estate:

```bash
FX_DATA_ROOT=/path/to/FX_Data - General
```

This path must point to the governed data estate location. FX_Analysis will read datasets from this location but will never write to it.

### MANIFEST_PATH

Path to the master manifest file that defines dataset schemas, paths, and lifecycle metadata:

```bash
MANIFEST_PATH=/path/to/manifest.json
```

The manifest is the single source of truth for:
- Dataset names and identifiers
- File system paths relative to `FX_DATA_ROOT`
- Schema definitions (columns, types, constraints)
- Dataset lifecycle metadata (creation dates, update frequencies)

### Example .env File

```bash
# FX Data Estate Root
FX_DATA_ROOT=/Users/jameshassett/Library/CloudStorage/OneDrive-IntellectiveCapitalPte.Ltd/FX_Data - General

# Master Manifest Path
MANIFEST_PATH=/path/to/fx-data-manifest.json
```

## Verification

Verify your setup:

```bash
# Check environment variables are loaded
python -c "from dotenv import load_dotenv; import os; load_dotenv(); print('FX_DATA_ROOT:', os.getenv('FX_DATA_ROOT')); print('MANIFEST_PATH:', os.getenv('MANIFEST_PATH'))"

# Verify FX_DATA_ROOT exists and is readable
python -c "import os; from dotenv import load_dotenv; load_dotenv(); root = os.getenv('FX_DATA_ROOT'); print('Exists:', os.path.exists(root) if root else False)"
```

## Repository Structure

FX_Analysis follows a `bin/` + `lib/` structure:

- **bin/**: Executable scripts and entry points (CLI commands, Streamlit app)
- **lib/**: Reusable Python modules (data access, analytics, utilities)
- **outputs/**: Ephemeral analytics outputs (gitignored)
- **docs/**: Documentation
- **config/**: Configuration files

This structure is consistent with other internal analytics repositories.
