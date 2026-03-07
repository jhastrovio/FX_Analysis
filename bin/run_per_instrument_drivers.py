#!/usr/bin/env python
"""
Per-Instrument Drivers Analysis Runner

Analytics-only: Compute model contributions to portfolio positions for attribution analysis.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

import pandas as pd
import typer
from lib.attribution.per_instrument_drivers import compute_per_instrument_drivers
from lib.config_manager import get_config

app = typer.Typer(add_completion=False, help="Per-instrument drivers analysis")


def _resolve_path(
    config_path: Optional[str],
    fx_config,
    default_onedrive_location: Optional[str] = None,
    use_onedrive_root: bool = False,
) -> Optional[str]:
    """Resolve a file path from config, handling both absolute and OneDrive relative paths.
    
    Args:
        config_path: Path from config (can be None, absolute path, or relative OneDrive path)
        fx_config: FXAnalysisConfig instance
        default_onedrive_location: If path is relative and this is set, prepend this OneDrive location
        use_onedrive_root: If True, resolve relative to OneDrive root instead of a subdirectory
        
    Returns:
        Resolved absolute path, or None if config_path is None
    """
    if config_path is None:
        return None
    
    # If it's an absolute path, return as-is
    if os.path.isabs(config_path):
        return config_path
    
    # Otherwise, it's a relative OneDrive path - resolve it
    if use_onedrive_root:
        # Resolve relative to OneDrive root (e.g., for _meta/ files)
        base_path = fx_config.od_root
    elif default_onedrive_location:
        # Use the specified OneDrive location as base
        base_path = fx_config.get_absolute_path(default_onedrive_location)
    else:
        # Use raw_data as default base
        base_path = fx_config.get_absolute_path("raw_data")
    
    # Join the base path with the relative path
    return os.path.join(base_path, config_path.replace("/", os.sep))


def _resolve_target_date(
    model_returns_df: pd.DataFrame,
    final_positions_df: pd.DataFrame,
    user_date: Optional[str] = None,
) -> str:
    """Resolve target date: intersection when not supplied, validate when supplied.
    
    Args:
        model_returns_df: Model returns DataFrame
        final_positions_df: Final positions DataFrame
        user_date: User-supplied date string (YYYY-MM-DD) or None
        
    Returns:
        Target date string (YYYY-MM-DD)
        
    Raises:
        typer.Exit: If user-supplied date is missing with helpful error message
    """
    # Ensure date columns are datetime
    model_returns_df = model_returns_df.copy()
    final_positions_df = final_positions_df.copy()
    
    model_returns_df["date"] = pd.to_datetime(model_returns_df["date"])
    final_positions_df["date"] = pd.to_datetime(final_positions_df["date"])
    
    # Get available dates
    dates_in_returns = set(model_returns_df["date"].dt.date)
    dates_in_positions = set(final_positions_df["date"].dt.date)
    intersection = sorted(dates_in_returns & dates_in_positions)
    
    if user_date is None:
        if not intersection:
            typer.echo(
                "Error: No common dates found between model returns and final positions.",
                err=True,
            )
            raise typer.Exit(code=1)
        # Use latest date from intersection
        target_date = intersection[-1].strftime("%Y-%m-%d")
        typer.echo(f"Using latest common date: {target_date}")
        return target_date
    
    # User supplied date - validate it exists
    user_date_dt = pd.to_datetime(user_date).date()
    
    if user_date_dt in intersection:
        return user_date
    
    # Date not found - find nearest dates
    if intersection:
        # Find nearest dates within ±5 days
        nearest = []
        for candidate in intersection:
            days_diff = abs((candidate - user_date_dt).days)
            if days_diff <= 5:
                nearest.append((days_diff, candidate))
        
        if nearest:
            nearest.sort()
            nearest_str = ", ".join(
                [d.strftime("%Y-%m-%d") for _, d in nearest[:5]]
            )
            typer.echo(
                f"Error: Date {user_date} not found in both datasets.\n"
                f"Nearest available dates (within ±5 days): {nearest_str}",
                err=True,
            )
        else:
            # No dates within ±5 days, show latest available
            latest = intersection[-1].strftime("%Y-%m-%d")
            earliest = intersection[0].strftime("%Y-%m-%d")
            typer.echo(
                f"Error: Date {user_date} not found in both datasets.\n"
                f"Available date range: {earliest} to {latest}",
                err=True,
            )
    else:
        typer.echo(
            "Error: No common dates found between model returns and final positions.",
            err=True,
        )
    
    raise typer.Exit(code=1)


def _load_allocations(path: str) -> pd.DataFrame:
    """Load allocations CSV.
    
    Args:
        path: Path to allocations CSV
        
    Returns:
        DataFrame with columns: model_id, strategy_name, risk_alloc
    """
    df = pd.read_csv(path)
    
    # Normalize column names (handle variations)
    col_map = {
        "model_id": ["model_id", "Model_ID", "MODEL_ID", "ID"],
        "strategy_name": ["strategy_name", "Strategy_Name", "STRATEGY_NAME", "Name"],
        "risk_alloc": ["risk_alloc", "Risk_Alloc", "RISK_ALLOC", "risk_alloc"],
    }
    
    for target, candidates in col_map.items():
        for candidate in candidates:
            if candidate in df.columns:
                if candidate != target:
                    df = df.rename(columns={candidate: target})
                break
        else:
            raise ValueError(
                f"Allocations CSV missing required column '{target}'. "
                f"Available columns: {list(df.columns)}"
            )
    
    return df[["model_id", "strategy_name", "risk_alloc"]]


def _load_model_returns(path: str) -> pd.DataFrame:
    """Load model returns CSV.
    
    Args:
        path: Path to model returns CSV
        
    Returns:
        DataFrame with columns: date, instrument, model_id, model_return
    """
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"])
    
    return df[["date", "instrument", "model_id", "model_return"]]


def _load_final_positions(path: str) -> pd.DataFrame:
    """Load final positions CSV.
    
    Supports multiple column name formats:
    - Standard: date, instrument, final_position
    - Derived format: ts_utc, symbol, target_exposure
    
    Args:
        path: Path to final positions CSV
        
    Returns:
        DataFrame with columns: date, instrument, final_position
    """
    df = pd.read_csv(path)
    
    # Handle column name variations
    # Map ts_utc -> date, symbol -> instrument, target_exposure -> final_position
    if "ts_utc" in df.columns:
        df["date"] = pd.to_datetime(df["ts_utc"]).dt.date
        df["date"] = pd.to_datetime(df["date"])
    elif "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
    else:
        raise ValueError(
            f"Final positions CSV missing date column. "
            f"Expected 'date' or 'ts_utc'. Found: {list(df.columns)}"
        )
    
    if "symbol" in df.columns:
        df["instrument"] = df["symbol"]
    elif "instrument" not in df.columns:
        raise ValueError(
            f"Final positions CSV missing instrument column. "
            f"Expected 'instrument' or 'symbol'. Found: {list(df.columns)}"
        )
    
    if "target_exposure" in df.columns:
        df["final_position"] = df["target_exposure"]
    elif "final_position" not in df.columns:
        raise ValueError(
            f"Final positions CSV missing final_position column. "
            f"Expected 'final_position' or 'target_exposure'. Found: {list(df.columns)}"
        )
    
    return df[["date", "instrument", "final_position"]]


@app.command()
def main(
    date: Optional[str] = typer.Option(
        None,
        "--date",
        "-d",
        help="Target date (YYYY-MM-DD). Default: latest common date",
    ),
    top_n: int = typer.Option(
        10,
        "--top-n",
        "-n",
        help="Number of top drivers to rank per instrument",
    ),
    allocations: Optional[Path] = typer.Option(
        None,
        "--allocations",
        "-a",
        help="Path to allocations CSV (default: from config or /mnt/data/Portfolio_Allocations_JH.csv)",
    ),
    model_returns: Optional[Path] = typer.Option(
        None,
        "--model-returns",
        "-r",
        help="Path to model returns CSV (default: from config)",
    ),
    final_positions: Optional[Path] = typer.Option(
        None,
        "--final-positions",
        "-p",
        help="Path to final positions CSV (default: from config)",
    ),
    config: Path = typer.Option(
        "fx_analysis_config.yaml",
        "--config",
        "-c",
        exists=True,
        readable=True,
        help="Path to YAML config file",
    ),
    output_dir: Path = typer.Option(
        "outputs/",
        "--output-dir",
        "-o",
        help="Output directory for CSVs",
    ),
) -> None:
    """Compute per-instrument model drivers for attribution analysis."""
    # Load configuration
    fx_config = get_config(str(config))
    
    # Resolve file paths (CLI args take precedence over config)
    # Handle nested structure: analysis_inputs.onedrive.*
    analysis_inputs = fx_config.config.get("analysis_inputs", {})
    onedrive_inputs = analysis_inputs.get("onedrive", {})
    
    if allocations is None:
        # Try nested onedrive structure first, then flat structure, then default
        if "portfolio_allocations" in onedrive_inputs:
            # Relative OneDrive path - _meta/ is at OneDrive root level
            allocations_path = _resolve_path(
                onedrive_inputs["portfolio_allocations"],
                fx_config,
                use_onedrive_root=True,  # _meta/ is at root, not in a subdirectory
            )
        elif "portfolio_allocations" in analysis_inputs:
            # Absolute path or legacy flat structure
            allocations_path = _resolve_path(
                analysis_inputs["portfolio_allocations"],
                fx_config,
            )
        else:
            # Fallback default
            allocations_path = "/mnt/data/Portfolio_Allocations_JH.csv"
    else:
        allocations_path = str(allocations)
    
    if model_returns is None:
        # Model returns are typically in processed_data
        if "model_returns_unscaled" in onedrive_inputs:
            model_returns_path = _resolve_path(
                onedrive_inputs["model_returns_unscaled"],
                fx_config,
                default_onedrive_location="processed_data",  # Model returns are in Processed
            )
        elif "model_returns_unscaled" in analysis_inputs:
            model_returns_path = _resolve_path(
                analysis_inputs["model_returns_unscaled"],
                fx_config,
                default_onedrive_location="processed_data",
            )
        else:
            typer.echo(
                "Error: --model-returns required or set analysis_inputs.onedrive.model_returns_unscaled in config",
                err=True,
            )
            raise typer.Exit(code=1)
    else:
        model_returns_path = str(model_returns)
    
    if final_positions is None:
        # Final positions can be in various locations (auth/, processed_data, etc.)
        # Use OneDrive root as base since paths like auth/ are at root level
        if "final_positions" in onedrive_inputs:
            final_positions_path = _resolve_path(
                onedrive_inputs["final_positions"],
                fx_config,
                use_onedrive_root=True,  # auth/ is at root, not in subdirectory
            )
        elif "final_positions" in analysis_inputs:
            # Try as absolute path first, then relative to processed_data
            final_positions_path = _resolve_path(
                analysis_inputs["final_positions"],
                fx_config,
                default_onedrive_location="processed_data",
            )
        else:
            typer.echo(
                "Error: --final-positions required or set analysis_inputs.onedrive.final_positions in config",
                err=True,
            )
            raise typer.Exit(code=1)
    else:
        final_positions_path = str(final_positions)
    
    # Load data
    typer.echo(f"Loading allocations from: {allocations_path}")
    allocations_df = _load_allocations(allocations_path)
    
    typer.echo(f"Loading model returns from: {model_returns_path}")
    model_returns_df = _load_model_returns(model_returns_path)
    
    typer.echo(f"Loading final positions from: {final_positions_path}")
    final_positions_df = _load_final_positions(final_positions_path)
    
    # Resolve target date
    target_date = _resolve_target_date(model_returns_df, final_positions_df, date)
    
    # Compute drivers
    typer.echo(f"Computing per-instrument drivers for date: {target_date}")
    results = compute_per_instrument_drivers(
        allocations_df=allocations_df,
        model_returns_df=model_returns_df,
        final_positions_df=final_positions_df,
        target_date=target_date,
        top_n=top_n,
        scaling_method="dummy_constant",
    )
    
    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Write outputs
    date_str = target_date.replace("-", "")
    
    # Ranked drivers
    ranked_path = output_dir / f"ranked_drivers_{date_str}.csv"
    results["ranked_drivers"].to_csv(ranked_path, index=False)
    typer.echo(f"Wrote ranked drivers: {ranked_path} ({len(results['ranked_drivers'])} rows)")
    
    # Instrument summary
    summary_path = output_dir / f"instrument_summary_{date_str}.csv"
    results["instrument_summary"].to_csv(summary_path, index=False)
    typer.echo(f"Wrote instrument summary: {summary_path} ({len(results['instrument_summary'])} rows)")
    
    # Diagnostics
    for key, df in results.items():
        if key.startswith("diagnostics_"):
            diag_path = output_dir / f"{key}_{date_str}.csv"
            df.to_csv(diag_path, index=False)
            typer.echo(f"Wrote {key}: {diag_path} ({len(df)} rows)")
    
    # Create run metadata
    metadata = {
        "date_used": target_date,
        "top_n": top_n,
        "rows_processed": {
            "ranked_drivers": len(results["ranked_drivers"]),
            "instrument_summary": len(results["instrument_summary"]),
            "diagnostics_missing_allocations": len(results["diagnostics_missing_allocations"]),
            "diagnostics_missing_returns": len(results["diagnostics_missing_returns"]),
            "diagnostics_missing_instruments": len(results["diagnostics_missing_instruments"]),
            "diagnostics_top_residuals": len(results["diagnostics_top_residuals"]),
        },
        "missing_coverage": {
            "models_in_returns_not_allocations": len(results["diagnostics_missing_allocations"]),
            "models_in_allocations_not_returns": len(results["diagnostics_missing_returns"]),
            "instruments_in_positions_not_returns": len(results["diagnostics_missing_instruments"]),
        },
        "top_residual_instruments": (
            results["diagnostics_top_residuals"]
            .nlargest(10, "residual", key=lambda x: x.abs())[["instrument", "residual"]]
            .to_dict("records")
            if len(results["diagnostics_top_residuals"]) > 0
            else []
        ),
    }
    
    metadata_path = output_dir / f"run_metadata_{date_str}.json"
    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2, default=str)
    typer.echo(f"Wrote run metadata: {metadata_path}")
    
    # Print console summary
    typer.echo("\n" + "=" * 60)
    typer.echo("Summary")
    typer.echo("=" * 60)
    typer.echo(f"Date used: {target_date}")
    typer.echo(f"Ranked drivers: {len(results['ranked_drivers'])} rows")
    typer.echo(f"Instruments: {len(results['instrument_summary'])}")
    typer.echo(
        f"Missing allocations (models in returns but not allocations): "
        f"{len(results['diagnostics_missing_allocations'])}"
    )
    typer.echo(
        f"Missing returns (models in allocations but not returns): "
        f"{len(results['diagnostics_missing_returns'])}"
    )
    typer.echo(
        f"Missing instruments (in positions but not returns): "
        f"{len(results['diagnostics_missing_instruments'])}"
    )
    
    if len(results["diagnostics_top_residuals"]) > 0:
        typer.echo("\nTop residual instruments:")
        top_res = results["diagnostics_top_residuals"].head(5)
        for _, row in top_res.iterrows():
            typer.echo(
                f"  {row['instrument']}: residual = {row['residual']:.6f} "
                f"(pred={row['pred_final']:.6f}, final={row['final_position']:.6f})"
            )
    
    typer.echo("=" * 60)


if __name__ == "__main__":
    app()
