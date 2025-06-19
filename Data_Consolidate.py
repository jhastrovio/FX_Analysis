import pandas as pd
from pathlib import Path
import re
from functools import reduce
import yaml

# Load config
with open("onedrive_config.yaml", "r") as f:
    config = yaml.safe_load(f)

base_path = Path(config["paths"]["base"])
raw_data_path = Path(config["paths"]["raw_data"])
processed_data_path = Path(config["paths"]["processed_data"])

# Load metadata
metadata_file = base_path / "Model_Index.csv"
model_index = pd.read_csv(metadata_file)

# Folder where model return files are stored
data_folder = raw_data_path

# Collect individual DataFrames
model_dfs = []

for file in data_folder.glob("*.csv"):
    if file.name == "Model_Index.csv":
        continue

    match = re.match(r"(\d+)_.*\.csv", file.name)
    if not match:
        continue

    model_id = int(match.group(1))
    meta_row = model_index[model_index["ID"] == model_id]
    if meta_row.empty:
        continue

    model_name = meta_row.iloc[0]["Name"]
    full_label = f"{model_id} - {model_name}"

    df = pd.read_csv(file)
    df["Date"] = pd.to_datetime(df["Category"], dayfirst=True, errors="coerce")
    return_cols = [col for col in df.columns if "ID:" in col and "(ex carry)" not in col]
    if not return_cols:
        continue

    return_col = return_cols[0]
    temp_df = df[["Date", return_col]].rename(columns={return_col: full_label})
    model_dfs.append(temp_df)

# Merge all into master DataFrame
master_df = reduce(lambda left, right: pd.merge(left, right, on="Date", how="outer"), model_dfs)
master_df.sort_values("Date", inplace=True)
master_df.reset_index(drop=True, inplace=True)

# Save or preview
output_file = processed_data_path / "Master_Return_Matrix.csv"
master_df.to_csv(output_file, index=False)
print("Master matrix created with shape:", master_df.shape)
