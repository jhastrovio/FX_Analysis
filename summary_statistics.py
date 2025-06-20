#!/usr/bin/env python
"""
FX Model Summary Statistics Calculator
=====================================
Calculates basic performance metrics for all FX trading models.

Usage:
------
python summary_statistics.py --preview  # Preview results
python summary_statistics.py --verbose  # Run with detailed logging
python summary_statistics.py            # Run and save to OneDrive
"""

from __future__ import annotations

import asyncio
import io
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import warnings

import numpy as np
import pandas as pd
import typer
from config_manager import get_config
from onedrive_storage import OneDriveStorage

app = typer.Typer(add_completion=False, invoke_without_command=True, help="FX model summary statistics")

# Suppress warnings for cleaner output
warnings.filterwarnings('ignore')

class FXPerformanceCalculator:
    """Calculate basic performance metrics for FX trading models."""
    
    def __init__(self, config):
        """Initialize calculator with configuration.
        
        Args:
            config: Configuration manager instance
        """
        self.config = config
        # Get annualization factor from config
        self.annualization_factor = config.get_annualization_factor()
    
    def cumulative_to_daily_returns(self, cumulative_returns: pd.Series) -> pd.Series:
        """
        Convert cumulative return percentages to daily returns in decimal.
        Assumes input is cumulative return in % terms.
        """
        return cumulative_returns.diff() / 100
    
    def annualized_return(self, cumulative_returns: pd.Series) -> float:
        """Calculate annualized return as a percentage from cumulative returns.
        
        Args:
            cumulative_returns: Cumulative returns as percentages
            
        Returns:
            float: Annualized return as a percentage
        """
        daily_returns = self.cumulative_to_daily_returns(cumulative_returns)
        clean_returns = daily_returns.dropna()
        if len(clean_returns) == 0:
            return np.nan
        
        # Calculate cumulative return
        cumulative_return = (1 + clean_returns).prod()
        
        # Annualize using the annualization factor
        n_days = len(clean_returns)
        annualized_return = cumulative_return**(self.annualization_factor / n_days) - 1
        
        # Convert to percentage
        return annualized_return * 100
    
    def mean_return(self, cumulative_returns: pd.Series) -> float:
        """Calculate mean daily return from cumulative returns.
        
        Args:
            cumulative_returns: Cumulative returns as percentages
            
        Returns:
            float: Mean daily return in decimal
        """
        daily_returns = self.cumulative_to_daily_returns(cumulative_returns)
        clean_returns = daily_returns.dropna()
        return clean_returns.mean() if len(clean_returns) > 0 else np.nan
    
    def volatility(self, cumulative_returns: pd.Series) -> float:
        """Calculate annualized volatility from cumulative returns.
        
        Args:
            cumulative_returns: Cumulative returns as percentages
            
        Returns:
            float: Annualized volatility in decimal
        """
        daily_returns = self.cumulative_to_daily_returns(cumulative_returns)
        clean_returns = daily_returns.dropna()
        if len(clean_returns) == 0:
            return np.nan
        return clean_returns.std() * np.sqrt(self.annualization_factor)
    
    def sharpe_ratio(self, cumulative_returns: pd.Series) -> float:
        """Calculate Sharpe ratio based on calendar monthly returns from cumulative returns.
        Returns annualized Sharpe ratio (monthly Sharpe / sqrt(12)).
        
        Args:
            cumulative_returns: Cumulative returns as percentages
            
        Returns:
            float: Annualized Sharpe ratio
        """
        daily_returns = self.cumulative_to_daily_returns(cumulative_returns)
        clean_returns = daily_returns.dropna()
        if len(clean_returns) == 0:
            return np.nan
        
        # Create cumulative index
        cumulative_index = (1 + clean_returns).cumprod()
        
        # Resample to monthly and calculate monthly returns
        monthly_index = cumulative_index.resample("M").last()
        monthly_returns = monthly_index.pct_change().dropna()
        
        if len(monthly_returns) == 0:
            return np.nan
        
        # Monthly Sharpe ratio
        monthly_sharpe = monthly_returns.mean() / monthly_returns.std()
        
        # Convert to annualized Sharpe ratio
        annualized_sharpe = monthly_sharpe * np.sqrt(12)
        
        return annualized_sharpe
    
    def max_drawdown(self, cumulative_returns: pd.Series) -> float:
        """Calculate maximum drawdown from cumulative returns.
        
        Args:
            cumulative_returns: Cumulative returns as percentages
            
        Returns:
            float: Maximum drawdown in decimal (negative value)
        """
        daily_returns = self.cumulative_to_daily_returns(cumulative_returns)
        clean_returns = daily_returns.dropna()
        if len(clean_returns) == 0:
            return np.nan
        
        # Calculate cumulative returns
        cumulative_returns_decimal = (1 + clean_returns).cumprod()
        
        # Calculate running maximum
        running_max = cumulative_returns_decimal.expanding().max()
        
        # Calculate drawdown
        drawdown = (cumulative_returns_decimal - running_max) / running_max
        
        return drawdown.min()


def load_master_matrix(storage: OneDriveStorage, config, test: bool = False) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Load master return matrix and model index from OneDrive."""
    # Determine file type based on test flag
    file_type = 'test' if test else 'processed'
    model_index_type = 'test' if test else 'raw'
    
    # Load master return matrix
    master_matrix_path = config.get_full_file_path(file_type, 'master_matrix')
    try:
        data = asyncio.run(storage.download_file(master_matrix_path))
        master_matrix = pd.read_csv(io.StringIO(data.decode('utf-8')))
        master_matrix['Date'] = pd.to_datetime(master_matrix['Date'])
        master_matrix.set_index('Date', inplace=True)
    except Exception as e:
        raise RuntimeError(f"Failed to load master matrix: {e}")
    
    # Load model index
    model_index_path = config.get_full_file_path(model_index_type, 'model_index')
    try:
        data = asyncio.run(storage.download_file(model_index_path))
        model_index = pd.read_csv(io.StringIO(data.decode('utf-8')))
    except Exception as e:
        raise RuntimeError(f"Failed to load model index: {e}")
    
    return master_matrix, model_index


def calculate_summary_statistics(master_matrix: pd.DataFrame, model_index: pd.DataFrame, 
                               config, verbose: bool = False) -> pd.DataFrame:
    """Calculate summary statistics for all models."""
    calculator = FXPerformanceCalculator(config)
    results = []
    
    # Get performance metrics from config
    performance_metrics = config.get_performance_metrics()
    
    # Get model columns (exclude Date)
    model_columns = [col for col in master_matrix.columns if ' - ' in col]
    total_models = len(model_columns)
    
    if verbose:
        typer.echo(f"Calculating summary statistics for {total_models} models...")
        typer.echo(f"Performance metrics: {performance_metrics}")
    
    for i, col in enumerate(model_columns, 1):
        if verbose:
            typer.echo(f"Processing {i}/{total_models}: {col}")
        
        # Extract model ID and name
        model_id_str, model_name = col.split(' - ', 1)
        model_id = int(model_id_str)
        
        # Get cumulative returns for this model
        cumulative_returns = master_matrix[col]
        
        # Calculate metrics based on config
        metrics = {
            'model_id': model_id,
            'model_name': model_name
        }
        
        # Add each performance metric from config
        for metric in performance_metrics:
            if metric == 'annualized_return':
                metrics[metric] = calculator.annualized_return(cumulative_returns)
            elif metric == 'volatility':
                metrics[metric] = calculator.volatility(cumulative_returns)
            elif metric == 'sharpe_ratio':
                metrics[metric] = calculator.sharpe_ratio(cumulative_returns)
            elif metric == 'max_drawdown':
                metrics[metric] = calculator.max_drawdown(cumulative_returns)
        
        # Get model metadata from index using config column names
        model_meta = model_index[model_index['ID'] == model_id]
        if not model_meta.empty:
            # Use column names from config
            model_index_config = config.get_file_type_config('raw', 'model_index')
            category_col = model_index_config['columns']['category']
            family_col = model_index_config['columns']['family']
            
            metrics['category'] = model_meta.iloc[0][category_col]
            metrics['family'] = model_meta.iloc[0][family_col]
        else:
            metrics['category'] = 'Unknown'
            metrics['family'] = 'Unknown'
        
        results.append(metrics)
        
        if verbose:
            typer.echo(f"✅ Completed {col}")
    
    # Create results DataFrame
    summary_df = pd.DataFrame(results)
    
    # Reorder columns for better readability
    column_order = ['model_id', 'model_name', 'category', 'family'] + performance_metrics
    summary_df = summary_df[column_order]
    
    return summary_df


@app.callback(invoke_without_command=True)
def main(
    config_file: Path = typer.Option(
        "fx_analysis_config.yaml",
        "--config",
        "-c",
        exists=True,
        readable=True,
        help="Path to YAML config file",
    ),
    preview: bool = typer.Option(
        False,
        "--preview/--no-preview",
        "-p",
        help="Preview results without saving",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose/--no-verbose",
        "-v",
        help="Enable verbose logging",
    ),
    test: bool = typer.Option(
        False,
        "--test/--no-test",
        "-t",
        help="Use test data instead of production data",
    ),
) -> None:
    """Calculate summary statistics for all FX models."""
    # Load configuration
    config = get_config(str(config_file))
    
    if verbose:
        typer.echo("Loading master return matrix and model index...")
    
    # Initialize OneDrive storage (uses onedrive_config.yaml by default)
    storage = OneDriveStorage()
    
    # Load data
    try:
        master_matrix, model_index = load_master_matrix(storage, config, test)
    except Exception as e:
        typer.echo(f"Failed to load data: {e}", err=True)
        raise typer.Exit(code=1)
    
    if verbose:
        typer.echo(f"Loaded master matrix with shape: {master_matrix.shape}")
        typer.echo(f"Loaded model index with {len(model_index)} models")
    
    # Calculate summary statistics
    summary_df = calculate_summary_statistics(master_matrix, model_index, config, verbose)
    
    if preview:
        typer.echo("\n=== SUMMARY STATISTICS PREVIEW ===")
        typer.echo(summary_df.head(10))
        typer.echo(f"\nShape: {summary_df.shape}")
        
        # Show some key statistics
        typer.echo(f"\n=== KEY STATISTICS ===")
        performance_metrics = config.get_performance_metrics()
        for metric in performance_metrics:
            if metric in summary_df.columns:
                avg_value = summary_df[metric].mean()
                typer.echo(f"Average {metric}: {avg_value:.6f}")
        
    else:
        # Save to OneDrive with enhanced naming
        date_range = config.get_default_date_range()
        analysis_type = config.get_analysis_type('summary_statistics')
        
        # Use test file type if test flag is set
        output_file_type = 'test' if test else 'processed'
        output_path = config.get_full_file_path(output_file_type, analysis_type, 
                                               date_range=date_range)
        
        try:
            asyncio.run(storage.upload_csv(output_path, summary_df))
            data_type = "test" if test else "production"
            typer.echo(f"Summary statistics uploaded to OneDrive ({data_type}): {output_path}")
            typer.echo(f"Shape: {summary_df.shape}")
            typer.echo(f"Date range: {date_range}")
            typer.echo(f"Analysis type: {analysis_type}")
        except Exception as e:
            typer.echo(f"Failed to upload summary statistics: {e}", err=True)
            raise typer.Exit(code=1)


if __name__ == "__main__":
    app() 