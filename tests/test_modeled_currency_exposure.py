import math
import tempfile
import unittest
from pathlib import Path

import pandas as pd
from openpyxl import Workbook

from lib.portfolio.modeled_currency_exposure import (
    build_modeled_currency_exposure_detail,
    discover_latest_model_files,
    extract_modeled_position_snapshot,
    load_allocations_with_strategy,
    load_model_histories,
    resolve_target_date,
)


def _make_model_file(path: Path, model_id: int, rows: list[dict]) -> None:
    pd.DataFrame(rows).to_csv(path, index=False)


class ModeledCurrencyExposureTests(unittest.TestCase):
    def test_load_allocations_with_strategy_reads_workbook(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "Portfolio_Allocations.xlsx"
            wb = Workbook()
            ws = wb.active
            ws.title = "INDEX"
            ws.append(["portfolio_name", "portfolio_id", "sheet_name"])
            ws.append(["Test", "10014", "Test_10014"])

            sheet = wb.create_sheet("Test_10014")
            sheet.append(["portfolio_id", "model_id", "strategy_name", "risk_alloc"])
            sheet.append(["10014", 1, "Model One", 0.6])
            sheet.append(["10014", 2, "Model Two", 0.4])
            wb.save(path)

            result = load_allocations_with_strategy(str(path), portfolio_id="10014")
            self.assertEqual(
                result.columns.tolist(),
                ["portfolio_id", "model_id", "strategy_name", "risk_alloc"],
            )
            self.assertEqual(result["strategy_name"].tolist(), ["Model One", "Model Two"])

    def test_extract_modeled_position_snapshot_includes_usd_and_excludes_context_columns(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "1_Model.csv"
            _make_model_file(
                path,
                1,
                [
                    {
                        "date": "2026-03-20",
                        "ID": 1,
                        "return": 0.01,
                        "SPX": 5000,
                        "US10Y": 4.2,
                        "AUD": 33.3,
                        "USD": -33.3,
                    }
                ],
            )
            histories = load_model_histories({1: path})
            snapshot = extract_modeled_position_snapshot(histories, pd.Timestamp("2026-03-20"))
            self.assertEqual(sorted(snapshot["currency"].tolist()), ["AUD", "USD"])

    def test_extract_modeled_position_snapshot_drops_zero_exposures(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "1_Model.csv"
            _make_model_file(
                path,
                1,
                [
                    {
                        "date": "2026-03-20",
                        "ID": 1,
                        "return": 0.01,
                        "AUD": 0.0,
                        "EUR": 12.5,
                        "USD": -12.5,
                    }
                ],
            )
            histories = load_model_histories({1: path})
            snapshot = extract_modeled_position_snapshot(histories, pd.Timestamp("2026-03-20"))
            self.assertEqual(sorted(snapshot["currency"].tolist()), ["EUR", "USD"])

    def test_resolve_target_date_uses_latest_common_date(self):
        histories = {
            1: pd.DataFrame({"date": pd.to_datetime(["2026-03-20", "2026-03-21", "2026-03-22"])}),
            2: pd.DataFrame({"date": pd.to_datetime(["2026-03-19", "2026-03-21", "2026-03-22"])}),
        }
        result = resolve_target_date(histories)
        self.assertEqual(result, pd.Timestamp("2026-03-22"))

    def test_resolve_target_date_raises_with_nearby_common_dates(self):
        histories = {
            1: pd.DataFrame({"date": pd.to_datetime(["2026-03-20", "2026-03-22"])}),
            2: pd.DataFrame({"date": pd.to_datetime(["2026-03-21", "2026-03-22"])}),
        }
        with self.assertRaisesRegex(ValueError, "Nearest common dates: 2026-03-22"):
            resolve_target_date(histories, requested_date="2026-03-21")

    def test_discover_latest_model_files_picks_latest_snapshot(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            _make_model_file(base / "1_Model-20260320.csv", 1, [{"date": "2026-03-20", "ID": 1, "return": 0.0}])
            _make_model_file(base / "1_Model-20260324.csv", 1, [{"date": "2026-03-24", "ID": 1, "return": 0.0}])
            result = discover_latest_model_files([1], str(base))
            self.assertTrue(str(result[1]).endswith("1_Model-20260324.csv"))

    def test_build_modeled_currency_exposure_detail_computes_expected_exposure(self):
        allocations_df = pd.DataFrame(
            {
                "portfolio_id": ["10014", "10014"],
                "model_id": [1, 2],
                "strategy_name": ["Model One", "Model Two"],
                "risk_alloc": [0.6, 0.4],
            }
        )
        dates = pd.date_range("2026-01-01", periods=42, freq="D")
        histories = {
            1: pd.DataFrame(
                {
                    "date": dates,
                    "model_id": [1] * len(dates),
                    "model_return": [0.01 + (i * 0.0001) for i in range(len(dates))],
                    "AUD": [20.0] * len(dates),
                    "USD": [-20.0] * len(dates),
                }
            ),
            2: pd.DataFrame(
                {
                    "date": dates,
                    "model_id": [2] * len(dates),
                    "model_return": [0.02 + (i * 0.0002) for i in range(len(dates))],
                    "AUD": [10.0] * len(dates),
                    "USD": [-10.0] * len(dates),
                }
            ),
        }

        result = build_modeled_currency_exposure_detail(
            allocations_df=allocations_df,
            model_histories=histories,
            target_date=pd.Timestamp("2026-02-11"),
        )
        self.assertEqual(
            result.columns.tolist(),
            [
                "date",
                "portfolio_id",
                "model_id",
                "strategy_name",
                "risk_alloc",
                "risk_alloc_norm",
                "vol_42d",
                "portfolio_wavg_vol",
                "vol_gap",
                "gap_scalar",
                "raw_weight",
                "final_weight",
                "raw_weight_sum",
                "currency",
                "model_position_pct",
                "modeled_exposure_usd_equiv",
            ],
        )
        detail_only = result[result["model_id"] != 0].copy()
        weights = detail_only[
            [
                "model_id",
                "risk_alloc_norm",
                "vol_42d",
                "portfolio_wavg_vol",
                "vol_gap",
                "gap_scalar",
                "raw_weight",
                "final_weight",
                "raw_weight_sum",
            ]
        ].drop_duplicates()
        self.assertAlmostEqual(
            weights.iloc[0]["vol_gap"],
            (weights.iloc[0]["portfolio_wavg_vol"] - weights.iloc[0]["vol_42d"]) / weights.iloc[0]["portfolio_wavg_vol"],
        )
        self.assertAlmostEqual(weights.iloc[0]["gap_scalar"], max(0.0, 1.0 + weights.iloc[0]["vol_gap"]))
        self.assertAlmostEqual(weights.iloc[0]["raw_weight"], weights.iloc[0]["risk_alloc_norm"] * weights.iloc[0]["gap_scalar"])
        self.assertAlmostEqual(weights.iloc[0]["raw_weight_sum"], weights["raw_weight"].sum())
        self.assertAlmostEqual(weights["final_weight"].sum(), 1.0)
        aud_row = detail_only[(detail_only["model_id"] == 1) & (detail_only["currency"] == "AUD")].iloc[0]
        self.assertAlmostEqual(
            aud_row["modeled_exposure_usd_equiv"],
            aud_row["final_weight"] * aud_row["model_position_pct"],
        )
        self.assertAlmostEqual(
            aud_row["raw_weight"],
            aud_row["risk_alloc_norm"] * aud_row["gap_scalar"],
        )
        self.assertAlmostEqual(
            aud_row["final_weight"],
            aud_row["raw_weight"] / aud_row["raw_weight_sum"],
        )
        total_aud_row = result[(result["model_id"] == 0) & (result["currency"] == "AUD")].iloc[0]
        self.assertEqual(total_aud_row["strategy_name"], "total")
        self.assertAlmostEqual(
            total_aud_row["modeled_exposure_usd_equiv"],
            detail_only.loc[detail_only["currency"] == "AUD", "modeled_exposure_usd_equiv"].sum(),
        )
        self.assertEqual(total_aud_row["model_position_pct"], 0.0)

    def test_gap_scalar_is_clipped_at_zero_for_extreme_vol(self):
        allocations_df = pd.DataFrame(
            {
                "portfolio_id": ["10014", "10014", "10014"],
                "model_id": [1, 2, 3],
                "strategy_name": ["Low Vol A", "Low Vol B", "High Vol"],
                "risk_alloc": [0.49, 0.49, 0.02],
            }
        )
        dates = pd.date_range("2026-01-01", periods=42, freq="D")
        histories = {
            1: pd.DataFrame(
                {
                    "date": dates,
                    "model_id": [1] * len(dates),
                    "model_return": [0.001 * ((-1) ** i) for i in range(len(dates))],
                    "AUD": [10.0] * len(dates),
                }
            ),
            2: pd.DataFrame(
                {
                    "date": dates,
                    "model_id": [2] * len(dates),
                    "model_return": [0.0015 * ((-1) ** i) for i in range(len(dates))],
                    "AUD": [10.0] * len(dates),
                }
            ),
            3: pd.DataFrame(
                {
                    "date": dates,
                    "model_id": [3] * len(dates),
                    "model_return": [0.4 * ((-1) ** i) for i in range(len(dates))],
                    "AUD": [10.0] * len(dates),
                }
            ),
        }

        result = build_modeled_currency_exposure_detail(
            allocations_df=allocations_df,
            model_histories=histories,
            target_date=pd.Timestamp("2026-02-11"),
        )
        high_vol_row = result[(result["model_id"] == 3) & (result["currency"] == "AUD")].iloc[0]
        self.assertEqual(high_vol_row["gap_scalar"], 0.0)
        self.assertEqual(high_vol_row["raw_weight"], 0.0)

    def test_insufficient_history_models_are_excluded_from_final_rows(self):
        allocations_df = pd.DataFrame(
            {
                "portfolio_id": ["10014"],
                "model_id": [1],
                "strategy_name": ["Short History"],
                "risk_alloc": [1.0],
            }
        )
        histories = {
            1: pd.DataFrame(
                {
                    "date": pd.date_range("2026-01-01", periods=10, freq="D"),
                    "model_id": [1] * 10,
                    "model_return": [0.01] * 10,
                    "AUD": [20.0] * 10,
                    "USD": [-20.0] * 10,
                }
            )
        }
        result = build_modeled_currency_exposure_detail(
            allocations_df=allocations_df,
            model_histories=histories,
            target_date=pd.Timestamp("2026-01-10"),
        )
        self.assertTrue(result.empty)


if __name__ == "__main__":
    unittest.main()
