#!/usr/bin/env python3
"""
Run model summary validation against a model signal history CSV and a summary CSV.
"""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Optional

import typer

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from lib.model_summary_validation import (
    DEFAULT_REL_TOLERANCE,
    DEFAULT_TOLERANCES,
    build_validation_artifacts,
    write_comparison_csv,
    write_validation_report,
)

app = typer.Typer(add_completion=False, help="Validate model summary metrics from a model signal history CSV.")


@app.command()
def main(
    model_id: int = typer.Option(..., "--model-id", help="Model identifier to validate."),
    signals_csv: Path = typer.Option(..., "--signals-csv", exists=True, readable=True, help="Path to model signal history CSV."),
    summary_csv: Path = typer.Option(..., "--summary-csv", exists=True, readable=True, help="Path to precomputed summary CSV."),
    return_mode: str = typer.Option("diff", "--return-mode", help="Daily return derivation: 'diff' for diff(return)/100 or 'raw' for return/100."),
    output_xlsx: Optional[Path] = typer.Option(None, "--output-xlsx", help="Optional output XLSX path for the validation artifact."),
    output_csv: Optional[Path] = typer.Option(None, "--output-csv", help="Optional output CSV path for the comparison table."),
    tolerance_main: float = typer.Option(DEFAULT_TOLERANCES["Annual. Return (%)"], "--tolerance-main", help="Absolute tolerance for return/vol/sharpe/sortino/correlation metrics."),
    tolerance_hit: float = typer.Option(DEFAULT_TOLERANCES["Hit* Ratio (%)"], "--tolerance-hit", help="Absolute tolerance for hit ratio."),
    tolerance_drawdown: float = typer.Option(DEFAULT_TOLERANCES["4% DD** Quantile (%)"], "--tolerance-drawdown", help="Absolute tolerance for drawdown quantile."),
    rel_tolerance: float = typer.Option(DEFAULT_REL_TOLERANCE, "--rel-tolerance", help="Relative tolerance (0-1). A metric passes if EITHER abs or rel tolerance is met."),
    sortino_mode: str = typer.Option("negative_only", "--sortino-mode", help="Sortino downside deviation: 'negative_only' or 'full_series'."),
    hit_mode: str = typer.Option("strict_positive", "--hit-mode", help="Hit ratio counting: 'strict_positive', 'non_negative', or 'exclude_zeros'."),
) -> None:
    if output_xlsx is None:
        output_xlsx = BASE_DIR / "output" / "validation" / f"model_{model_id}_summary_validation.xlsx"
    if output_csv is None:
        output_csv = BASE_DIR / "output" / "validation" / f"model_{model_id}_summary_validation_comparison.csv"

    tolerances = {
        "Annual. Return (%)": tolerance_main,
        "Annual. Vol. (%)": tolerance_main,
        "Sharpe Ratio": tolerance_main,
        "Sortino Ratio": tolerance_main,
        "SPX Correl. (wkly)": tolerance_main,
        "US10Y Corr. (wkly)": tolerance_main,
        "Hit* Ratio (%)": tolerance_hit,
        "4% DD** Quantile (%)": tolerance_drawdown,
    }

    artifacts = build_validation_artifacts(
        signals_csv=signals_csv,
        summary_csv=summary_csv,
        model_id=model_id,
        tolerances=tolerances,
        rel_tolerance=rel_tolerance,
        return_mode=return_mode,
        sortino_mode=sortino_mode,
        hit_mode=hit_mode,
    )
    xlsx_path = write_validation_report(output_xlsx, artifacts)
    csv_path = write_comparison_csv(output_csv, artifacts.comparison_df)

    typer.echo(f"XLSX report: {xlsx_path}")
    typer.echo(f"Comparison CSV: {csv_path}")
    typer.echo(f"Return derivation mode: {return_mode}")
    typer.echo(f"Supported metric passes: {(artifacts.comparison_df['Status'] == 'pass').sum()}")
    typer.echo(f"Supported metric failures: {(artifacts.comparison_df['Status'] == 'fail').sum()}")
    typer.echo(f"Unsupported metrics: {(artifacts.comparison_df['Status'] == 'unsupported').sum()}")


if __name__ == "__main__":
    app()
