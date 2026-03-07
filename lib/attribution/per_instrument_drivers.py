"""
Per-Instrument Drivers Analysis

Analytics-only: Compute model contributions to portfolio positions for attribution analysis.
"""

from __future__ import annotations

import warnings
from typing import Dict

import pandas as pd
import numpy as np


def scale_positions(
    model_returns: pd.DataFrame, method: str = "dummy_constant"
) -> pd.DataFrame:
    """Scale model returns to positions using specified method.
    
    Args:
        model_returns: DataFrame with columns: date, instrument, model_id, model_return
        method: Scaling method. "dummy_constant" means model_position = model_return
        
    Returns:
        DataFrame with columns: date, instrument, model_id, model_return, model_position
    """
    result = model_returns.copy()
    
    if method == "dummy_constant":
        result["model_position"] = result["model_return"]
    else:
        raise ValueError(f"Unknown scaling method: {method}")
    
    # Ensure model_return is kept in output
    return result[["date", "instrument", "model_id", "model_return", "model_position"]]


def _normalize_allocations(allocations_df: pd.DataFrame) -> pd.DataFrame:
    """Normalize risk_alloc to sum to 1.0.
    
    Args:
        allocations_df: DataFrame with risk_alloc column
        
    Returns:
        DataFrame with normalized risk_alloc
        
    Raises:
        AssertionError: If normalized sum is not 1.0 within tolerance
    """
    result = allocations_df.copy()
    original_sum = result["risk_alloc"].sum()
    
    # Warn if original sum deviates significantly from 1.0
    if abs(original_sum - 1.0) > 1e-3:
        warnings.warn(
            f"Original risk_alloc sum is {original_sum:.6f}, not 1.0. Normalizing.",
            UserWarning
        )
    
    # Normalize unconditionally
    result["risk_alloc"] = result["risk_alloc"] / original_sum
    
    # Assert normalized sum equals 1.0 within tolerance
    normalized_sum = result["risk_alloc"].sum()
    assert abs(normalized_sum - 1.0) < 1e-6, (
        f"Normalized risk_alloc sum is {normalized_sum:.10f}, expected 1.0"
    )
    
    return result


def _validate_required_columns(
    df: pd.DataFrame, name: str, required_cols: list[str]
) -> None:
    """Validate that DataFrame has required columns.
    
    Args:
        df: DataFrame to validate
        name: Name of DataFrame for error messages
        required_cols: List of required column names
        
    Raises:
        ValueError: If any required columns are missing
    """
    missing = [col for col in required_cols if col not in df.columns]
    if missing:
        raise ValueError(
            f"{name} missing required columns: {missing}. "
            f"Available columns: {list(df.columns)}"
        )


def _compute_contributions(
    allocations_df: pd.DataFrame,
    scaled_returns_df: pd.DataFrame,
    target_date: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Compute model contributions and instrument-level summaries.
    
    Args:
        allocations_df: DataFrame with columns: model_id, strategy_name, risk_alloc
        scaled_returns_df: DataFrame with columns: date, instrument, model_id, 
                          model_return, model_position
        target_date: Target date string (YYYY-MM-DD)
        
    Returns:
        Tuple of:
        - contributions_df: Columns: date, instrument, model_id, strategy_name, 
                           risk_alloc, model_return, model_position, contrib
        - instrument_summary_df: Columns: date, instrument, pred_final, 
                                final_position, residual
    """
    # Ensure date column is datetime for consistent filtering
    scaled_returns_df = scaled_returns_df.copy()
    if not pd.api.types.is_datetime64_any_dtype(scaled_returns_df["date"]):
        scaled_returns_df["date"] = pd.to_datetime(scaled_returns_df["date"])
    
    # Filter to target date
    target_date_dt = pd.to_datetime(target_date)
    date_filtered = scaled_returns_df[
        scaled_returns_df["date"].dt.date == target_date_dt.date()
    ].copy()
    
    # Join allocations to model returns on model_id
    # This is an inner join on model_id, so models in returns but not in allocations
    # will be dropped (reported in diagnostics)
    merged = date_filtered.merge(
        allocations_df[["model_id", "strategy_name", "risk_alloc"]],
        on="model_id",
        how="inner"
    )
    
    # Compute contribution
    merged["contrib"] = merged["risk_alloc"] * merged["model_position"]
    
    # Contributions DataFrame (model-level)
    contributions_df = merged[[
        "date", "instrument", "model_id", "strategy_name",
        "risk_alloc", "model_return", "model_position", "contrib"
    ]].copy()
    
    # Aggregate by instrument to get pred_final
    instrument_summary_df = merged.groupby(
        ["date", "instrument"], as_index=False
    ).agg(
        pred_final=("contrib", "sum")
    )
    
    # Note: final_position and residual will be added later when final_positions
    # is merged in the main function
    
    return contributions_df, instrument_summary_df


def _rank_drivers(
    contributions_df: pd.DataFrame,
    instrument_summary_df: pd.DataFrame,
    top_n: int,
) -> pd.DataFrame:
    """Rank drivers per instrument in three ways: absolute, positive, negative.
    
    Args:
        contributions_df: Model-level contributions
        instrument_summary_df: Instrument-level summary with pred_final
        top_n: Number of top drivers to rank
        
    Returns:
        Long DataFrame with columns: date, instrument, model_id, strategy_name,
        risk_alloc, model_return, model_position, contrib, pct_of_pred,
        rank_type, rank
    """
    # Merge pred_final into contributions
    merged = contributions_df.merge(
        instrument_summary_df[["date", "instrument", "pred_final"]],
        on=["date", "instrument"],
        how="left"
    )
    
    # Compute pct_of_pred with safe division
    eps = 1e-10
    merged["pct_of_pred"] = np.where(
        np.abs(merged["pred_final"]) < eps,
        np.nan,
        merged["contrib"] / merged["pred_final"]
    )
    
    # Rank drivers for each instrument in three ways
    ranked_list = []
    
    for instrument in merged["instrument"].unique():
        inst_data = merged[merged["instrument"] == instrument].copy()
        
        # Absolute ranking
        inst_data_abs = inst_data.copy()
        inst_data_abs["abs_contrib"] = inst_data_abs["contrib"].abs()
        inst_data_abs = inst_data_abs.nlargest(top_n, "abs_contrib")
        inst_data_abs["rank_type"] = "abs"
        inst_data_abs["rank"] = range(1, len(inst_data_abs) + 1)
        inst_data_abs = inst_data_abs.drop(columns=["abs_contrib"])
        ranked_list.append(inst_data_abs)
        
        # Positive ranking
        inst_data_pos = inst_data[inst_data["contrib"] > 0].copy()
        if len(inst_data_pos) > 0:
            inst_data_pos = inst_data_pos.nlargest(top_n, "contrib")
            inst_data_pos["rank_type"] = "pos"
            inst_data_pos["rank"] = range(1, len(inst_data_pos) + 1)
            ranked_list.append(inst_data_pos)
        
        # Negative ranking (most negative first, by magnitude)
        inst_data_neg = inst_data[inst_data["contrib"] < 0].copy()
        if len(inst_data_neg) > 0:
            inst_data_neg = inst_data_neg.nsmallest(top_n, "contrib")
            inst_data_neg["rank_type"] = "neg"
            inst_data_neg["rank"] = range(1, len(inst_data_neg) + 1)
            ranked_list.append(inst_data_neg)
    
    if not ranked_list:
        # Return empty DataFrame with correct columns
        result = merged.copy()
        result["rank_type"] = ""
        result["rank"] = 0
        return result[[
            "date", "instrument", "model_id", "strategy_name",
            "risk_alloc", "model_return", "model_position", "contrib",
            "pct_of_pred", "rank_type", "rank"
        ]].iloc[:0]
    
    result = pd.concat(ranked_list, ignore_index=True)
    
    return result[[
        "date", "instrument", "model_id", "strategy_name",
        "risk_alloc", "model_return", "model_position", "contrib",
        "pct_of_pred", "rank_type", "rank"
    ]]


def _compute_diagnostics(
    allocations_df: pd.DataFrame,
    model_returns_df: pd.DataFrame,
    final_positions_df: pd.DataFrame,
    contributions_df: pd.DataFrame,
    instrument_summary_df: pd.DataFrame,
    target_date: str,
) -> Dict[str, pd.DataFrame]:
    """Compute diagnostics: missing coverage, missing instruments, top residuals.
    
    Args:
        allocations_df: Allocations DataFrame
        model_returns_df: Model returns DataFrame
        final_positions_df: Final positions DataFrame
        contributions_df: Contributions DataFrame
        instrument_summary_df: Instrument summary DataFrame
        target_date: Target date string
        
    Returns:
        Dictionary with diagnostic DataFrames
    """
    diagnostics = {}
    
    # Ensure date columns are datetime for consistent filtering
    model_returns_df = model_returns_df.copy()
    final_positions_df = final_positions_df.copy()
    
    if not pd.api.types.is_datetime64_any_dtype(model_returns_df["date"]):
        model_returns_df["date"] = pd.to_datetime(model_returns_df["date"])
    if not pd.api.types.is_datetime64_any_dtype(final_positions_df["date"]):
        final_positions_df["date"] = pd.to_datetime(final_positions_df["date"])
    
    # Filter to target date
    target_date_dt = pd.to_datetime(target_date)
    returns_date = model_returns_df[
        model_returns_df["date"].dt.date == target_date_dt.date()
    ]
    positions_date = final_positions_df[
        final_positions_df["date"].dt.date == target_date_dt.date()
    ]
    
    # Missing allocations: models in returns but not in allocations
    models_in_returns = set(returns_date["model_id"].unique())
    models_in_allocations = set(allocations_df["model_id"].unique())
    missing_allocations = models_in_returns - models_in_allocations
    
    if missing_allocations:
        diagnostics["diagnostics_missing_allocations"] = pd.DataFrame({
            "model_id": list(missing_allocations)
        })
    else:
        diagnostics["diagnostics_missing_allocations"] = pd.DataFrame(
            columns=["model_id"]
        )
    
    # Missing returns: models in allocations but not in returns for target_date
    missing_returns = models_in_allocations - models_in_returns
    
    if missing_returns:
        missing_returns_info = allocations_df[
            allocations_df["model_id"].isin(missing_returns)
        ][["model_id", "strategy_name", "risk_alloc"]].copy()
        diagnostics["diagnostics_missing_returns"] = missing_returns_info
    else:
        diagnostics["diagnostics_missing_returns"] = pd.DataFrame(
            columns=["model_id", "strategy_name", "risk_alloc"]
        )
    
    # Missing instruments: instruments in final_positions but not in model_returns
    instruments_in_positions = set(positions_date["instrument"].unique())
    instruments_in_returns = set(returns_date["instrument"].unique())
    missing_instruments = instruments_in_positions - instruments_in_returns
    
    if missing_instruments:
        diagnostics["diagnostics_missing_instruments"] = pd.DataFrame({
            "instrument": list(missing_instruments)
        })
    else:
        diagnostics["diagnostics_missing_instruments"] = pd.DataFrame(
            columns=["instrument"]
        )
    
    # Top residuals: top instruments by absolute residual
    if "residual" in instrument_summary_df.columns:
        top_residuals = instrument_summary_df.nlargest(
            20, "residual", key=lambda x: x.abs()
        )[["date", "instrument", "pred_final", "final_position", "residual"]].copy()
        top_residuals = top_residuals.sort_values(
            "residual", key=lambda x: x.abs(), ascending=False
        )
        diagnostics["diagnostics_top_residuals"] = top_residuals
    else:
        diagnostics["diagnostics_top_residuals"] = pd.DataFrame(
            columns=["date", "instrument", "pred_final", "final_position", "residual"]
        )
    
    return diagnostics


def compute_per_instrument_drivers(
    allocations_df: pd.DataFrame,
    model_returns_df: pd.DataFrame,
    final_positions_df: pd.DataFrame,
    target_date: str,
    top_n: int = 10,
    scaling_method: str = "dummy_constant",
) -> Dict[str, pd.DataFrame]:
    """Compute per-instrument model drivers for attribution analysis.
    
    Args:
        allocations_df: DataFrame with columns: model_id, strategy_name, risk_alloc
                        (optional: category, family)
        model_returns_df: DataFrame with columns: date, instrument, model_id, model_return
        final_positions_df: DataFrame with columns: date, instrument, final_position
        target_date: Target date string (YYYY-MM-DD)
        top_n: Number of top drivers to rank (default: 10)
        scaling_method: Scaling method for positions (default: "dummy_constant")
        
    Returns:
        Dictionary with keys:
        - ranked_drivers: Long format with rank_type and rank columns
        - instrument_summary: Instrument-level pred_final, final_position, residual
        - diagnostics_missing_allocations: Models in returns but not allocations
        - diagnostics_missing_returns: Models in allocations but not returns
        - diagnostics_missing_instruments: Instruments in positions but not returns
        - diagnostics_top_residuals: Top instruments by abs(residual)
    """
    # Validate required columns
    _validate_required_columns(
        allocations_df, "allocations_df", ["model_id", "strategy_name", "risk_alloc"]
    )
    _validate_required_columns(
        model_returns_df, "model_returns_df", ["date", "instrument", "model_id", "model_return"]
    )
    _validate_required_columns(
        final_positions_df, "final_positions_df", ["date", "instrument", "final_position"]
    )
    
    # Normalize allocations
    allocations_df = _normalize_allocations(allocations_df)
    
    # Scale positions
    scaled_returns_df = scale_positions(model_returns_df, method=scaling_method)
    
    # Compute contributions
    contributions_df, instrument_summary_df = _compute_contributions(
        allocations_df, scaled_returns_df, target_date
    )
    
    # Ensure date column is datetime for consistent filtering
    final_positions_df = final_positions_df.copy()
    if not pd.api.types.is_datetime64_any_dtype(final_positions_df["date"]):
        final_positions_df["date"] = pd.to_datetime(final_positions_df["date"])
    
    # Merge final positions to compute residuals
    target_date_dt = pd.to_datetime(target_date)
    positions_date = final_positions_df[
        final_positions_df["date"].dt.date == target_date_dt.date()
    ][["date", "instrument", "final_position"]].copy()
    
    instrument_summary_df = instrument_summary_df.merge(
        positions_date,
        on=["date", "instrument"],
        how="outer"  # Keep all instruments from both sides
    )
    
    # Compute residual
    instrument_summary_df["residual"] = (
        instrument_summary_df["final_position"] - instrument_summary_df["pred_final"]
    )
    
    # Fill NaN pred_final with 0 for instruments with no model coverage
    instrument_summary_df["pred_final"] = instrument_summary_df["pred_final"].fillna(0.0)
    
    # Rank drivers
    ranked_drivers_df = _rank_drivers(
        contributions_df, instrument_summary_df, top_n
    )
    
    # Compute diagnostics
    diagnostics = _compute_diagnostics(
        allocations_df,
        model_returns_df,
        final_positions_df,
        contributions_df,
        instrument_summary_df,
        target_date,
    )
    
    # Return flattened dictionary
    return {
        "ranked_drivers": ranked_drivers_df,
        "instrument_summary": instrument_summary_df,
        **diagnostics,
    }
