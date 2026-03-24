"""
Reusable annualized volatility helpers for daily return series.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd


TRADING_DAYS_PER_YEAR = 252


def annualized_vol(
    returns: pd.Series,
    annualization_factor: int = TRADING_DAYS_PER_YEAR,
) -> float:
    """Calculate annualized volatility from daily returns.

    NaNs are dropped before calculation. Returns NaN if fewer than 2 clean
    observations remain.
    """
    clean_returns = pd.to_numeric(returns, errors="coerce").dropna()
    if len(clean_returns) < 2:
        return np.nan
    return float(clean_returns.std(ddof=1) * np.sqrt(annualization_factor))


def trailing_vol(
    returns: pd.Series,
    window: int,
    annualization_factor: int = TRADING_DAYS_PER_YEAR,
) -> float:
    """Calculate annualized trailing volatility from daily returns.

    NaNs are dropped before windowing. Returns NaN if fewer than `window`
    clean observations are available.
    """
    clean_returns = pd.to_numeric(returns, errors="coerce").dropna()
    if len(clean_returns) < window:
        return np.nan
    return annualized_vol(clean_returns.tail(window), annualization_factor=annualization_factor)


def volatility_summary(
    returns: pd.Series,
    annualization_factor: int = TRADING_DAYS_PER_YEAR,
) -> dict[str, float]:
    """Return the standard annualized volatility summary."""
    return {
        "vol_all": annualized_vol(returns, annualization_factor=annualization_factor),
        "vol_252d": trailing_vol(returns, 252, annualization_factor=annualization_factor),
        "vol_42d": trailing_vol(returns, 42, annualization_factor=annualization_factor),
    }
