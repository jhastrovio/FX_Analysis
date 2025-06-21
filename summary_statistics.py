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

# Set pandas display options for consistent float formatting
pd.set_option('display.float_format', '{:.6f}'.format)

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
    date_range: str = typer.Option(
        None,
        "--date-range",
        "-d",
        help="Date range for analysis (full_period, recent_10y, recent_5y, recent_2y, recent_1y)",
    ),
) -> None:
    """Calculate summary statistics for all FX models."""
    # Load configuration
    config = get_config(str(config_file))
    
    # Validate date range if provided
    if date_range:
        available_ranges = config.get_date_ranges()
        if date_range not in available_ranges:
            typer.echo(f"Error: Invalid date range '{date_range}'", err=True)
            typer.echo(f"Available ranges: {', '.join(available_ranges.keys())}", err=True)
            raise typer.Exit(code=1)
    else:
        date_range = config.get_default_date_range()
    
    if verbose:
        typer.echo(f"Using date range: {date_range}")
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
        typer.echo(f"Date Range: {date_range}")
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
        analysis_type = config.get_analysis_type('summary_statistics')
        
        # Use test file type if test flag is set
        output_file_type = 'test' if test else 'processed'
        output_path = config.get_full_file_path(output_file_type, analysis_type, 
                                               date_range=date_range)
        
        try:
            # Format float columns to 6 decimal places before uploading
            float_columns = summary_df.select_dtypes(include=[np.number]).columns
            for col in float_columns:
                summary_df[col] = summary_df[col].round(6)
            
            asyncio.run(storage.upload_csv(output_path, summary_df))
            data_type = "test" if test else "production"
            typer.echo(f"Summary statistics uploaded to OneDrive ({data_type}): {output_path}")
            typer.echo(f"Shape: {summary_df.shape}")
            typer.echo(f"Date range: {date_range}")
            typer.echo(f"Analysis type: {analysis_type}")
        except Exception as e:
            typer.echo(f"Failed to upload summary statistics: {e}", err=True)
            raise typer.Exit(code=1)


@app.command()
def all_ranges(
    config_file: Path = typer.Option(
        "fx_analysis_config.yaml",
        "--config",
        "-c",
        exists=True,
        readable=True,
        help="Path to YAML config file",
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
    """Calculate summary statistics for all available date ranges."""
    # Load configuration
    config = get_config(str(config_file))
    
    # Get all available date ranges
    available_ranges = config.get_date_ranges()
    
    if verbose:
        typer.echo(f"Running summary statistics for all {len(available_ranges)} date ranges:")
        for range_name, range_desc in available_ranges.items():
            typer.echo(f"  - {range_name}: {range_desc}")
        typer.echo()
    
    # Initialize OneDrive storage
    storage = OneDriveStorage()
    
    # Load data once (will be filtered for each date range)
    try:
        master_matrix, model_index = load_master_matrix(storage, config, test)
        if verbose:
            typer.echo(f"Loaded master matrix with shape: {master_matrix.shape}")
            typer.echo(f"Loaded model index with {len(model_index)} models")
    except Exception as e:
        typer.echo(f"Failed to load data: {e}", err=True)
        raise typer.Exit(code=1)
    
    # Process each date range
    results_summary = []
    
    for range_name, range_desc in available_ranges.items():
        if verbose:
            typer.echo(f"\n=== Processing {range_name}: {range_desc} ===")
        
        try:
            # Filter data based on date range
            filtered_matrix = filter_data_by_date_range(master_matrix, range_name, range_desc)
            
            if filtered_matrix.empty:
                typer.echo(f"⚠️  No data available for {range_name}, skipping...")
                continue
            
            if verbose:
                typer.echo(f"Filtered data shape: {filtered_matrix.shape}")
            
            # Calculate summary statistics for this date range
            summary_df = calculate_summary_statistics(filtered_matrix, model_index, config, verbose)
            
            # Format float columns to 6 decimal places
            float_columns = summary_df.select_dtypes(include=[np.number]).columns
            for col in float_columns:
                summary_df[col] = summary_df[col].round(6)
            
            # Save to OneDrive
            analysis_type = config.get_analysis_type('summary_statistics')
            output_file_type = 'test' if test else 'processed'
            output_path = config.get_full_file_path(output_file_type, analysis_type, 
                                                   date_range=range_name)
            
            asyncio.run(storage.upload_csv(output_path, summary_df))
            
            # Store summary info
            results_summary.append({
                'date_range': range_name,
                'description': range_desc,
                'shape': summary_df.shape,
                'output_path': output_path
            })
            
            data_type = "test" if test else "production"
            typer.echo(f"✅ {range_name}: Uploaded to OneDrive ({data_type})")
            typer.echo(f"   Shape: {summary_df.shape}")
            typer.echo(f"   Path: {output_path}")
            
        except Exception as e:
            typer.echo(f"❌ Error processing {range_name}: {e}", err=True)
            continue
    
    # Print final summary
    typer.echo(f"\n=== SUMMARY ===")
    typer.echo(f"Successfully processed {len(results_summary)} out of {len(available_ranges)} date ranges")
    
    for result in results_summary:
        typer.echo(f"✅ {result['date_range']}: {result['description']} - {result['shape']}")


def filter_data_by_date_range(master_matrix: pd.DataFrame, range_name: str, range_desc: str) -> pd.DataFrame:
    """Filter master matrix data based on date range specification."""
    if range_name == 'full_period':
        return master_matrix
    
    # Parse the range description to get the number of years
    if 'years' in range_desc.lower():
        try:
            years = int(range_desc.split()[0])
        except (ValueError, IndexError):
            # Fallback to full period if parsing fails
            return master_matrix
    else:
        # For other formats, return full period
        return master_matrix
    
    # Calculate the start date (years ago from the latest date)
    latest_date = master_matrix.index.max()
    start_date = latest_date - pd.DateOffset(years=years)
    
    # Filter the data
    filtered_data = master_matrix[master_matrix.index >= start_date]
    
    return filtered_data


if __name__ == "__main__":
    app() 