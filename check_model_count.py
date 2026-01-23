#!/usr/bin/env python3
"""
Check model count from multiple sources:
1. Model CSV files in Models directory
2. Model_Index.csv metadata
3. Master Return Matrix (if it exists)
"""
import os
import re
import csv
from pathlib import Path

def get_od_root():
    """Get OneDrive root path from .env or environment."""
    od_root = os.getenv('OD')
    
    if not od_root:
        env_file = Path('.env')
        if env_file.exists():
            try:
                with open(env_file, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith('OD=') and not line.startswith('#'):
                            od_root = line.split('=', 1)[1].strip().strip('"').strip("'")
                            break
            except Exception as e:
                print(f"⚠️  Could not read .env file: {e}")
    
    return od_root

def count_from_files(models_path):
    """Count models from CSV files."""
    if not models_path.exists():
        return None
    
    all_csv_files = list(models_path.glob("*.csv"))
    file_names = [f.name for f in all_csv_files]
    model_files = [f for f in file_names if f != "Model_Index.csv" and re.match(r"(\d+)_.*\.csv", f)]
    return len(model_files), model_files

def count_from_index(models_path):
    """Count models from Model_Index.csv."""
    model_index_path = models_path / "Model_Index.csv"
    if not model_index_path.exists():
        return None
    
    try:
        with open(model_index_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            return len(rows), rows
    except Exception as e:
        print(f"⚠️  Could not read Model_Index.csv: {e}")
        return None

def count_from_master_matrix(processed_path):
    """Count models from Master Return Matrix."""
    master_files = list(processed_path.glob("*Master*.csv"))
    if not master_files:
        return None
    
    # Use the most recent master matrix
    master_file = max(master_files, key=lambda p: p.stat().st_mtime)
    
    try:
        with open(master_file, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            header = next(reader)
            # Count columns that match model pattern (ID - Name)
            model_cols = [col for col in header if ' - ' in col]
            return len(model_cols), master_file.name
    except Exception as e:
        print(f"⚠️  Could not read master matrix: {e}")
        return None

def main():
    """Main function to count models."""
    # Try the actual folder location first
    actual_path = Path('/Users/jameshassett/Library/CloudStorage/OneDrive-IntellectiveCapitalPte.Ltd/FX_Data - General/clean/models_signals_systemacro')
    
    if actual_path.exists():
        print(f"✅ Found data at: {actual_path}\n")
        models_path = actual_path
        # Check if Models is a subdirectory or if files are directly here
        if (actual_path / "Models").exists():
            models_path = actual_path / "Models"
        processed_path = actual_path.parent / "systemacro_analysis" / "Processed"
        if not processed_path.exists():
            processed_path = actual_path / "Processed"
            if not processed_path.exists():
                processed_path = actual_path.parent / "Processed"
    else:
        # Fall back to config-based path
        od_root = get_od_root()
        if not od_root:
            print("❌ Error: OD environment variable not set")
            print("   Set it in .env file or environment")
            return
        models_path = Path(od_root) / "clean" / "systemacro_analysis" / "Models"
        processed_path = Path(od_root) / "clean" / "systemacro_analysis" / "Processed"
    
    print("🔍 Checking model count from multiple sources...\n")
    
    results = {}
    
    # 1. Count from CSV files
    print("1️⃣  Checking Model CSV files...")
    file_count = count_from_files(models_path)
    if file_count:
        count, files = file_count
        results['files'] = count
        print(f"   ✅ Found {count} model CSV files")
        if count > 0 and count <= 10:
            print(f"   Files: {', '.join(files)}")
    else:
        print(f"   ⚠️  Models directory empty or not accessible: {models_path}")
        results['files'] = 0
    
    # 2. Count from Model_Index.csv
    print("\n2️⃣  Checking Model_Index.csv...")
    index_count = count_from_index(models_path)
    if index_count:
        count, rows = index_count
        results['index'] = count
        print(f"   ✅ Model_Index.csv contains {count} models")
    else:
        print(f"   ⚠️  Model_Index.csv not found or not readable")
        results['index'] = None
    
    # 3. Count from Master Matrix
    print("\n3️⃣  Checking Master Return Matrix...")
    matrix_count = count_from_master_matrix(processed_path)
    if matrix_count:
        count, filename = matrix_count
        results['matrix'] = count
        print(f"   ✅ Master matrix '{filename}' contains {count} models")
    else:
        print(f"   ⚠️  Master matrix not found in Processed directory")
        results['matrix'] = None
    
    # Summary
    print("\n" + "="*50)
    print("📊 SUMMARY")
    print("="*50)
    
    if results.get('files'):
        print(f"   Model CSV files: {results['files']}")
    if results.get('index') is not None:
        print(f"   Model_Index.csv entries: {results['index']}")
    if results.get('matrix'):
        print(f"   Master matrix columns: {results['matrix']}")
    
    # Determine the most reliable count
    counts = [v for v in results.values() if v is not None and v > 0]
    if counts:
        max_count = max(counts)
        print(f"\n✅ Maximum model count found: {max_count}")
        if max_count != 100:
            print(f"   ⚠️  This differs from the README which mentions 100 models")
    else:
        print("\n⚠️  Could not determine model count - directories may be empty or not synced")
        print("   Try running: python Data_Consolidate.py --verbose")

if __name__ == "__main__":
    main()
