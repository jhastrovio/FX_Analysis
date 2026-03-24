#!/usr/bin/env python
"""
On-demand annualized volatility analysis for model, currency, and portfolio returns.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd
import typer

from lib.config_manager import get_config
from lib.onedrive_storage import OneDriveStorage
from lib.summary_statistics import load_master_matrix
from lib.volatility_analysis import summarize_long_returns, summarize_wide_returns

app = typer.Typer(add_completion=False, help="On-demand volatility analysis from daily returns")


def _normalize_columns(df: pd.DataFrame, mapping: dict[str, list[str]], name: str) -> pd.DataFrame:
    result = df.copy()
    for target, candidates in mapping.items():
        for candidate in candidates:
            if candidate in result.columns:
                if candidate != target:
                    result = result.rename(columns={candidate: target})
                break
        else:
            raise ValueError(
                f"{name} missing required column '{target}'. Available columns: {list(result.columns)}"
            )
    return result


def _load_long_returns(
    path: str,
    name: str,
    series_candidates: list[str],
    return_candidates: list[str],
    default_series_id: Optional[str] = None,
) -> pd.DataFrame:
    df = pd.read_csv(path)
    df = _normalize_columns(
        df,
        {
            "date": ["date", "Date", "DATE", "ts_utc", "trade_date"],
            "daily_return": return_candidates,
        },
        name,
    )

    for candidate in series_candidates:
        if candidate in df.columns:
            df = df.rename(columns={candidate: "series_id"})
            break
    else:
        if default_series_id is None:
            raise ValueError(
                f"{name} missing series id column. Expected one of {series_candidates}. "
                f"Available columns: {list(df.columns)}"
            )
        df["series_id"] = default_series_id

    df["date"] = pd.to_datetime(df["date"])
    df["daily_return"] = pd.to_numeric(df["daily_return"], errors="coerce")
    return df[["date", "series_id", "daily_return"]]


@app.command()
def main(
    config: Path = typer.Option(
        "fx_analysis_config.yaml",
        "--config",
        "-c",
        exists=True,
        readable=True,
        help="Path to YAML config file",
    ),
    model_returns: Optional[Path] = typer.Option(
        None,
        "--model-returns",
        help="Optional model returns CSV. If omitted, use the existing master_matrix.",
    ),
    currency_returns: Optional[Path] = typer.Option(
        None,
        "--currency-returns",
        help="Optional currency returns CSV with date/instrument/return-style columns.",
    ),
    portfolio_returns: Optional[Path] = typer.Option(
        None,
        "--portfolio-returns",
        help="Optional portfolio returns CSV with date/portfolio/return-style columns.",
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Optional output CSV path. Default: outputs/analysis/volatility_summary.csv",
    ),
    preview: bool = typer.Option(
        False,
        "--preview/--no-preview",
        help="Print the summary table without writing it.",
    ),
) -> None:
    """Build a simple on-demand volatility summary table."""
    config_obj = get_config(str(config))
    tables: list[pd.DataFrame] = []

    if model_returns is None:
        storage = OneDriveStorage()
        master_matrix, _ = load_master_matrix(storage, config_obj, test=False)
        tables.append(summarize_wide_returns(master_matrix, series_type="model"))
    else:
        model_returns_df = _load_long_returns(
            str(model_returns),
            name="Model returns CSV",
            series_candidates=["model_id", "model_name", "model", "series_id"],
            return_candidates=["model_return", "return", "daily_return"],
        )
        tables.append(summarize_long_returns(model_returns_df, series_type="model"))

    if currency_returns is not None:
        currency_returns_df = _load_long_returns(
            str(currency_returns),
            name="Currency returns CSV",
            series_candidates=["instrument", "currency", "symbol", "series_id"],
            return_candidates=["currency_return", "return", "daily_return"],
        )
        tables.append(summarize_long_returns(currency_returns_df, series_type="currency"))

    if portfolio_returns is not None:
        portfolio_returns_df = _load_long_returns(
            str(portfolio_returns),
            name="Portfolio returns CSV",
            series_candidates=["portfolio_id", "portfolio_name", "portfolio", "series_id"],
            return_candidates=["portfolio_return", "return", "daily_return"],
            default_series_id="portfolio",
        )
        tables.append(summarize_long_returns(portfolio_returns_df, series_type="portfolio"))

    summary_df = pd.concat(tables, ignore_index=True)
    summary_df = summary_df[["series_type", "series_id", "vol_all", "vol_1y", "vol_42d"]]
    summary_df = summary_df.sort_values(["series_type", "series_id"]).reset_index(drop=True)

    typer.echo(summary_df.to_string(index=False))

    if not preview:
        output_path = output or Path("outputs/analysis/volatility_summary.csv")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        summary_df.to_csv(output_path, index=False)
        typer.echo(f"\nWrote volatility summary: {output_path}")


if __name__ == "__main__":
    app()
