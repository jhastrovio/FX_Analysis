#!/usr/bin/env python
"""
Configuration Manager for FX Analysis Project
============================================
Provides centralized access to project configuration, file paths, and analysis parameters.
This is a OneDrive-only implementation - all data is stored in the cloud.
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
import logging

class FXAnalysisConfig:
    """Configuration manager for FX analysis project (OneDrive-only)."""
    
    def __init__(self, config_file: str = "fx_analysis_config.yaml"):
        """Initialize configuration manager.
        
        Args:
            config_file: Path to YAML configuration file
        """
        self.config_file = Path(config_file)
        self.config = self._load_config()
        self._setup_logging()
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from YAML file."""
        if not self.config_file.exists():
            raise FileNotFoundError(f"Configuration file not found: {self.config_file}")
        
        with open(self.config_file, 'r') as f:
            return yaml.safe_load(f)
    
    def _setup_logging(self):
        """Setup logging based on configuration."""
        log_config = self.config.get('logging', {})
        
        # Setup logging to console only (logs will be uploaded to OneDrive)
        logging.basicConfig(
            level=getattr(logging, log_config.get('level', 'INFO')),
            format=log_config.get('format', '%(asctime)s - %(name)s - %(levelname)s - %(message)s'),
            handlers=[
                logging.StreamHandler()
            ]
        )
    
    # OneDrive storage path methods
    def get_onedrive_path(self, path_key: str) -> str:
        """Get OneDrive storage path from configuration.
        
        Args:
            path_key: Key for the specific OneDrive path
            
        Returns:
            str: The configured OneDrive path
        """
        return self.config['storage']['onedrive'][path_key]
    
    def get_onedrive_file_path(self, path_key: str, filename: str) -> str:
        """Get full OneDrive file path by combining storage path with filename.
        
        Args:
            path_key: Key for the specific OneDrive path
            filename: The filename to append
            
        Returns:
            str: The full OneDrive file path
        """
        base_path = self.get_onedrive_path(path_key)
        return f"{base_path}/{filename}"
    
    # File type methods
    def get_file_type_config(self, file_category: str, file_type: str) -> Dict:
        """Get configuration for a specific file type.
        
        Args:
            file_category: 'raw' or 'processed'
            file_type: Specific file type
            
        Returns:
            Dict: File type configuration
        """
        if 'file_types' not in self.config:
            raise ValueError("Config missing 'file_types' section")
        
        if file_category not in self.config['file_types']:
            raise ValueError(f"Unknown file category: {file_category}")
        
        if file_type not in self.config['file_types'][file_category]:
            raise ValueError(f"Unknown file type '{file_type}' in category '{file_category}'")
        
        return self.config['file_types'][file_category][file_type]
    
    def get_file_pattern(self, file_category: str, file_type: str) -> str:
        """Get file pattern for a specific file type."""
        return self.get_file_type_config(file_category, file_type)['pattern']
    
    def get_file_location(self, file_category: str, file_type: str) -> str:
        """Get OneDrive location for a specific file type."""
        location_key = self.get_file_type_config(file_category, file_type)['location']
        storage_type, path_key = location_key.split('.')
        return self.get_onedrive_path(path_key)
    
    def get_full_file_path(self, file_type: str, file_name: str, 
                          date_range: str = None, **kwargs) -> str:
        """Get full file path for a given file type and name.
        
        Args:
            file_type: Type of file (raw, processed, etc.)
            file_name: Name of the file
            date_range: Date range for analysis (optional)
            **kwargs: Additional parameters for file naming
            
        Returns:
            str: Full file path
        """
        if 'file_types' not in self.config:
            raise ValueError("Config missing 'file_types' section")
        
        if file_type not in self.config['file_types']:
            raise ValueError(f"Unknown file type: {file_type}")
        
        if file_name not in self.config['file_types'][file_type]:
            raise ValueError(f"Unknown file name '{file_name}' in type '{file_type}'")
        
        file_config = self.config['file_types'][file_type][file_name]
        pattern = file_config['pattern']
        
        # Replace placeholders in pattern
        if date_range and '{date_range}' in pattern:
            pattern = pattern.replace('{date_range}', date_range)
        
        if '{timestamp}' in pattern:
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            pattern = pattern.replace('{timestamp}', timestamp)
        
        # Replace other placeholders from kwargs
        for key, value in kwargs.items():
            placeholder = f'{{{key}}}'
            if placeholder in pattern:
                pattern = pattern.replace(placeholder, str(value))
        
        # Get location and resolve OneDrive keys
        location = file_config['location']
        if location.startswith('onedrive.'):
            # Extract OneDrive storage key, e.g., 'processed_data'
            storage_key = location.split('.', 1)[1]
            # Look up full path in config['storage']['onedrive']
            onedrive_base = self.config['storage']['onedrive']
            if storage_key not in onedrive_base:
                raise ValueError(f"Unknown OneDrive storage key: {storage_key}")
            full_path = onedrive_base[storage_key]
            return f"{full_path}/{pattern}"
        else:
            return f"{location}/{pattern}"
    
    # Analysis configuration methods
    def get_analysis_config(self, section: str) -> Dict[str, Any]:
        """Get analysis configuration section.
        
        Args:
            section: 'performance_metrics', 'rolling_windows', 'correlation', etc.
            
        Returns:
            Dict: Analysis configuration
        """
        return self.config['analysis'].get(section, {})
    
    def get_performance_metrics(self) -> List[str]:
        """Get list of performance metrics to calculate."""
        return self.config['analysis']['performance_metrics']
    
    def get_rolling_windows(self) -> List[int]:
        """Get list of rolling window periods."""
        return self.config['analysis']['rolling_windows']
    
    def get_annualization_factor(self) -> int:
        """Get annualization factor for converting daily metrics to annual."""
        return self.config['analysis'].get('annualization_factor', 260)
    
    def get_default_date_range(self) -> str:
        """Get the default date range for analysis."""
        return 'full_period'  # Default to full period
    
    def get_analysis_type(self, script_name: str) -> str:
        """Get analysis type based on script name."""
        analysis_mapping = {
            'summary_statistics': 'summary_stats',
            'correlation_analysis': 'correlation_matrix',
            'rolling_metrics': 'rolling_metrics',
            'portfolio_construction': 'portfolio_weights',
            'performance_analysis': 'performance_analysis'
        }
        return analysis_mapping.get(script_name, 'analysis')
    
    def get_date_ranges(self) -> Dict[str, str]:
        """Get available date ranges for analysis."""
        return self.config['analysis']['date_ranges']
    
    # Portfolio configuration methods
    def get_portfolio_config(self, strategy: str) -> Dict[str, Any]:
        """Get portfolio construction configuration for a strategy.
        
        Args:
            strategy: 'equal_weight', 'risk_parity', 'mean_variance', 'hierarchical_risk_parity'
            
        Returns:
            Dict: Portfolio strategy configuration
        """
        return self.config['portfolio'].get(strategy, {})
    
    def get_available_portfolio_strategies(self) -> List[str]:
        """Get list of available portfolio strategies."""
        return list(self.config['portfolio'].keys())
    
    # Model classification methods
    def get_model_categories(self) -> List[str]:
        """Get list of model categories."""
        return self.config['model_classification']['categories']
    
    def get_model_families(self) -> List[str]:
        """Get list of model families."""
        return self.config['model_classification']['families']
    
    # Output format methods
    def get_output_format(self, format_type: str) -> Dict[str, Any]:
        """Get output format configuration.
        
        Args:
            format_type: 'csv', 'excel', 'json'
            
        Returns:
            Dict: Output format configuration
        """
        return self.config['output_formats'].get(format_type, {})
    
    # Validation methods
    def get_validation_rules(self, rule_type: str) -> Dict[str, Any]:
        """Get validation rules.
        
        Args:
            rule_type: 'data_quality' or 'model_metadata'
            
        Returns:
            Dict: Validation rules
        """
        return self.config['validation'].get(rule_type, {})
    
    # Utility methods
    def get_project_info(self) -> Dict[str, str]:
        """Get project information."""
        return self.config['project']
    
    def format_filename(self, pattern: str, **kwargs) -> str:
        """Format filename using pattern and provided values.
        
        Args:
            pattern: Filename pattern with placeholders
            **kwargs: Values to format into the pattern
            
        Returns:
            str: Formatted filename
        """
        # Add timestamp if not provided
        if 'timestamp' not in kwargs:
            kwargs['timestamp'] = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        return pattern.format(**kwargs)
    
    def get_timestamp(self, format_str: str = '%Y%m%d_%H%M%S') -> str:
        """Get current timestamp in specified format."""
        return datetime.now().strftime(format_str)
    
    def is_onedrive_only(self) -> bool:
        """Check if this is a OneDrive-only implementation."""
        return self.config['project'].get('storage_type') == 'onedrive'

# Global configuration instance
_config_instance = None

def get_config(config_file: str = "fx_analysis_config.yaml") -> FXAnalysisConfig:
    """Get global configuration instance.
    
    Args:
        config_file: Path to configuration file
        
    Returns:
        FXAnalysisConfig: Configuration instance
    """
    global _config_instance
    if _config_instance is None:
        _config_instance = FXAnalysisConfig(config_file)
    return _config_instance

# Example usage:
if __name__ == "__main__":
    # Test configuration loading
    config = get_config()
    
    print("Project Info:", config.get_project_info())
    print("OneDrive Raw Data Path:", config.get_onedrive_path('raw_data'))
    print("Performance Metrics:", config.get_performance_metrics())
    print("Model Categories:", config.get_model_categories())
    print("Is OneDrive Only:", config.is_onedrive_only())
    
    # Test file path generation
    master_matrix_path = config.get_full_file_path('processed', 'master_matrix')
    print("Master Matrix Path:", master_matrix_path) 