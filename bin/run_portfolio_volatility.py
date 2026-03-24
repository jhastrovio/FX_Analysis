#!/usr/bin/env python
"""
On-demand portfolio return construction and volatility analysis.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd
import typer

from lib.config_manager import get_config
from lib.onedrive_storage import OneDriveStorage
from lib.portfolio.construction import (
    compute_model_vol_42d,
    compute_portfolio_returns,
    load_model_returns,
    load_portfolio_allocations,
    master_matrix_to_model_returns,
    risk_alloc_to_weights,
)
from lib.risk.volatility import volatility_summary
from lib.summary_statistics import load_master_matrix

app = typer.Typer(add_completion=False, help="Construct portfolio returns from risk allocations and model returns")


@app.command()
def main(
    allocations: Path = typer.Option(
        ...,
        "--allocations",
        "-a",
        exists=True,
        readable=True,
        help="Path to portfolio allocations workbook or CSV.",
    ),
    portfolio_id: Optional[str] = typer.Option(
        None,
        "--portfolio-id",
        help="Portfolio identifier to analyze. Required when the allocation source contains multiple portfolios.",
    ),
    model_returns: Optional[Path] = typer.Option(
        None,
        "--model-returns",
        "-m",
        help="Optional model returns CSV. If omitted, use the existing master_matrix analysis artifact.",
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
    """Construct portfolio returns on-demand and report annualized vol metrics."""
    allocations_df = load_portfolio_allocations(str(allocations), portfolio_id=portfolio_id)
    selected_portfolio_id = allocations_df["portfolio_id"].iloc[0]

    if model_returns is None:
        config_obj = get_config(str(config))
        storage = OneDriveStorage()
        master_matrix, _ = load_master_matrix(storage, config_obj, test=False)
        model_returns_df = master_matrix_to_model_returns(master_matrix)
    else:
        model_returns_df = load_model_returns(str(model_returns))

    model_vol_df = compute_model_vol_42d(model_returns_df)
    weights_df = risk_alloc_to_weights(allocations_df, model_vol_df)
    portfolio_returns_df = compute_portfolio_returns(model_returns_df, weights_df)

    portfolio_vol_summary_df = pd.DataFrame(
        [
            {"metric": metric, "value": value}
            for metric, value in volatility_summary(portfolio_returns_df["portfolio_return"]).items()
        ]
    )

    weights_view = weights_df[["model_id", "risk_alloc", "vol_42d", "weight"]].copy()

    typer.echo(f"Portfolio: {selected_portfolio_id}")
    typer.echo("\nDerived Model Weights")
    typer.echo(weights_view.to_string(index=False))
    typer.echo("\nPortfolio Volatility Summary")
    typer.echo(portfolio_vol_summary_df.to_string(index=False))


if __name__ == "__main__":
    app()
