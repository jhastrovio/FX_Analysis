# Market & Model Analysis Dashboard — Design Plan

**Owner:** James Hassett  
**Repo:** FX_Analysis  
**Data source:** Prod1 (OneDrive, read-only) — governed by `Prod1/_meta/manifests/manifest.json`  
**Framework:** Streamlit  
**Scope:** Working prototype  

---

## 1. Data Contract

All data is read from Prod1 via the `OD` environment variable. The manifest.json in `_meta/manifests/` is the single source of truth for schemas, paths, and column definitions. No guessing or fallback logic — if a dataset isn't described in the manifest, it's not consumed.

**Prod1 root:** `${OD}/Prod1` (note: current `.env` sets OD to `…/FX_Data - Documents/General`, so Prod1 is a subdirectory)

### 1.1 Datasets the dashboard will consume

| Dataset | Area | Path Pattern | Key Columns | Use |
|---------|------|-------------|-------------|-----|
| `models_signals_systemacro` | clean | `clean/models_signals_systemacro/latest/{id}_{name}.csv` | date, Category, ID, return, return_ex_carry, 24 ccy allocations | Model performance, signal analysis |
| `Model_Index.csv` | _meta | `_meta/Model_Index.csv` | Name, ID, CATEGORY, FAMILY | Model metadata, filtering |
| `eod_portfolio` | auth | `auth/eod_portfolio/Year={yyyy}/YM=…/eod_portfolio_{ts}.csv` | symbol, eod_date, mid, prev_close_mid, pct_change, abs_change | Market rates, daily changes |
| `eod_daily` | publish | `publish/eod_daily/Year={yyyy}/YM=…/eod_daily-{date}-{cut}.csv` | symbol, eod_date, cut_label, mid | Simpler market rate view |
| `market_changes` | publish | `publish/market_changes/Year={yyyy}/YM=…/market_changes_{date}.csv` | symbol, pct_change_1d/3d/1w/1m | Multi-horizon FX moves |
| `eod_xasset` | publish | `publish/eod_xasset/Year={yyyy}/YM=…/eod_xasset-{date}-{cut}.csv` | symbol, asset_class, close | Cross-asset context (SPX, US10Y) |
| `positions_derived` | auth | `auth/positions_derived/Year={yyyy}/YM=…/positions_derived-{date}.csv` | symbol, target_exposure, broker_exposure, exposure_usd | Portfolio exposure |
| `portfolio_construction_state` | auth | `auth/portfolio_construction_state/Year={yyyy}/YM=…/…-{date}.csv` | instrument, final_position | Current portfolio state |
| `pnl_hourly` | publish | `publish/pnl_hourly/Year={yyyy}/YM=…/pnl_hourly_{ts}.csv` | symbol, px_open, px_now, dpx, pct | Intraday P&L |
| `eod_pnl` | auth | `auth/eod_pnl/Year={yyyy}/YM=…/eod_pnl_{date}_1100.csv` | symbol, pnl_abs, pnl_pct, pnl_abs_wtd/mtd/ytd | EOD P&L attribution |

---

## 2. Architecture

```
bin/market_dashboard.py          ← Streamlit entrypoint
lib/dashboard/
    __init__.py
    manifest.py                  ← Manifest parser: reads manifest.json, resolves paths
    loaders.py                   ← Dataset loaders: one function per dataset, all @st.cache_data
    calculations.py              ← Perf metrics, rolling stats, risk calcs (reuse from lib/)
    components.py                ← Reusable Streamlit chart/table components
```

### 2.1 `manifest.py` — Manifest-driven data access

The manifest parser reads `Prod1/_meta/manifests/manifest.json` and provides:
- `resolve_path(dataset, date=None, **kwargs)` → absolute file path for a dataset
- `latest_file(dataset)` → most recent file matching the path pattern
- `list_files(dataset, year=None)` → all files for a dataset
- `get_schema(dataset)` → column list, required columns
- `get_datasets_by_domain(domain)` → filter by domain (market, models, pnl, etc.)

This replaces all guessing / fallback logic. Every file access goes through the manifest.

### 2.2 `loaders.py` — Cached data loaders

Each loader function takes a dataset name and optional date parameters, uses `manifest.py` to resolve the file path, loads the CSV, and validates columns against the manifest schema.

Key loaders:
- `load_model_signals(model_id=None)` → load from `latest/` dir, returns DataFrame with date index
- `load_model_index()` → load `_meta/Model_Index.csv`
- `load_all_model_returns()` → consolidate all 115 latest model CSVs into a return matrix
- `load_eod_rates(date_range)` → stack eod_daily or eod_portfolio CSVs across dates
- `load_market_changes(date)` → single-date multi-horizon FX changes
- `load_positions(date)` → positions_derived for a specific date
- `load_portfolio_state(date)` → portfolio_construction_state
- `load_pnl(date)` → pnl_hourly or eod_pnl

### 2.3 `calculations.py`

Reuse existing logic from `lib/summary_statistics.py` and `lib/risk/volatility.py`:
- `calc_model_metrics(cum_returns)` → ann_return, vol, sharpe, max_dd, total_return
- `rolling_vol(daily, window)` / `rolling_sharpe(daily, window)`
- `correlation_matrix(daily_returns)`
- `calc_var_cvar(daily_returns, level=0.05)`

---

## 3. Dashboard Tabs

### Tab 1: 📈 Model Performance

**Data:** `models_signals_systemacro/latest/`, `Model_Index.csv`

**Sidebar controls:**
- Date range preset (Full / 10Y / 5Y / 2Y / 1Y / 6M / 3M / 1M)
- Category filter (from Model_Index CATEGORY)
- Family filter (from Model_Index FAMILY)

**Content:**
1. **KPI row** — # models, avg ann return, avg Sharpe, avg vol, avg max DD
2. **Performance table** — sortable by any metric, with model_id, name, category, family, all metrics
3. **Cumulative return curves** — top N models by Sharpe, line chart
4. **Return vs Volatility scatter** — all models, color by Sharpe
5. **Category/Family breakdown** — grouped mean metrics table

### Tab 2: 🌍 Market Data & Signals

**Data:** `eod_portfolio` or `eod_daily`, `market_changes`, `eod_xasset`, `models_signals_systemacro`

**Content:**
1. **FX Rate Dashboard** — latest EOD rates for all 24 symbols, with 1d/3d/1w/1m changes from `market_changes`. Color-coded (green/red).
2. **Cross-asset context** — SPX, US10Y from `eod_xasset`
3. **Currency signal heatmap** — aggregate model signals (from the 24 currency allocation columns in model CSVs) across all models. Shows net signal per currency.
4. **Signal momentum** — model-level return changes over 1D/1W/1M/3M horizons
5. **Model correlation matrix** — top N models, using daily returns

### Tab 3: ⚡ Risk & Volatility

**Data:** `models_signals_systemacro`, `positions_derived`, `portfolio_construction_state`, `pnl_hourly`, `eod_pnl`

**Content:**
1. **Portfolio exposure summary** — from `positions_derived`: current exposure by symbol (USD terms), bar chart
2. **Rolling volatility** — configurable window, for selected models
3. **Rolling Sharpe** — same window, same models
4. **Drawdown curves** — selected models
5. **Volatility summary table** — full/252d/63d/21d trailing vol for all models
6. **Tail risk metrics** — worst day, VaR 5%, CVaR 5%, skew, kurtosis
7. **Risk correlation** — correlation between selected model returns
8. **P&L summary** (if `eod_pnl` data available) — daily/WTD/MTD/YTD P&L by symbol

---

## 4. Implementation Steps (for Claude Code)

### Step 1: Create `lib/dashboard/manifest.py`
- Parse `manifest.json`
- Resolve Hive-style partition paths (`Year={yyyy}/YM={mon_abbrev}_{yy}/`)
- Find latest file for any dataset
- Validate column presence

### Step 2: Create `lib/dashboard/loaders.py`
- One loader per dataset
- All `@st.cache_data(ttl=600)`
- Use `manifest.py` for all path resolution
- Handle the unstructured `position_systemacro` CSV (skip header rows)
- Handle the `latest/` symlink directory for model signals

### Step 3: Create `lib/dashboard/calculations.py`
- Extract reusable calc logic from existing `lib/summary_statistics.py` and `lib/risk/volatility.py`
- Add: correlation matrix, VaR/CVaR, signal aggregation

### Step 4: Create `lib/dashboard/components.py`
- Reusable Streamlit components: KPI row, metric table, currency heatmap, time series chart

### Step 5: Build `bin/market_dashboard.py`
- Wire tabs together using loaders + calculations + components
- Sidebar: data source info, date range, model filters
- Footer: data source path, last refresh, model count

### Step 6: Update `.env` and config
- Add `PROD1` path variable or document that Prod1 is `${OD}/Prod1`
- No changes to existing configs needed (this is additive)

### Step 7: Test
- Run `streamlit run bin/market_dashboard.py` locally
- Verify each tab loads data correctly
- Check edge cases: missing dates, locked files (OneDrive sync)

---

## 5. Key Design Decisions

1. **Manifest-driven, not guessing.** Every file access goes through the manifest. No fallback discovery.
2. **`latest/` directory for models.** The `clean/models_signals_systemacro/latest/` directory contains undated model CSVs (the full history for each model). Use these rather than the date-stamped snapshots.
3. **Schema v2 for model signals.** Columns are: `date, Category, ID, return, return_ex_carry, SPX, US10Y, {24 currencies}`. The `return` column is cumulative %. Currency columns are net FX allocations (long + short).
4. **Hive-style partitions.** Most auth/publish datasets use `Year={yyyy}/YM={Mon_yy}/` partitioning. The manifest parser must resolve these.
5. **Read-only contract.** The dashboard never writes to Prod1. All ephemeral outputs go to `outputs/`.
6. **Reuse existing lib code.** Don't duplicate the performance calculator — import from `lib/summary_statistics.py`.
7. **OneDrive lock handling.** Files actively being synced may throw "Resource deadlock avoided". Loaders should catch this and show a warning rather than crashing.

---

## 6. File Manifest (what gets created/modified)

**New files:**
- `lib/dashboard/__init__.py`
- `lib/dashboard/manifest.py`
- `lib/dashboard/loaders.py`
- `lib/dashboard/calculations.py`
- `lib/dashboard/components.py`
- `bin/market_dashboard.py` (replace the prototype already there)

**Modified files:**
- None required (this is additive)

**Not modified:**
- `.env` (already has OD set correctly)
- `fx_analysis_config.yaml` (dashboard uses manifest.json directly)
- Existing `bin/streamlit_app.py` (kept as-is, separate dashboard)
