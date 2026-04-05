#!/usr/bin/env python
"""
Build a single-date modeled currency exposure detail table.
"""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Optional

import typer

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from lib.config_manager import get_config
from lib.portfolio.modeled_currency_exposure import (
    build_modeled_currency_exposure_detail,
    discover_latest_model_files,
    load_allocations_with_strategy,
    load_model_histories,
    resolve_target_date,
)

app = typer.Typer(add_completion=False, help="Build modeled currency exposure detail for one portfolio/date")


@app.command()
def main(
    portfolio_id: str = typer.Option(
        ...,
        "--portfolio-id",
        help="Portfolio identifier from the allocations workbook.",
    ),
    date: Optional[str] = typer.Option(
        None,
        "--date",
        "-d",
        help="Target date (YYYY-MM-DD). Default: latest common date across selected models.",
    ),
    allocations: Optional[Path] = typer.Option(
        None,
        "--allocations",
        "-a",
        exists=True,
        readable=True,
        help="Optional path to portfolio allocations workbook or CSV.",
    ),
    model_data_dir: Optional[Path] = typer.Option(
        None,
        "--model-data-dir",
        exists=True,
        file_okay=False,
        readable=True,
        help="Optional directory containing models_signals_systemacro CSV files.",
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Optional output CSV path. Default: outputs/analysis/modeled_currency_exposure_detail_<portfolio>_<date>.csv",
    ),
    config: Path = typer.Option(
        "fx_analysis_config.yaml",
        "--config",
        "-c",
        exists=True,
        readable=True,
        help="Path to YAML config file.",
    ),
) -> None:
    """Build the modeled currency exposure detail output for one portfolio/date."""
    config_obj = get_config(str(config))
    analysis_root = Path(config_obj.od_root)
    allocations_path = allocations or (analysis_root / "_meta" / "Portfolio_Allocations.xlsx")
    models_path = model_data_dir or (analysis_root / "clean" / "models_signals_systemacro")

    allocations_df = load_allocations_with_strategy(str(allocations_path), portfolio_id=portfolio_id)
    model_files = discover_latest_model_files(allocations_df["model_id"].tolist(), str(models_path))
    model_histories = load_model_histories(model_files)
    target_date = resolve_target_date(model_histories, requested_date=date)

    detail_df = build_modeled_currency_exposure_detail(
        allocations_df=allocations_df,
        model_histories=model_histories,
        target_date=target_date,
    )

    output_path = output or Path(
        f"outputs/analysis/modeled_currency_exposure_detail_{portfolio_id}_{target_date.strftime('%Y%m%d')}.csv"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    detail_df.to_csv(output_path, index=False)

    typer.echo(f"Portfolio: {portfolio_id}")
    typer.echo(f"Date: {target_date.strftime('%Y-%m-%d')}")
    typer.echo(f"Models with exposure rows: {detail_df['model_id'].nunique()}")
    typer.echo(f"Exposure rows written: {len(detail_df)}")
    typer.echo(f"Output: {output_path}")


if __name__ == "__main__":
    app()
