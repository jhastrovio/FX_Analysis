"""
Reusable helpers for simple annualized volatility analysis on daily returns.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd


ANNUALIZATION_FACTOR = 252


def annualized_volatility(
    returns: pd.Series,
    window: Optional[int] = None,
    annualization_factor: int = ANNUALIZATION_FACTOR,
) -> float:
    """Calculate annualized volatility from daily returns.

    Drops NaNs before calculation. Uses sample standard deviation (`ddof=1`).
    Returns NaN if fewer than 2 observations are available, or if a requested
    window has fewer than `window` clean observations.
    """
    clean_returns = returns.dropna()
    if window is not None:
        if len(clean_returns) < window:
            return np.nan
        clean_returns = clean_returns.tail(window)

    if len(clean_returns) < 2:
        return np.nan

    return float(clean_returns.std(ddof=1) * np.sqrt(annualization_factor))


def summarize_volatility(
    returns: pd.Series,
    annualization_factor: int = ANNUALIZATION_FACTOR,
) -> dict[str, float]:
    """Return the standard volatility summary for one return series."""
    return {
        "vol_all": annualized_volatility(
            returns,
            window=None,
            annualization_factor=annualization_factor,
        ),
        "vol_1y": annualized_volatility(
            returns,
            window=252,
            annualization_factor=annualization_factor,
        ),
        "vol_42d": annualized_volatility(
            returns,
            window=42,
            annualization_factor=annualization_factor,
        ),
    }


def summarize_long_returns(
    df: pd.DataFrame,
    series_type: str,
    series_id_col: str = "series_id",
    return_col: str = "daily_return",
    annualization_factor: int = ANNUALIZATION_FACTOR,
) -> pd.DataFrame:
    """Summarize volatilities for long-form daily return data."""
    if df.empty:
        return pd.DataFrame(columns=["series_type", "series_id", "vol_all", "vol_1y", "vol_42d"])

    result_rows = []
    for series_id, group in df.groupby(series_id_col, sort=True):
        vols = summarize_volatility(group[return_col], annualization_factor=annualization_factor)
        result_rows.append(
            {
                "series_type": series_type,
                "series_id": series_id,
                **vols,
            }
        )

    return pd.DataFrame(result_rows)


def summarize_wide_returns(
    df: pd.DataFrame,
    series_type: str,
    annualization_factor: int = ANNUALIZATION_FACTOR,
) -> pd.DataFrame:
    """Summarize volatilities for wide-form daily return data indexed by date."""
    if df.empty:
        return pd.DataFrame(columns=["series_type", "series_id", "vol_all", "vol_1y", "vol_42d"])

    result_rows = []
    for column in df.columns:
        vols = summarize_volatility(df[column], annualization_factor=annualization_factor)
        result_rows.append(
            {
                "series_type": series_type,
                "series_id": column,
                **vols,
            }
        )

    return pd.DataFrame(result_rows)

