import streamlit as st
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
from pathlib import Path
from file_manager import list_files, load_full_file, get_folder_stats
from onedrive_storage import OneDriveStorage
import datetime

# --- Config ---
# Use OneDrive path key instead of local directory
onedrive_path_key = "processed_data"  # Maps to clean/systemacro_analysis/Processed
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
        # Use direct function call (no longer async)
        files = list_files(storage, onedrive_path_key, pattern=default_pattern)
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
            df = load_full_file(storage, onedrive_path_key, filename)
            
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
                metric_cols = ['annualized_return', 'return', 'volatility', 'sharpe_ratio', 'max_drawdown']
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

            # --- Dynamic Column Operations ---
            st.subheader("📊 Column Operations")
            col1, col2, col3 = st.columns(3)

            with col1:
                if st.button("Add Rank Columns"):
                    # Add ranking columns for each metric (higher is better)
                    for col in ['annualized_return', 'return', 'sharpe_ratio']:
                        if col in df_filtered.columns:
                            df_filtered[f"{col}_rank"] = df_filtered[col].rank(ascending=False, method='dense').astype(int)
                    
                    # Add ranking columns for metrics where lower is better
                    for col in ['volatility', 'max_drawdown']:
                        if col in df_filtered.columns:
                            df_filtered[f"{col}_rank"] = df_filtered[col].rank(ascending=True, method='dense').astype(int)
                    
                    st.success("✅ Rank columns added!")
                    st.rerun()

            with col2:
                if st.button("Add Percentiles"):
                    # Add percentile columns
                    for col in ['annualized_return', 'return', 'volatility', 'sharpe_ratio', 'max_drawdown']:
                        if col in df_filtered.columns:
                            df_filtered[f"{col}_pct"] = (df_filtered[col].rank(pct=True) * 100).round(1)
                    
                    st.success("✅ Percentile columns added!")
                    st.rerun()

            with col3:
                if st.button("Add Z-Scores"):
                    # Add standardized scores
                    for col in ['annualized_return', 'return', 'volatility', 'sharpe_ratio', 'max_drawdown']:
                        if col in df_filtered.columns:
                            mean_val = df_filtered[col].mean()
                            std_val = df_filtered[col].std()
                            if std_val != 0:
                                df_filtered[f"{col}_zscore"] = ((df_filtered[col] - mean_val) / std_val).round(3)
                    
                    st.success("✅ Z-score columns added!")
                    st.rerun()

            # --- Advanced Sorting & Grouping ---
            st.subheader("🔄 Advanced Sorting & Grouping")
            
            # Sorting section
            st.write("**Multi-Column Sorting:**")
            sort_col1, sort_col2, sort_col3 = st.columns([2, 1, 1])
            
            with sort_col1:
                sort_cols = st.multiselect(
                    "Sort by columns", 
                    df_filtered.columns.tolist(),
                    help="Select one or more columns to sort by"
                )
                
            with sort_col2:
                sort_orders = []
                if sort_cols:
                    for i, col in enumerate(sort_cols):
                        order = st.selectbox(
                            f"{col[:15]}..." if len(col) > 15 else col, 
                            ["Descending", "Ascending"], 
                            key=f"order_{i}_{col}"
                        )
                        sort_orders.append(order == "Ascending")

            with sort_col3:
                if st.button("Apply Sort", disabled=not sort_cols):
                    if sort_cols:
                        df_filtered = df_filtered.sort_values(sort_cols, ascending=sort_orders)
                        st.success(f"✅ Sorted by {len(sort_cols)} columns!")
                        st.rerun()

            # Grouping section
            st.write("**Grouping & Summary Statistics:**")
            group_col1, group_col2 = st.columns([1, 3])
            
            with group_col1:
                grouping_cols = ['None']
                if 'category' in df_filtered.columns:
                    grouping_cols.append('category')
                if 'family' in df_filtered.columns:
                    grouping_cols.append('family')
                
                group_by = st.selectbox("Group by", grouping_cols)
                
            with group_col2:
                if group_by != 'None' and group_by in df_filtered.columns:
                    # Show grouped statistics
                    numeric_cols = df_filtered.select_dtypes(include=[float, int]).columns.tolist()
                    
                    if numeric_cols:
                        st.write(f"**Summary by {group_by}:**")
                        
                        # Calculate group statistics
                        grouped = df_filtered.groupby(group_by)[numeric_cols].agg([
                            'count', 'mean', 'std', 'min', 'max'
                        ]).round(3)
                        
                        # Flatten column names for better display
                        grouped.columns = [f"{col[0]}_{col[1]}" for col in grouped.columns]
                        
                        st.dataframe(grouped, use_container_width=True)
                        
                        # Quick export for grouped data
                        csv_grouped = grouped.to_csv()
                        st.download_button(
                            f"Download {group_by} Summary", 
                            csv_grouped, 
                            file_name=f"grouped_by_{group_by}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                            mime="text/csv"
                        )

            # --- Charts ---
            if not df_filtered.empty:
                st.subheader("📊 Metric Visualizations")
                
                # Find available metric columns
                metric_cols = ['annualized_return', 'return', 'volatility', 'sharpe_ratio', 'max_drawdown']
                available_metrics = [col for col in metric_cols if col in df_filtered.columns]
                
                if available_metrics:
                    metric_to_plot = st.selectbox("Choose a metric to plot", available_metrics)
                    
                    if 'model_name' in df_filtered.columns:
                        chart_data = df_filtered.sort_values(metric_to_plot, ascending=False).set_index("model_name")
                        st.bar_chart(chart_data[metric_to_plot])
                    else:
                        # Fallback chart without model_name
                        st.bar_chart(df_filtered[metric_to_plot])

                    # --- Enhanced Multi-Period Comparison Heatmap ---
                    if 'period' in df_filtered.columns and 'model_name' in df_filtered.columns:
                        st.subheader("🔥 Enhanced Multi-Period Comparison Heatmap")
                        
                        # Create pivot table for heatmap
                        try:
                            # Prepare data for heatmap
                            df_for_heatmap = df_filtered.copy()
                            
                            # Clean and abbreviate period names
                            df_for_heatmap['period_clean'] = (
                                df_for_heatmap['period']
                                .str.replace('Summary_Statistics_', '', regex=False)
                                .str.replace('.csv', '', regex=False)
                            )
                            
                            # Extract dates for sorting
                            df_for_heatmap['period_start'] = pd.to_datetime(
                                df_for_heatmap['period_clean'].str.extract(r'(\d{4}[-_]\d{2}[-_]\d{2})')[0].str.replace('_', '-'),
                                errors='coerce'
                            )
                            
                            # Create period ordering
                            period_order = (
                                df_for_heatmap[['period_clean', 'period_start']]
                                .drop_duplicates()
                                .sort_values('period_start')
                                .loc[:, 'period_clean']
                                .tolist()
                            )
                            
                            # Create base pivot table
                            pivot_df = df_for_heatmap.pivot(index='model_name', columns='period_clean', values=metric_to_plot)
                            pivot_df = pivot_df[period_order] if period_order else pivot_df
                            
                            if not pivot_df.empty:
                                # === ENHANCED HEATMAP CONTROLS ===
                                st.subheader("🎛️ Enhanced Heatmap Controls")
                                
                                # Row 1: Heatmap Type and Color Scheme
                                control_col1, control_col2, control_col3 = st.columns(3)
                                
                                with control_col1:
                                    heatmap_type = st.selectbox(
                                        "📊 Heatmap Type",
                                        ["Absolute Values", "Relative to Mean", "Percentile Rank", "Z-Score"],
                                        help="Choose how to transform the data for visualization"
                                    )
                                
                                with control_col2:
                                    color_scheme = st.selectbox(
                                        "🎨 Color Scheme",
                                        ["RdYlGn", "viridis", "plasma", "coolwarm", "RdBu", "Spectral", "Blues"],
                                        help="Select color palette for the heatmap"
                                    )
                                
                                with control_col3:
                                    top_n_models = st.slider(
                                        "🏆 Top N Models",
                                        min_value=5,
                                        max_value=len(pivot_df),
                                        value=min(25, len(pivot_df)),
                                        help="Show only top N performing models"
                                    )
                                
                                # Row 2: Period Selection and Data Filtering
                                control_col4, control_col5, control_col6 = st.columns(3)
                                
                                with control_col4:
                                    selected_periods = st.multiselect(
                                        "📅 Select Periods",
                                        pivot_df.columns.tolist(),
                                        default=pivot_df.columns.tolist(),
                                        help="Choose which periods to include"
                                    )
                                
                                with control_col5:
                                    filter_incomplete = st.checkbox(
                                        "🚫 Filter Incomplete Data",
                                        value=False,
                                        help="Remove models with missing data in any period"
                                    )
                                
                                with control_col6:
                                    sort_method = st.selectbox(
                                        "📈 Sort Models By",
                                        ["Average Performance", "Latest Period", "Consistency (Low Volatility)", 
                                         "Best Single Period", "Worst Single Period", "Alphabetical"],
                                        help="Choose how to sort the models in the heatmap"
                                    )
                                
                                # === DATA PROCESSING ===
                                # Apply period selection
                                if selected_periods:
                                    display_df = pivot_df[selected_periods].copy()
                                else:
                                    display_df = pivot_df.copy()
                                
                                # Filter incomplete data
                                if filter_incomplete:
                                    display_df = display_df.dropna()
                                    if display_df.empty:
                                        st.warning("⚠️ No complete data available after filtering. Showing all data.")
                                        display_df = pivot_df[selected_periods] if selected_periods else pivot_df
                                
                                # Apply Top N filter and sorting
                                if len(display_df) > top_n_models:
                                    if sort_method == "Average Performance":
                                        avg_performance = display_df.mean(axis=1)
                                        ascending_order = metric_to_plot in ['volatility', 'max_drawdown']
                                        top_models = avg_performance.sort_values(ascending=ascending_order).head(top_n_models).index
                                    elif sort_method == "Latest Period":
                                        latest_col = display_df.columns[-1]
                                        ascending_order = metric_to_plot in ['volatility', 'max_drawdown']
                                        top_models = display_df[latest_col].sort_values(ascending=ascending_order).head(top_n_models).index
                                    elif sort_method == "Consistency (Low Volatility)":
                                        consistency = display_df.std(axis=1)
                                        top_models = consistency.sort_values(ascending=True).head(top_n_models).index
                                    elif sort_method == "Best Single Period":
                                        best_performance = display_df.max(axis=1) if metric_to_plot not in ['volatility', 'max_drawdown'] else display_df.min(axis=1)
                                        ascending_order = metric_to_plot in ['volatility', 'max_drawdown']
                                        top_models = best_performance.sort_values(ascending=ascending_order).head(top_n_models).index
                                    elif sort_method == "Worst Single Period":
                                        worst_performance = display_df.min(axis=1) if metric_to_plot not in ['volatility', 'max_drawdown'] else display_df.max(axis=1)
                                        ascending_order = metric_to_plot not in ['volatility', 'max_drawdown']
                                        top_models = worst_performance.sort_values(ascending=ascending_order).head(top_n_models).index
                                    else:  # Alphabetical
                                        top_models = display_df.index.sort_values()[:top_n_models]
                                    
                                    display_df = display_df.loc[top_models]
                                
                                # Sort the filtered data
                                if sort_method == "Average Performance":
                                    avg_performance = display_df.mean(axis=1)
                                    ascending_order = metric_to_plot in ['volatility', 'max_drawdown']
                                    display_df = display_df.loc[avg_performance.sort_values(ascending=ascending_order).index]
                                elif sort_method == "Latest Period":
                                    latest_col = display_df.columns[-1]
                                    ascending_order = metric_to_plot in ['volatility', 'max_drawdown']
                                    display_df = display_df.sort_values(latest_col, ascending=ascending_order)
                                elif sort_method == "Consistency (Low Volatility)":
                                    consistency = display_df.std(axis=1)
                                    display_df = display_df.loc[consistency.sort_values(ascending=True).index]
                                elif sort_method == "Alphabetical":
                                    display_df = display_df.sort_index()
                                
                                # === HEATMAP DATA TRANSFORMATION ===
                                if heatmap_type == "Absolute Values":
                                    heatmap_data = display_df.copy()
                                    center_value = 0
                                elif heatmap_type == "Relative to Mean":
                                    col_means = display_df.mean()
                                    heatmap_data = display_df - col_means
                                    center_value = 0
                                elif heatmap_type == "Percentile Rank":
                                    heatmap_data = display_df.rank(pct=True) * 100
                                    center_value = 50
                                elif heatmap_type == "Z-Score":
                                    heatmap_data = (display_df - display_df.mean()) / display_df.std()
                                    center_value = 0
                                
                                # === HEATMAP VISUALIZATION ===
                                # Calculate optimal figure size
                                fig_width = max(12, len(heatmap_data.columns) * 1.5)
                                fig_height = max(8, len(heatmap_data) * 0.35)
                                
                                fig, ax = plt.subplots(figsize=(fig_width, fig_height))
                                
                                # Determine annotation format
                                if heatmap_type == "Percentile Rank":
                                    fmt = ".0f"
                                    annot_suffix = "%"
                                elif heatmap_type == "Z-Score":
                                    fmt = ".2f"
                                    annot_suffix = ""
                                else:
                                    fmt = ".3f"
                                    annot_suffix = ""
                                
                                # Create annotations with suffix
                                if annot_suffix:
                                    annotations = heatmap_data.round(0 if heatmap_type == "Percentile Rank" else 2).astype(str) + annot_suffix
                                    annot_data = annotations
                                    show_annot = True
                                else:
                                    annot_data = True
                                    show_annot = True
                                
                                # Create heatmap
                                sns.heatmap(
                                    heatmap_data,
                                    annot=show_annot,
                                    fmt="" if annot_suffix else fmt,
                                    cmap=color_scheme,
                                    center=center_value,
                                    ax=ax,
                                    cbar_kws={'label': f"{metric_to_plot.replace('_', ' ').title()} ({heatmap_type})"},
                                    annot_kws={'size': max(6, min(10, 120 // len(heatmap_data.columns)))},
                                    linewidths=0.5
                                )
                                
                                # Enhance plot formatting
                                title = f"{metric_to_plot.replace('_', ' ').title()} - {heatmap_type}\n({len(heatmap_data)} models across {len(heatmap_data.columns)} periods)"
                                plt.title(title, pad=20, fontsize=14, fontweight='bold')
                                plt.xlabel("Time Period", fontweight='bold')
                                plt.ylabel("Model Name", fontweight='bold')
                                
                                # Optimize label formatting
                                ax.xaxis.set_label_position('top')
                                ax.xaxis.tick_top()
                                plt.xticks(rotation=45, ha='left')
                                plt.yticks(rotation=0)
                                
                                # Adjust layout
                                plt.tight_layout()
                                
                                # Display heatmap
                                st.pyplot(fig)
                                
                                # === ENHANCED ANALYTICS PANEL ===
                                st.subheader("📊 Enhanced Analytics Panel")
                                
                                # Performance metrics
                                metrics_col1, metrics_col2, metrics_col3, metrics_col4 = st.columns(4)
                                
                                with metrics_col1:
                                    best_avg = display_df.mean(axis=1).max()
                                    best_model = display_df.mean(axis=1).idxmax()
                                    st.metric("🏆 Best Average", f"{best_avg:.3f}", help=f"Model: {best_model}")
                                
                                with metrics_col2:
                                    most_consistent = display_df.std(axis=1).min()
                                    consistent_model = display_df.std(axis=1).idxmin()
                                    st.metric("🎯 Most Consistent", f"{most_consistent:.3f}", help=f"Model: {consistent_model}")
                                
                                with metrics_col3:
                                    if metric_to_plot not in ['volatility', 'max_drawdown']:
                                        best_single = display_df.max().max()
                                        best_period = display_df.max().idxmax()
                                    else:
                                        best_single = display_df.min().min()
                                        best_period = display_df.min().idxmin()
                                    st.metric("⭐ Best Single Result", f"{best_single:.3f}", help=f"Period: {best_period}")
                                
                                with metrics_col4:
                                    correlation_avg = abs(display_df.corr().values[display_df.corr().values != 1]).mean()
                                    st.metric("🔄 Avg Correlation", f"{correlation_avg:.3f}", help="Average correlation between periods")
                                
                                # Top performers table
                                st.write("**🏅 Top Performers Summary:**")
                                
                                summary_df = pd.DataFrame({
                                    'Model': display_df.index,
                                    'Average': display_df.mean(axis=1).round(3),
                                    'Std Dev': display_df.std(axis=1).round(3),
                                    'Best Period': display_df.max(axis=1).round(3) if metric_to_plot not in ['volatility', 'max_drawdown'] else display_df.min(axis=1).round(3),
                                    'Worst Period': display_df.min(axis=1).round(3) if metric_to_plot not in ['volatility', 'max_drawdown'] else display_df.max(axis=1).round(3),
                                    'Range': (display_df.max(axis=1) - display_df.min(axis=1)).round(3)
                                }).sort_values('Average', ascending=metric_to_plot in ['volatility', 'max_drawdown'])
                                
                                st.dataframe(summary_df, use_container_width=True)
                                
                                # === ENHANCED EXPORT OPTIONS ===
                                st.subheader("📥 Export Options")
                                
                                export_col1, export_col2, export_col3 = st.columns(3)
                                
                                with export_col1:
                                    # Heatmap data export
                                    heatmap_csv = heatmap_data.to_csv(index=True)
                                    st.download_button(
                                        "📊 Download Heatmap Data",
                                        heatmap_csv,
                                        file_name=f"heatmap_{heatmap_type.lower().replace(' ', '_')}_{metric_to_plot}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                                        mime="text/csv",
                                        help="Download the transformed heatmap data"
                                    )
                                
                                with export_col2:
                                    # Summary statistics export
                                    summary_csv = summary_df.to_csv(index=False)
                                    st.download_button(
                                        "📈 Download Summary Stats",
                                        summary_csv,
                                        file_name=f"summary_stats_{metric_to_plot}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                                        mime="text/csv",
                                        help="Download performance summary statistics"
                                    )
                                
                                with export_col3:
                                    # Correlation matrix export
                                    if len(display_df.columns) > 1:
                                        correlation_csv = display_df.corr().to_csv(index=True)
                                        st.download_button(
                                            "🔄 Download Correlations",
                                            correlation_csv,
                                            file_name=f"correlations_{metric_to_plot}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                                            mime="text/csv",
                                            help="Download period correlation matrix"
                                        )
                                
                                # === QUICK INSIGHTS ===
                                st.subheader("💡 Quick Insights")
                                
                                insights_col1, insights_col2 = st.columns(2)
                                
                                with insights_col1:
                                    st.write("**📈 Performance Trends:**")
                                    
                                    # Trend analysis
                                    if len(display_df.columns) >= 2:
                                        period_means = display_df.mean()
                                        if metric_to_plot not in ['volatility', 'max_drawdown']:
                                            trend = "📈 Improving" if period_means.iloc[-1] > period_means.iloc[0] else "📉 Declining"
                                        else:
                                            trend = "📈 Improving" if period_means.iloc[-1] < period_means.iloc[0] else "📉 Declining"
                                        st.write(f"• Overall Trend: {trend}")
                                        
                                        volatility_trend = period_means.std()
                                        st.write(f"• Period Volatility: {volatility_trend:.3f}")
                                        
                                        best_period_name = period_means.idxmax() if metric_to_plot not in ['volatility', 'max_drawdown'] else period_means.idxmin()
                                        st.write(f"• Best Period: {best_period_name}")
                                
                                with insights_col2:
                                    st.write("**🎯 Model Distribution:**")
                                    
                                    # Distribution insights
                                    model_averages = display_df.mean(axis=1)
                                    top_quartile = model_averages.quantile(0.75 if metric_to_plot not in ['volatility', 'max_drawdown'] else 0.25)
                                    bottom_quartile = model_averages.quantile(0.25 if metric_to_plot not in ['volatility', 'max_drawdown'] else 0.75)
                                    
                                    st.write(f"• Models Shown: {len(display_df)}")
                                    st.write(f"• Top Quartile Threshold: {top_quartile:.3f}")
                                    st.write(f"• Bottom Quartile Threshold: {bottom_quartile:.3f}")
                                    st.write(f"• Performance Spread: {(model_averages.max() - model_averages.min()):.3f}")
                            
                            else:
                                st.info("📊 Not enough data for heatmap visualization. Need at least 2 periods and 2 models.")
                                
                        except Exception as e:
                            st.warning(f"⚠️ Could not create enhanced heatmap: {e}")
                            st.error(f"Error details: {str(e)}")
                            # Fallback to basic heatmap if enhanced version fails
                            st.info("🔄 Falling back to basic heatmap...")
                            try:
                                basic_pivot = df_for_heatmap.pivot(index='model_name', columns='period_clean', values=metric_to_plot)
                                fig, ax = plt.subplots(figsize=(12, 8))
                                sns.heatmap(basic_pivot, annot=True, fmt=".3f", cmap="RdYlGn", ax=ax)
                                plt.title(f"Basic {metric_to_plot.replace('_', ' ').title()} Heatmap")
                                plt.tight_layout()
                                st.pyplot(fig)
                            except Exception as fallback_error:
                                st.error(f"❌ Fallback heatmap also failed: {fallback_error}")
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
        stats = get_folder_stats(storage, onedrive_path_key)
        
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