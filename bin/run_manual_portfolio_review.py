#!/usr/bin/env python3
"""Entry point for manual portfolio workbook review."""

from pathlib import Path
import sys

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from lib.portfolio.manual_analysis_summary import build_review, write_review_workbook


def main() -> None:
    allmodels_path = BASE_DIR / "outputs" / "manual_analysis" / "allmodels_20260326.xlsx"
    portfolio_path = BASE_DIR / "outputs" / "manual_analysis" / "10014_20260326.xlsx"
    output_path = BASE_DIR / "output" / "spreadsheet" / "portfolio_10014_review_20260326.xlsx"

    review = build_review(allmodels_path=allmodels_path, portfolio_path=portfolio_path)
    written_path = write_review_workbook(review=review, output_path=output_path)
    print(written_path)


if __name__ == "__main__":
    main()
