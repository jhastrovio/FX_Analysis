#!/usr/bin/env python
"""
Test OneDrive connectivity and list files in the Models folder.
"""
import asyncio
from onedrive_storage import OneDriveStorage

async def test_onedrive():
    """Test OneDrive connection and list files."""
    try:
        print("Initializing OneDrive storage...")
        storage = OneDriveStorage()
        
        # Test listing files in the Models folder
        models_path = "FX_Data/Systemacro_Data/Models"
        print(f"Listing files in: {models_path}")
        
        files = await storage.list_files(models_path)
        
        print(f"Found {len(files)} files:")
        for file in files:
            print(f"  - {file['name']}")
            
        # Check specifically for Model_Index.csv
        model_index_files = [f for f in files if f['name'] == 'Model_Index.csv']
        if model_index_files:
            print(f"\n✅ Model_Index.csv found!")
        else:
            print(f"\n❌ Model_Index.csv NOT found in {models_path}")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_onedrive()) 