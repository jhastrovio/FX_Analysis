#!/usr/bin/env python3
"""
Attribution for SYMAP_JH portfolio (10014).

For a given date, attributes each currency's net modelled position
to the underlying strategies by weighting each model's unscaled
currency position by its vol-adjusted portfolio weight.

Portfolio construction (portfolio-level vol targeting):
  - Each model's risk allocation (risk_alloc) defines its share of the
    total 10% portfolio vol target.
  - The vol-targeting formula sizes each model in isolation, then scales
    all notionals by the diversification ratio so that the PORTFOLIO-LEVEL
    vol (accounting for cross-model correlations) hits the 10% target.
  - Isolated notional = AUM × target_vol × (risk_alloc / Σrisk_alloc) / vol_42d_decimal
  - Diversification ratio = Σ(w_i × σ_i) / σ_portfolio
    where σ_portfolio comes from the full covariance matrix of model returns
  - Final dollar_notl = isolated_notional × diversification_ratio

Usage:
    python bin/attribute_portfolio.py [--date YYYY-MM-DD]
"""
import argparse
from pathlib import Path
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


# ── attribution ───────────────────────────────────────────────────────────────

def build_position_matrix(
    alloc: pd.DataFrame, target_date: pd.Timestamp, portfolio_scalar: float = 1.0,
) -> pd.DataFrame:
    """One row per model with positions, vol, and weights.

    Vol-adjusted weights (step 1 — relative sizing):
        raw_weight    = risk_alloc / vol_42d
        vol_weight    = raw_weight / Σ(raw_weights)

    Dollar notional (step 2 — portfolio-level vol targeting):
        dollar_notl = AUM × vol_weight × portfolio_scalar

    The portfolio_scalar = TARGET_VOL_PCT / portfolio_vol_PCT, where
    portfolio_vol is measured from the vol-weight-weighted return series.
    This accounts for diversification: because the models are weakly
    correlated, the risk-weighted portfolio runs below target vol.
    Scaling up ensures the aggregate hits the 10% target.
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
        print(f"  [warn] No vol computed for model(s): {no_vol} — excluded from weights")

    df = pd.DataFrame(rows)
    df["raw_weight"] = df["risk_alloc"] / df["vol_42d"]
    total_raw = df["raw_weight"].sum()
    df["vol_weight"] = df["raw_weight"] / total_raw
    df["dollar_notl"] = AUM * df["vol_weight"] * portfolio_scalar
    return df


def compute_attribution(pos_matrix: pd.DataFrame) -> pd.DataFrame:
    """Long-format attribution table, one row per (currency, model).

    Columns:
      weighted_pos  — raw_position × vol_weight  (dimensionless signal share)
      pct_of_net    — share of net modelled position (%)
      usd_contrib   — bottom-up USD: (raw_position / 100) × dollar_notl
    """
    rows = []
    for ccy in CCY_COLS:
        if ccy not in pos_matrix.columns:
            continue
        for _, m in pos_matrix.iterrows():
            raw_pos = m[ccy]
            if raw_pos == 0 or pd.isna(raw_pos):
                continue
            rows.append({
                "currency":      ccy,
                "model_id":      int(m["model_id"]),
                "strategy_name": m["strategy_name"],
                "category":      m["category"],
                "risk_alloc":    m["risk_alloc"],
                "vol_42d":       round(m["vol_42d"], 2),
                "vol_weight":    round(m["vol_weight"], 4),
                "dollar_notl":   round(m["dollar_notl"]),
                "raw_position":  raw_pos,
                "weighted_pos":  raw_pos * m["vol_weight"],
            })

    if not rows:
        return pd.DataFrame()

    attr = pd.DataFrame(rows)

    # Net weighted position and pct attribution
    net = attr.groupby("currency")["weighted_pos"].sum().rename("net_weighted_pos")
    attr = attr.join(net, on="currency")
    attr["pct_of_net"] = (attr["weighted_pos"] / attr["net_weighted_pos"] * 100).round(1)

    # Bottom-up USD: raw position as a fraction of notional scale (0–100) × model risk budget
    attr["usd_contrib"] = attr["raw_position"] / 100.0 * attr["dollar_notl"]

    # ── apply per-currency position limits ────────────────────────────────
    # Tier 1 currencies: max 100% AUM per CCY; Tier 2: max 60% AUM per CCY.
    # If the uncapped net |usd_contrib| for a currency exceeds its limit,
    # scale all model contributions for that currency proportionally.
    max_t1 = MAX_SINGLE_T1 / 100.0 * AUM   # $1,000,000
    max_t2 = MAX_SINGLE_T2 / 100.0 * AUM   # $600,000

    net_usd_per_ccy = attr.groupby("currency")["usd_contrib"].sum()
    ccy_scale = {}
    for ccy, net_usd in net_usd_per_ccy.items():
        cap = max_t1 if ccy in TIER1_CCYS else max_t2 if ccy in TIER2_CCYS else max_t1
        if abs(net_usd) > cap:
            ccy_scale[ccy] = cap / abs(net_usd)

    if ccy_scale:
        attr["ccy_cap_scale"] = attr["currency"].map(lambda c: ccy_scale.get(c, 1.0))
        attr["usd_contrib"] = attr["usd_contrib"] * attr["ccy_cap_scale"]
        attr.drop(columns=["ccy_cap_scale"], inplace=True)

    # ── apply aggregate gross limit (500% AUM) ───────────────────────────
    # If the sum of |net per-ccy usd| exceeds the 500% cap, scale everything
    # down proportionally.
    net_usd_after_ccy = attr.groupby("currency")["usd_contrib"].sum()
    agg_gross = net_usd_after_ccy.abs().sum()
    agg_cap = MAX_AGG_PCT / 100.0 * AUM   # $5,000,000
    if agg_gross > agg_cap:
        agg_scale = agg_cap / agg_gross
        attr["usd_contrib"] = attr["usd_contrib"] * agg_scale

    attr["usd_contrib"] = attr["usd_contrib"].round()

    return attr.sort_values(["currency", "pct_of_net"], ascending=[True, False]).reset_index(drop=True)


# ── reconciliation ────────────────────────────────────────────────────────────

def reconcile(attr: pd.DataFrame, port_pos: pd.Series) -> pd.DataFrame:
    """Per-currency reconciliation: bottom-up model USD vs live portfolio notional."""
    net_by_ccy = (
        attr.groupby("currency")["net_weighted_pos"]
        .first()
        .reset_index()
    )
    rows = []
    for _, r in net_by_ccy.iterrows():
        ccy = r["currency"]
        net_units = r["net_weighted_pos"]
        pair_info = CCY_TO_PAIR.get(ccy)
        pair, sign_mult = pair_info if pair_info else (None, None)
        actual = port_pos.get(pair) if pair else None
        adj_units = net_units * sign_mult if sign_mult is not None else None

        if actual is not None and adj_units:
            signs_match = (adj_units > 0) == (actual > 0)
            implied_scale = round(actual / adj_units, 0) if adj_units != 0 else None
        else:
            signs_match, implied_scale = None, None

        # Bottom-up USD: sum of (raw_position / 100) × dollar_notl for this currency
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

    # ── live_ccy_usd: actual notional in long-CCY convention ──────────────────
    sign_map_local = {c: s for c, (_, s) in CCY_TO_PAIR.items()}
    recon["live_ccy_usd"] = recon.apply(
        lambda row: int(row["actual_notional"] * sign_map_local.get(row["currency"], 1))
        if pd.notna(row["actual_notional"]) else None,
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
    wt_sorted = pos_matrix.sort_values("vol_weight", ascending=False)
    weights_js = []
    for _, r in wt_sorted.iterrows():
        rb = int(round(r["dollar_notl"])) if r["dollar_notl"] == r["dollar_notl"] else 0
        weights_js.append(
            f'  {{id:{int(r["model_id"])},name:{json.dumps(r["strategy_name"])},'
            f'cat:{json.dumps(_cat_slug(r["category"]))},'
            f'alloc:{r["risk_alloc"]:.2f},'
            f'vol:{r["vol_42d"]:.2f},'
            f'wt:{r["vol_weight"]:.4f},'
            f'rb:{rb}}}'
        )

    # ── SUMMARY data ─────────────────────────────────────────────────────────
    summary_rows = (
        attr.groupby("currency")
        .agg(
            net_units  =("net_weighted_pos", "first"),
            bu_usd     =("usd_contrib",      "sum"),
            n_models   =("model_id",         "count"),
            top_driver =("strategy_name",    "first"),
            top_pct    =("pct_of_net",       "first"),
        )
        .reset_index()
        .sort_values("bu_usd", key=abs, ascending=False)
    )
    # Map ccy → pair from CCY_TO_PAIR
    pair_map = {c: p for c, (p, _) in CCY_TO_PAIR.items()}
    summary_js = []
    for _, r in summary_rows.iterrows():
        ccy  = r["currency"]
        pair = pair_map.get(ccy, "")
        summary_js.append(
            f'  {{ccy:{json.dumps(ccy)},pair:{json.dumps(pair)},'
            f'usd:{int(r["bu_usd"])},sig:{r["net_units"]:.3f},'
            f'n:{int(r["n_models"])},top:{json.dumps(r["top_driver"])},'
            f'topPct:{r["top_pct"]:.1f}}}'
        )

    # ── RECON data ────────────────────────────────────────────────────────────
    ols_scale       = recon.attrs.get("ols_scale", float("nan"))
    bu_gross        = recon.attrs.get("bu_gross", 0)
    live_gross      = recon.attrs.get("live_gross", 0)
    naive_ratio     = recon.attrs.get("naive_ratio", float("nan"))
    max_agg_impl    = recon.attrs.get("max_agg_implied", float("nan"))
    port_scalar     = recon.attrs.get("portfolio_scalar", float("nan"))
    port_vol        = recon.attrs.get("portfolio_vol", float("nan"))
    ols_scale_str   = f"{ols_scale:.3f}\u00d7" if not np.isnan(ols_scale) else "n/a"
    ols_scale_js    = str(round(ols_scale, 4)) if not np.isnan(ols_scale) else "null"
    port_scalar_str = f"{port_scalar:.2f}\u00d7" if not np.isnan(port_scalar) else "n/a"
    port_vol_str    = f"{port_vol:.2f}%" if not np.isnan(port_vol) else "n/a"

    sign_map = {c: s for c, (_, s) in CCY_TO_PAIR.items()}
    recon_js = []
    for _, r in recon.sort_values("net_model_units", key=abs, ascending=False).iterrows():
        ccy  = r["currency"]
        pair = pair_map.get(ccy, "")
        sign = sign_map.get(ccy, 1)
        actual = r["actual_notional"]
        live_ccy = int(actual * sign) if pd.notna(actual) else 0
        model_bu = int(r["model_usd_bu"]) if pd.notna(r["model_usd_bu"]) else 0
        scale    = r.get("scale_ratio")
        fitted   = int(r["fitted_bu_usd"]) if pd.notna(r.get("fitted_bu_usd")) else 0
        delta_f  = int(r["delta_fitted"])  if pd.notna(r.get("delta_fitted"))  else 0
        scale_js = "null" if (scale is None or (isinstance(scale, float) and np.isnan(scale))) \
                   else f"{scale:.3f}"
        recon_js.append(
            f'  {{ccy:{json.dumps(ccy)},pair:{json.dumps(pair)},'
            f'live_ccy:{live_ccy},model:{model_bu},'
            f'scale:{scale_js},fitted:{fitted},delta_f:{delta_f}}}'
        )

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
        rb  = int(round(m["dollar_notl"])) if m["dollar_notl"] == m["dollar_notl"] else 0
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
            f'wt:{m["vol_weight"]*100:.2f},rb:{rb},'
            f'ccys:[{ccys_js}]}}'
        )

    # ── assemble HTML ─────────────────────────────────────────────────────────
    weights_block      = ",\n".join(weights_js)
    summary_block      = ",\n".join(summary_js)
    recon_block        = ",\n".join(recon_js)
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

<h2>1 &middot; Model Weights &nbsp;<span style="font-weight:400;text-transform:none;letter-spacing:0;font-size:10.5px">&mdash; vol-adjusted, sorted by portfolio weight</span></h2>
<div class="tbl-wrap">
<table>
  <thead>
    <tr>
      <th class="left">Strategy</th>
      <th class="left">Category</th>
      <th>Risk alloc</th>
      <th>42d vol</th>
      <th>Portfolio weight</th>
      <th>Risk budget</th>
      <th class="left" style="padding-left:20px">Weight</th>
    </tr>
  </thead>
  <tbody id="wt-body"></tbody>
</table>
</div>
<p style="color:var(--muted);font-size:10.5px;margin-top:8px">
  <strong style="color:var(--text)">Risk budget</strong> = dollars allocated to this model after vol-risk targeting
  (AUM &times; {TARGET_VOL:.0%} &times; risk_alloc_share &divide; 42d&nbsp;vol).
  A higher-vol model gets a smaller dollar allocation for the same risk budget.
</p>

<h2>2 &middot; Net Position Summary &nbsp;<span style="font-weight:400;text-transform:none;letter-spacing:0;font-size:10.5px">&mdash; all currencies, sorted by |bottom-up USD|</span></h2>
<div class="tbl-wrap">
<table>
  <thead>
    <tr>
      <th class="left">Currency</th>
      <th class="left">Pair</th>
      <th>Bottom-up USD</th>
      <th>Net signal</th>
      <th># Models</th>
      <th class="left">Top driver</th>
      <th>Driver %</th>
    </tr>
  </thead>
  <tbody id="summary-body"></tbody>
</table>
</div>
<p style="color:var(--muted);font-size:10.5px;margin-top:8px">
  <strong style="color:var(--text)">Bottom-up USD</strong> = sum of (raw&nbsp;position&nbsp;&divide;&nbsp;100) &times; risk&nbsp;budget across all models for that currency.
  &nbsp;&nbsp;<strong style="color:var(--text)">Net signal</strong> = vol-weighted sum (dimensionless).
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

<h2>5 &middot; Reconciliation
  <span style="font-weight:400;text-transform:none;letter-spacing:0;font-size:10.5px">&mdash; bottom-up vs live</span>
</h2>
<div style="background:#13161f;border:1px solid var(--border);border-radius:6px;
            padding:12px 16px;margin-bottom:14px;font-size:11.5px;
            display:flex;gap:28px;flex-wrap:wrap;">
  <span style="color:var(--muted)">Target vol <strong style="color:var(--text)">{TARGET_VOL:.0%}</strong></span>
  <span style="color:var(--muted)">Pre-diversification vol <strong style="color:var(--muted)">{port_vol_str}</strong></span>
  <span style="color:var(--muted)">Diversification scalar <strong style="color:var(--muted)">{port_scalar_str}</strong></span>
  <span style="color:var(--muted)">BU gross <strong style="color:var(--text)">${bu_gross:,}</strong></span>
  <span style="color:var(--muted)">Live gross <strong style="color:var(--text)">${live_gross:,}</strong></span>
  <span style="color:var(--muted)">Naive ratio <strong style="color:var(--text)">{naive_ratio:.3f}&times;</strong></span>
  <span style="color:var(--muted)">OLS residual <strong style="color:var(--muted)">{ols_scale_str}</strong></span>
</div>
<div class="tbl-wrap">
<table>
  <thead>
    <tr>
      <th class="left">Currency</th>
      <th class="left">Pair</th>
      <th>Live USD (CCY basis)</th>
      <th>Model bottom-up USD</th>
      <th>&Delta;</th>
      <th>Scale ratio</th>
      <th>Fitted BU &times;N</th>
      <th>&Delta; fitted</th>
      <th>Direction</th>
    </tr>
  </thead>
  <tbody id="recon-body"></tbody>
</table>
</div>
<p style="color:var(--muted);font-size:10.5px;margin-top:8px">
  <strong style="color:var(--text)">Live USD</strong>: position file notional in long-CCY convention (USD/CCY pairs sign-flipped).
  &nbsp;&nbsp;<strong style="color:var(--text)">Model bottom-up USD</strong>: &sum;(raw&nbsp;position &divide; 100 &times; risk&nbsp;budget) across all models.
  Risk budgets are portfolio-level vol-targeted: each model&rsquo;s isolated notional is scaled by the diversification ratio ({port_scalar_str})
  so the aggregate portfolio vol hits {TARGET_VOL:.0%}.
  &nbsp;&nbsp;<strong style="color:var(--text)">Scale ratio</strong>: live &divide; bottom-up per currency.
  &nbsp;&nbsp;<strong style="color:var(--text)">&Delta; fitted</strong>: residual after applying OLS scalar.
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

const RECON = [
{recon_block}
];

const OLS_SCALE = {ols_scale_js};

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
    <td>${{(w.alloc*100).toFixed(0)}}%</td>
    <td>${{w.vol.toFixed(2)}}%</td>
    <td>${{(w.wt*100).toFixed(2)}}%</td>
    <td>$${{w.rb.toLocaleString()}}</td>
    <td class="left" style="padding-left:20px"><span class="spark" style="width:${{bw}}px"></span></td>
  </tr>`;
}}).join("");

// 2. Summary
document.getElementById("summary-body").innerHTML = SUMMARY.map(s => {{
  return `<tr>
    <td class="left"><strong style="font-size:13.5px;letter-spacing:.05em">${{s.ccy}}</strong></td>
    <td class="left muted">${{s.pair}}</td>
    <td class="${{cls(s.usd)}}">${{fmtUSD(s.usd)}}</td>
    <td class="${{cls(s.sig)}}">${{(s.sig>=0?"+":"")+s.sig.toFixed(3)}}</td>
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
      <span class="bar-pct ${{pos>=0?'pos':'neg'}}" style="width:60px;min-width:60px">${{pos>=0?"+":""+pos.toFixed(1)}}</span>
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
      <span>Weight <strong style="color:var(--text)">${{m.wt.toFixed(2)}}%</strong></span>
      <span>Risk budget <strong style="color:var(--text)">$${{m.rb.toLocaleString()}}</strong></span>
      <span>${{m.ccys.length}} CCY${{m.ccys.length>1?"s":""}}</span>
    </div>
    ${{bars}}
  </div>`;
}}).join("");

// 5. Reconciliation
document.getElementById("recon-body").innerHTML = RECON.map(r => {{
  const delta = r.model - r.live_ccy;
  const absDelta = Math.abs(delta);
  const pct = r.live_ccy !== 0 ? absDelta / Math.abs(r.live_ccy) * 100 : 0;
  // Amber when delta > 200% of live (sign flip or extreme scale mismatch); muted otherwise
  const deltaClass = pct < 200 ? "delta-ok" : "delta-warn";
  const dirOk = (r.live_ccy > 0) === (r.model > 0);
  // Scale ratio — amber if outlier (>8× indicates near-cancellation)
  const scaleStr = r.scale != null ? r.scale.toFixed(3) + "\u00d7" : "\u2014";
  const scaleColor = (r.scale != null && Math.abs(r.scale) > 8) ? "var(--amber)" : "var(--muted)";
  // Fitted BU
  const fittedStr = fmtUSD(r.fitted);
  // Delta fitted — amber when residual > $100k
  const deltaFStr = r.delta_f >= 0 ? "+" + fmtUSD(r.delta_f).replace("+","") : fmtUSD(r.delta_f);
  const deltaFColor = Math.abs(r.delta_f) > 100000 ? "var(--amber)" : "var(--muted)";
  return `<tr>
    <td class="left"><strong>${{r.ccy}}</strong></td>
    <td class="left muted">${{r.pair}}</td>
    <td class="${{cls(r.live_ccy)}}">${{fmtUSD(r.live_ccy)}}</td>
    <td class="${{cls(r.model)}}">${{fmtUSD(r.model)}}</td>
    <td class="${{deltaClass}}">${{delta >= 0 ? "+" : ""}}${{fmtUSD(delta).replace("+","").replace("-","")}}</td>
    <td style="text-align:right;color:${{scaleColor}};font-size:11px">${{scaleStr}}</td>
    <td class="${{cls(r.fitted)}}">${{fittedStr}}</td>
    <td style="text-align:right;color:${{deltaFColor}};font-size:11px">${{deltaFStr}}</td>
    <td style="text-align:center;font-weight:700;color:${{dirOk?'var(--green)':'var(--red)'}}">${{dirOk ? "✓" : "✗"}}</td>
  </tr>`;
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

    print(f"  Computing portfolio-level vol scalar...")
    portfolio_scalar, portfolio_vol = compute_portfolio_scalar(alloc, target_date)
    print(f"  Portfolio vol (42d): {portfolio_vol:.2f}%  |  "
          f"Scalar: {portfolio_scalar:.3f}x  "
          f"(diversification uplift to hit {TARGET_VOL:.0%} target)")

    print(f"  Loading signal files for {target_date.date()}...")
    pos_matrix = build_position_matrix(alloc, target_date, portfolio_scalar)
    n_valid = pos_matrix["vol_42d"].notna().sum()
    print(f"  {len(pos_matrix)} / {len(alloc)} models loaded  |  "
          f"{n_valid} with valid vol\n")

    port_pos = load_portfolio_positions(target_date)
    attr = compute_attribution(pos_matrix)

    # ── save outputs ──────────────────────────────────────────────────────────
    OUTPUT_DIR.mkdir(exist_ok=True)
    date_str = target_date.strftime("%Y%m%d")

    attr_path  = OUTPUT_DIR / f"attribution_10014_{date_str}.csv"
    recon_path = OUTPUT_DIR / f"reconciliation_10014_{date_str}.csv"
    wt_path    = OUTPUT_DIR / f"model_weights_10014_{date_str}.csv"

    attr.to_csv(attr_path, index=False)
    recon = reconcile(attr, port_pos)
    recon.attrs["portfolio_scalar"] = round(portfolio_scalar, 4)
    recon.attrs["portfolio_vol"]    = round(portfolio_vol, 2)
    recon.to_csv(recon_path, index=False)

    wt_out = pos_matrix[["model_id", "strategy_name", "category",
                          "risk_alloc", "vol_42d", "vol_weight", "dollar_notl"]].copy()
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
    wt_display["vol_42d"]    = wt_display["vol_42d"].map(lambda x: f"{x:.2f}%")
    wt_display["vol_weight"] = wt_display["vol_weight"].map(lambda x: f"{x:.3f}")
    wt_display["dollar_notl"] = wt_display["dollar_notl"].map(
        lambda x: f"${x:,.0f}" if x == x else "n/a")
    print("── Model weights (vol-adjusted, target vol 10%) ──")
    print(wt_display.to_string(index=False))

    # ── net position summary ──────────────────────────────────────────────────
    net_summary = (
        attr.groupby("currency")
        .agg(
            net_units  =("net_weighted_pos", "first"),
            bu_usd     =("usd_contrib",      "sum"),
            n_models   =("model_id",         "count"),
            top_driver =("strategy_name",    "first"),
            top_pct    =("pct_of_net",       "first"),
        )
        .reset_index()
        .sort_values("net_units", key=abs, ascending=False)
    )
    net_summary["bu_usd"] = net_summary["bu_usd"].map(lambda x: f"${x:,.0f}")

    print("\n── Net position per currency (bu_usd = bottom-up reconstruction) ──\n")
    print(net_summary.to_string(index=False))

    # ── per-currency driver detail (top 8 by abs net units) ──────────────────
    top_ccys = (
        attr.groupby("currency")["net_weighted_pos"]
        .first()
        .abs()
        .nlargest(8)
        .index.tolist()
    )
    for ccy in top_ccys:
        sub = attr[attr["currency"] == ccy][
            ["strategy_name", "category", "raw_position",
             "weighted_pos", "pct_of_net", "usd_contrib"]
        ].copy()
        net_u   = attr.loc[attr["currency"] == ccy, "net_weighted_pos"].iloc[0]
        net_usd = sub["usd_contrib"].sum()
        sub["usd_contrib"] = sub["usd_contrib"].map(lambda x: f"${x:,.0f}")
        print(f"\n── {ccy}  net: {net_u:+.3f} units  |  bu_usd: ${net_usd:,.0f} ──")
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
