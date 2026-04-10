#!/usr/bin/env python
"""
Market & Model Analysis Dashboard
==================================
Reads directly from OneDrive Prod1 data and provides interactive analysis
across three views: Model Performance, Market Data & Signals, Risk & Volatility.

Usage:
    streamlit run bin/market_dashboard.py
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from functools import reduce
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import streamlit as st

# ---------------------------------------------------------------------------
# Path setup — allow imports from repo root
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv

load_dotenv(REPO_ROOT / ".env", override=True)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
TRADING_DAYS = 260  # annualisation factor from fx_analysis_config
PROD1_SUBDIR = "Prod1"

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Market & Model Analysis",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ---------------------------------------------------------------------------
# Data-loading helpers (all read-only, cached)
# ---------------------------------------------------------------------------
def _get_od_root() -> Path:
    """Resolve the OneDrive root from the OD env-var."""
    od = os.getenv("OD")
    if not od:
        st.error("Missing `OD` environment variable. Set it in `.env`.")
        st.stop()
    return Path(od)


def _get_prod1_path() -> Path:
    """Return the Prod1 data directory path."""
    return _get_od_root() / PROD1_SUBDIR


def _get_models_path() -> Path:
    """Return the models_signals_systemacro directory path."""
    return _get_od_root() / "clean" / "models_signals_systemacro"


@st.cache_data(ttl=600)
def discover_data_root() -> dict:
    """Discover available data locations and return a summary."""
    prod1 = _get_prod1_path()
    models = _get_models_path()
    info: dict = {"prod1_exists": prod1.exists(), "models_exists": models.exists()}

    # Discover what's in Prod1
    if prod1.exists():
        all_items = list(prod1.iterdir())
        info["prod1_path"] = str(prod1)
        info["prod1_csvs"] = sorted([f.name for f in all_items if f.suffix.lower() == ".csv"])
        info["prod1_xlsx"] = sorted([f.name for f in all_items if f.suffix.lower() in (".xlsx", ".xls")])
        info["prod1_dirs"] = sorted([f.name for f in all_items if f.is_dir()])
    else:
        info["prod1_path"] = str(prod1)
        info["prod1_csvs"] = []
        info["prod1_xlsx"] = []
        info["prod1_dirs"] = []

    # Check models directory
    if models.exists():
        model_files = sorted([f.name for f in models.iterdir() if f.suffix.lower() == ".csv"])
        info["model_csvs"] = model_files
        info["models_path"] = str(models)
    else:
        info["model_csvs"] = []
        info["models_path"] = str(models)

    return info


@st.cache_data(ttl=600)
def load_model_index(base_path: str) -> pd.DataFrame | None:
    """Load Model_Index.csv from the given base path."""
    idx_path = Path(base_path) / "Model_Index.csv"
    if not idx_path.exists():
        return None
    df = pd.read_csv(idx_path)
    return df


@st.cache_data(ttl=600)
def load_single_model_csv(filepath: str) -> pd.DataFrame | None:
    """Load a single model CSV and return a 2-col DataFrame (Date, return)."""
    try:
        df = pd.read_csv(filepath)
    except Exception:
        return None

    # Find date column
    date_col = None
    for candidate in ("Date", "date", "DATE", "Category"):
        if candidate in df.columns:
            date_col = candidate
            break
    if date_col is None:
        return None

    df["Date"] = pd.to_datetime(df[date_col], dayfirst=True, errors="coerce")

    # Find return column (ID:xxxx but not ex-carry)
    ret_cols = [c for c in df.columns if "ID:" in c and "(ex carry)" not in c]
    if not ret_cols:
        # Fallback: look for any numeric column that isn't the date
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        if numeric_cols:
            ret_cols = numeric_cols[:1]
        else:
            return None

    return df[["Date", ret_cols[0]]].dropna(subset=["Date"]).copy()


@st.cache_data(ttl=600)
def load_master_matrix_from_od(base_path: str, max_models: int = 300) -> pd.DataFrame:
    """Build a consolidated return matrix from individual model CSVs."""
    base = Path(base_path)
    model_files = sorted([f for f in base.glob("*.csv") if re.match(r"\d+_.*\.csv", f.name)])

    model_index = load_model_index(base_path)
    model_dfs: list[pd.DataFrame] = []

    for fpath in model_files[:max_models]:
        match = re.match(r"(\d+)_(.*)\.csv", fpath.name)
        if not match:
            continue
        model_id = int(match.group(1))

        # Determine label
        if model_index is not None and "ID" in model_index.columns:
            row = model_index.loc[model_index["ID"] == model_id]
            name = row.iloc[0]["Name"] if not row.empty else match.group(2)
        else:
            name = match.group(2)

        label = f"{model_id} - {name}"
        single = load_single_model_csv(str(fpath))
        if single is not None:
            single.columns = ["Date", label]
            model_dfs.append(single)

    if not model_dfs:
        return pd.DataFrame()

    master = reduce(lambda l, r: pd.merge(l, r, on="Date", how="outer"), model_dfs)
    master.sort_values("Date", inplace=True)
    master.set_index("Date", inplace=True)
    return master


@st.cache_data(ttl=600)
def load_csv_auto(filepath: str) -> pd.DataFrame:
    """General-purpose CSV loader with date detection."""
    df = pd.read_csv(filepath)
    for col in ("Date", "date", "DATE", "Timestamp", "timestamp"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], dayfirst=True, errors="coerce")
            df.set_index(col, inplace=True)
            break
    return df


@st.cache_data(ttl=600)
def load_consolidated_csv(filepath: str) -> pd.DataFrame:
    """Load a pre-consolidated matrix CSV (e.g. Master_Return_Matrix.csv).

    Handles files where columns are already 'ID - Name' format with a Date index.
    """
    df = pd.read_csv(filepath)
    for col in ("Date", "date", "DATE"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], dayfirst=True, errors="coerce")
            df.set_index(col, inplace=True)
            df.sort_index(inplace=True)
            return df
    return df


# ---------------------------------------------------------------------------
# Calculation helpers
# ---------------------------------------------------------------------------
def cumulative_to_daily(cum_returns: pd.Series) -> pd.Series:
    """Convert cumulative % returns to daily decimal returns."""
    return cum_returns.diff() / 100


def calc_metrics(cum_series: pd.Series) -> dict:
    """Calculate standard performance metrics from a cumulative return series."""
    daily = cumulative_to_daily(cum_series).dropna()
    if len(daily) < 2:
        return {}

    cum_prod = (1 + daily).cumprod()
    n = len(daily)

    ann_ret = (cum_prod.iloc[-1] ** (TRADING_DAYS / n) - 1) * 100
    ann_vol = daily.std() * np.sqrt(TRADING_DAYS)
    sharpe = np.nan
    if ann_vol > 0:
        # Monthly Sharpe → annualised
        monthly = cum_prod.resample("ME").last().pct_change().dropna()
        if len(monthly) > 1 and monthly.std() > 0:
            sharpe = (monthly.mean() / monthly.std()) * np.sqrt(12)

    running_max = cum_prod.expanding().max()
    drawdown = (cum_prod - running_max) / running_max
    max_dd = drawdown.min()

    total_ret = (cum_prod.iloc[-1] - 1) * 100

    return {
        "ann_return_pct": round(ann_ret, 3),
        "total_return_pct": round(total_ret, 3),
        "ann_vol": round(ann_vol, 4),
        "sharpe": round(sharpe, 3) if not np.isnan(sharpe) else np.nan,
        "max_drawdown": round(max_dd, 4),
        "n_days": n,
    }


def rolling_vol(daily_returns: pd.Series, window: int) -> pd.Series:
    """Rolling annualised volatility."""
    return daily_returns.rolling(window).std() * np.sqrt(TRADING_DAYS)


def rolling_sharpe(daily_returns: pd.Series, window: int) -> pd.Series:
    """Rolling annualised Sharpe (daily basis)."""
    roll_mean = daily_returns.rolling(window).mean() * TRADING_DAYS
    roll_std = daily_returns.rolling(window).std() * np.sqrt(TRADING_DAYS)
    return roll_mean / roll_std


# ---------------------------------------------------------------------------
# Sidebar — data source selection
# ---------------------------------------------------------------------------
st.sidebar.title("📊 Market & Model Analysis")

data_info = discover_data_root()

# Show data discovery results
with st.sidebar.expander("Data Sources", expanded=True):
    st.caption(f"OD root: `{os.getenv('OD', 'NOT SET')}`")

    if data_info["prod1_exists"]:
        st.success(f"Prod1: {len(data_info['prod1_csvs'])} CSVs, {len(data_info['prod1_dirs'])} subdirs")
    else:
        st.warning("Prod1 directory not found")

    if data_info["models_exists"]:
        st.success(f"Models: {len(data_info['model_csvs'])} CSVs")
    else:
        st.warning("Models directory not found")

# Choose primary data source
source_options = []
if data_info["prod1_exists"]:
    source_options.append("Prod1")
if data_info["models_exists"]:
    source_options.append("models_signals_systemacro")

if not source_options:
    st.error("No data sources found. Check your OD environment variable and OneDrive sync.")
    st.stop()

primary_source = st.sidebar.selectbox("Primary data source", source_options)

if primary_source == "Prod1":
    data_base_path = data_info["prod1_path"]
    # Check if Prod1 has model-style CSVs directly or in subdirs
    prod1_path = Path(data_base_path)
    model_csvs_direct = [f for f in data_info["prod1_csvs"] if re.match(r"\d+_.*\.csv", f)]

    if model_csvs_direct:
        model_data_path = data_base_path
    elif data_info["prod1_dirs"]:
        # Let user choose a subdirectory
        subdir = st.sidebar.selectbox("Subdirectory", ["(root)"] + data_info["prod1_dirs"])
        if subdir == "(root)":
            model_data_path = data_base_path
        else:
            model_data_path = str(prod1_path / subdir)
    else:
        model_data_path = data_base_path
else:
    model_data_path = data_info["models_path"]


# Date range filter
st.sidebar.markdown("---")
st.sidebar.subheader("Date Range")
date_preset = st.sidebar.selectbox(
    "Preset",
    ["Full History", "10 Years", "5 Years", "2 Years", "1 Year", "6 Months", "3 Months", "1 Month"],
    index=0,
)

PRESET_DAYS = {
    "Full History": None,
    "10 Years": 3650,
    "5 Years": 1825,
    "2 Years": 730,
    "1 Year": 365,
    "6 Months": 182,
    "3 Months": 91,
    "1 Month": 30,
}


def filter_by_date(df: pd.DataFrame, preset: str) -> pd.DataFrame:
    """Filter a DatetimeIndex DataFrame by the sidebar preset."""
    days = PRESET_DAYS.get(preset)
    if days is None or df.empty:
        return df
    cutoff = df.index.max() - pd.Timedelta(days=days)
    return df.loc[df.index >= cutoff]


# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
with st.spinner("Loading model data from OneDrive…"):
    master = load_master_matrix_from_od(model_data_path)

    # Fallback: try to find a pre-consolidated master matrix in Prod1
    if master.empty:
        data_dir = Path(model_data_path)
        candidates = [
            "Master_Return_Matrix.csv",
            "master_return_matrix.csv",
            "returns.csv",
            "model_returns.csv",
        ]
        for cand in candidates:
            cand_path = data_dir / cand
            if cand_path.exists():
                master = load_consolidated_csv(str(cand_path))
                if not master.empty:
                    st.sidebar.info(f"Loaded consolidated file: {cand}")
                    break

        # Second fallback: load ANY CSV that has a Date column and multiple numeric cols
        if master.empty:
            for csv_file in sorted(data_dir.glob("*.csv")):
                try:
                    candidate_df = load_consolidated_csv(str(csv_file))
                    numeric_cols = candidate_df.select_dtypes(include=[np.number]).columns
                    if isinstance(candidate_df.index, pd.DatetimeIndex) and len(numeric_cols) > 3:
                        master = candidate_df
                        st.sidebar.info(f"Auto-detected matrix: {csv_file.name}")
                        break
                except Exception:
                    continue

if master.empty:
    st.warning(
        f"No model data found at `{model_data_path}`. "
        "Check that the directory contains CSVs matching the `<id>_<name>.csv` pattern, "
        "or a consolidated matrix with a Date column."
    )

    # Show what IS available so the user can debug
    with st.expander("Available files at this location"):
        avail_path = Path(model_data_path)
        if avail_path.exists():
            for f in sorted(avail_path.iterdir()):
                st.text(f"{'[DIR]' if f.is_dir() else '     '} {f.name}")
        else:
            st.error(f"Path does not exist: {model_data_path}")
    st.stop()

model_index = load_model_index(model_data_path)

# Model columns
model_cols = [c for c in master.columns if " - " in c]
n_models = len(model_cols)

# Apply date filter
master_filtered = filter_by_date(master, date_preset)

st.sidebar.metric("Models loaded", n_models)
st.sidebar.metric("Date range", f"{master_filtered.index.min():%Y-%m-%d} → {master_filtered.index.max():%Y-%m-%d}")

# Model selector in sidebar
st.sidebar.markdown("---")
st.sidebar.subheader("Model Filter")

# Category filter (if model index available)
categories = ["All"]
families = ["All"]
if model_index is not None:
    if "CATEGORY" in model_index.columns:
        categories += sorted(model_index["CATEGORY"].dropna().unique().tolist())
    if "FAMILY" in model_index.columns:
        families += sorted(model_index["FAMILY"].dropna().unique().tolist())

sel_category = st.sidebar.selectbox("Category", categories)
sel_family = st.sidebar.selectbox("Family", families)


def _filter_model_cols(cols: list[str], category: str, family: str) -> list[str]:
    """Filter model columns by category/family using model_index."""
    if model_index is None or (category == "All" and family == "All"):
        return cols

    filtered_ids = set()
    mi = model_index.copy()
    if category != "All" and "CATEGORY" in mi.columns:
        mi = mi[mi["CATEGORY"] == category]
    if family != "All" and "FAMILY" in mi.columns:
        mi = mi[mi["FAMILY"] == family]

    filtered_ids = set(mi["ID"].astype(str).tolist()) if "ID" in mi.columns else set()

    result = []
    for c in cols:
        mid = c.split(" - ")[0].strip()
        if mid in filtered_ids:
            result.append(c)
    return result if result else cols


active_cols = _filter_model_cols(model_cols, sel_category, sel_family)
st.sidebar.caption(f"Showing {len(active_cols)} of {n_models} models")


# ---------------------------------------------------------------------------
# TABS
# ---------------------------------------------------------------------------
tab_perf, tab_market, tab_risk = st.tabs(
    ["📈 Model Performance", "🌍 Market Data & Signals", "⚡ Risk & Volatility"]
)


# ===== TAB 1: MODEL PERFORMANCE ===========================================
with tab_perf:
    st.header("Model Performance")

    # Compute metrics for each model
    @st.cache_data(ttl=600)
    def compute_all_metrics(_df: pd.DataFrame, cols: tuple) -> pd.DataFrame:
        records = []
        for col in cols:
            m = calc_metrics(_df[col])
            if m:
                mid, mname = col.split(" - ", 1)
                m["model_id"] = int(mid)
                m["model_name"] = mname
                records.append(m)
        return pd.DataFrame(records)

    metrics_df = compute_all_metrics(master_filtered, tuple(active_cols))

    if metrics_df.empty:
        st.info("No metrics to display. Adjust date range or model filter.")
    else:
        # Enrich with category/family
        if model_index is not None and "ID" in model_index.columns:
            mi_slim = model_index[["ID"]].copy()
            if "CATEGORY" in model_index.columns:
                mi_slim["category"] = model_index["CATEGORY"]
            if "FAMILY" in model_index.columns:
                mi_slim["family"] = model_index["FAMILY"]
            metrics_df = metrics_df.merge(mi_slim, left_on="model_id", right_on="ID", how="left").drop(columns=["ID"], errors="ignore")

        # KPI row
        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("Models", len(metrics_df))
        col2.metric("Avg Ann. Return", f"{metrics_df['ann_return_pct'].mean():.2f}%")
        col3.metric("Avg Sharpe", f"{metrics_df['sharpe'].mean():.2f}")
        col4.metric("Avg Vol", f"{metrics_df['ann_vol'].mean():.4f}")
        col5.metric("Avg Max DD", f"{metrics_df['max_drawdown'].mean():.2%}")

        # Sortable table
        st.subheader("Performance Table")
        sort_col = st.selectbox(
            "Sort by",
            ["sharpe", "ann_return_pct", "ann_vol", "max_drawdown", "total_return_pct"],
            index=0,
        )
        ascending = sort_col in ("ann_vol", "max_drawdown")
        st.dataframe(
            metrics_df.sort_values(sort_col, ascending=ascending).reset_index(drop=True),
            use_container_width=True,
            height=500,
        )

        # --- Charts ---
        st.subheader("Cumulative Return Curves")
        top_n = st.slider("Show top N models (by Sharpe)", 5, min(50, len(active_cols)), 10)
        top_models = metrics_df.nlargest(top_n, "sharpe")["model_id"].tolist()
        top_cols = [c for c in active_cols if int(c.split(" - ")[0]) in top_models]

        # Build cumulative return index
        cum_chart_data = pd.DataFrame(index=master_filtered.index)
        for col in top_cols:
            daily = cumulative_to_daily(master_filtered[col]).fillna(0)
            cum_chart_data[col.split(" - ", 1)[1]] = (1 + daily).cumprod() - 1

        st.line_chart(cum_chart_data, height=450)

        # Scatter: Return vs Vol
        st.subheader("Return vs Volatility")
        scatter_df = metrics_df[["model_name", "ann_return_pct", "ann_vol", "sharpe"]].copy()
        scatter_df.columns = ["Model", "Ann Return %", "Ann Vol", "Sharpe"]
        st.scatter_chart(scatter_df, x="Ann Vol", y="Ann Return %", color="Sharpe", height=400)

        # Category breakdown
        if "category" in metrics_df.columns:
            st.subheader("Performance by Category")
            cat_summary = (
                metrics_df.groupby("category")[["ann_return_pct", "ann_vol", "sharpe", "max_drawdown"]]
                .agg(["mean", "count"])
                .round(3)
            )
            cat_summary.columns = [f"{m}_{s}" for m, s in cat_summary.columns]
            st.dataframe(cat_summary, use_container_width=True)


# ===== TAB 2: MARKET DATA & SIGNALS =======================================
with tab_market:
    st.header("Market Data & Signals")

    # Cross-model signal heatmap (latest positions)
    if not master_filtered.empty:
        st.subheader("Latest Model Signals (daily change)")

        latest_window = st.selectbox("Signal window (days)", [1, 5, 10, 20], index=0, key="sig_window")

        # Compute recent change for each model
        recent = master_filtered[active_cols].tail(latest_window + 1)
        if len(recent) > 1:
            signal_change = recent.iloc[-1] - recent.iloc[0]
            signal_df = pd.DataFrame({
                "model": [c.split(" - ", 1)[1] for c in signal_change.index],
                "signal_change": signal_change.values,
            }).sort_values("signal_change", ascending=False)

            # Color-coded bar chart
            pos = signal_df[signal_df["signal_change"] >= 0]
            neg = signal_df[signal_df["signal_change"] < 0]

            col_a, col_b = st.columns(2)
            with col_a:
                st.markdown("**Positive movers**")
                if not pos.empty:
                    st.bar_chart(pos.set_index("model").head(20), height=350)
                else:
                    st.caption("None")
            with col_b:
                st.markdown("**Negative movers**")
                if not neg.empty:
                    st.bar_chart(neg.set_index("model").tail(20), height=350)
                else:
                    st.caption("None")

        # Cross-model correlation heatmap
        st.subheader("Model Correlation Matrix")
        corr_n = st.slider("Top N models for correlation", 5, min(30, len(active_cols)), 10, key="corr_n")
        if not metrics_df.empty:
            corr_top_ids = metrics_df.nlargest(corr_n, "sharpe")["model_id"].tolist()
            corr_cols = [c for c in active_cols if int(c.split(" - ")[0]) in corr_top_ids]
            daily_rets = master_filtered[corr_cols].apply(cumulative_to_daily)
            corr_matrix = daily_rets.corr()
            # Shorten labels
            corr_matrix.index = [c.split(" - ", 1)[1][:25] for c in corr_matrix.index]
            corr_matrix.columns = corr_matrix.index
            st.dataframe(corr_matrix.style.background_gradient(cmap="RdYlGn", vmin=-1, vmax=1), use_container_width=True)

        # Signal momentum table
        st.subheader("Signal Momentum (multi-horizon)")
        horizons = {"1D": 1, "1W": 5, "1M": 20, "3M": 60}
        momentum_records = []
        for col in active_cols:
            mid, mname = col.split(" - ", 1)
            row = {"model_id": int(mid), "model": mname}
            series = master_filtered[col]
            for label, days in horizons.items():
                if len(series) > days:
                    row[label] = round(series.iloc[-1] - series.iloc[-1 - days], 3)
                else:
                    row[label] = np.nan
            momentum_records.append(row)

        momentum_df = pd.DataFrame(momentum_records)
        sort_momentum = st.selectbox("Sort momentum by", list(horizons.keys()), index=0)
        st.dataframe(
            momentum_df.sort_values(sort_momentum, ascending=False).reset_index(drop=True),
            use_container_width=True,
            height=500,
        )

    # Explore arbitrary CSVs from Prod1
    st.markdown("---")
    st.subheader("Explore Prod1 Files")
    prod1_all_csvs = data_info.get("prod1_csvs", [])
    if prod1_all_csvs:
        chosen_csv = st.selectbox("Select a CSV to preview", ["(none)"] + prod1_all_csvs)
        if chosen_csv != "(none)":
            preview_df = load_csv_auto(str(Path(data_info["prod1_path"]) / chosen_csv))
            st.dataframe(preview_df.head(200), use_container_width=True)
            st.caption(f"Shape: {preview_df.shape}")
    else:
        st.caption("No CSVs found in Prod1 root.")


# ===== TAB 3: RISK & VOLATILITY ===========================================
with tab_risk:
    st.header("Risk & Volatility Analysis")

    if not master_filtered.empty and not metrics_df.empty:
        # Select models
        risk_n = st.slider("Number of models to analyse", 3, min(20, len(active_cols)), 5, key="risk_n")
        risk_sort = st.selectbox("Select models by", ["sharpe", "ann_vol", "ann_return_pct"], key="risk_sort")
        ascending_risk = risk_sort == "ann_vol"
        risk_ids = metrics_df.nlargest(risk_n, risk_sort)["model_id"].tolist() if not ascending_risk else metrics_df.nsmallest(risk_n, risk_sort)["model_id"].tolist()
        risk_cols = [c for c in active_cols if int(c.split(" - ")[0]) in risk_ids]

        # Rolling volatility
        st.subheader("Rolling Volatility")
        vol_window = st.selectbox("Window (trading days)", [21, 42, 63, 126, 252], index=1, key="vol_win")

        vol_data = pd.DataFrame(index=master_filtered.index)
        for col in risk_cols:
            daily = cumulative_to_daily(master_filtered[col])
            vol_data[col.split(" - ", 1)[1]] = rolling_vol(daily, vol_window)

        st.line_chart(vol_data.dropna(how="all"), height=400)

        # Rolling Sharpe
        st.subheader("Rolling Sharpe Ratio")
        sharpe_data = pd.DataFrame(index=master_filtered.index)
        for col in risk_cols:
            daily = cumulative_to_daily(master_filtered[col])
            sharpe_data[col.split(" - ", 1)[1]] = rolling_sharpe(daily, vol_window)

        st.line_chart(sharpe_data.dropna(how="all"), height=400)

        # Drawdown chart
        st.subheader("Drawdown Curves")
        dd_data = pd.DataFrame(index=master_filtered.index)
        for col in risk_cols:
            daily = cumulative_to_daily(master_filtered[col]).fillna(0)
            cum = (1 + daily).cumprod()
            running_max = cum.expanding().max()
            dd_data[col.split(" - ", 1)[1]] = (cum - running_max) / running_max

        st.line_chart(dd_data.dropna(how="all"), height=400)

        # Volatility summary table
        st.subheader("Volatility Summary")
        vol_records = []
        for col in active_cols:
            mid, mname = col.split(" - ", 1)
            daily = cumulative_to_daily(master_filtered[col]).dropna()
            if len(daily) < 42:
                continue
            vol_records.append({
                "model_id": int(mid),
                "model": mname,
                "vol_full": round(daily.std() * np.sqrt(TRADING_DAYS), 4),
                "vol_252d": round(daily.tail(252).std() * np.sqrt(TRADING_DAYS), 4) if len(daily) >= 252 else np.nan,
                "vol_63d": round(daily.tail(63).std() * np.sqrt(TRADING_DAYS), 4) if len(daily) >= 63 else np.nan,
                "vol_21d": round(daily.tail(21).std() * np.sqrt(TRADING_DAYS), 4) if len(daily) >= 21 else np.nan,
            })

        vol_summary = pd.DataFrame(vol_records)
        if not vol_summary.empty:
            st.dataframe(
                vol_summary.sort_values("vol_full", ascending=True).reset_index(drop=True),
                use_container_width=True,
                height=500,
            )

        # Correlation heatmap for risk
        st.subheader("Risk Correlation (selected models)")
        daily_risk = master_filtered[risk_cols].apply(cumulative_to_daily)
        risk_corr = daily_risk.corr()
        risk_corr.index = [c.split(" - ", 1)[1][:25] for c in risk_corr.index]
        risk_corr.columns = risk_corr.index
        st.dataframe(
            risk_corr.style.background_gradient(cmap="coolwarm", vmin=-1, vmax=1),
            use_container_width=True,
        )

        # Tail risk metrics
        st.subheader("Tail Risk Metrics")
        tail_records = []
        for col in active_cols:
            mid, mname = col.split(" - ", 1)
            daily = cumulative_to_daily(master_filtered[col]).dropna()
            if len(daily) < 30:
                continue
            sorted_rets = daily.sort_values()
            tail_records.append({
                "model_id": int(mid),
                "model": mname,
                "worst_day": round(sorted_rets.iloc[0], 6),
                "VaR_5pct": round(sorted_rets.quantile(0.05), 6),
                "CVaR_5pct": round(sorted_rets[sorted_rets <= sorted_rets.quantile(0.05)].mean(), 6),
                "best_day": round(sorted_rets.iloc[-1], 6),
                "skew": round(daily.skew(), 3),
                "kurtosis": round(daily.kurtosis(), 3),
            })

        tail_df = pd.DataFrame(tail_records)
        if not tail_df.empty:
            st.dataframe(
                tail_df.sort_values("CVaR_5pct", ascending=True).reset_index(drop=True),
                use_container_width=True,
                height=500,
            )
    else:
        st.info("Load model data to see risk analytics.")


# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------
st.markdown("---")
st.caption(
    f"Data source: `{model_data_path}` · "
    f"Last refresh: {datetime.now():%Y-%m-%d %H:%M} · "
    f"Models: {n_models} · "
    f"Analytics-only: read-only consumer of FX data estate"
)
