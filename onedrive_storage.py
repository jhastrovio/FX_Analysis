"""OneDrive Storage Module
A reusable module for interacting with Microsoft OneDrive via Graph API.
Supports reading, writing, listing, and deleting files.
"""

import os
import asyncio
import io
from typing import List, Dict
from datetime import datetime

import aiohttp
import msal
import yaml
import pandas as pd
from dotenv import load_dotenv

from pathlib import PurePosixPath

# Constants
GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0/users/{user_email}/drive/root:/{path}:/content"
DEVICE_CACHE_PATH = os.path.expanduser("~/.onedrive_msal_cache.bin")

class OneDriveStorage:
    """OneDrive storage client for file operations."""
    
    def __init__(self, 
                 client_id: str = None,
                 client_secret: str = None,
                 tenant_id: str = None,
                 user_email: str = None,
                 env_file: str = ".env",
                 config_file: str = "onedrive_config.yaml"):
        """Initialize OneDrive client with credentials.
        
        Args:
            client_id: Microsoft Graph API client ID
            client_secret: Microsoft Graph API client secret
            tenant_id: Microsoft tenant ID
            user_email: User's email for OneDrive access
            env_file: Path to .env file (default: .env)
            config_file: Path to YAML config file (default: onedrive_config.yaml)
        """
        # Load environment variables if env_file exists
        if os.path.exists(env_file):
            load_dotenv(env_file, override=True)
        
        # Use provided credentials or fall back to environment variables
        self.client_id = client_id or os.getenv('ONEDRIVE_CLIENT_ID')
        self.client_secret = client_secret or os.getenv('ONEDRIVE_CLIENT_SECRET')
        self.tenant_id = tenant_id or os.getenv('ONEDRIVE_TENANT_ID')
        self.user_email = user_email or os.getenv('ONEDRIVE_USER_EMAIL')
        
        if not all([self.client_id, self.client_secret, self.tenant_id, self.user_email]):
            raise ValueError("Missing OneDrive credentials. Provide them directly or via environment variables.")
        
        # Load configuration
        self.config = self._load_config(config_file)
    
    def _load_config(self, config_file: str) -> Dict:
        """Load configuration from YAML file."""
        if not os.path.exists(config_file):
            raise FileNotFoundError(f"Configuration file not found: {config_file}")
        
        with open(config_file, 'r') as f:
            return yaml.safe_load(f)
    
    def get_path(self, path_key: str) -> str:
        """Get a configured path from the config file.
        
        Args:
            path_key: Dot-notation path key (e.g., 'market_data.hourly')
            
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
            path_key: Dot-notation path key (e.g., 'market_data.hourly')
            filename: The filename to append (e.g., 'rates_2024.csv')

        Returns:
            str: The normalized POSIX-style full file path relative to OneDrive root.

        Example:
            get_file_path('reports.daily', 'summary.csv')
            -> 'FX_Data/Reports/Daily/summary.csv'
        """
        base_path = self.get_path(path_key)
        full_path = str(PurePosixPath(base_path, filename))
        return full_path
    
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

    def _get_access_token(self) -> str:
        """Get Microsoft Graph access token using MSAL Client Credentials Flow."""
        authority = f"https://login.microsoftonline.com/{self.tenant_id}"
        scope = ["https://graph.microsoft.com/.default"]

        # Use a persistent token cache
        cache = msal.SerializableTokenCache()
        if os.path.exists(DEVICE_CACHE_PATH):
            cache.deserialize(open(DEVICE_CACHE_PATH, "r").read())
        
        app = msal.ConfidentialClientApplication(
            client_id=self.client_id,
            client_credential=self.client_secret,
            authority=authority,
            token_cache=cache
        )

        # Try to get token silently first
        accounts = app.get_accounts()
        if accounts:
            result = app.acquire_token_silent(scope, account=accounts[0])
            if result and "access_token" in result:
                return result["access_token"]

        # Use client credentials flow
        result = app.acquire_token_for_client(scopes=scope)
        
        if "access_token" in result:
            # Save cache
            with open(DEVICE_CACHE_PATH, "w") as f:
                f.write(cache.serialize())
            return result["access_token"]
        else:
            raise RuntimeError(f"Failed to acquire token: {result.get('error_description', result)}")

    async def _get_access_token_async(self, session: aiohttp.ClientSession) -> str:
        """Async wrapper for getting access token."""
        return await asyncio.get_event_loop().run_in_executor(None, self._get_access_token)

    async def upload_file(self, path: str, data: bytes) -> None:
        """Upload bytes to OneDrive at the given path.
        
        Args:
            path: Target file path relative to OneDrive root
            data: Binary data to upload
        """
        async with aiohttp.ClientSession() as session:
            token = await self._get_access_token_async(session)
            
            # Determine content type based on file extension
            ext = os.path.splitext(path)[1].lower().lstrip('.')
            content_type = self.config['content_types'].get(ext, 'application/octet-stream')
            
            url = GRAPH_BASE_URL.format(user_email=self.user_email, path=path) + "?@microsoft.graph.conflictBehavior=replace"
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": content_type
            }
            
            async with session.put(url, headers=headers, data=data) as resp:
                try:
                    resp.raise_for_status()
                except aiohttp.ClientResponseError as e:
                    if e.status == 423:
                        raise RuntimeError(
                            f"OneDrive file is locked (status 423).\n"
                            "Please close the file in Excel or Office and retry upload."
                        )
                    else:
                        raise

    async def download_file(self, path: str) -> bytes:
        """Download bytes from OneDrive at the given path.
        
        Args:
            path: File path relative to OneDrive root
            
        Returns:
            bytes: File contents
        """
        url = GRAPH_BASE_URL.format(user_email=self.user_email, path=path)
        async with aiohttp.ClientSession() as session:
            token = await self._get_access_token_async(session)
            headers = {"Authorization": f"Bearer {token}"}
            async with session.get(url, headers=headers) as resp:
                resp.raise_for_status()
                return await resp.read()

    async def list_files(self, folder_path: str) -> List[Dict]:
        """List files in a OneDrive folder.
        
        Args:
            folder_path: Folder path relative to OneDrive root
            
        Returns:
            List of file metadata dictionaries
        """
        url = f"https://graph.microsoft.com/v1.0/users/{self.user_email}/drive/root:/{folder_path}:/children"
        async with aiohttp.ClientSession() as session:
            token = await self._get_access_token_async(session)
            headers = {"Authorization": f"Bearer {token}"}
            async with session.get(url, headers=headers) as resp:
                resp.raise_for_status()
                data = await resp.json()
                return data.get('value', [])

    async def delete_file(self, path: str) -> None:
        """Delete a file from OneDrive.
        
        Args:
            path: File path relative to OneDrive root
        """
        url = f"https://graph.microsoft.com/v1.0/users/{self.user_email}/drive/root:/{path}"
        async with aiohttp.ClientSession() as session:
            token = await self._get_access_token_async(session)
            headers = {"Authorization": f"Bearer {token}"}
            async with session.delete(url, headers=headers) as resp:
                resp.raise_for_status()

    async def upload_csv(self, path: str, df: pd.DataFrame) -> None:
        """Upload a pandas DataFrame as a CSV file to OneDrive.
        
        Args:
            path: Target file path relative to OneDrive root
            df: DataFrame to upload
        """
        with io.StringIO() as buffer:
            df.to_csv(buffer, index=False)
            data = buffer.getvalue().encode("utf-8")
        await self.upload_file(path, data)

    async def download_csv(self, path: str) -> pd.DataFrame:
        """Download a CSV file from OneDrive and return as a pandas DataFrame.
        
        Args:
            path: File path relative to OneDrive root
            
        Returns:
            pd.DataFrame: The CSV data as a DataFrame
        """
        data = await self.download_file(path)
        with io.StringIO(data.decode('utf-8')) as buffer:
            return pd.read_csv(buffer)

# Example usage:
"""
# Initialize the client
storage = OneDriveStorage()

# Save a market rates file with timestamp
timestamp = storage.get_timestamp()
filename = storage.format_filename('market_rates', timestamp=timestamp)
path = storage.get_file_path('market_data.hourly', filename)

# Upload the file
csv_data = "timestamp,symbol,price\n2024-01-01,EUR-USD,1.2345".encode('utf-8')
await storage.upload_file(path, csv_data)

# List files in a configured folder
files = await storage.list_files(storage.get_path('market_data.hourly'))

# Download a config file
config_data = await storage.download_file(storage.get_path('config.stream_config'))
"""