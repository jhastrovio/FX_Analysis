import streamlit as st
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
import asyncio
from pathlib import Path
from file_manager import list_files, load_full_file, get_folder_stats
from onedrive_storage import OneDriveStorage
import datetime

# --- Config ---
# Use OneDrive path key instead of local directory
onedrive_path_key = "processed_data"  # Maps to FX_Data/Systemacro_Data/Processed
default_pattern = "*.csv"

st.set_page_config(page_title="FX Model Dashboard", layout="wide")
st.title("📈 FX Model Summary Dashboard")

# --- Initialize OneDrive Storage ---
@st.cache_resource
def get_storage():
    """Initialize OneDrive storage client with caching."""
    try:
        return OneDriveStorage()
    except Exception as e:
        st.error(f"Failed to initialize OneDrive connection: {e}")
        return None

storage = get_storage()

# --- File Selection ---
st.sidebar.header("📂 File Selection")

# Get files from OneDrive
@st.cache_data(ttl=300)  # Cache for 5 minutes
def get_file_list():
    """Get list of files from OneDrive with caching."""
    if storage is None:
        return []
    
    try:
        # Use asyncio to run the async function
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        files = loop.run_until_complete(list_files(storage, onedrive_path_key, pattern=default_pattern))
        loop.close()
        return files
    except Exception as e:
        st.error(f"Failed to load files from OneDrive: {e}")
        return []

files = get_file_list()
file_options = [f.get('name', '') for f in files if not f.get('folder', False)]

# Multi-file selection
analysis_mode = st.sidebar.radio(
    "Analysis Mode",
    ["Single File", "Multi-File Comparison"],
    help="Choose between analyzing one file or comparing multiple files"
)

if analysis_mode == "Single File":
    selected_file = st.sidebar.selectbox("Select a file to preview", file_options)
    selected_files = [selected_file] if selected_file else []
else:
    selected_files = st.sidebar.multiselect(
        "Select files for comparison", 
        file_options,
        help="Select multiple summary statistics files to compare"
    )

# --- Load & Display Selected File(s) ---
if selected_files and storage:
    try:
        # Load all selected files
        all_dataframes = []
        file_names = []
        
        for filename in selected_files:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            df = loop.run_until_complete(load_full_file(storage, onedrive_path_key, filename))
            loop.close()
            
            if not df.empty:
                # Add period column if it exists in filename
                if 'period' not in df.columns:
                    period_label = filename.replace(".csv", "")
                    df['period'] = period_label
                
                all_dataframes.append(df)
                file_names.append(filename)
        
        if all_dataframes:
            # Combine all dataframes
            combined_df = pd.concat(all_dataframes, ignore_index=True)
            st.success(f"Loaded {len(selected_files)} files: {len(combined_df)} total rows, {len(combined_df.columns)} columns")

            # --- Filters ---
            st.sidebar.header("🔍 Filters")
            
            # Check if model_name column exists
            if 'model_name' in combined_df.columns:
                model_names = combined_df['model_name'].unique()
                
                # Add "Select All" option
                col1, col2 = st.sidebar.columns(2)
                with col1:
                    if st.button("Select All Models"):
                        st.session_state.selected_models = list(model_names)
                with col2:
                    if st.button("Clear Selection"):
                        st.session_state.selected_models = []
                
                # Top N filter
                st.sidebar.subheader("🏆 Top Performers Filter")
                
                # Find available metric columns for top N filtering
                metric_cols = ['annualized_return', 'volatility', 'sharpe_ratio', 'max_drawdown']
                available_metrics = [col for col in metric_cols if col in combined_df.columns]
                
                if available_metrics:
                    top_n_metric = st.sidebar.selectbox(
                        "Rank by metric", 
                        available_metrics,
                        help="Select metric to rank models by"
                    )
                    
                    top_n_count = st.sidebar.number_input(
                        "Show top N models", 
                        min_value=1, 
                        max_value=len(model_names), 
                        value=25,
                        help="Show only the top N performing models"
                    )
                    
                    # Apply top N filter
                    if st.sidebar.button("Apply Top N Filter"):
                        # Get the best models for the selected metric
                        # For metrics where higher is better (returns, sharpe), sort descending
                        # For metrics where lower is better (volatility, drawdown), sort ascending
                        ascending_order = top_n_metric in ['volatility', 'max_drawdown']
                        
                        top_models = combined_df.groupby('model_name')[top_n_metric].mean().sort_values(
                            ascending=ascending_order
                        ).head(top_n_count).index.tolist()
                        
                        st.session_state.selected_models = top_models
                        st.sidebar.success(f"✅ Showing top {len(top_models)} models by {top_n_metric}")
                
                # Initialize session state if not exists
                if 'selected_models' not in st.session_state:
                    st.session_state.selected_models = list(model_names)  # Default to all models
                
                selected_models = st.sidebar.multiselect(
                    "Model(s)", 
                    model_names, 
                    default=st.session_state.selected_models,
                    key="model_selector"
                )
                
                # Update session state
                st.session_state.selected_models = selected_models
                
                df_filtered = combined_df[combined_df['model_name'].isin(selected_models)]
                
                # Show selection info
                st.sidebar.info(f"Showing {len(selected_models)} of {len(model_names)} models")
            else:
                # Fallback if no model_name column
                st.warning("No 'model_name' column found. Showing all data.")
                df_filtered = combined_df
                selected_models = []

            # --- Main Data Table ---
            st.subheader("Model Performance Table")
            st.dataframe(df_filtered, use_container_width=True)

            # --- Charts ---
            if not df_filtered.empty:
                st.subheader("📊 Metric Visualizations")
                
                # Find available metric columns
                metric_cols = ['annualized_return', 'volatility', 'sharpe_ratio', 'max_drawdown']
                available_metrics = [col for col in metric_cols if col in df_filtered.columns]
                
                if available_metrics:
                    metric_to_plot = st.selectbox("Choose a metric to plot", available_metrics)
                    
                    if 'model_name' in df_filtered.columns:
                        chart_data = df_filtered.sort_values(metric_to_plot, ascending=False).set_index("model_name")
                        st.bar_chart(chart_data[metric_to_plot])
                    else:
                        # Fallback chart without model_name
                        st.bar_chart(df_filtered[metric_to_plot])

                    # --- Multi-Period Comparison Heatmap ---
                    if 'period' in df_filtered.columns and 'model_name' in df_filtered.columns:
                        st.subheader("🧊 Multi-Period Comparison Heatmap")
                        
                        # Create pivot table for heatmap
                        try:
                            # Abbreviate period names by removing common prefix
                            df_for_heatmap = df_filtered.copy()
                            df_for_heatmap['period_abbreviated'] = df_for_heatmap['period'].str.replace('Summary_Statistics_', '', regex=False)
                            
                            pivot_df = df_for_heatmap.pivot(index='model_name', columns='period_abbreviated', values=metric_to_plot)
                            
                            if not pivot_df.empty:
                                # Calculate figure size based on data
                                fig_width = max(12, len(pivot_df.columns) * 2)
                                fig_height = max(8, len(pivot_df) * 0.4)
                                
                                fig, ax = plt.subplots(figsize=(fig_width, fig_height))
                                
                                # Create heatmap with better formatting
                                sns.heatmap(
                                    pivot_df, 
                                    annot=True, 
                                    fmt=".3f", 
                                    cmap="RdYlGn", 
                                    center=0, 
                                    ax=ax,
                                    cbar_kws={'label': metric_to_plot.replace('_', ' ').title()}
                                )
                                
                                plt.title(f"{metric_to_plot.replace('_', ' ').title()} Across Periods", pad=20)
                                plt.xlabel("Period")
                                plt.ylabel("Model Name")
                                
                                # Move x-axis labels to top
                                ax.xaxis.set_label_position('top')
                                ax.xaxis.tick_top()
                                
                                # Rotate x-axis labels for better readability
                                plt.xticks(rotation=45, ha='left')
                                plt.yticks(rotation=0)
                                
                                # Adjust layout to ensure proper spacing
                                plt.tight_layout()
                                
                                st.pyplot(fig)
                                
                                # Add download button for the heatmap data
                                csv = pivot_df.to_csv(index=True)
                                st.download_button(
                                    label="Download Heatmap Data (CSV)",
                                    data=csv,
                                    file_name=f"heatmap_{metric_to_plot}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                                    mime="text/csv"
                                )
                            else:
                                st.info("Not enough data for heatmap visualization.")
                        except Exception as e:
                            st.warning(f"Could not create heatmap: {e}")
                            st.error(f"Error details: {str(e)}")
                else:
                    st.info("No standard metric columns found. Available columns: " + ", ".join(df_filtered.columns))
        else:
            st.error("No data loaded from files.")

    except Exception as e:
        st.error(f"Failed to load or parse the files: {e}")
        st.error(f"Error details: {str(e)}")

# --- OneDrive Status & Stats ---
if storage:
    st.sidebar.header("☁️ OneDrive Status")
    
    # Get folder statistics
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        stats = loop.run_until_complete(get_folder_stats(storage, onedrive_path_key))
        loop.close()
        
        st.sidebar.metric("Total Files", stats['files'])
        st.sidebar.metric("Total Size", f"{stats['total_size_mb']} MB")
        
        if stats['file_types']:
            st.sidebar.write("**File Types:**")
            for ext, count in sorted(stats['file_types'].items()):
                st.sidebar.write(f"• .{ext}: {count}")
                
    except Exception as e:
        st.sidebar.error(f"Could not load stats: {e}")

else:
    st.error("❌ OneDrive connection not available. Please check your configuration.")