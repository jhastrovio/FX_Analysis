#!/usr/bin/env python
"""
Consolidate individual FX-model return CSVs into a single master return matrix.

Usage examples:
---------------
# Build with default config paths
python Data_Consolidate.py

# Specify alternative config and output paths
python Data_Consolidate.py --config my_config.yaml --output ./out/master.csv

# Preview the first rows instead of writing
python Data_Consolidate.py --preview
"""
from __future__ import annotations

import re
from functools import reduce
from pathlib import Path
from typing import List, Optional
import asyncio
import io

import pandas as pd
import typer
from config_manager import get_config
from onedrive_storage import OneDriveStorage

app = typer.Typer(add_completion=False, invoke_without_command=True, help="FX return-matrix utilities")


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
    """Fetch model CSVs from OneDrive via Graph API and return list of 2-column DataFrames."""
    model_dfs: List[pd.DataFrame] = []

    try:
        files = asyncio.run(storage.list_files(data_folder))
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
            data = asyncio.run(storage.download_file(f"{data_folder}/{file_name}"))
            df = pd.read_csv(io.StringIO(data.decode('utf-8')))
        except Exception as e:
            if verbose:
                typer.echo(f"Failed to download {file_name}: {e}")
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
        help="Destination CSV file; defaults to <processed_data>/Master_Return_Matrix.csv",
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
    """Build the master return matrix from individual model CSVs."""
    # Load configuration
    fx_config = get_config(str(config))
    
    # Get paths from configuration
    raw_data_path = fx_config.get_onedrive_path('raw_data')
    processed_data_path = fx_config.get_onedrive_path('processed_data')

    storage = OneDriveStorage()  # Loads config from .env

    # Get model index path from configuration
    model_index_config = fx_config.get_file_type_config('raw', 'model_index')
    model_index_path = f"{raw_data_path}/{model_index_config['pattern']}"

    try:
        data = asyncio.run(storage.download_file(model_index_path))
        model_index = pd.read_csv(io.StringIO(data.decode('utf-8')))
    except Exception as e:
        typer.echo(f"Failed to download metadata file {model_index_path}: {e}", err=True)
        raise typer.Exit(code=1)

    model_dfs = _gather_model_dfs(storage, raw_data_path, model_index, verbose)
    if not model_dfs:
        typer.echo("No model data found — nothing to do.", err=True)
        raise typer.Exit(code=1)

    master_df = reduce(lambda l, r: pd.merge(l, r, on="Date", how="outer"), model_dfs)
    master_df.sort_values("Date", inplace=True)
    master_df.reset_index(drop=True, inplace=True)

    # Determine output path for OneDrive
    if output is not None:
        out_path = str(output)
    else:
        out_path = fx_config.get_full_file_path('processed', 'master_matrix')

    if preview:
        typer.echo(master_df.head())
        typer.echo(f"Shape: {master_df.shape}")
    else:
        # Upload to OneDrive
        try:
            asyncio.run(storage.upload_csv(out_path, master_df))
            typer.echo(f"Master matrix uploaded to OneDrive: {out_path} (shape {master_df.shape})")
        except Exception as e:
            typer.echo(f"Failed to upload to OneDrive: {e}", err=True)
            raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
