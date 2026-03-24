import math
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from bin.run_volatility_analysis import _load_long_returns
from lib.volatility_analysis import annualized_volatility, summarize_long_returns, summarize_volatility


class VolatilityAnalysisTests(unittest.TestCase):
    def test_annualized_volatility_uses_ddof_1(self):
        returns = pd.Series([0.01, -0.02, 0.03, 0.00])
        expected = returns.std(ddof=1) * math.sqrt(252)
        self.assertAlmostEqual(annualized_volatility(returns), expected)

    def test_window_returns_nan_when_not_enough_data(self):
        returns = pd.Series([0.01, 0.02, 0.03])
        self.assertTrue(math.isnan(annualized_volatility(returns, window=42)))

    def test_summarize_volatility_drops_nans(self):
        returns = pd.Series([0.01, None, -0.02, 0.03, None])
        summary = summarize_volatility(returns)
        expected = pd.Series([0.01, -0.02, 0.03]).std(ddof=1) * math.sqrt(252)
        self.assertAlmostEqual(summary["vol_all"], expected)

    def test_summarize_long_returns_builds_clean_table(self):
        df = pd.DataFrame(
            {
                "date": pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-01", "2026-01-02"]),
                "series_id": ["EUR", "EUR", "JPY", "JPY"],
                "daily_return": [0.01, -0.01, 0.02, -0.02],
            }
        )
        summary = summarize_long_returns(df, series_type="currency")
        self.assertEqual(summary.columns.tolist(), ["series_type", "series_id", "vol_all", "vol_1y", "vol_42d"])
        self.assertEqual(summary["series_type"].unique().tolist(), ["currency"])
        self.assertEqual(sorted(summary["series_id"].tolist()), ["EUR", "JPY"])

    def test_load_long_returns_supports_default_series_id(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "portfolio_returns.csv"
            pd.DataFrame(
                {
                    "date": ["2026-01-01", "2026-01-02"],
                    "portfolio_return": [0.01, -0.02],
                }
            ).to_csv(path, index=False)

            loaded = _load_long_returns(
                str(path),
                name="Portfolio returns CSV",
                series_candidates=["portfolio_id"],
                return_candidates=["portfolio_return"],
                default_series_id="portfolio",
            )
            self.assertEqual(loaded["series_id"].unique().tolist(), ["portfolio"])


if __name__ == "__main__":
    unittest.main()
