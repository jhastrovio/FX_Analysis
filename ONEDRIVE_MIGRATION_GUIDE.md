# OneDrive Configuration and Migration Guide
**Extracted from fx-data-backend-v2 codebase**

This document provides complete OneDrive configuration details for migrating to another repository (FX_Analysis).

---

## 1. AUTHENTICATION CONFIGURATION

### Current Implementation (v2 - Local Filesystem Sync)

**Important Note**: The current codebase (v2) uses **local filesystem sync** rather than direct Microsoft Graph API calls. Files are written to a local OneDrive-synced directory, and OneDrive client handles the cloud sync automatically.

**No Graph API credentials are required** for the current implementation.

### Deprecated Implementation (Graph API - Archived)

The archived code in `_archive/graph_api_deprecated/` shows the previous Graph API implementation. If you need to restore Graph API functionality, use these credentials:

#### Environment Variables (from deprecated code):

```env
# Microsoft Graph API Credentials (for deprecated Graph API implementation)
ONEDRIVE_CLIENT_ID=your_client_id
ONEDRIVE_CLIENT_SECRET=your_client_secret
ONEDRIVE_TENANT_ID=your_tenant_id
ONEDRIVE_USER_EMAIL=your_email
```

#### MSAL Configuration (from deprecated code):

- **Authority**: `https://login.microsoftonline.com/{tenant_id}`
- **Scope**: `["https://graph.microsoft.com/.default"]`
- **Token Cache**: `~/.onedrive_msal_cache.bin`
- **Flow**: Client Credentials Flow (Application permissions)
- **Library**: `msal>=1.25`

#### Graph API Email Service (Still Active)

The email service (`lib/providers/graph_email_service_app_only.py`) still uses Graph API for sending emails:

- **Graph URL**: `https://graph.microsoft.com/v1.0`
- **Sender Email**: Configured via `ALERT_SENDER_EMAIL` env var (default: `alerts@tassehcapital.onmicrosoft.com`)
- **Recipient**: Uses `USER_EMAIL` from settings
- **Endpoint**: `/users/{from_address}/sendMail`
- **Note**: This service references `_get_access_token_client_credentials` from `lib.storage.onedrive`, but this function is missing in the current implementation (likely needs to be restored from deprecated code)

---

## 2. ONEDRIVE FOLDER STRUCTURE AND PATHS

### Root Path

**OneDrive Root Path**:
```
/Users/jameshassett/Library/CloudStorage/OneDrive-SharedLibraries-IntellectiveCapitalPte.Ltd/FX_Data - General
```

**Environment Variable**:
- `OD` - Must be set to the OneDrive root directory

### Complete Folder Hierarchy

```
${OD}/
├── clean/                          # Processed/cleaned datasets
│   ├── snapshot_hourly_live/      # Hourly live snapshots
│   │   └── ym=YYYY-MM/            # Partitioned by year-month
│   │       └── port_snapshot_hourly_YYYYMMDD_HHMM.csv
│   │       └── port_snapshot_hourly_YYYYMMDD_HHMM.csv.manifest.json
│   ├── models_signals_systemacro/  # Systemacro model signals
│   │   └── {model_id}_{model_name}-{date}.csv
│   ├── position_systemacro/        # Systemacro position data
│   │   └── position_systemacro-{YYYYMMDD}.csv
│   └── reactive_dload/            # Reactive Markets trade data
│
├── auth/                           # Authoritative datasets
│   ├── hist_hourly/               # Historical hourly data (per symbol)
│   │   └── symbol={SYMBOL}/      # e.g., symbol=EURUSD
│   │       └── hist_hourly_{SYMBOL}_{YYYY-MM}.csv
│   │       └── hist_hourly_{SYMBOL}_{YYYY-MM}.csv.manifest.json
│   ├── eod_close_auth/            # EOD close authoritative data
│   │   └── symbol={SYMBOL}/
│   │       └── ym={YYYY-MM}/
│   │           └── eod_close_auth_{SYMBOL}_{YYYY-MM}.csv
│   ├── eod/                       # EOD portfolio data
│   │   └── portfolio={PORTFOLIO}/ # e.g., portfolio=FX24
│   │       └── ym={YYYY-MM}/
│   │           └── eod_portfolio_{PORTFOLIO}_{YYYYMMDD}.csv
│   └── positions_derived/         # Derived position data
│       └── positions_derived-{YYYYMMDD}.csv
│
├── publish/                        # Published datasets (for consumption)
│   ├── hourly_snapshot_csv/        # Hourly snapshots (published)
│   │   └── ymd={YYYY-MM-DD}/
│   │       └── snapshot_{YYYYMMDD}_{HHMM}.csv
│   ├── eod_csv/                    # EOD CSV files
│   ├── eod_daily/                  # Unified EOD daily dataset
│   │   └── Year={YYYY}/
│   │       └── YM={Mon_YY}/        # e.g., YM=Jan_25
│   │           └── eod_daily-{YYYYMMDD}-{cut_label}.csv
│   ├── eod_xasset/                 # EOD cross-asset dataset
│   │   └── Year={YYYY}/
│   │       └── YM={Mon_YY}/
│   │           └── eod_xasset-{YYYYMMDD}-{cut_label}.csv
│   ├── pnl_hourly/                 # Hourly P&L data
│   │   └── Year={YYYY}/
│   │       └── YM={Mon_YY}/
│   │           └── pnl_hourly_{YYYYMMDD}_{HHMM}.csv
│   └── eod/                        # Legacy EOD portfolio files
│       └── eod_portfolio_{PORTFOLIO}_{YYYYMMDD}.csv
│
└── _meta/                          # Metadata and configuration
    ├── manifests/                  # Manifest registry
    │   └── manifest.json
    ├── inventory/                  # Data inventory
    │   └── current_data_inventory.json
    ├── symbols.yaml                # Symbol definitions
    ├── provider_adapters.yaml      # Provider configuration
    ├── provider_priority.yaml      # Provider priority rules
    ├── symbol_map.yaml             # Symbol mapping
    └── trading_calendar.json       # Trading calendar
```

### Path Configuration File

**File**: `config/paths.yaml`

```yaml
# Local SharePoint path (authoritative storage)
OD: "${OD}"
V2_ROOT: "${OD}"

# Dataset roots
CLEAN: "${V2_ROOT}/clean"
AUTH: "${V2_ROOT}/auth"

# Publish directories
PUBLISH_HOURLY: "${V2_ROOT}/publish/hourly_snapshot_csv"
PUBLISH_EOD: "${V2_ROOT}/publish/eod_csv"

# Metadata
META: "${V2_ROOT}/_meta"
```

**Path Resolution**:
- Paths are loaded via `lib/utils/config.py`
- `${OD}` placeholder is replaced with the `OD` environment variable
- Paths are expanded using `os.path.expanduser()` and `os.path.expandvars()`

---

## 3. FILE NAMING PATTERNS AND CONVENTIONS

### Hourly Snapshots
- **Pattern**: `port_snapshot_hourly_{YYYYMMDD}_{HHMM}.csv`
- **Example**: `port_snapshot_hourly_20251017_06.csv`
- **Manifest**: `port_snapshot_hourly_{YYYYMMDD}_{HHMM}.csv.manifest.json`
- **Directory**: `clean/snapshot_hourly_live/ym={YYYY-MM}/`

### Systemacro Models
- **Pattern**: `{model_id}_{model_name}-{YYYYMMDD}.csv`
- **Example**: `113_COT NC Follow v01-20250924.csv`
- **Directory**: `clean/models_signals_systemacro/`

### Systemacro Positions
- **Pattern**: `position_systemacro-{YYYYMMDD}.csv`
- **Example**: `position_systemacro-20251017.csv`
- **Directory**: `clean/position_systemacro/`

### Historical Hourly (Authoritative)
- **Pattern**: `hist_hourly_{SYMBOL}_{YYYY-MM}.csv`
- **Example**: `hist_hourly_EURUSD_2025-10.csv`
- **Directory**: `auth/hist_hourly/symbol={SYMBOL}/`

### EOD Portfolio
- **Pattern**: `eod_portfolio_{PORTFOLIO}_{YYYYMMDD}.csv`
- **Example**: `eod_portfolio_FX24_20251016.csv`
- **Directory**: `auth/eod/portfolio={PORTFOLIO}/ym={YYYY-MM}/`

### EOD Close (Authoritative)
- **Pattern**: `eod_close_auth_{SYMBOL}_{YYYY-MM}.csv`
- **Directory**: `auth/eod_close_auth/symbol={SYMBOL}/ym={YYYY-MM}/`

### EOD Daily (Published)
- **Pattern**: `eod_daily-{YYYYMMDD}-{cut_label}.csv`
- **Example**: `eod_daily-20251031-1700NY.csv`
- **Cut Labels**: `1100LON`, `1700NY`
- **Directory**: `publish/eod_daily/Year={YYYY}/YM={Mon_YY}/`

### EOD Cross-Asset
- **Pattern**: `eod_xasset-{YYYYMMDD}-{cut_label}.csv`
- **Directory**: `publish/eod_xasset/Year={YYYY}/YM={Mon_YY}/`

### PnL Hourly
- **Pattern**: `pnl_hourly_{YYYYMMDD}_{HHMM}.csv`
- **Directory**: `publish/pnl_hourly/Year={YYYY}/YM={Mon_YY}/`

### Positions Derived
- **Pattern**: `positions_derived-{YYYYMMDD}.csv`
- **Directory**: `auth/positions_derived/`

### File Extensions
- **Data Files**: `.csv`
- **Manifests**: `.manifest.json`
- **Metadata**: `.json`, `.yaml`

### Timestamp Formats
- **Date**: `YYYYMMDD` (e.g., `20251017`)
- **Date with separators**: `YYYY-MM-DD` (e.g., `2025-10-17`)
- **Date-Time**: `YYYYMMDD_HHMM` (e.g., `20251017_0600`)
- **ISO Timestamp**: `YYYY-MM-DDTHH:MM:SSZ` (e.g., `2025-10-17T06:00:00Z`)
- **Year-Month**: `YYYY-MM` (e.g., `2025-10`)
- **Month Abbreviation**: `Mon_YY` (e.g., `Jan_25`)

---

## 4. ONEDRIVE API IMPLEMENTATION

### Current Implementation (v2 - Local Filesystem)

**File**: `lib/storage/onedrive.py`

The current implementation uses simple filesystem operations:

```python
def upload_bytes(dest_path: str, data: bytes) -> str:
    """Write bytes to dest_path atomically."""
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    tmp = dest_path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, dest_path)
    return dest_path

def download_bytes(src_path: str) -> bytes:
    """Read all bytes from src_path."""
    with open(src_path, "rb") as f:
        return f.read()
```

**Key Points**:
- **No Graph API calls** - uses local filesystem only
- **Atomic writes** - uses temporary file + rename pattern
- **OneDrive sync** - handled automatically by OneDrive client
- **Synchronous operations** - no async/await

### Deprecated Implementation (Graph API)

**File**: `_archive/graph_api_deprecated/onedrive_storage.py`

The deprecated implementation shows the Graph API approach:

#### Libraries Used:
- `aiohttp>=3.9` - Async HTTP client
- `msal>=1.25` - Microsoft Authentication Library
- `python-dotenv>=1.0` - Environment variable loading
- `PyYAML>=6.0` - YAML configuration parsing

#### Key Functions:

1. **`_get_access_token()`** - Get MSAL access token using Client Credentials Flow
2. **`upload_file(path, data)`** - Upload bytes to OneDrive
3. **`download_file(path)`** - Download bytes from OneDrive
4. **`list_files(folder_path)`** - List files in OneDrive folder
5. **`delete_file(path)`** - Delete file from OneDrive

#### Graph API Endpoints:

- **Upload**: `https://graph.microsoft.com/v1.0/users/{user_email}/drive/root:/{path}:/content?@microsoft.graph.conflictBehavior=replace`
- **Download**: `https://graph.microsoft.com/v1.0/users/{user_email}/drive/root:/{path}:/content`
- **List**: `https://graph.microsoft.com/v1.0/users/{user_email}/drive/root:/{folder_path}:/children`
- **Delete**: `https://graph.microsoft.com/v1.0/users/{user_email}/drive/root:/{path}`

#### Error Handling:

- **423 Locked**: Handles files locked by Excel/Office
- **Token caching**: Uses `~/.onedrive_msal_cache.bin` for persistent token cache
- **Retry logic**: Not explicitly shown, but can be added

#### Operations:

- **Async**: All operations are async (`async def`)
- **Token management**: Automatic token refresh via MSAL cache

---

## 5. CONFIGURATION FILES

### Path Configuration

**File**: `config/paths.yaml`
```yaml
# Local SharePoint path (authoritative storage)
OD: "${OD}"
V2_ROOT: "${OD}"

# Dataset roots
CLEAN: "${V2_ROOT}/clean"
AUTH: "${V2_ROOT}/auth"

# Publish directories
PUBLISH_HOURLY: "${V2_ROOT}/publish/hourly_snapshot_csv"
PUBLISH_EOD: "${V2_ROOT}/publish/eod_csv"

# Metadata
META: "${V2_ROOT}/_meta"
```

### Deprecated OneDrive Config (Graph API)

**File**: `_archive/graph_api_deprecated/onedrive_config.yaml`

```yaml
# Base paths for different types of data
paths:
  systemacro:
    base: "FX_Data/Systemacro_Data"
    raw_data: "FX_Data/Systemacro_Data/Models"
    logs: "FX_Data/Systemacro_Data/Logs"

# File naming patterns
file_patterns:
  systemacro_data: "{model_id}_{model_name}.csv"
  systemacro_batch: "systemacro_batch_{timestamp}.zip"

# Timestamp formats for file names
timestamp_formats:
  default: "%Y-%m-%d_%H-%M-%S"  # 2024-01-01_14-30-00
  daily: "%Y-%m-%d"             # 2024-01-01
  weekly: "%Y-W%W"              # 2024-W01
  hour: "%Y-%m-%d_%H"           # 2024-01-01_14

# Content types for different file extensions
content_types:
  csv: "text/csv"
  json: "application/json"
  txt: "text/plain"
  log: "text/plain"
  pdf: "application/pdf"
  xlsx: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
  zip: "application/zip"
```

### Environment Variables

**Current Implementation** (v2):
```env
# OneDrive root path (required)
OD=/Users/jameshassett/Library/CloudStorage/OneDrive-SharedLibraries-IntellectiveCapitalPte.Ltd/FX_Data - General

# Email settings (for Graph API email service)
ALERT_SENDER_EMAIL=alerts@tassehcapital.onmicrosoft.com
USER_EMAIL=your_email@example.com
```

**Deprecated Implementation** (Graph API):
```env
# OneDrive API Credentials
ONEDRIVE_CLIENT_ID=your_client_id
ONEDRIVE_CLIENT_SECRET=your_client_secret
ONEDRIVE_TENANT_ID=your_tenant_id
ONEDRIVE_USER_EMAIL=your_email
```

### Python Configuration Modules

**File**: `lib/utils/config.py`
- Loads and expands paths from `config/paths.yaml`
- Resolves `${OD}` placeholder from environment variable
- Validates OD path (ensures it's `FX_Data - General`, not `FX_Data - Documents/General`)

**File**: `lib/config/auth_paths.py`
- Provides path helpers for authoritative datasets
- Methods for hourly, EOD, and publish paths
- Uses `AuthPaths` dataclass with `od_root` parameter

**File**: `lib/core/settings.py`
- Loads settings from environment variables
- Uses `python-dotenv` to load `.env` file
- Caches settings with `@lru_cache`

---

## 6. DEPENDENCIES AND REQUIREMENTS

### Current Implementation (v2)

**File**: `requirements.txt`

Relevant packages for OneDrive/filesystem operations:
```
python-dotenv>=1.0          # Environment variable loading
PyYAML>=6.0                # YAML configuration parsing
```

**Note**: No Graph API dependencies required for current filesystem-based approach.

### Deprecated Implementation (Graph API)

If using Graph API, these additional packages are needed:
```
aiohttp>=3.9               # Async HTTP client for Graph API
msal>=1.25                 # Microsoft Authentication Library
python-dotenv>=1.0         # Environment variable loading
PyYAML>=6.0                # YAML configuration parsing
```

### Complete Requirements

**File**: `requirements.txt`
```
pydantic>=2.6
python-dateutil>=2.9
keyring>=24
requests>=2.31
httpx>=0.27
pytz>=2024.1
openpyxl>=3.1
PyYAML>=6.0
cryptography>=41
urllib3<2
fastapi>=0.110
uvicorn[standard]>=0.23
itsdangerous>=2.1
redis>=5.0
python-multipart>=0.0.9
aiohttp>=3.9
msal>=1.25
pytest-asyncio>=0.21
pandas>=2.0
selenium>=4.0
python-dotenv>=1.0
jinja2>=3.0
```

---

## 7. CODE STRUCTURE AND KEY MODULES

### Main OneDrive Storage Module

**File**: `lib/storage/onedrive.py` (Current v2)
- `upload_bytes(dest_path, data)` - Write bytes atomically
- `download_bytes(src_path)` - Read bytes from file

**File**: `_archive/graph_api_deprecated/onedrive_storage.py` (Deprecated)
- `OneDriveStorage` class with full Graph API implementation
- Methods: `upload_file()`, `download_file()`, `list_files()`, `delete_file()`
- Token management via MSAL

### Path Configuration Modules

**File**: `lib/utils/config.py`
- `load_paths()` - Load and expand paths from YAML
- `_expand_placeholders()` - Resolve `${OD}` and other placeholders

**File**: `lib/config/paths.py`
- Exposes commonly used paths as `Path` objects
- `od_root`, `fx_data_root`, `hourly_live_root()`

**File**: `lib/config/auth_paths.py`
- `AuthPaths` dataclass with path helper methods
- Methods for hourly, EOD, and publish datasets

### Graph API Email Service

**File**: `lib/providers/graph_email_service_app_only.py`
- `GraphEmailServiceAppOnly` class
- Uses Graph API to send emails
- **Issue**: References missing `_get_access_token_client_credentials` function

### Utility Functions

**File**: `lib/io/atomic_writer.py`
- `write_csv_atomic()` - Atomic CSV writing
- `write_manifest_for_csv()` - Write manifest files

**File**: `lib/models/manifest.py`
- Manifest data structures and serialization

**File**: `lib/models/manifest_auth.py`
- Authoritative manifest structures

### Example Usage

**File**: `bin/capture_hourly_v2.py`
- Example of writing to OneDrive using `upload_bytes()`
- Shows path construction and file naming patterns

**File**: `bin/systemacro_daily_models.py`
- Example of uploading model files to OneDrive
- Shows path: `od_root / "clean" / "models_signals_systemacro" / filename`

---

## 8. MIGRATION CHECKLIST

### For Local Filesystem Approach (Current v2)

1. ✅ Set `OD` environment variable to OneDrive root path
2. ✅ Copy `config/paths.yaml` configuration
3. ✅ Copy `lib/storage/onedrive.py` (simple filesystem functions)
4. ✅ Copy `lib/utils/config.py` for path loading
5. ✅ Ensure OneDrive client is installed and syncing
6. ✅ Create folder structure: `clean/`, `auth/`, `publish/`, `_meta/`

### For Graph API Approach (Deprecated)

1. ✅ Set up Azure App Registration
2. ✅ Configure environment variables: `ONEDRIVE_CLIENT_ID`, `ONEDRIVE_CLIENT_SECRET`, `ONEDRIVE_TENANT_ID`, `ONEDRIVE_USER_EMAIL`
3. ✅ Copy `_archive/graph_api_deprecated/onedrive_storage.py`
4. ✅ Copy `_archive/graph_api_deprecated/onedrive_config.yaml`
5. ✅ Install dependencies: `aiohttp`, `msal`, `python-dotenv`, `PyYAML`
6. ✅ Implement token caching (use `~/.onedrive_msal_cache.bin`)
7. ✅ Add error handling for locked files (423 errors)

---

## 9. IMPORTANT NOTES

### Migration History

- **Old Account**: TassehCapital OneDrive (`OneDrive-SharedLibraries-TassehCapital`)
- **New Account**: IntellectiveCapital SharePoint (`OneDrive-SharedLibraries-IntellectiveCapitalPte.Ltd`)
- **Migration Date**: 2025-10-17
- **New Approach**: Local filesystem sync (no Graph API required)

### Current Architecture

- **Storage**: Local filesystem with OneDrive sync
- **No Graph API**: Direct API calls removed
- **Benefits**: Simpler, faster, no authentication complexity
- **Limitation**: Requires OneDrive client to be running and syncing

### Graph API Email Service

- Still uses Graph API for sending emails
- **Missing Function**: `_get_access_token_client_credentials` needs to be implemented
- Can be restored from deprecated code or implemented separately

### Path Validation

- Code validates that `OD` points to `FX_Data - General`, not `FX_Data - Documents/General`
- Error message guides user to correct path if wrong

---

## 10. EXAMPLE CODE SNIPPETS

### Writing to OneDrive (Current v2)

```python
from lib.storage.onedrive import upload_bytes
from lib.utils.config import load_paths
from pathlib import Path

paths = load_paths()
od_root = Path(paths.OD)

# Write CSV file
csv_path = od_root / "clean" / "snapshot_hourly_live" / "ym=2025-10" / "snapshot_20251017_0600.csv"
csv_data = "timestamp,symbol,price\n2025-10-17T06:00:00Z,EURUSD,1.2345".encode('utf-8')
upload_bytes(str(csv_path), csv_data)
```

### Reading from OneDrive (Current v2)

```python
from lib.storage.onedrive import download_bytes

csv_path = od_root / "clean" / "snapshot_hourly_live" / "ym=2025-10" / "snapshot_20251017_0600.csv"
data = download_bytes(str(csv_path))
content = data.decode('utf-8')
```

### Using Graph API (Deprecated)

```python
from onedrive_storage import OneDriveStorage
import asyncio

storage = OneDriveStorage()

async def upload_example():
    path = "FX_Data/clean/snapshot_hourly_live/snapshot_20251017_0600.csv"
    data = "timestamp,symbol,price\n2025-10-17T06:00:00Z,EURUSD,1.2345".encode('utf-8')
    await storage.upload_file(path, data)

asyncio.run(upload_example())
```

---

## END OF DOCUMENT

For questions or clarifications, refer to:
- `_archive/graph_api_deprecated/README.md` - Migration details
- `_archive/graph_api_deprecated/CONFIGURATION_GUIDE.md` - Setup guide
- `onedrive_verification_report.md` - Data verification report
- `docs/data_layout_rules_v1.1.md` - Data layout rules
