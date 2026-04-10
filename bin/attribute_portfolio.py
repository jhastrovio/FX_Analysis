#!/usr/bin/env python3
"""
Attribution for SYMAP_JH portfolio (10014).

For a given date, attributes each currency's net modelled position
to the underlying strategies using Thomas's unconstrained position formula:

    scaled_pos_i_c = (sig_i_c / 100) * (TARGET_VOL / vol_42d_i) * sqrt(risk_alloc_i)

where:
  - sig_i_c     = raw signal for model i, currency c (–100 to +100 scale)
  - TARGET_VOL  = 0.10 (10% annualised vol target, decimal)
  - vol_42d_i   = 42-day trailing annualised vol for model i (decimal)
  - risk_alloc_i = risk budget for model i (from Portfolio_Allocations.xlsx)

Per-currency net position = sum of scaled_pos across all models.
USD contribution per model = scaled_pos × AUM (unconstrained; no caps applied).

Constraints (per-currency caps, aggregate gross cap, fundvolfactor) are
layered on in step 2 and are NOT applied here.

Usage:
    python bin/attribute_portfolio.py [--date YYYY-MM-DD]
"""
import argparse
from pathlib import Path
import warnings
import numpy as np
import pandas as pd

# ── constants ─────────────────────────────────────────────────────────────────
PORTFOLIO_ID    = 10014       # SYMAP_JH only
AUM             = 1_000_000   # Portfolio AUM in USD
TARGET_VOL      = 0.10        # Portfolio annualised vol target (10%)
MAX_AGG_PCT     = 500.0       # max_aggregate_ccy_exposure_pct (hard cap on gross notional)
MAX_SINGLE_T1   = 100.0       # max single-CCY exposure % AUM — Tier 1
MAX_SINGLE_T2   =  60.0       # max single-CCY exposure % AUM — Tier 2

TIER1_CCYS = {
    "AUD", "BRL", "CAD", "CHF", "EUR", "GBP", "JPY",
    "KRW", "MXN", "NOK", "NZD", "SEK", "SGD", "USD", "CNH",
}
TIER2_CCYS = {
    "HUF", "IDR", "INR", "PHP", "PLN", "TWD", "ZAR", "CLP",
}

# ── paths ─────────────────────────────────────────────────────────────────────
OD = Path(
    "/Users/jameshassett/Library/CloudStorage/"
    "OneDrive-SharedLibraries-IntellectiveCapitalPte.Ltd/"
    "FX_Data - Documents/General/Prod1"
)
ALLOC_FILE    = OD / "_meta/Portfolio_Allocations.xlsx"
SIGNALS_DIR   = OD / "clean/models_signals_systemacro"
POSITIONS_DIR = OD / "clean/position_systemacro"
OUTPUT_DIR    = Path(__file__).resolve().parent.parent / "outputs"

ALLOC_SHEET = "JH_10014"

# Currency columns as they appear in model signal files.
# All expressed in CCY/USD convention (positive = long CCY, short USD).
# USD is included explicitly — some models (e.g. USDCNH momentum) carry a
# direct long/short USD position that must be attributed.
CCY_COLS = [
    "AUD", "BRL", "CAD", "CHF", "CLP", "CNH", "EUR", "GBP",
    "HUF", "IDR", "INR", "JPY", "KRW", "MXN", "MYR", "NOK",
    "NZD", "PHP", "PLN", "RUB", "SEK", "SGD", "TRY", "TWD", "USD", "ZAR",
]

# Maps model ccy → (portfolio pair name, sign multiplier).
# sign_mult converts model CCY units (CCY/USD) to the portfolio pair's direction:
#   CCY/USD pairs (EURUSD, GBPUSD, AUDUSD, NZDUSD): sign_mult = +1
#   USD/CCY pairs (USDJPY, USDCHF, etc.):             sign_mult = -1
#
# USD has no direct pair — the portfolio's net USD exposure is the sum of all
# USD legs across every live pair, computed in load_portfolio_positions() and
# stored under the key "USD_NET".  sign_mult = +1 because the model and the
# implied portfolio USD are both expressed in the same direction (long = +).
CCY_TO_PAIR = {
    "EUR": ("EURUSD",  +1), "GBP": ("GBPUSD",  +1),
    "AUD": ("AUDUSD",  +1), "NZD": ("NZDUSD",  +1),
    "JPY": ("USDJPY",  -1), "CHF": ("USDCHF",  -1),
    "CAD": ("USDCAD",  -1), "SEK": ("USDSEK",  -1),
    "NOK": ("USDNOK",  -1), "MXN": ("USDMXN",  -1),
    "BRL": ("USDBRL",  -1), "ZAR": ("USDZAR",  -1),
    "SGD": ("USDSGD",  -1), "PLN": ("USDPLN",  -1),
    "HUF": ("USDHUF",  -1), "KRW": ("USDKRW",  -1),
    "IDR": ("USDIDR",  -1), "INR": ("USDINR",  -1),
    "MYR": ("USDMYR",  -1), "PHP": ("USDPHP",  -1),
    "CLP": ("USDCLP",  -1), "CNH": ("USDCNH",  -1),
    "TWD": ("USDTWD",  -1), "TRY": ("USDTRY",  -1),
    "USD": ("USD_NET", +1),   # implied net USD from portfolio pair legs
}

# CCY/USD pairs where the position file stores notional in native CCY (not USD).
# e.g. NZDUSD notional is in NZD, GBPUSD notional is in GBP.
CCY_USD_PAIRS = frozenset(
    pair for _, (pair, _) in CCY_TO_PAIR.items() if pair.endswith("USD") and pair != "USD_NET"
)


# ── data loading ──────────────────────────────────────────────────────────────

def load_allocations() -> pd.DataFrame:
    df = pd.read_excel(ALLOC_FILE, sheet_name=ALLOC_SHEET)
    df.columns = df.columns.str.strip().str.lower()
    # Sheet contains rows for other portfolios — keep only 10014
    df = df[df["portfolio_id"] == PORTFOLIO_ID].copy()
    return df[["model_id", "strategy_name", "risk_alloc", "category"]].reset_index(drop=True)


def find_signal_file(model_id: int) -> "Path | None":
    """Return the most recent signal file for model_id.
    File publish dates lag data dates by 1 day, so the newest file always
    contains the most up-to-date positions.
    """
    candidates = [
        p for p in SIGNALS_DIR.glob(f"{model_id}_*-*.csv")
        if not p.name.endswith(".json")
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stem.split("-")[-1])


def load_model_positions(model_id: int, target_date: pd.Timestamp) -> "pd.Series | None":
    """Return {ccy: raw_position} for model_id on target_date."""
    path = find_signal_file(model_id)
    if path is None:
        return None
    df = pd.read_csv(path, parse_dates=["date"], low_memory=False)
    row = df[df["date"] == target_date]
    if row.empty:
        return None
    row = row.iloc[0]
    available = [c for c in CCY_COLS if c in df.columns]
    return row[available].astype(float)


def compute_vol_42d(model_id: int, target_date: pd.Timestamp) -> "float | None":
    """Compute 42-day trailing annualised vol of model returns.

    The 'return' column is a cumulative index → daily P&L = first difference.
    Uses outlier-clipped std (clip at ±3× 252-day baseline) to handle
    both sparse models (many zero-return days) and position-flip spikes.
    Annualises by √252.  Returns None if < 10 observations available.
    """
    path = find_signal_file(model_id)
    if path is None:
        return None
    df = pd.read_csv(path, usecols=["date", "return"], parse_dates=["date"])
    df = df[df["date"] <= target_date].sort_values("date").tail(300)
    daily = pd.to_numeric(df["return"], errors="coerce").diff().dropna()
    if len(daily) < 10:
        return None
    baseline_std = daily.tail(252).std()
    if baseline_std > 0:
        daily = daily.clip(-3.0 * baseline_std, 3.0 * baseline_std)
    last42 = daily.tail(42)
    if len(last42) < 10:
        return None
    return float(last42.std() * (252 ** 0.5))


def compute_portfolio_scalar(
    alloc: pd.DataFrame, target_date: pd.Timestamp, vol_window: int = 42,
) -> tuple[float, float]:
    """Compute the portfolio-level vol scalar.

    After vol-scaling, the risk-weighted portfolio has a realised vol well
    below the 10% target due to diversification across weakly-correlated
    models.  This function measures that portfolio vol and returns the
    scalar needed to hit TARGET_VOL.

    Steps:
      1. Load daily returns (first-diff of cumulative 'return' column)
         for every model in the allocation.
      2. Weight by vol_weight = (risk_alloc / vol_42d) / Σ(risk_alloc / vol_42d)
         — the same weights used in build_position_matrix.
      3. Construct the portfolio return series = Σ(vol_weight_i × daily_pnl_i).
      4. Measure its trailing annualised vol over *vol_window* days.
      5. portfolio_scalar = TARGET_VOL / (portfolio_vol_decimal).

    Returns (portfolio_scalar, portfolio_vol_pct).
    """
    # ── load daily return series per model (date-indexed) ───────────────
    series = {}
    model_vol = {}
    for _, a in alloc.iterrows():
        mid = int(a["model_id"])
        path = find_signal_file(mid)
        if path is None:
            continue
        df = pd.read_csv(path, usecols=["date", "return"], parse_dates=["date"])
        df = df[df["date"] <= target_date].sort_values("date").tail(300)
        df = df.set_index("date")
        daily = pd.to_numeric(df["return"], errors="coerce").diff().dropna()
        if len(daily) < 10:
            continue
        # outlier clipping (same as compute_vol_42d)
        baseline_std = daily.tail(252).std()
        if baseline_std > 0:
            daily = daily.clip(-3.0 * baseline_std, 3.0 * baseline_std)
        vol = float(daily.tail(vol_window).std() * (252 ** 0.5))
        if vol == 0 or np.isnan(vol):
            continue
        daily.name = mid
        series[mid] = daily
        model_vol[mid] = vol

    # ── compute vol-weights (same logic as build_position_matrix) ─────────
    weights = {}
    for _, a in alloc.iterrows():
        mid = int(a["model_id"])
        if mid not in model_vol:
            continue
        weights[mid] = a["risk_alloc"] / model_vol[mid]
    total_raw = sum(weights.values())
    weights = {mid: w / total_raw for mid, w in weights.items()}

    # ── build portfolio return series ─────────────────────────────────────
    frames = [series[mid] for mid in series if mid in weights]
    if not frames:
        print("  [warn] Cannot compute portfolio scalar — no model data")
        return 1.0, float("nan")

    # Outer join on dates; fillna(0) for models missing specific dates
    # (e.g. recently added models with short history).
    combined = pd.concat(frames, axis=1, join="outer").fillna(0.0)

    port_daily = sum(
        weights[mid] * combined[mid]
        for mid in combined.columns
        if mid in weights
    )
    last_n = port_daily.tail(vol_window)
    if len(last_n) < 10:
        print("  [warn] Insufficient overlapping data for portfolio vol")
        return 1.0, float("nan")

    port_vol_pct = float(last_n.std() * (252 ** 0.5))   # pct-pt units

    if port_vol_pct <= 0:
        print("  [warn] Portfolio vol is zero — cannot compute scalar")
        return 1.0, 0.0

    # TARGET_VOL is decimal (0.10 = 10%); port_vol_pct is pct-pts (e.g. 2.5).
    scalar = (TARGET_VOL * 100) / port_vol_pct
    return scalar, port_vol_pct


def load_portfolio_positions(target_date: pd.Timestamp) -> pd.Series:
    """Parse position_systemacro → Series {pair: current_notional}.
    Primary pairs only (6 uppercase alpha chars, no leading space).
    Falls back to most recent file if exact date not found.
    """
    date_str = target_date.strftime("%Y%m%d")
    path = POSITIONS_DIR / f"position_systemacro-{date_str}.csv"
    if not path.exists():
        files = sorted(
            p for p in POSITIONS_DIR.glob("position_systemacro-*.csv")
            if not p.name.endswith(".json")
        )
        if not files:
            print("  [warn] No position files found.")
            return pd.Series(dtype=float)
        path = files[-1]
        print(f"  [warn] No position file for {date_str}, using {path.name}")
    raw = pd.read_csv(path, header=None, keep_default_na=False)
    positions = {}
    for _, row in raw.iterrows():
        pair = str(row.iloc[0]).strip()
        if len(pair) == 6 and pair.isupper() and pair.isalpha():
            val = pd.to_numeric(str(row.iloc[3]).strip(), errors="coerce")
            if not pd.isna(val):
                positions[pair] = val

    # Compute implied net USD from the USD legs of every live pair.
    # CCY/USD pairs (EURUSD, GBPUSD, AUDUSD, NZDUSD): positive notional = long CCY = short USD
    # USD/CCY pairs (USDJPY, USDCAD, …):               positive notional = long USD
    net_usd = 0.0
    for pair, notional in positions.items():
        if pair.endswith("USD"):           # CCY/USD: long CCY = short USD
            net_usd -= notional
        elif pair.startswith("USD"):       # USD/CCY: positive = long USD
            net_usd += notional
    positions["USD_NET"] = net_usd

    return pd.Series(positions)


def load_spot_rates(pairs: list, target_date: pd.Timestamp) -> dict:
    """Load closing spot rate (mid) for each pair from historical hourly data.

    Data lives at:
        OD/auth/hist_hourly/symbol={PAIR}/hist_hourly_{PAIR}_{YYYY-MM}.csv

    Columns: symbol, ts_utc, provider, mid, run_id
    Returns {pair: float} for pairs with available data; omits pairs where
    data is missing (caller handles the fallback).
    """
    fx_dir = OD / "auth/hist_hourly"
    rates: dict = {}

    for pair in pairs:
        ym = target_date.strftime("%Y-%m")
        csv_path = fx_dir / f"symbol={pair}" / f"hist_hourly_{pair}_{ym}.csv"

        # If current-month file is missing or has no rows before target,
        # fall back to the previous month's file.
        candidate_paths = [csv_path]
        prev_ym = (target_date - pd.DateOffset(months=1)).strftime("%Y-%m")
        candidate_paths.append(
            fx_dir / f"symbol={pair}" / f"hist_hourly_{pair}_{prev_ym}.csv"
        )

        dfs = []
        for path in candidate_paths:
            if not path.exists():
                continue
            try:
                df = pd.read_csv(path, usecols=["ts_utc", "mid"])
                df["ts_utc"] = pd.to_datetime(df["ts_utc"], utc=True)
                dfs.append(df)
            except Exception as exc:
                warnings.warn(f"FX rate load error for {pair} ({path.name}): {exc}")

        if not dfs:
            warnings.warn(
                f"No FX rate data found for {pair}; "
                "live_usd will use actual_notional as-is (units mismatch)."
            )
            continue

        combined = pd.concat(dfs, ignore_index=True)
        # End-of-day cutoff in UTC: take the last hourly bar on or before target_date
        cutoff = pd.Timestamp(target_date.date()).tz_localize("UTC") + pd.Timedelta(hours=23, minutes=59)
        before = combined[combined["ts_utc"] <= cutoff]

        if before.empty:
            warnings.warn(
                f"No FX data for {pair} on or before {target_date.date()}; "
                "live_usd will use actual_notional as-is (units mismatch)."
            )
            continue

        rates[pair] = float(before.loc[before["ts_utc"].idxmax(), "mid"])

    return rates


# ── attribution ───────────────────────────────────────────────────────────────

def build_position_matrix(
    alloc: pd.DataFrame, target_date: pd.Timestamp,
) -> pd.DataFrame:
    """One row per model with positions, vol, and per-model sizing factors.

    Per-model columns for the Thomas attribution formula:
        volfactor = (TARGET_VOL * 100) / vol_42d   (vol ratio; TARGET_VOL decimal, vol_42d pct-pts)
        sqrt_rb   = sqrt(risk_alloc)               (square-root of risk budget)

    These feed directly into compute_attribution():
        scaled_pos = (sig / 100) * volfactor * sqrt_rb
    """
    rows, missing, no_vol = [], [], []

    for _, a in alloc.iterrows():
        mid = int(a["model_id"])
        pos = load_model_positions(mid, target_date)
        if pos is None:
            missing.append(mid)
            continue
        vol = compute_vol_42d(mid, target_date)
        if vol is None or vol == 0:
            no_vol.append(mid)
            vol = float("nan")
        row = {
            "model_id":      mid,
            "strategy_name": a["strategy_name"],
            "risk_alloc":    a["risk_alloc"],
            "category":      a["category"],
            "vol_42d":       vol,
        }
        for ccy in CCY_COLS:
            row[ccy] = float(pos.get(ccy, 0.0) or 0.0)
        rows.append(row)

    if missing:
        print(f"  [warn] No signal data for model(s): {missing}")
    if no_vol:
        print(f"  [warn] No vol computed for model(s): {no_vol} — excluded from attribution")

    df = pd.DataFrame(rows)
    df["volfactor"] = (TARGET_VOL * 100) / df["vol_42d"]   # NaN where vol is missing; vol_42d in pct-pts
    df["sqrt_rb"]   = df["risk_alloc"] ** 0.5
    return df


def compute_attribution(pos_matrix: pd.DataFrame) -> pd.DataFrame:
    """Long-format attribution table, one row per (currency, model).

    Uses Thomas's unconstrained position formula:
        scaled_pos = (sig / 100) * volfactor * sqrt_rb

    where volfactor = TARGET_VOL / vol_42d  and  sqrt_rb = sqrt(risk_alloc).
    Models with missing vol (volfactor = NaN) are excluded.

    Columns:
      scaled_pos     — Thomas formula output (dimensionless)
      net_scaled_pos — sum of scaled_pos across all models for this currency
      pct_of_net     — scaled_pos / net_scaled_pos × 100
      usd_contrib    — scaled_pos × AUM (unconstrained USD, no caps applied)
    """
    rows = []
    for ccy in CCY_COLS:
        if ccy not in pos_matrix.columns:
            continue
        for _, m in pos_matrix.iterrows():
            raw_pos = m[ccy]
            if raw_pos == 0 or pd.isna(raw_pos):
                continue
            if pd.isna(m["volfactor"]):   # model excluded due to missing vol
                continue
            scaled_pos = (raw_pos / 100.0) * m["volfactor"] * m["sqrt_rb"]
            rows.append({
                "currency":      ccy,
                "model_id":      int(m["model_id"]),
                "strategy_name": m["strategy_name"],
                "category":      m["category"],
                "risk_alloc":    m["risk_alloc"],
                "vol_42d":       m["vol_42d"],
                "volfactor":     round(m["volfactor"], 4),
                "raw_position":  raw_pos,
                "scaled_pos":    scaled_pos,
            })

    if not rows:
        return pd.DataFrame()

    attr = pd.DataFrame(rows)

    net = attr.groupby("currency")["scaled_pos"].sum().rename("net_scaled_pos")
    attr = attr.join(net, on="currency")
    attr["pct_of_net"]  = (attr["scaled_pos"] / attr["net_scaled_pos"] * 100).round(1)
    attr["usd_contrib"] = (attr["scaled_pos"] * AUM).round()

    return attr.sort_values(["currency", "pct_of_net"], ascending=[True, False]).reset_index(drop=True)


# ── reconciliation ────────────────────────────────────────────────────────────

def reconcile(attr: pd.DataFrame, port_pos: pd.Series, fx_rates: "dict | None" = None) -> pd.DataFrame:
    """Per-currency reconciliation: bottom-up model USD vs live portfolio notional.

    fx_rates: {pair: spot_rate} for CCY/USD pairs (NZDUSD, AUDUSD, GBPUSD, EURUSD).
    These pairs store notionals in the base (native) currency in the position file,
    so we multiply by the spot rate to convert to USD before comparing with model_usd_bu.
    If fx_rates is None or a pair is missing, falls back to raw notional (with a warning).
    """
    net_by_ccy = (
        attr.groupby("currency")["net_scaled_pos"]
        .first()
        .reset_index()
    )
    rows = []
    for _, r in net_by_ccy.iterrows():
        ccy = r["currency"]
        net_units = r["net_scaled_pos"]
        pair_info = CCY_TO_PAIR.get(ccy)
        pair, sign_mult = pair_info if pair_info else (None, None)
        actual = port_pos.get(pair) if pair else None
        adj_units = net_units * sign_mult if sign_mult is not None else None

        if actual is not None and adj_units:
            signs_match = (adj_units > 0) == (actual > 0)
            implied_scale = round(actual / adj_units, 0) if adj_units != 0 else None
        else:
            signs_match, implied_scale = None, None

        # Bottom-up USD: sum of scaled_pos × AUM for this currency
        net_usd = attr.loc[attr["currency"] == ccy, "usd_contrib"].sum()

        rows.append({
            "currency":        ccy,
            "pair":            pair,
            "net_model_units": round(net_units, 3),
            "actual_notional": actual,
            "model_usd_bu":    round(net_usd),
            "signs_match":     signs_match,
            "implied_scale":   implied_scale,
        })

    recon = pd.DataFrame(rows)

    # ── live_usd: actual notional converted to USD ────────────────────────────
    # For CCY/USD pairs (NZDUSD, AUDUSD, GBPUSD, EURUSD) the position file stores
    # notionals in the native base currency (NZD, AUD, GBP, EUR).  Multiply by the
    # spot rate to get USD.  For USD/CCY pairs the notional is already in USD.
    _fx = fx_rates or {}
    sign_map_local = {c: s for c, (_, s) in CCY_TO_PAIR.items()}

    def _notional_to_usd(notional, pair):
        if pair in CCY_USD_PAIRS:
            rate = _fx.get(pair)
            if rate is not None:
                return notional * rate
            warnings.warn(
                f"No spot rate for {pair}; live_usd uses native-CCY notional "
                "(units mismatch vs model_usd_bu)."
            )
        return notional

    recon["live_usd"] = recon.apply(
        lambda row: int(_notional_to_usd(row["actual_notional"], row["pair"]))
        if pd.notna(row["actual_notional"]) else None,
        axis=1,
    )

    # ── live_ccy_usd: live_usd in long-CCY convention ─────────────────────────
    recon["live_ccy_usd"] = recon.apply(
        lambda row: int(row["live_usd"] * sign_map_local.get(row["currency"], 1))
        if pd.notna(row["live_usd"]) else None,
        axis=1,
    )

    # ── OLS scalar: no-intercept regression (same-sign rows only) ────────────
    # Restricting to same-sign excludes near-cancellation outliers (CHF, JPY)
    # so they don't distort the portfolio-level scalar estimate.
    mask = (
        recon["live_ccy_usd"].notna()
        & (recon["model_usd_bu"] != 0)
        & (np.sign(recon["live_ccy_usd"].fillna(0)) == np.sign(recon["model_usd_bu"]))
    )
    x = recon.loc[mask, "model_usd_bu"].values.astype(float)
    y = recon.loc[mask, "live_ccy_usd"].values.astype(float)
    ols_scale = float(np.dot(x, y) / np.dot(x, x)) if len(x) >= 2 else float("nan")

    # ── per-currency derived columns ──────────────────────────────────────────
    recon["scale_ratio"] = recon.apply(
        lambda r: round(r["live_ccy_usd"] / r["model_usd_bu"], 3)
        if pd.notna(r["live_ccy_usd"]) and r["model_usd_bu"] != 0 else None,
        axis=1,
    )
    recon["fitted_bu_usd"] = recon["model_usd_bu"].apply(
        lambda v: round(v * ols_scale) if not np.isnan(ols_scale) else None
    )
    recon["delta_fitted"] = recon.apply(
        lambda r: int(r["live_ccy_usd"] - r["fitted_bu_usd"])
        if pd.notna(r["live_ccy_usd"]) and pd.notna(r.get("fitted_bu_usd")) else None,
        axis=1,
    )

    # ── portfolio-level diagnostic metadata (via DataFrame.attrs) ─────────────
    bu_gross   = float(recon["model_usd_bu"].abs().sum())
    live_gross = float(recon["live_ccy_usd"].abs().dropna().sum())
    recon.attrs.update({
        "ols_scale":       round(ols_scale, 4),
        "bu_gross":        int(bu_gross),
        "live_gross":      int(live_gross),
        "naive_ratio":     round(live_gross / bu_gross, 4) if bu_gross else float("nan"),
        "max_agg_implied": round(MAX_AGG_PCT / 100 * AUM / bu_gross, 4) if bu_gross else float("nan"),
    })

    return recon.sort_values("net_model_units", key=abs, ascending=False).reset_index(drop=True)


# ── HTML report ───────────────────────────────────────────────────────────────

def _cat_slug(cat: str) -> str:
    """Convert category name to CSS slug (spaces → hyphens, lowercase)."""
    return cat.lower().replace(" ", "-")


def generate_html_report(
    pos_matrix: pd.DataFrame,
    attr: pd.DataFrame,
    recon: pd.DataFrame,
    target_date: pd.Timestamp,
) -> str:
    """Return the full HTML report as a string."""
    import json
    from datetime import date as _date

    today = _date.today().isoformat()
    date_str = target_date.strftime("%Y-%m-%d")
    n_models = len(pos_matrix)
    n_ccys   = attr["currency"].nunique()

    # ── WEIGHTS data ─────────────────────────────────────────────────────────
    wt_sorted = pos_matrix.sort_values("risk_alloc", ascending=False)
    weights_js = []
    for _, r in wt_sorted.iterrows():
        rb = int(round(r["risk_alloc"] * AUM))
        vf = r["volfactor"] if r["volfactor"] == r["volfactor"] else float("nan")
        weights_js.append(
            f'  {{id:{int(r["model_id"])},name:{json.dumps(r["strategy_name"])},'
            f'cat:{json.dumps(_cat_slug(r["category"]))},'
            f'alloc:{r["risk_alloc"]:.4f},'
            f'vol:{r["vol_42d"]:.4f},'
            f'wt:{vf:.4f},'
            f'rb:{rb}}}'
        )

    # ── SUMMARY data ─────────────────────────────────────────────────────────
    summary_rows = (
        attr.groupby("currency")
        .agg(
            net_units  =("net_scaled_pos", "first"),
            bu_usd     =("usd_contrib",    "sum"),
            n_models   =("model_id",       "count"),
            top_driver =("strategy_name",  "first"),
            top_pct    =("pct_of_net",     "first"),
        )
        .reset_index()
        .sort_values("bu_usd", key=abs, ascending=False)
    )
    # Map ccy → pair from CCY_TO_PAIR
    pair_map = {c: p for c, (p, _) in CCY_TO_PAIR.items()}

    # Build lookup: ccy → live_ccy_usd from recon (already FX-converted and sign-adjusted)
    recon_lookup = recon.set_index("currency")["live_ccy_usd"].to_dict()

    summary_js = []
    for _, r in summary_rows.iterrows():
        ccy  = r["currency"]
        pair = pair_map.get(ccy, "")
        live_ccy = recon_lookup.get(ccy)
        live_js = str(live_ccy) if live_ccy is not None else "null"
        summary_js.append(
            f'  {{ccy:{json.dumps(ccy)},pair:{json.dumps(pair)},'
            f'usd:{int(r["bu_usd"])},live:{live_js},'
            f'n:{int(r["n_models"])},top:{json.dumps(r["top_driver"])},'
            f'topPct:{r["top_pct"]:.1f}}}'
        )

    # ── RECON metadata (for diagnostic box) ─────────────────────────────────
    bu_gross   = recon.attrs.get("bu_gross", 0)
    live_gross = recon.attrs.get("live_gross", 0)

    # ── DETAIL data (per-ccy, per-model) ─────────────────────────────────────
    detail_parts = []
    for ccy, grp in attr.groupby("currency"):
        grp_sorted = grp.sort_values("pct_of_net", ascending=False)
        rows_js = []
        for _, r in grp_sorted.iterrows():
            rows_js.append(
                f'[{json.dumps(r["strategy_name"])},'
                f'{json.dumps(_cat_slug(r["category"]))},'
                f'{r["pct_of_net"]:.1f},{int(r["usd_contrib"])}]'
            )
        detail_parts.append(f'  {json.dumps(ccy)}:[{",".join(rows_js)}]')

    # ── MODEL_DETAIL data (per-model, per-ccy) ────────────────────────────────
    model_detail_js = []
    for _, m in wt_sorted.iterrows():
        mid = int(m["model_id"])
        rb  = int(round(m["risk_alloc"] * AUM))
        vf  = m["volfactor"] if m["volfactor"] == m["volfactor"] else 0.0
        # Collect non-zero CCY positions, sorted by |raw_pos| desc
        ccy_rows = []
        for ccy in CCY_COLS:
            val = float(m.get(ccy, 0.0) or 0.0)
            if val != 0:
                ccy_rows.append((ccy, val))
        ccy_rows.sort(key=lambda x: abs(x[1]), reverse=True)
        ccys_js = ",".join(f'[{json.dumps(c)},{v}]' for c, v in ccy_rows)
        model_detail_js.append(
            f'  {{id:{mid},name:{json.dumps(m["strategy_name"])},'
            f'cat:{json.dumps(_cat_slug(m["category"]))},'
            f'wt:{vf:.4f},rb:{rb},'
            f'ccys:[{ccys_js}]}}'
        )

    # ── assemble HTML ─────────────────────────────────────────────────────────
    weights_block      = ",\n".join(weights_js)
    summary_block      = ",\n".join(summary_js)
    detail_block       = ",\n".join(detail_parts)
    model_detail_block = ",\n".join(model_detail_js)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>SYMAP_JH Attribution \u2014 {date_str}</title>
<style>
  :root {{
    --bg:       #0f1117;
    --surface:  #1a1d27;
    --border:   #2a2d3a;
    --text:     #e2e4ec;
    --muted:    #8890a8;
    --accent:   #4f8ef7;
    --green:    #34d399;
    --red:      #f87171;
    --amber:    #fbbf24;
  }}

  * {{ box-sizing: border-box; margin: 0; padding: 0; }}

  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
    background: var(--bg);
    color: var(--text);
    font-size: 13px;
    line-height: 1.5;
    padding: 28px 32px 60px;
  }}

  .header {{
    display: flex; align-items: center; gap: 16px;
    border-bottom: 1px solid var(--border);
    padding-bottom: 16px; margin-bottom: 32px; flex-wrap: wrap;
  }}
  .header h1 {{ font-size: 18px; font-weight: 600; }}
  .pill {{
    background: #1e2a45; color: var(--accent);
    border: 1px solid #2a3d6a; border-radius: 99px;
    padding: 2px 10px; font-size: 11px; font-weight: 700; letter-spacing:.04em;
  }}
  .header .meta {{ color: var(--muted); font-size: 12px; margin-left: auto; }}

  h2 {{
    font-size: 11px; font-weight: 700; text-transform: uppercase;
    letter-spacing: .1em; color: var(--muted);
    margin-bottom: 14px; margin-top: 40px;
    padding-bottom: 8px; border-bottom: 1px solid var(--border);
  }}

  .tbl-wrap {{ overflow-x: auto; border: 1px solid var(--border); border-radius: 8px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 12.5px; }}
  thead th {{
    background: #13161f; color: var(--muted); font-weight: 600;
    text-transform: uppercase; letter-spacing: .05em; font-size: 10px;
    padding: 9px 14px; text-align: right;
    border-bottom: 1px solid var(--border); white-space: nowrap;
  }}
  thead th.left {{ text-align: left; }}
  tbody tr {{ border-bottom: 1px solid #1f2230; }}
  tbody tr:last-child {{ border-bottom: none; }}
  tbody tr:hover {{ background: rgba(255,255,255,.02); }}
  td {{ padding: 8px 14px; text-align: right; white-space: nowrap; }}
  td.left {{ text-align: left; }}

  .pos {{ color: var(--green); }}
  .neg {{ color: var(--red); }}
  .muted {{ color: var(--muted); }}

  .tag {{
    display: inline-block; border-radius: 4px; padding: 1px 7px;
    font-size: 10px; font-weight: 600; white-space: nowrap;
  }}
  .tag-carry          {{ background:#142014; color:#4ade80; }}
  .tag-momentum       {{ background:#111a2e; color:#60a5fa; }}
  .tag-macro          {{ background:#1e1228; color:#c084fc; }}
  .tag-valuation      {{ background:#211900; color:#fbbf24; }}
  .tag-positioning    {{ background:#0e1e28; color:#38bdf8; }}
  .tag-cross-asset    {{ background:#181820; color:#a78bfa; }}
  .tag-capital-flow   {{ background:#1e1800; color:#f59e0b; }}
  .tag-mean-reversion {{ background:#0e1e1e; color:#2dd4bf; }}
  .tag-bespoke        {{ background:#1e0e1a; color:#f472b6; }}
  .tag-static         {{ background:#1c1c24; color:#94a3b8; }}

  .spark {{ display:inline-block; height:8px; background:var(--accent); border-radius:2px; opacity:.65; vertical-align:middle; }}

  .ccy-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
    gap: 12px;
  }}
  .card {{
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 8px; padding: 14px 16px;
  }}
  .card-head {{
    display: flex; justify-content: space-between;
    align-items: baseline; margin-bottom: 12px;
  }}
  .card-ccy  {{ font-size: 15px; font-weight: 700; letter-spacing: .05em; }}
  .card-pair {{ font-size: 11px; color: var(--muted); margin-left: 6px; }}
  .card-usd  {{ font-size: 13px; font-weight: 600; }}

  .bar-row {{
    display: flex; align-items: center; gap: 8px;
    margin-bottom: 4px; font-size: 11px;
  }}
  .bar-name {{
    width: 190px; min-width: 190px;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    color: var(--text);
  }}
  .bar-track {{ flex: 1; height: 5px; background: #1e2130; border-radius: 99px; overflow: hidden; }}
  .bar-fill  {{ height: 100%; border-radius: 99px; }}
  .bar-pct   {{ width: 50px; min-width: 50px; text-align: right; color: var(--muted); font-variant-numeric: tabular-nums; }}

  .delta-ok   {{ color: var(--muted); font-size: 11px; }}
  .delta-warn {{ color: var(--amber); font-size: 11px; }}

  .footer {{
    margin-top: 48px; padding-top: 16px;
    border-top: 1px solid var(--border);
    color: var(--muted); font-size: 11px;
  }}

  ::-webkit-scrollbar {{ width:5px; height:5px; }}
  ::-webkit-scrollbar-track {{ background: transparent; }}
  ::-webkit-scrollbar-thumb {{ background: var(--border); border-radius: 3px; }}
</style>
</head>
<body>

<div class="header">
  <h1>SYMAP_JH &nbsp;&middot;&nbsp; Position Attribution</h1>
  <span class="pill">10014</span>
  <div class="meta">
    {date_str} &nbsp;&middot;&nbsp; AUM ${AUM:,} &nbsp;&middot;&nbsp; Target vol {TARGET_VOL:.0%}
    &nbsp;&middot;&nbsp; {n_models} models &nbsp;&middot;&nbsp; {n_ccys} currencies (incl. USD)
  </div>
</div>

<h2>1 &middot; Model Sizing Factors &nbsp;<span style="font-weight:400;text-transform:none;letter-spacing:0;font-size:10.5px">&mdash; unconstrained, sorted by risk allocation</span></h2>
<div class="tbl-wrap">
<table>
  <thead>
    <tr>
      <th class="left">Strategy</th>
      <th class="left">Category</th>
      <th>Risk alloc</th>
      <th>42d vol</th>
      <th>Vol factor</th>
      <th>Risk budget (USD)</th>
      <th class="left" style="padding-left:20px">Vol factor</th>
    </tr>
  </thead>
  <tbody id="wt-body"></tbody>
</table>
</div>
<p style="color:var(--muted);font-size:10.5px;margin-top:8px">
  <strong style="color:var(--text)">Vol factor</strong> = TARGET_VOL &divide; vol_42d &mdash; the leverage applied to the raw signal.
  A lower-vol model gets a higher vol factor and therefore a larger scaled position.
  &nbsp;&nbsp;<strong style="color:var(--text)">Risk budget (USD)</strong> = risk_alloc &times; AUM.
  &nbsp;&nbsp;Scaled position = (signal&nbsp;&divide;&nbsp;100) &times; vol_factor &times; &radic;risk_alloc (unconstrained).
</p>

<h2>2 &middot; Net Position Summary &nbsp;<span style="font-weight:400;text-transform:none;letter-spacing:0;font-size:10.5px">&mdash; all currencies, sorted by |bottom-up USD|</span></h2>
<div style="background:#13161f;border:1px solid var(--border);border-radius:6px;
            padding:12px 16px;margin-bottom:14px;font-size:11.5px;
            display:flex;gap:28px;flex-wrap:wrap;">
  <span style="color:var(--muted)">Target vol <strong style="color:var(--text)">{TARGET_VOL:.0%}</strong></span>
  <span style="color:var(--muted)">BU gross (unconstrained) <strong style="color:var(--text)">${bu_gross:,}</strong></span>
  <span style="color:var(--muted)">Live gross <strong style="color:var(--text)">${live_gross:,}</strong></span>
</div>
<div class="tbl-wrap">
<table>
  <thead>
    <tr>
      <th class="left">Currency</th>
      <th>Bottom-up USD</th>
      <th>Live USD</th>
      <th>&Delta;</th>
      <th># Models</th>
      <th class="left">Top driver</th>
      <th>Driver %</th>
    </tr>
  </thead>
  <tbody id="summary-body"></tbody>
</table>
</div>
<p style="color:var(--muted);font-size:10.5px;margin-top:8px">
  <strong style="color:var(--text)">Bottom-up USD</strong> = sum of scaled_pos &times; AUM across all models (unconstrained; no caps applied).
  scaled_pos = (signal&nbsp;&divide;&nbsp;100) &times; vol_factor &times; &radic;risk_alloc.
  &nbsp;&nbsp;<strong style="color:var(--text)">Live USD</strong> = position file notional converted to USD in long-CCY convention.
  CCY/USD pairs (NZD, AUD, GBP, EUR) are FX-converted using the closing spot rate.
  &nbsp;&nbsp;<strong style="color:var(--text)">Driver %</strong> = top model&rsquo;s share of the net directional signal.
</p>

<h2>3 &middot; Per-Currency Attribution &nbsp;<span style="font-weight:400;text-transform:none;letter-spacing:0;font-size:10.5px">&mdash; model contributions as % of net position</span></h2>
<div class="ccy-grid" id="ccy-grid"></div>

<h2>4 &middot; Per-Model Attribution &nbsp;<span style="font-weight:400;text-transform:none;letter-spacing:0;font-size:10.5px">&mdash; currency contributions as % of each model&rsquo;s gross position</span></h2>
<div class="ccy-grid" id="model-grid"></div>
<p style="color:var(--muted);font-size:10.5px;margin-top:8px">
  Bar width = |raw position| as % of that model&rsquo;s total gross position.
  &nbsp;&nbsp;<strong style="color:var(--green)">Blue</strong> = long CCY.
  &nbsp;&nbsp;<strong style="color:var(--red)">Red</strong> = short CCY.
</p>


<div class="footer">
  Generated {today} &nbsp;&middot;&nbsp; FX_Analysis / attribute_portfolio.py &nbsp;&middot;&nbsp; SYMAP_JH (10014)
</div>

<script>
const WEIGHTS = [
{weights_block}
];

const SUMMARY = [
{summary_block}
];

const DETAIL = {{
{detail_block}
}};

const MODEL_DETAIL = [
{model_detail_block}
];

const fmtUSD = n => {{
  if (n === 0) return "$0";
  const s = Math.abs(n).toLocaleString("en-US");
  return (n > 0 ? "+$" : "-$") + s;
}};
const cls = n => n > 0 ? "pos" : n < 0 ? "neg" : "muted";
const pctStr = n => (n >= 0 ? "+" : "") + n.toFixed(1) + "%";

// 1. Weights
const maxWt = Math.max(...WEIGHTS.map(w => w.wt));
document.getElementById("wt-body").innerHTML = WEIGHTS.map(w => {{
  const bw = Math.round(w.wt / maxWt * 100);
  return `<tr>
    <td class="left" style="font-weight:500">${{w.name}} <span class="muted" style="font-size:10px">#${{w.id}}</span></td>
    <td class="left"><span class="tag tag-${{w.cat}}">${{w.cat.replace(/-/g," ")}}</span></td>
    <td>${{(w.alloc*100).toFixed(2)}}%</td>
    <td>${{(w.vol*100).toFixed(2)}}%</td>
    <td>${{isFinite(w.wt) ? w.wt.toFixed(3) : "n/a"}}</td>
    <td>$${{w.rb.toLocaleString()}}</td>
    <td class="left" style="padding-left:20px"><span class="spark" style="width:${{isFinite(w.wt) ? bw : 0}}px"></span></td>
  </tr>`;
}}).join("");

// 2. Summary (merged with reconciliation)
document.getElementById("summary-body").innerHTML = SUMMARY.map(s => {{
  const live = s.live != null ? s.live : 0;
  const delta = live - s.usd;
  const absDelta = Math.abs(delta);
  const pctOff = live !== 0 ? absDelta / Math.abs(live) * 100 : 0;
  const deltaClass = pctOff > 50 ? "delta-warn" : "delta-ok";
  return `<tr>
    <td class="left"><strong style="font-size:13.5px;letter-spacing:.05em">${{s.ccy}}</strong></td>
    <td class="${{cls(s.usd)}}">${{fmtUSD(s.usd)}}</td>
    <td class="${{cls(live)}}">${{s.live != null ? fmtUSD(live) : "\u2014"}}</td>
    <td class="${{deltaClass}}">${{s.live != null ? fmtUSD(delta) : "\u2014"}}</td>
    <td class="muted">${{s.n}}</td>
    <td class="left" style="max-width:220px;overflow:hidden;text-overflow:ellipsis">${{s.top}}</td>
    <td class="${{cls(s.usd)}}">${{s.topPct.toFixed(1)}}%</td>
  </tr>`;
}}).join("");

// 3. Per-currency cards
document.getElementById("ccy-grid").innerHTML = SUMMARY.map(s => {{
  const rows = DETAIL[s.ccy] || [];
  const maxAbs = Math.max(...rows.map(r => Math.abs(r[2])));
  const bars = rows.map(([name, cat, pct, usd]) => {{
    const w = Math.round(Math.abs(pct) / maxAbs * 100);
    const col = pct > 0 ? "#4f8ef7" : "#f87171";
    return `<div class="bar-row">
      <span class="bar-name" title="${{name}}">${{name}}</span>
      <div class="bar-track"><div class="bar-fill" style="width:${{w}}%;background:${{col}}"></div></div>
      <span class="bar-pct ${{pct>=0?'pos':'neg'}}">${{pctStr(pct)}}</span>
    </div>`;
  }}).join("");
  return `<div class="card">
    <div class="card-head">
      <span>
        <span class="card-ccy ${{cls(s.usd)}}">${{s.ccy}}</span>
        <span class="card-pair">${{s.pair}}</span>
      </span>
      <span class="card-usd ${{cls(s.usd)}}">${{fmtUSD(s.usd)}}</span>
    </div>
    ${{bars}}
  </div>`;
}}).join("");

// 4. Per-model cards
document.getElementById("model-grid").innerHTML = MODEL_DETAIL.map(m => {{
  const gross = m.ccys.reduce((s,[,p]) => s + Math.abs(p), 0);
  if (m.ccys.length === 0) {{
    return `<div class="card" style="opacity:.45">
      <div class="card-head">
        <span><span class="card-ccy muted">${{m.name}}</span>
        <span class="card-pair">#${{m.id}}</span></span>
        <span class="tag tag-${{m.cat}}">${{m.cat.replace(/-/g," ")}}</span>
      </div>
      <div style="color:var(--muted);font-size:11px;margin-top:4px">No positions on this date</div>
    </div>`;
  }}
  const bars = m.ccys.map(([ccy, pos]) => {{
    const w = Math.round(Math.abs(pos) / gross * 200);
    const col = pos > 0 ? "#4f8ef7" : "#f87171";
    return `<div class="bar-row">
      <span class="bar-name" style="width:60px;min-width:60px;font-weight:600;letter-spacing:.04em">${{ccy}}</span>
      <div class="bar-track" style="flex:1">
        <div class="bar-fill" style="width:${{Math.min(w,100)}}%;background:${{col}}"></div>
      </div>
      <span class="bar-pct ${{pos>=0?'pos':'neg'}}" style="width:60px;min-width:60px">${{pos>=0?"+"+pos.toFixed(1):pos.toFixed(1)}}</span>
    </div>`;
  }}).join("");
  return `<div class="card">
    <div class="card-head">
      <span>
        <span class="card-ccy" style="font-size:12px;font-weight:600">${{m.name}}</span>
        <span class="card-pair">#${{m.id}}</span>
      </span>
      <span class="tag tag-${{m.cat}}">${{m.cat.replace(/-/g," ")}}</span>
    </div>
    <div style="display:flex;gap:16px;margin-bottom:10px;font-size:10.5px;color:var(--muted)">
      <span>Vol factor <strong style="color:var(--text)">${{isFinite(m.wt) ? m.wt.toFixed(3) : "n/a"}}</strong></span>
      <span>Risk budget <strong style="color:var(--text)">$${{m.rb.toLocaleString()}}</strong></span>
      <span>${{m.ccys.length}} CCY${{m.ccys.length>1?"s":""}}</span>
    </div>
    ${{bars}}
  </div>`;
}}).join("");

</script>
</body>
</html>"""


# ── main ──────────────────────────────────────────────────────────────────────

def run(target_date: pd.Timestamp) -> None:
    print(f"\n{'='*66}")
    print(f"  Attribution  |  SYMAP_JH (10014)  |  {target_date.date()}"
          f"  |  AUM ${AUM:,.0f}  |  Target vol {TARGET_VOL:.0%}")
    print(f"{'='*66}\n")

    alloc = load_allocations()
    print(f"  {len(alloc)} models in allocations")

    print(f"  Loading signal files for {target_date.date()}...")
    pos_matrix = build_position_matrix(alloc, target_date)
    n_valid = pos_matrix["vol_42d"].notna().sum()
    print(f"  {len(pos_matrix)} / {len(alloc)} models loaded  |  "
          f"{n_valid} with valid vol\n")

    port_pos = load_portfolio_positions(target_date)
    attr = compute_attribution(pos_matrix)

    fx_rates = load_spot_rates(sorted(CCY_USD_PAIRS), target_date)
    if fx_rates:
        loaded = ", ".join(f"{p}={v:.5f}" for p, v in sorted(fx_rates.items()))
        print(f"  FX spot rates: {loaded}")
    else:
        print("  [warn] No FX spot rates loaded; CCY/USD notionals will not be converted.")

    # ── save outputs ──────────────────────────────────────────────────────────
    OUTPUT_DIR.mkdir(exist_ok=True)
    date_str = target_date.strftime("%Y%m%d")

    attr_path  = OUTPUT_DIR / f"attribution_10014_{date_str}.csv"
    recon_path = OUTPUT_DIR / f"reconciliation_10014_{date_str}.csv"
    wt_path    = OUTPUT_DIR / f"model_weights_10014_{date_str}.csv"

    attr.to_csv(attr_path, index=False)
    recon = reconcile(attr, port_pos, fx_rates)
    recon.to_csv(recon_path, index=False)

    wt_out = pos_matrix[["model_id", "strategy_name", "category",
                          "risk_alloc", "vol_42d", "volfactor", "sqrt_rb"]].copy()
    wt_out.to_csv(wt_path, index=False)

    html_path = OUTPUT_DIR / f"attribution_report_10014_{date_str}.html"
    html_path.write_text(
        generate_html_report(pos_matrix, attr, recon, target_date),
        encoding="utf-8",
    )

    print(f"  Attribution   → {attr_path.name}")
    print(f"  Weights       → {wt_path.name}")
    print(f"  Reconciliation→ {recon_path.name}")
    print(f"  HTML report   → {html_path.name}\n")

    # ── weight table ──────────────────────────────────────────────────────────
    wt_display = wt_out.copy()
    wt_display["vol_42d"]   = wt_display["vol_42d"].map(lambda x: f"{x:.4f}" if x == x else "n/a")
    wt_display["volfactor"] = wt_display["volfactor"].map(lambda x: f"{x:.3f}" if x == x else "n/a")
    wt_display["sqrt_rb"]   = wt_display["sqrt_rb"].map(lambda x: f"{x:.4f}")
    print("── Model sizing factors (unconstrained, target vol 10%) ──")
    print(wt_display.to_string(index=False))

    # ── net position summary ──────────────────────────────────────────────────
    net_summary = (
        attr.groupby("currency")
        .agg(
            net_units  =("net_scaled_pos", "first"),
            bu_usd     =("usd_contrib",    "sum"),
            n_models   =("model_id",       "count"),
            top_driver =("strategy_name",  "first"),
            top_pct    =("pct_of_net",     "first"),
        )
        .reset_index()
        .sort_values("net_units", key=abs, ascending=False)
    )
    net_summary["bu_usd"] = net_summary["bu_usd"].map(lambda x: f"${x:,.0f}")

    print("\n── Net position per currency (bu_usd = bottom-up reconstruction) ──\n")
    print(net_summary.to_string(index=False))

    # ── per-currency driver detail (top 8 by abs net units) ──────────────────
    top_ccys = (
        attr.groupby("currency")["net_scaled_pos"]
        .first()
        .abs()
        .nlargest(8)
        .index.tolist()
    )
    for ccy in top_ccys:
        sub = attr[attr["currency"] == ccy][
            ["strategy_name", "category", "raw_position",
             "scaled_pos", "pct_of_net", "usd_contrib"]
        ].copy()
        net_u   = attr.loc[attr["currency"] == ccy, "net_scaled_pos"].iloc[0]
        net_usd = sub["usd_contrib"].sum()
        sub["usd_contrib"] = sub["usd_contrib"].map(lambda x: f"${x:,.0f}")
        print(f"\n── {ccy}  net: {net_u:+.4f} scaled  |  usd_unconstrained: ${net_usd:,.0f} ──")
        print(sub.to_string(index=False))

    # ── reconciliation summary ────────────────────────────────────────────────
    print("\n── Reconciliation vs position_systemacro  (model_usd_bu = bottom-up) ──")
    recon_disp = recon.copy()
    recon_disp["model_usd_bu"] = recon_disp["model_usd_bu"].map(
        lambda x: f"${x:,.0f}" if pd.notna(x) else "")
    recon_disp["signs_match"] = recon_disp["signs_match"].map(
        {True: "✓", False: "✗", None: "-"})
    print(recon_disp.to_string(index=False))

    n_match = (recon["signs_match"] == True).sum()
    n_total = recon["signs_match"].notna().sum()
    print(f"\n  Direction agreement: {n_match}/{n_total} currencies")
    mismatches = recon.loc[recon["signs_match"] == False, "currency"].tolist()
    if mismatches:
        print(f"  Sign mismatches: {mismatches}")


def main():
    parser = argparse.ArgumentParser(description="Attribution for SYMAP_JH (10014)")
    parser.add_argument("--date", help="Target date YYYY-MM-DD (default: most recent)")
    args = parser.parse_args()

    if args.date:
        target = pd.Timestamp(args.date)
    else:
        latest = max(
            (p for p in SIGNALS_DIR.glob("*.csv") if not p.name.endswith(".json")),
            key=lambda p: p.stem.split("-")[-1],
        )
        df = pd.read_csv(latest, usecols=["date"], parse_dates=["date"])
        target = df["date"].max()
        print(f"  Defaulting to most recent date in signal files: {target.date()}")

    run(target)


if __name__ == "__main__":
    main()
