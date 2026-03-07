#!/usr/bin/env python
"""
Configuration Manager for FX Analysis Project
============================================
Analytics-only: Provides configuration for read-only data access and analysis parameters.

This module manages configuration for analytics workflows. It does not handle
data production, ingestion, or dataset creation. All data access is read-only.

"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
import logging
from dotenv import load_dotenv

class FXAnalysisConfig:
    """Configuration manager for FX analysis project.
    
    Analytics-only: Manages configuration for read-only data access and analysis.
    Does not handle data production or dataset creation.
    """
    
    def __init__(self, config_file: str = "fx_analysis_config.yaml"):
        """Initialize configuration manager.
        
        Args:
            config_file: Path to YAML configuration file
        """
        # Load environment variables
        if os.path.exists('.env'):
            load_dotenv('.env', override=True)
        
        self.config_file = Path(config_file)
        self.repo_root = self.config_file.resolve().parent
        self.config = self._load_config()
        self._setup_logging()
        
        # Get OneDrive root path
        self.od_root = os.getenv('OD')
        if not self.od_root:
            raise ValueError("Missing OD environment variable. Set OD to your OneDrive root path.")
        
        # Validate OneDrive path
        if not os.path.exists(self.od_root):
            raise ValueError(f"OneDrive path does not exist: {self.od_root}")
        
        # Validate it's the correct OneDrive location (read-only data estate)
        if not self.od_root.endswith('FX_Data - General'):
            raise ValueError(f"OD should point to 'FX_Data - General', not: {self.od_root}")
        # Note: This path is read-only. FX_Analysis never writes to this location.
    
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
        """Get OneDrive storage path from configuration (relative to OneDrive root).
        
        Args:
            path_key: Key for the specific OneDrive path
            
        Returns:
            str: The configured OneDrive path (relative)
        """
        return self.config['storage']['onedrive'][path_key]
    
    def get_absolute_path(self, path_key: str) -> str:
        """Get absolute filesystem path for OneDrive storage.
        
        Args:
            path_key: Key for the specific OneDrive path
            
        Returns:
            str: The absolute filesystem path
        """
        relative_path = self.get_onedrive_path(path_key)
        return os.path.join(self.od_root, relative_path.replace('/', os.sep))
    
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

    def get_local_path(self, path_key: str) -> str:
        """Get local storage path from configuration (relative to repo root)."""
        return self.config['storage']['local'][path_key]

    def get_absolute_local_path(self, path_key: str) -> str:
        """Get absolute local filesystem path from configuration."""
        relative_path = self.get_local_path(path_key)
        return str((self.repo_root / relative_path).resolve())

    def resolve_storage_location(self, location: str) -> Dict[str, str]:
        """Resolve a storage location reference to a storage type and base path."""
        if location.startswith('onedrive.'):
            storage_key = location.split('.', 1)[1]
            return {'storage': 'onedrive', 'base_path': self.get_onedrive_path(storage_key)}
        if location.startswith('local.'):
            storage_key = location.split('.', 1)[1]
            return {'storage': 'local', 'base_path': self.get_absolute_local_path(storage_key)}
        return {'storage': 'local', 'base_path': str((self.repo_root / location).resolve())}
    
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
        """Get resolved base location for a specific file type."""
        location_key = self.get_file_type_config(file_category, file_type)['location']
        return self.resolve_storage_location(location_key)['base_path']

    def get_file_target(self, file_type: str, file_name: str,
                        date_range: str = None, **kwargs) -> Dict[str, str]:
        """Get target storage type and path for a configured file."""
        if 'file_types' not in self.config:
            raise ValueError("Config missing 'file_types' section")

        if file_type not in self.config['file_types']:
            raise ValueError(f"Unknown file type: {file_type}")

        if file_name not in self.config['file_types'][file_type]:
            raise ValueError(f"Unknown file name '{file_name}' in type '{file_type}'")

        file_config = self.config['file_types'][file_type][file_name]
        pattern = file_config['pattern']

        if date_range and '{date_range}' in pattern:
            pattern = pattern.replace('{date_range}', date_range)

        if '{timestamp}' in pattern:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            pattern = pattern.replace('{timestamp}', timestamp)

        if '{date}' in pattern:
            date = datetime.now().strftime("%Y%m%d")
            pattern = pattern.replace('{date}', date)

        for key, value in kwargs.items():
            placeholder = f'{{{key}}}'
            if placeholder in pattern:
                pattern = pattern.replace(placeholder, str(value))

        resolved = self.resolve_storage_location(file_config['location'])
        return {
            'storage': resolved['storage'],
            'path': f"{resolved['base_path']}/{pattern}",
        }
    
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
        return self.get_file_target(file_type, file_name, date_range=date_range, **kwargs)['path']
    
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
        return 'full'  # Default to full period
    
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
    # Note: 'master_matrix' is a legacy name for temporary consolidated analysis artifact
    master_matrix_path = config.get_full_file_path('processed', 'master_matrix')
    print("Consolidated Matrix Path (ephemeral):", master_matrix_path) 
