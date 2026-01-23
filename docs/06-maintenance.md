# Maintenance Guide

## Repository Structure Conventions

FX_Analysis follows a `bin/` + `lib/` structure consistent with other internal analytics repositories:

```
FX_Analysis/
├── bin/                    # Executable scripts
│   ├── consolidate.py      # Data consolidation CLI
│   ├── summary_stats.py    # Performance metrics CLI
│   └── streamlit_app.py    # Dashboard entry point
├── lib/                    # Reusable modules
│   ├── data/               # Data access layer
│   ├── analytics/          # Analysis functions
│   └── utils/              # Shared utilities
├── outputs/                # Ephemeral outputs (gitignored)
├── docs/                   # Documentation
├── config/                 # Configuration files
│   └── fx_analysis_config.yaml
├── requirements.txt
└── README.md
```

### bin/ Directory

Contains executable scripts and entry points:

- **CLI Commands**: Typer-based command-line interfaces
- **Streamlit App**: Dashboard application
- **Workflow Scripts**: Multi-step analysis pipelines

Scripts in `bin/` should be:
- Executable and directly runnable
- Well-documented with help text
- Idempotent where possible
- Following consistent argument patterns

### lib/ Directory

Contains reusable Python modules organized by function:

- **data/**: Dataset loading, manifest integration, schema validation
- **analytics/**: Performance calculations, statistical functions, portfolio methods
- **utils/**: Configuration management, logging, file I/O

Modules in `lib/` should be:
- Importable and reusable
- Well-documented with docstrings
- Unit testable
- Independent of execution context

## Adding New Workflows

### 1. Define the Workflow

Create a new script in `bin/`:

```python
#!/usr/bin/env python
"""Description of what this workflow does."""

import typer
from lib.data import load_dataset
from lib.analytics import your_analysis_function

app = typer.Typer()

@app.command()
def run(
    manifest_name: str = typer.Option(..., help="Dataset name from manifest"),
    output: str = typer.Option("outputs/", help="Output directory"),
):
    """Execute the workflow."""
    dataset = load_dataset(manifest_name)
    results = your_analysis_function(dataset)
    results.to_csv(f"{output}/results.csv")

if __name__ == "__main__":
    app()
```

### 2. Implement Analysis Logic

Add reusable functions to `lib/analytics/`:

```python
# lib/analytics/your_analysis.py
def your_analysis_function(dataset):
    """Perform analysis on dataset."""
    # Implementation
    return results
```

### 3. Update Configuration

Add any new parameters to `fx_analysis_config.yaml`:

```yaml
your_workflow:
  parameter1: value1
  parameter2: value2
```

### 4. Document the Workflow

Add documentation to `docs/05-workflows.md` describing:
- Purpose and use cases
- Required inputs (manifest dataset names)
- Outputs and their formats
- Example usage

### 5. Follow Conventions

- **Manifest-Driven**: Always reference datasets by manifest name
- **Read-Only**: Never write to `FX_DATA_ROOT`
- **Output Isolation**: Write all results to `outputs/`
- **Error Handling**: Validate inputs and provide clear errors
- **Logging**: Use structured logging for debugging

## Permanent Data Extensions

**Important**: Permanent data extensions belong in the producer repository, not FX_Analysis.

### What Belongs in Producer Repo

- New dataset schemas
- Data normalization logic
- Reconciliation rules
- Schema migrations
- Data quality checks
- Lifecycle management

### What Belongs in FX_Analysis

- Analytics calculations
- Visualization code
- Report generation
- Temporary transformations
- Derived metrics

### Decision Process

When considering where to add functionality:

1. **Does it modify source data?** → Producer repo
2. **Does it create a new authoritative dataset?** → Producer repo
3. **Does it define a new schema?** → Producer repo
4. **Is it a calculation or analysis?** → FX_Analysis
5. **Is the output ephemeral?** → FX_Analysis

If unsure, consult with the data platform team.

## Code Review Guidelines

When submitting changes:

1. **Verify Read-Only Contract**: Ensure no writes to `FX_DATA_ROOT`
2. **Check Manifest Usage**: Datasets referenced by name, not path
3. **Test Output Isolation**: Confirm outputs go to `outputs/`
4. **Update Documentation**: Keep docs in sync with code changes
5. **Follow Structure**: Adhere to `bin/` + `lib/` conventions

## Testing

FX_Analysis should include:

- **Unit Tests**: For `lib/` modules (analytics functions, utilities)
- **Integration Tests**: For `bin/` scripts (end-to-end workflows)
- **Contract Tests**: Verify read-only behavior, manifest compliance

Tests should:
- Use test datasets (not production data)
- Validate outputs without modifying sources
- Be runnable in CI/CD pipelines

## Dependencies

When adding dependencies:

1. **Justify Need**: Explain why the dependency is required
2. **Check Compatibility**: Ensure it works with existing stack
3. **Update requirements.txt**: Pin versions appropriately
4. **Document Usage**: Note any special configuration needed

Avoid dependencies that:
- Require system-level installation
- Conflict with existing packages
- Have unclear licensing
- Are unmaintained or deprecated
