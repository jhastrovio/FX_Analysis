"""OneDrive Storage Module - Filesystem Implementation
A simplified module for interacting with OneDrive via local filesystem operations.
Uses OneDrive sync to handle cloud synchronization automatically.
"""

import os
import io
from typing import List, Dict, Optional
from datetime import datetime
from pathlib import Path, PurePosixPath
import yaml
import pandas as pd
from dotenv import load_dotenv


class OneDriveStorage:
    """OneDrive storage client using local filesystem operations."""
    
    def __init__(self, 
                 env_file: str = ".env",
                 config_file: str = "onedrive_config.yaml"):
        """Initialize OneDrive client with local filesystem approach.
        
        Args:
            env_file: Path to .env file (default: .env)
            config_file: Path to YAML config file (default: onedrive_config.yaml)
        """
        # Load environment variables if env_file exists
        if os.path.exists(env_file):
            load_dotenv(env_file, override=True)
        
        # Get OneDrive root path from environment
        self.od_root = os.getenv('OD')
        if not self.od_root:
            raise ValueError("Missing OD environment variable. Set OD to your OneDrive root path.")
        
        # Validate OneDrive path exists and is accessible
        if not os.path.exists(self.od_root):
            raise ValueError(f"OneDrive path does not exist: {self.od_root}")
        
        # Load configuration
        self.config = self._load_config(config_file)
    
    def _load_config(self, config_file: str) -> Dict:
        """Load configuration from YAML file."""
        if not os.path.exists(config_file):
            # Create a minimal default config if file doesn't exist
            return {
                'paths': {
                    'base': 'clean/models_signals_systemacro',
                    'raw_data': 'clean/models_signals_systemacro',
                    'processed_data': 'clean/models_signals_systemacro/Processed',
                    'logs': 'clean/models_signals_systemacro/Logs'
                },
                'file_patterns': {
                    'systemacro_data': '{model_id}_{model_name}.csv',
                    'processed_data': '{processed_type}_{timestamp}.csv'
                },
                'timestamp_formats': {
                    'default': '%Y-%m-%d_%H-%M-%S',
                    'daily': '%Y-%m-%d'
                },
                'content_types': {
                    'csv': 'text/csv',
                    'json': 'application/json',
                    'txt': 'text/plain'
                }
            }
        
        with open(config_file, 'r') as f:
            return yaml.safe_load(f)
    
    def get_path(self, path_key: str) -> str:
        """Get a configured path from the config file.
        
        Args:
            path_key: Dot-notation path key (e.g., 'raw_data')
            
        Returns:
            str: The configured path
        """
        keys = path_key.split('.')
        value = self.config['paths']
        for key in keys:
            value = value[key]
        return value
    
    def get_file_path(self, path_key: str, filename: str) -> str:
        """Get a full file path by combining a configured path with a filename.

        Args:
            path_key: Dot-notation path key (e.g., 'raw_data')
            filename: The filename to append

        Returns:
            str: The full file path relative to OneDrive root
        """
        base_path = self.get_path(path_key)
        full_path = str(PurePosixPath(base_path, filename))
        return full_path
    
    def _get_absolute_path(self, relative_path: str) -> str:
        """Convert relative OneDrive path to absolute filesystem path."""
        return os.path.join(self.od_root, relative_path.replace('/', os.sep))
    
    def format_filename(self, pattern_key: str, **kwargs) -> str:
        """Format a filename using a pattern from the config.
        
        Args:
            pattern_key: Key for the file pattern in config
            **kwargs: Values to format into the pattern
            
        Returns:
            str: Formatted filename
        """
        pattern = self.config['file_patterns'][pattern_key]
        return pattern.format(**kwargs)
    
    def get_timestamp(self, format_key: str = 'default') -> str:
        """Get a formatted timestamp using a format from the config.
        
        Args:
            format_key: Key for the timestamp format in config
            
        Returns:
            str: Formatted timestamp
        """
        format_str = self.config['timestamp_formats'][format_key]
        return datetime.now().strftime(format_str)

    def upload_file(self, path: str, data: bytes) -> None:
        """Upload bytes to OneDrive at the given path using atomic write.
        
        Args:
            path: Target file path relative to OneDrive root
            data: Binary data to upload
        """
        abs_path = self._get_absolute_path(path)
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        
        # Atomic write: write to temp file then rename
        temp_path = abs_path + ".tmp"
        try:
            with open(temp_path, "wb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())  # Force write to disk
            
            # Atomic rename
            os.replace(temp_path, abs_path)
        except Exception as e:
            # Clean up temp file if it exists
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise e

    def download_file(self, path: str) -> bytes:
        """Download bytes from OneDrive at the given path.
        
        Args:
            path: File path relative to OneDrive root
            
        Returns:
            bytes: File contents
        """
        abs_path = self._get_absolute_path(path)
        
        if not os.path.exists(abs_path):
            raise FileNotFoundError(f"File not found: {path}")
        
        with open(abs_path, "rb") as f:
            return f.read()

    def list_files(self, folder_path: str) -> List[Dict]:
        """List files in a OneDrive folder.
        
        Args:
            folder_path: Folder path relative to OneDrive root
            
        Returns:
            List of file metadata dictionaries (compatible with Graph API format)
        """
        abs_folder_path = self._get_absolute_path(folder_path)
        
        if not os.path.exists(abs_folder_path):
            return []
        
        files = []
        try:
            for item in os.listdir(abs_folder_path):
                item_path = os.path.join(abs_folder_path, item)
                stat = os.stat(item_path)
                
                # Create metadata dict compatible with Graph API format
                file_info = {
                    'name': item,
                    'size': stat.st_size,
                    'lastModifiedDateTime': datetime.fromtimestamp(stat.st_mtime).isoformat() + 'Z',
                    'folder': os.path.isdir(item_path),
                    'parentReference': {'path': folder_path},
                    'id': f"local_{abs(hash(item_path))}",  # Generate pseudo-ID
                    'webUrl': f"file://{item_path}"
                }
                files.append(file_info)
        except PermissionError:
            # Return empty list if we can't access the folder
            pass
        
        return files

    def delete_file(self, path: str) -> None:
        """Delete a file from OneDrive.
        
        Args:
            path: File path relative to OneDrive root
        """
        abs_path = self._get_absolute_path(path)
        
        if os.path.exists(abs_path):
            os.remove(abs_path)

    def upload_csv(self, path: str, df: pd.DataFrame) -> None:
        """Upload a pandas DataFrame as a CSV file to OneDrive.
        
        Args:
            path: Target file path relative to OneDrive root
            df: DataFrame to upload
        """
        with io.StringIO() as buffer:
            df.to_csv(buffer, index=False)
            data = buffer.getvalue().encode("utf-8")
        self.upload_file(path, data)

    def download_csv(self, path: str) -> pd.DataFrame:
        """Download a CSV file from OneDrive and return as a pandas DataFrame.
        
        Args:
            path: File path relative to OneDrive root
            
        Returns:
            pd.DataFrame: The CSV data as a DataFrame
        """
        data = self.download_file(path)
        with io.StringIO(data.decode('utf-8')) as buffer:
            return pd.read_csv(buffer)

    def file_exists(self, path: str) -> bool:
        """Check if a file exists in OneDrive.
        
        Args:
            path: File path relative to OneDrive root
            
        Returns:
            bool: True if file exists, False otherwise
        """
        abs_path = self._get_absolute_path(path)
        return os.path.exists(abs_path)

    def get_file_size(self, path: str) -> int:
        """Get file size in bytes.
        
        Args:
            path: File path relative to OneDrive root
            
        Returns:
            int: File size in bytes
        """
        abs_path = self._get_absolute_path(path)
        if os.path.exists(abs_path):
            return os.path.getsize(abs_path)
        return 0


# Backward compatibility - maintain async interface for existing code
class AsyncOneDriveStorage(OneDriveStorage):
    """Async wrapper for OneDriveStorage to maintain backward compatibility."""
    
    async def upload_file(self, path: str, data: bytes) -> None:
        """Async wrapper for upload_file."""
        super().upload_file(path, data)
    
    async def download_file(self, path: str) -> bytes:
        """Async wrapper for download_file."""
        return super().download_file(path)
    
    async def list_files(self, folder_path: str) -> List[Dict]:
        """Async wrapper for list_files."""
        return super().list_files(folder_path)
    
    async def delete_file(self, path: str) -> None:
        """Async wrapper for delete_file."""
        super().delete_file(path)
    
    async def upload_csv(self, path: str, df: pd.DataFrame) -> None:
        """Async wrapper for upload_csv."""
        super().upload_csv(path, df)
    
    async def download_csv(self, path: str) -> pd.DataFrame:
        """Async wrapper for download_csv."""
        return super().download_csv(path)


# Example usage:
"""
# Initialize the client
storage = OneDriveStorage()

# Save a file with timestamp
timestamp = storage.get_timestamp()
filename = storage.format_filename('processed_data', processed_type='summary', timestamp=timestamp)
path = storage.get_file_path('processed_data', filename)

# Upload the file
csv_data = "model_id,return,volatility\n3995,0.12,0.15".encode('utf-8')
storage.upload_file(path, csv_data)

# List files in a configured folder
files = storage.list_files(storage.get_path('raw_data'))

# Download a file
data = storage.download_file(path)
"""