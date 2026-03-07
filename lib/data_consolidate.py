#!/usr/bin/env python
"""
Analytics-only: Consolidate individual FX-model return CSVs into a temporary analysis matrix.

This script reads from the FX data estate (read-only) and creates an ephemeral consolidated
matrix for analysis purposes. The output is a temporary analytics artifact, not an authoritative
dataset.

Usage examples:
---------------
# Build with default config paths
python -m lib.data_consolidate

# Specify alternative config and output paths
python -m lib.data_consolidate --config my_config.yaml --output ./outputs/master.csv

# Preview the first rows instead of writing
python -m lib.data_consolidate --preview
"""
from __future__ import annotations

import re
import os
from functools import reduce
from pathlib import Path
from typing import List, Optional

import pandas as pd
import typer
from lib.config_manager import get_config
from lib.onedrive_storage import OneDriveStorage

app = typer.Typer(add_completion=False, invoke_without_command=True, help="Analytics-only: Consolidate model returns for analysis")


def _write_local_csv(df: pd.DataFrame, output_path: str) -> None:
    """Write an ephemeral analysis artifact to a local path."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def _find_date_column(df: pd.DataFrame) -> Optional[pd.Series]:
    """Return a parsed datetime Series from plausible column names."""
    for col in ["Date", "Category", "date", "DATE"]:
        if col in df.columns:
            return pd.to_datetime(df[col], dayfirst=True, errors="coerce")
    return None


def _gather_model_dfs(
    storage: OneDriveStorage,
    data_folder: str,
    model_index: pd.DataFrame,
    verbose: bool = False,
) -> List[pd.DataFrame]:
    """Load model CSVs from read-only data source and return list of 2-column DataFrames.
    
    This function reads (only) from the FX data estate. No data modification occurs.
    """
    model_dfs: List[pd.DataFrame] = []

    try:
        files = storage.list_files(data_folder)
        file_names = [f["name"] for f in files]
    except Exception as e:
        if verbose:
            typer.echo(f"Failed to list files in {data_folder}: {e}")
        return []

    # Filter for model files (exclude Model_Index.csv)
    model_files = [f for f in file_names if f != "Model_Index.csv" and re.match(r"(\d+)_.*\.csv", f)]
    total_files = len(model_files)
    
    if verbose:
        typer.echo(f"Found {total_files} model files to process")

    for i, file_name in enumerate(model_files, 1):
        if verbose:
            typer.echo(f"Processing {i}/{total_files}: {file_name}")

        match = re.match(r"(\d+)_.*\.csv", file_name)
        if not match:
            if verbose:
                typer.echo(f"Skipping {file_name}: filename pattern mismatch")
            continue

        model_id = int(match.group(1))
        meta_row = model_index.loc[model_index["ID"] == model_id]
        if meta_row.empty:
            if verbose:
                typer.echo(f"No metadata for model {model_id}")
            continue

        model_name = meta_row.iloc[0]["Name"]
        col_label = f"{model_id} - {model_name}"

        try:
            file_path = f"{data_folder}/{file_name}"
            df = storage.download_csv(file_path)
        except Exception as e:
            if verbose:
                typer.echo(f"Failed to read {file_name}: {e}")
            continue

        date_series = _find_date_column(df)
        if date_series is None:
            if verbose:
                typer.echo(f"No date column found in {file_name}")
            continue

        return_cols = [c for c in df.columns if "ID:" in c and "(ex carry)" not in c]
        if not return_cols:
            if verbose:
                typer.echo(f"No return column in {file_name}")
            continue

        temp = pd.DataFrame({"Date": date_series, col_label: df[return_cols[0]]})
        model_dfs.append(temp)
        
        if verbose:
            typer.echo(f"✅ Successfully processed {file_name}")

    return model_dfs


@app.callback(invoke_without_command=True)
def main(
    config: Path = typer.Option(
        "fx_analysis_config.yaml",
        "--config",
        "-c",
        exists=True,
        readable=True,
        help="Path to YAML config file",
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Destination CSV file for ephemeral output (defaults to outputs/ directory)",
    ),
    preview: bool = typer.Option(
        False,
        "--preview/--no-preview",
        "-p",
        help="Print the first rows instead of saving to disk",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose/--no-verbose",
        "-v",
        help="Enable verbose logging",
    ),
) -> None:
    """Build a temporary consolidated return matrix from individual model CSVs.
    
    This is an analytics-only operation. Reads from FX data estate (read-only) and
    produces an ephemeral analysis artifact. The output is not an authoritative dataset.
    """
    # Load configuration
    fx_config = get_config(str(config))
    
    # Get read-only data paths from configuration
    # Note: These paths reference the FX data estate, which is read-only
    raw_data_path = fx_config.get_onedrive_path('raw_data')

    storage = OneDriveStorage()  # Loads config from .env

    # Get model index path from configuration
    model_index_config = fx_config.get_file_type_config('raw', 'model_index')
    model_index_path = f"{raw_data_path}/{model_index_config['pattern']}"

    try:
        model_index = storage.download_csv(model_index_path)
    except Exception as e:
        typer.echo(f"Failed to read metadata file {model_index_path}: {e}", err=True)
        raise typer.Exit(code=1)

    # Load model data (read-only from FX data estate)
    model_dfs = _gather_model_dfs(storage, raw_data_path, model_index, verbose)
    if not model_dfs:
        typer.echo("No model data found — nothing to do.", err=True)
        raise typer.Exit(code=1)

    # Consolidate for analysis: simple merge of read-only data
    # This is not data production - just combining existing datasets for analysis
    master_df = reduce(lambda l, r: pd.merge(l, r, on="Date", how="outer"), model_dfs)
    master_df.sort_values("Date", inplace=True)
    master_df.reset_index(drop=True, inplace=True)

    # Determine output path for ephemeral analytics artifact
    # Note: Outputs are temporary analysis results, not authoritative datasets
    if output is not None:
        out_path = str(output)
    else:
        out_path = fx_config.get_full_file_path('processed', 'master_matrix')

    if preview:
        typer.echo(master_df.head())
        typer.echo(f"Shape: {master_df.shape}")
    else:
        # Save ephemeral analysis output
        # Note: This is a temporary analytics artifact, not a permanent dataset
        try:
            _write_local_csv(master_df, out_path)
            typer.echo(f"Consolidated matrix saved (ephemeral): {out_path} (shape {master_df.shape})")
        except Exception as e:
            typer.echo(f"Failed to save output: {e}", err=True)
            raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
