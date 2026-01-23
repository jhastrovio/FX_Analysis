"""
OneDrive File Manager
====================
Analytics-only: File management interface for read-only data access.

Provides utilities for listing, exploring, and reading files from the FX data estate.
All operations are read-only with respect to /FX_Data - General. Write operations
are for ephemeral outputs only.

Note: Future structure - this will move to lib/utils/file_manager.py

Setup:
------
1. Ensure onedrive_storage.py and onedrive_config.yaml are in the same directory
2. Set up your .env file with OneDrive root path:
   OD=/path/to/your/OneDrive/root
3. Ensure OneDrive client is installed and syncing

Usage Examples:
--------------
# List files in a configured path
python file_manager.py list-onedrive-files base

# List files with filters
python file_manager.py list-onedrive-files base --pattern "*.csv" --days-ago 7

# Explore folder structure
python file_manager.py explore-onedrive-folder base --details

# List only folders
python file_manager.py list-onedrive-folders base --recursive

# Get folder statistics
python file_manager.py folder-stats base

# Preview a CSV file
python file_manager.py preview-onedrive-file base "data.csv"

# Export file list to CSV
python file_manager.py export-onedrive-list base --output-file "inventory.csv"

# Delete a file (with confirmation)
python file_manager.py delete-onedrive-file base "old_file.csv"

Programmatic Usage:
------------------
from lib.file_manager import list_files, explore_folder, get_folder_stats
from lib.onedrive_storage import OneDriveStorage

storage = OneDriveStorage()
files = list_files(storage, 'base', pattern='*.csv', recursive=True)
explore_folder(storage, 'base', show_details=True)
stats = get_folder_stats(storage, 'base')

Key Features:
------------
- List files and folders with filtering (pattern, size, date)
- Recursive search through subfolders
- Tree-like folder exploration
- File preview and metadata export
- Folder statistics and analysis
- CLI interface with Typer
- Local filesystem operations with OneDrive sync
- Error handling and user feedback

Path Keys (from onedrive_config.yaml):
-------------------------------------
- 'base': clean/systemacro_analysis
- 'raw_data': clean/systemacro_analysis/Models  
- 'processed_data': clean/systemacro_analysis/Processed
- 'logs': clean/systemacro_analysis/Logs
"""

import pandas as pd
import typer
import datetime
from pathlib import Path
from typing import List, Dict, Optional

from lib.onedrive_storage import OneDriveStorage


def list_files(
    storage: OneDriveStorage,
    path_key: str,
    pattern: str = "*.csv",
    modified_after: datetime.datetime = None,
    min_size_kb: int = None,
    include_folders: bool = False,
    recursive: bool = False
) -> List[Dict]:
    """
    List all files in a OneDrive directory matching pattern, with optional filters.

    Args:
        storage (OneDriveStorage): OneDrive storage client
        path_key (str): Dot notation path key from config (e.g. 'base', 'raw_data')
        pattern (str): File pattern filter (e.g. '*.csv')
        modified_after (datetime): Only include files modified after this
        min_size_kb (int): Only include files larger than this size in KB
        include_folders (bool): Whether to include folders in results
        recursive (bool): Whether to search subfolders recursively

    Returns:
        List[Dict]: List of file metadata dictionaries
    """
    folder_path = storage.get_path(path_key)
    files = storage.list_files(folder_path)
    
    filtered = []
    
    def process_folder(folder_path: str, current_files: List[Dict], depth: int = 0):
        """Recursively process folders and files."""
        for file_info in current_files:
            is_folder = file_info.get('folder', False)
            
            if is_folder:
                if include_folders:
                    # Add folder info with depth indicator
                    file_info['_depth'] = depth
                    file_info['_is_folder'] = True
                    filtered.append(file_info)
                
                if recursive:
                    # Get subfolder path and recursively process
                    subfolder_path = f"{folder_path}/{file_info.get('name', '')}"
                    try:
                        subfolder_files = storage.list_files(subfolder_path)
                        process_folder(subfolder_path, subfolder_files, depth + 1)
                    except Exception as e:
                        typer.echo(f"⚠️  Could not access subfolder {file_info.get('name', '')}: {e}")
            else:
                # Process files
                filename = file_info.get('name', '')
                
                # Apply pattern filter with proper wildcard support
                import fnmatch
                if not fnmatch.fnmatch(filename, pattern):
                    continue
                    
                # Apply size filter
                if min_size_kb:
                    size_kb = file_info.get('size', 0) / 1024
                    if size_kb < min_size_kb:
                        continue
                        
                # Apply date filter
                if modified_after:
                    last_modified = datetime.datetime.fromisoformat(
                        file_info.get('lastModifiedDateTime', '').replace('Z', '+00:00')
                    )
                    if last_modified < modified_after:
                        continue
                
                file_info['_depth'] = depth
                file_info['_is_folder'] = False
                filtered.append(file_info)
    
    process_folder(folder_path, files)
    return filtered


def list_folders(storage: OneDriveStorage, path_key: str, recursive: bool = False) -> List[Dict]:
    """
    List all folders in a OneDrive directory.

    Args:
        storage (OneDriveStorage): OneDrive storage client
        path_key (str): Dot notation path key from config
        recursive (bool): Whether to list subfolders recursively

    Returns:
        List[Dict]: List of folder metadata dictionaries
    """
    folder_path = storage.get_path(path_key)
    items = storage.list_files(folder_path)
    
    folders = []
    
    def process_folders(current_path: str, current_items: List[Dict], depth: int = 0):
        """Recursively process folders."""
        for item in current_items:
            if item.get('folder', False):
                item['_depth'] = depth
                item['_is_folder'] = True
                folders.append(item)
                
                if recursive:
                    # Get subfolder path and recursively process
                    subfolder_path = f"{current_path}/{item.get('name', '')}"
                    try:
                        subfolder_items = storage.list_files(subfolder_path)
                        process_folders(subfolder_path, subfolder_items, depth + 1)
                    except Exception as e:
                        typer.echo(f"⚠️  Could not access subfolder {item.get('name', '')}: {e}")
    
    process_folders(folder_path, items)
    return folders


def explore_folder(storage: OneDriveStorage, path_key: str, show_details: bool = False) -> None:
    """
    Explore a OneDrive folder structure with a tree-like display.

    Args:
        storage (OneDriveStorage): OneDrive storage client
        path_key (str): Dot notation path key from config
        show_details (bool): Whether to show file details (size, date)
    """
    folder_path = storage.get_path(path_key)
    items = storage.list_files(folder_path)
    
    typer.echo(f"\n📁 Exploring: {folder_path}")
    typer.echo("=" * 50)
    
    def display_tree(current_path: str, current_items: List[Dict], depth: int = 0):
        """Display folder structure as a tree."""
        indent = "  " * depth
        
        for item in sorted(current_items, key=lambda x: (not x.get('folder', False), x.get('name', ''))):
            is_folder = item.get('folder', False)
            name = item.get('name', 'Unknown')
            
            if is_folder:
                icon = "📁"
                typer.echo(f"{indent}{icon} {name}/")
                
                # Recursively explore subfolder
                subfolder_path = f"{current_path}/{name}"
                try:
                    subfolder_items = storage.list_files(subfolder_path)
                    display_tree(subfolder_path, subfolder_items, depth + 1)
                except Exception as e:
                    typer.echo(f"{indent}  ⚠️  Cannot access: {e}")
            else:
                icon = "📄"
                if show_details:
                    size_kb = round(item.get('size', 0) / 1024, 2)
                    modified = item.get('lastModifiedDateTime', 'Unknown')
                    typer.echo(f"{indent}{icon} {name} ({size_kb} KB, {modified})")
                else:
                    typer.echo(f"{indent}{icon} {name}")
    
    display_tree(folder_path, items)


def get_folder_stats(storage: OneDriveStorage, path_key: str) -> Dict:
    """
    Get statistics about a OneDrive folder.

    Args:
        storage (OneDriveStorage): OneDrive storage client
        path_key (str): Dot notation path key from config

    Returns:
        Dict: Folder statistics
    """
    folder_path = storage.get_path(path_key)
    items = storage.list_files(folder_path)
    
    stats = {
        'total_items': len(items),
        'files': 0,
        'folders': 0,
        'total_size_bytes': 0,
        'file_types': {},
        'oldest_file': None,
        'newest_file': None
    }
    
    for item in items:
        if item.get('folder', False):
            stats['folders'] += 1
        else:
            stats['files'] += 1
            size = item.get('size', 0)
            stats['total_size_bytes'] += size
            
            # Track file types
            filename = item.get('name', '')
            if '.' in filename:
                ext = filename.split('.')[-1].lower()
                stats['file_types'][ext] = stats['file_types'].get(ext, 0) + 1
            
            # Track dates
            modified_str = item.get('lastModifiedDateTime', '')
            if modified_str:
                try:
                    modified_date = datetime.datetime.fromisoformat(
                        modified_str.replace('Z', '+00:00')
                    )
                    if not stats['oldest_file'] or modified_date < stats['oldest_file']:
                        stats['oldest_file'] = modified_date
                    if not stats['newest_file'] or modified_date > stats['newest_file']:
                        stats['newest_file'] = modified_date
                except:
                    pass
    
    stats['total_size_mb'] = round(stats['total_size_bytes'] / (1024 * 1024), 2)
    return stats


def preview_file(storage: OneDriveStorage, path_key: str, filename: str, n: int = 5) -> pd.DataFrame:
    """Load and preview the first few rows (read-only from FX data estate)."""
    try:
        file_path = storage.get_file_path(path_key, filename)
        df = storage.download_csv(file_path)
        typer.echo(f"\nPreview of: {filename} (rows: {len(df)}, columns: {len(df.columns)})")
        return df.head(n)
    except Exception as e:
        typer.echo(f"❌ Failed to read {filename}: {e}")
        return pd.DataFrame()


def load_full_file(storage: OneDriveStorage, path_key: str, filename: str) -> pd.DataFrame:
    """Load the complete file (read-only from FX data estate)."""
    try:
        file_path = storage.get_file_path(path_key, filename)
        df = storage.download_csv(file_path)
        return df
    except Exception as e:
        typer.echo(f"❌ Failed to read {filename}: {e}")
        return pd.DataFrame()


def delete_file(storage: OneDriveStorage, path_key: str, filename: str, confirm: bool = True) -> bool:
    """Delete a file from OneDrive with optional confirmation."""
    if confirm:
        response = input(f"Are you sure you want to delete {filename}? [y/N] ")
        if response.lower() != 'y':
            typer.echo("❌ Deletion cancelled.")
            return False
    
    try:
        file_path = storage.get_file_path(path_key, filename)
        storage.delete_file(file_path)
        typer.echo(f"✅ Deleted: {filename}")
        return True
    except Exception as e:
        typer.echo(f"❌ Could not delete {filename}: {e}")
        return False


def export_file_list(files: List[Dict], output_path: str) -> None:
    """
    Export list of OneDrive files and metadata to a CSV.

    Args:
        files (List[Dict]): List of file metadata dictionaries from OneDrive
        output_path (str): Where to save the metadata CSV
    """
    rows = []
    for file_info in files:
        try:
            # Convert OneDrive datetime to Python datetime
            last_modified_str = file_info.get('lastModifiedDateTime', '')
            if last_modified_str:
                last_modified = datetime.datetime.fromisoformat(
                    last_modified_str.replace('Z', '+00:00')
                )
            else:
                last_modified = None
                
            rows.append({
                "filename": file_info.get('name', ''),
                "path": file_info.get('parentReference', {}).get('path', ''),
                "size_kb": round(file_info.get('size', 0) / 1024, 2),
                "modified_time": last_modified,
                "file_id": file_info.get('id', ''),
                "web_url": file_info.get('webUrl', '')
            })
        except Exception:
            continue
    
    df = pd.DataFrame(rows)
    df.to_csv(output_path, index=False)
    typer.echo(f"📄 Exported file list to {output_path}")


def upload_file(storage: OneDriveStorage, path_key: str, filename: str, data: bytes) -> bool:
    """
    Write a file (for ephemeral outputs only).
    
    Note: This is for temporary analysis artifacts, not for writing back to
    the governed data estate at /FX_Data - General.

    Args:
        storage (OneDriveStorage): OneDrive storage client
        path_key (str): Dot notation path key from config
        filename (str): Name of the file to write
        data (bytes): File data to write

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        file_path = storage.get_file_path(path_key, filename)
        storage.upload_file(file_path, data)
        typer.echo(f"✅ Uploaded: {filename}")
        return True
    except Exception as e:
        typer.echo(f"❌ Failed to upload {filename}: {e}")
        return False


def upload_csv(storage: OneDriveStorage, path_key: str, filename: str, df: pd.DataFrame) -> bool:
    """
    Write a pandas DataFrame as CSV (for ephemeral outputs only).
    
    Note: This is for temporary analysis artifacts, not for writing back to
    the governed data estate at /FX_Data - General.

    Args:
        storage (OneDriveStorage): OneDrive storage client
        path_key (str): Dot notation path key from config
        filename (str): Name of the CSV file
        df (pd.DataFrame): DataFrame to write

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        file_path = storage.get_file_path(path_key, filename)
        storage.upload_csv(file_path, df)
        typer.echo(f"✅ Uploaded CSV: {filename}")
        return True
    except Exception as e:
        typer.echo(f"❌ Failed to upload CSV {filename}: {e}")
        return False


# CLI Commands using Typer
app = typer.Typer()


@app.command()
def list_onedrive_files(
    path_key: str = typer.Argument(..., help="Path key from config (e.g., 'base', 'raw_data')"),
    pattern: str = typer.Option("*.csv", help="File pattern filter"),
    min_size_kb: Optional[int] = typer.Option(None, help="Minimum file size in KB"),
    days_ago: Optional[int] = typer.Option(None, help="Only files modified in last N days"),
    include_folders: bool = typer.Option(False, help="Include folders in results"),
    recursive: bool = typer.Option(False, help="Search subfolders recursively")
):
    """List files in OneDrive directory with optional filters."""
    storage = OneDriveStorage()
    
    modified_after = None
    if days_ago:
        modified_after = datetime.datetime.now() - datetime.timedelta(days=days_ago)
    
    files = list_files(storage, path_key, pattern, modified_after, min_size_kb, include_folders, recursive)
    
    if not files:
        # Check if there are any items (folders) in the directory
        folder_path = storage.get_path(path_key)
        all_items = storage.list_files(folder_path)
        if all_items:
            folders_only = [item for item in all_items if item.get('folder', False)]
            if folders_only and not include_folders:
                typer.echo(f"No files found matching '{pattern}' in {path_key}.")
                typer.echo(f"Found {len(folders_only)} folder(s). Use --include-folders to see them, or check subdirectories like 'raw_data' or 'processed_data'.")
            else:
                typer.echo("No files found matching criteria.")
        else:
            typer.echo(f"Directory '{path_key}' is empty.")
        return
        
    typer.echo(f"\nFound {len(files)} items in {path_key}:")
    for file_info in files:
        depth = file_info.get('_depth', 0)
        indent = "  " * depth
        is_folder = file_info.get('_is_folder', False)
        
        if is_folder:
            icon = "📁"
            typer.echo(f"{indent}{icon} {file_info.get('name', 'Unknown')}/")
        else:
            icon = "📄"
            size_kb = round(file_info.get('size', 0) / 1024, 2)
            modified = file_info.get('lastModifiedDateTime', 'Unknown')
            typer.echo(f"{indent}{icon} {file_info.get('name', 'Unknown')} ({size_kb} KB) - {modified}")


@app.command()
def preview_onedrive_file(
    path_key: str = typer.Argument(..., help="Path key from config"),
    filename: str = typer.Argument(..., help="Name of file to preview"),
    rows: int = typer.Option(5, help="Number of rows to preview")
):
    """Preview the first few rows of a OneDrive CSV file."""
    storage = OneDriveStorage()
    df = preview_file(storage, path_key, filename, rows)
    if not df.empty:
        typer.echo(df.to_string(index=False))


@app.command()
def load_onedrive_file(
    path_key: str = typer.Argument(..., help="Path key from config"),
    filename: str = typer.Argument(..., help="Name of file to load"),
    output_file: str = typer.Option(None, help="Save to local CSV file")
):
    """Load the complete OneDrive CSV file."""
    storage = OneDriveStorage()
    df = load_full_file(storage, path_key, filename)
    if not df.empty:
        typer.echo(f"✅ Loaded: {filename} (rows: {len(df)}, columns: {len(df.columns)})")
        if output_file:
            df.to_csv(output_file, index=False)
            typer.echo(f"📄 Saved to: {output_file}")
        else:
            typer.echo(df.to_string(index=False))
    else:
        typer.echo(f"❌ Failed to load {filename}")


@app.command()
def export_onedrive_list(
    path_key: str = typer.Argument(..., help="Path key from config"),
    output_file: str = typer.Option("onedrive_files.csv", help="Output CSV file name"),
    pattern: str = typer.Option("*.csv", help="File pattern filter")
):
    """Export OneDrive file list to CSV."""
    storage = OneDriveStorage()
    files = list_files(storage, path_key, pattern)
    export_file_list(files, output_file)


@app.command()
def delete_onedrive_file(
    path_key: str = typer.Argument(..., help="Path key from config"),
    filename: str = typer.Argument(..., help="Name of file to delete"),
    force: bool = typer.Option(False, help="Skip confirmation prompt")
):
    """Delete a file from OneDrive."""
    storage = OneDriveStorage()
    delete_file(storage, path_key, filename, not force)


@app.command()
def list_onedrive_folders(
    path_key: str = typer.Argument(..., help="Path key from config"),
    recursive: bool = typer.Option(False, help="List subfolders recursively")
):
    """List folders in OneDrive directory."""
    storage = OneDriveStorage()
    folders = list_folders(storage, path_key, recursive)
    
    if not folders:
        typer.echo("No folders found.")
        return
        
    typer.echo(f"\nFound {len(folders)} folders in {path_key}:")
    for folder_info in folders:
        depth = folder_info.get('_depth', 0)
        indent = "  " * depth
        name = folder_info.get('name', 'Unknown')
        modified = folder_info.get('lastModifiedDateTime', 'Unknown')
        typer.echo(f"{indent}📁 {name}/ - {modified}")


@app.command()
def explore_onedrive_folder(
    path_key: str = typer.Argument(..., help="Path key from config"),
    details: bool = typer.Option(False, help="Show file details (size, date)")
):
    """Explore OneDrive folder structure with tree view."""
    storage = OneDriveStorage()
    explore_folder(storage, path_key, details)


@app.command()
def folder_stats(
    path_key: str = typer.Argument(..., help="Path key from config")
):
    """Get statistics about a OneDrive folder."""
    storage = OneDriveStorage()
    stats = get_folder_stats(storage, path_key)
    
    typer.echo(f"\n📊 Folder Statistics for {path_key}:")
    typer.echo("=" * 40)
    typer.echo(f"Total items: {stats['total_items']}")
    typer.echo(f"Files: {stats['files']}")
    typer.echo(f"Folders: {stats['folders']}")
    typer.echo(f"Total size: {stats['total_size_mb']} MB")
    
    if stats['file_types']:
        typer.echo(f"\nFile types:")
        for ext, count in sorted(stats['file_types'].items()):
            typer.echo(f"  .{ext}: {count} files")
    
    if stats['oldest_file']:
        typer.echo(f"\nOldest file: {stats['oldest_file']}")
    if stats['newest_file']:
        typer.echo(f"Newest file: {stats['newest_file']}")


if __name__ == "__main__":
    app()