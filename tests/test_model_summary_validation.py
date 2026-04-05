import math
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from lib.model_summary_validation import (
    TRADING_DAYS,
    _annualized_return,
    _annualized_return_cagr,
    _annualized_vol,
    _hit_ratio,
    _sharpe_ratio,
    _sortino_ratio,
    build_validation_artifacts,
    compare_to_summary,
    compute_validation_windows,
    load_model_validation_inputs,
    recompute_summary_metrics,
)

# 10 synthetic daily returns (decimal, not percentage)
SYNTH_DAILY = pd.Series([0.001, -0.002, 0.003, 0.0, -0.001, 0.002, 0.001, -0.003, 0.002, 0.001])


class ModelSummaryValidationTests(unittest.TestCase):
    def test_load_model_validation_inputs_derives_daily_returns_from_cumulative_return(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            signals_path = Path(tmpdir) / "signals.csv"
            summary_path = Path(tmpdir) / "summary.csv"
            pd.DataFrame(
                {
                    "date": ["2026-01-01", "2026-01-02", "2026-01-03"],
                    "ID": [297, 297, 297],
                    "return": [None, 0.0, 1.5],
                    "return_ex_carry": [None, 0.0, 1.4],
                    "SPX": [100.0, 101.0, 102.0],
                    "US10Y": [4.0, 4.1, 4.2],
                }
            ).to_csv(signals_path, index=False)
            pd.DataFrame({"Evaluation Period": ["since 2000"]}).to_csv(summary_path, index=False)

            signals_df, _ = load_model_validation_inputs(signals_path, summary_path, model_id=297)
            self.assertTrue(math.isnan(signals_df.loc[0, "daily_return"]))
            self.assertTrue(math.isnan(signals_df.loc[1, "daily_return"]))
            self.assertAlmostEqual(signals_df.loc[2, "daily_return"], 0.015)

    def test_load_model_validation_inputs_supports_raw_return_mode(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            signals_path = Path(tmpdir) / "signals.csv"
            summary_path = Path(tmpdir) / "summary.csv"
            pd.DataFrame(
                {
                    "date": ["2026-01-01", "2026-01-02"],
                    "ID": [297, 297],
                    "return": [1.5, -0.5],
                    "return_ex_carry": [1.4, -0.6],
                    "SPX": [100.0, 101.0],
                    "US10Y": [4.0, 4.1],
                }
            ).to_csv(signals_path, index=False)
            pd.DataFrame({"Evaluation Period": ["since 2000"]}).to_csv(summary_path, index=False)

            signals_df, _ = load_model_validation_inputs(signals_path, summary_path, model_id=297, return_mode="raw")
            self.assertAlmostEqual(signals_df.loc[0, "daily_return"], 0.015)
            self.assertAlmostEqual(signals_df.loc[1, "daily_return"], -0.005)

    def test_compute_validation_windows_uses_expected_start_dates(self):
        signals_df = pd.DataFrame(
            {
                "date": pd.bdate_range("2026-01-01", periods=50),
                "daily_return": [0.01] * 50,
            }
        )
        windows_df = compute_validation_windows(signals_df)
        self.assertEqual(windows_df.loc[0, "Evaluation Period"], "last 2 months")
        self.assertEqual(windows_df.loc[0, "observation_count"], 42)
        self.assertEqual(windows_df.loc[0, "start_date"], signals_df.iloc[-42]["date"].date().isoformat())
        self.assertEqual(windows_df.loc[2, "start_date"], "2000-01-01")
        self.assertEqual(windows_df.loc[3, "start_date"], "2010-01-01")
        self.assertEqual(windows_df.loc[4, "start_date"], "2021-01-01")

    def test_compare_to_summary_marks_exact_matches_as_pass(self):
        recomputed_df = pd.DataFrame(
            {
                "Evaluation Period": ["since 2000"],
                "Annual. Return (%)": [1.0],
                "Annual. Vol. (%)": [2.0],
                "Sharpe Ratio": [0.5],
                "Sortino Ratio": [0.7],
                "Hit* Ratio (%)": [51.0],
                "4% DD** Quantile (%)": [float("nan")],
                "SPX Correl. (wkly)": [0.1],
                "US10Y Corr. (wkly)": [-0.2],
            }
        )
        summary_df = pd.DataFrame(
            {
                "Evaluation Period": ["since 2000"],
                "Annual. Return (%)": [1.0],
                "Annual. Vol. (%)": [2.0],
                "Sharpe Ratio": [0.5],
                "Sortino Ratio": [0.7],
                "Hit* Ratio (%)": [51.0],
                "4% DD** Quantile (%)": [-3.0],
                "SPX Correl. (wkly)": [0.1],
                "US10Y Corr. (wkly)": [-0.2],
            }
        )
        comparison_df = compare_to_summary(recomputed_df, summary_df)
        supported = comparison_df[
            (comparison_df["Evaluation Period"] == "since 2000")
            & (comparison_df["Metric"] != "4% DD** Quantile (%)")
        ]
        self.assertTrue((supported["Status"] == "pass").all())
        unsupported = comparison_df[
            (comparison_df["Evaluation Period"] == "since 2000")
            & (comparison_df["Metric"] == "4% DD** Quantile (%)")
        ]
        self.assertEqual(unsupported.iloc[0]["Status"], "unsupported")

    def test_compare_to_summary_marks_large_delta_as_fail(self):
        recomputed_df = pd.DataFrame(
            {
                "Evaluation Period": ["since 2010"],
                "Annual. Return (%)": [1.0],
                "Annual. Vol. (%)": [2.0],
                "Sharpe Ratio": [0.5],
                "Sortino Ratio": [0.7],
                "Hit* Ratio (%)": [51.0],
                "4% DD** Quantile (%)": [float("nan")],
                "SPX Correl. (wkly)": [0.1],
                "US10Y Corr. (wkly)": [-0.2],
            }
        )
        summary_df = pd.DataFrame(
            {
                "Evaluation Period": ["since 2010"],
                "Annual. Return (%)": [5.0],
                "Annual. Vol. (%)": [2.0],
                "Sharpe Ratio": [0.5],
                "Sortino Ratio": [0.7],
                "Hit* Ratio (%)": [51.0],
                "4% DD** Quantile (%)": [-3.0],
                "SPX Correl. (wkly)": [0.1],
                "US10Y Corr. (wkly)": [-0.2],
            }
        )
        comparison_df = compare_to_summary(recomputed_df, summary_df)
        failed = comparison_df[
            (comparison_df["Evaluation Period"] == "since 2010")
            & (comparison_df["Metric"] == "Annual. Return (%)")
        ]
        self.assertEqual(failed.iloc[0]["Status"], "fail")

    def test_recompute_summary_metrics_returns_expected_columns(self):
        signals_df = pd.DataFrame(
            {
                "date": pd.to_datetime(["2026-01-02", "2026-01-03", "2026-01-09", "2026-01-10"]),
                "daily_return": [0.01, -0.02, 0.03, 0.01],
                "SPX": [100.0, 101.0, 102.0, 103.0],
                "US10Y": [4.0, 4.1, 4.2, 4.1],
            }
        )
        windows_df = pd.DataFrame(
            {
                "Evaluation Period": ["since 2000"],
                "start_date": ["2026-01-02"],
                "end_date": ["2026-01-10"],
                "window_method": ["from first valid daily return"],
                "observation_count": [4],
            }
        )
        result = recompute_summary_metrics(signals_df, windows_df)
        self.assertIn("Annual. Return (%)", result.columns)
        self.assertIn("Annual Return CAGR (%)", result.columns)
        self.assertIn("SPX Correl. (wkly)", result.columns)
        self.assertEqual(result.iloc[0]["Evaluation Period"], "since 2000")

    def test_annual_return_primary_metric_is_arithmetic(self):
        signals_df = pd.DataFrame(
            {
                "date": pd.to_datetime(["2026-01-02", "2026-01-03", "2026-01-04"]),
                "daily_return": [0.01, 0.02, -0.01],
                "daily_return_method": ["diff", "diff", "diff"],
                "SPX": [100.0, 101.0, 102.0],
                "US10Y": [4.0, 4.1, 4.2],
            }
        )
        windows_df = pd.DataFrame(
            {
                "Evaluation Period": ["since 2000"],
                "start_date": ["2026-01-02"],
                "end_date": ["2026-01-04"],
                "window_method": ["from first valid daily return"],
                "observation_count": [3],
            }
        )
        result = recompute_summary_metrics(signals_df, windows_df)
        expected_arithmetic = ((0.01 + 0.02 - 0.01) / 3.0) * 252 * 100
        self.assertAlmostEqual(result.iloc[0]["Annual. Return (%)"], expected_arithmetic)

    def test_build_validation_artifacts_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            signals_path = Path(tmpdir) / "signals.csv"
            summary_path = Path(tmpdir) / "summary.csv"
            signals_df = pd.DataFrame(
                {
                    "date": pd.date_range("2025-01-01", periods=320, freq="B"),
                    "ID": [297] * 320,
                    "return": [float(i) / 10.0 for i in range(320)],
                    "return_ex_carry": [float(i) / 10.0 for i in range(320)],
                    "SPX": [1000.0 + i for i in range(320)],
                    "US10Y": [4.0 + (i / 1000.0) for i in range(320)],
                }
            )
            signals_df.loc[0, "return"] = None
            signals_df.loc[0, "return_ex_carry"] = None
            signals_df.to_csv(signals_path, index=False)

            summary_df = pd.DataFrame(
                {
                    "Evaluation Period": ["last 2 months", "last year", "since 2000", "since 2010", "since 2021"],
                    "Annual. Return (%)": [1.0, 1.0, 1.0, 1.0, 1.0],
                    "Annual. Vol. (%)": [1.0, 1.0, 1.0, 1.0, 1.0],
                    "Sharpe Ratio": [1.0, 1.0, 1.0, 1.0, 1.0],
                    "Sortino Ratio": [1.0, 1.0, 1.0, 1.0, 1.0],
                    "Hit* Ratio (%)": [50.0, 50.0, 50.0, 50.0, 50.0],
                    "4% DD** Quantile (%)": [-1.0, -1.0, -1.0, -1.0, -1.0],
                    "SPX Correl. (wkly)": [0.0, 0.0, 0.0, 0.0, 0.0],
                    "US10Y Corr. (wkly)": [0.0, 0.0, 0.0, 0.0, 0.0],
                }
            )
            summary_df.to_csv(summary_path, index=False)

            artifacts = build_validation_artifacts(signals_path, summary_path, model_id=297)
            self.assertEqual(artifacts.windows_df["Evaluation Period"].tolist(), ["last 2 months", "last year", "since 2000", "since 2010", "since 2021"])
            self.assertEqual(sorted(artifacts.summary_df["Evaluation Period"].tolist()), sorted(["last 2 months", "last year", "since 2000", "since 2010", "since 2021"]))
            self.assertFalse(artifacts.comparison_df.empty)


class TestAnnualizedReturn(unittest.TestCase):
    def test_basic(self):
        expected = float(SYNTH_DAILY.mean() * TRADING_DAYS * 100)
        self.assertAlmostEqual(_annualized_return(SYNTH_DAILY), expected, places=8)

    def test_empty(self):
        self.assertTrue(math.isnan(_annualized_return(pd.Series(dtype=float))))


class TestAnnualizedReturnCAGR(unittest.TestCase):
    def test_basic(self):
        cumulative = (1 + SYNTH_DAILY).prod()
        expected = float((cumulative ** (TRADING_DAYS / len(SYNTH_DAILY)) - 1) * 100)
        self.assertAlmostEqual(_annualized_return_cagr(SYNTH_DAILY), expected, places=8)


class TestAnnualizedVol(unittest.TestCase):
    def test_basic(self):
        expected = float(SYNTH_DAILY.std(ddof=1) * np.sqrt(TRADING_DAYS) * 100)
        self.assertAlmostEqual(_annualized_vol(SYNTH_DAILY), expected, places=8)

    def test_single_observation(self):
        self.assertTrue(math.isnan(_annualized_vol(pd.Series([0.01]))))


class TestSharpeRatio(unittest.TestCase):
    def test_basic(self):
        expected = float(SYNTH_DAILY.mean() / SYNTH_DAILY.std(ddof=1) * np.sqrt(TRADING_DAYS))
        self.assertAlmostEqual(_sharpe_ratio(SYNTH_DAILY), expected, places=8)

    def test_zero_vol(self):
        self.assertTrue(math.isnan(_sharpe_ratio(pd.Series([0.0, 0.0, 0.0]))))


class TestSortinoRatio(unittest.TestCase):
    def test_negative_only_mode(self):
        negatives = SYNTH_DAILY[SYNTH_DAILY < 0]
        downside_std = negatives.std(ddof=1)
        expected = float(SYNTH_DAILY.mean() / downside_std * np.sqrt(TRADING_DAYS))
        self.assertAlmostEqual(_sortino_ratio(SYNTH_DAILY, "negative_only"), expected, places=8)

    def test_full_series_mode(self):
        downside_sq = np.minimum(SYNTH_DAILY, 0.0) ** 2
        downside_std = np.sqrt(downside_sq.mean())
        expected = float(SYNTH_DAILY.mean() / downside_std * np.sqrt(TRADING_DAYS))
        self.assertAlmostEqual(_sortino_ratio(SYNTH_DAILY, "full_series"), expected, places=8)

    def test_modes_differ(self):
        neg_only = _sortino_ratio(SYNTH_DAILY, "negative_only")
        full = _sortino_ratio(SYNTH_DAILY, "full_series")
        self.assertNotAlmostEqual(neg_only, full, places=4)

    def test_invalid_mode_raises(self):
        with self.assertRaises(ValueError):
            _sortino_ratio(SYNTH_DAILY, "bad_mode")


class TestHitRatio(unittest.TestCase):
    def test_strict_positive(self):
        # indices: 0(+), 1(-), 2(+), 3(0), 4(-), 5(+), 6(+), 7(-), 8(+), 9(+) => 6 hits / 10
        self.assertAlmostEqual(_hit_ratio(SYNTH_DAILY, "strict_positive"), 60.0)

    def test_non_negative(self):
        # 6 positive + 1 zero = 7 / 10
        self.assertAlmostEqual(_hit_ratio(SYNTH_DAILY, "non_negative"), 70.0)

    def test_exclude_zeros(self):
        # 6 positive / 9 non-zero
        self.assertAlmostEqual(_hit_ratio(SYNTH_DAILY, "exclude_zeros"), 6 / 9 * 100, places=8)

    def test_invalid_mode_raises(self):
        with self.assertRaises(ValueError):
            _hit_ratio(SYNTH_DAILY, "bad_mode")


class TestHybridTolerance(unittest.TestCase):
    def test_large_value_passes_on_relative_tolerance(self):
        recomputed = pd.DataFrame([{
            "Evaluation Period": "since 2000",
            "Annual. Return (%)": 33.25,
            "Annual. Vol. (%)": 6.94,
            "Sharpe Ratio": 4.79,
            "Sortino Ratio": 5.0,
            "Hit* Ratio (%)": 55.0,
            "4% DD** Quantile (%)": np.nan,
            "SPX Correl. (wkly)": 0.1,
            "US10Y Corr. (wkly)": 0.1,
        }])
        summary = pd.DataFrame([{
            "Evaluation Period": "since 2000",
            "Annual. Return (%)": 33.50,  # abs delta 0.25 > 0.02, rel delta ~0.75% < 1%
            "Annual. Vol. (%)": 6.94,
            "Sharpe Ratio": 4.79,
            "Sortino Ratio": 5.0,
            "Hit* Ratio (%)": 55.0,
            "4% DD** Quantile (%)": np.nan,
            "SPX Correl. (wkly)": 0.1,
            "US10Y Corr. (wkly)": 0.1,
        }])
        result = compare_to_summary(recomputed, summary, rel_tolerance=0.01)
        ret_row = result[
            (result["Evaluation Period"] == "since 2000") & (result["Metric"] == "Annual. Return (%)")
        ].iloc[0]
        # abs delta 0.25 > default abs tol 0.02, but rel delta ~0.75% < 1%
        self.assertEqual(ret_row["Status"], "pass")

    def test_small_value_fails_on_both(self):
        recomputed = pd.DataFrame([{
            "Evaluation Period": "since 2000",
            "Annual. Return (%)": 0.10,
            "Annual. Vol. (%)": 1.0,
            "Sharpe Ratio": 0.1,
            "Sortino Ratio": 0.1,
            "Hit* Ratio (%)": 50.0,
            "4% DD** Quantile (%)": np.nan,
            "SPX Correl. (wkly)": 0.1,
            "US10Y Corr. (wkly)": 0.1,
        }])
        summary = pd.DataFrame([{
            "Evaluation Period": "since 2000",
            "Annual. Return (%)": 0.50,  # abs 0.40 > 0.02, rel 80% > 1%
            "Annual. Vol. (%)": 1.0,
            "Sharpe Ratio": 0.1,
            "Sortino Ratio": 0.1,
            "Hit* Ratio (%)": 50.0,
            "4% DD** Quantile (%)": np.nan,
            "SPX Correl. (wkly)": 0.1,
            "US10Y Corr. (wkly)": 0.1,
        }])
        result = compare_to_summary(recomputed, summary, rel_tolerance=0.01)
        ret_row = result[
            (result["Evaluation Period"] == "since 2000") & (result["Metric"] == "Annual. Return (%)")
        ].iloc[0]
        self.assertEqual(ret_row["Status"], "fail")


if __name__ == "__main__":
    unittest.main()
