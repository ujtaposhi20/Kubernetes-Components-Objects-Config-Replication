import argparse
import pandas as pd

# Import matplotlib safely to provide friendly installation advice if missing
try:
    import matplotlib.pyplot as plt
except ImportError:
    plt = None

def plot_time_series(csv_path, x_col, y_col, output_path, window_size=3, group_col=None):
    """
    Loads data from a CSV file and plots a line chart.
    """
    print(f"Loading data from '{csv_path}'...")
    try:
        df = pd.read_csv(csv_path)
    except FileNotFoundError:
        print(f"[ERROR] File not found at '{csv_path}'")
        return
    except Exception as e:
        print(f"[ERROR] Failed to read CSV file: {e}")
        return

    # Check columns
    if x_col not in df.columns:
        print(f"[ERROR] X-axis column '{x_col}' not found in CSV. Available columns: {list(df.columns)}")
        return
    if y_col not in df.columns:
        print(f"[ERROR] Y-axis column '{y_col}' not found in CSV. Available columns: {list(df.columns)}")
        return
    if group_col and group_col not in df.columns:
        print(f"[ERROR] Group column '{group_col}' not found in CSV. Available columns: {list(df.columns)}")
        return

    # Drop missing values in the plotted columns
    initial_len = len(df)
    cols_to_clean = [x_col, y_col]
    if group_col:
        cols_to_clean.append(group_col)
    df_clean = df.dropna(subset=cols_to_clean)
    dropped = initial_len - len(df_clean)
    if dropped > 0:
        print(f"Warning: Dropped {dropped} rows with missing values in {cols_to_clean}.")

    # Sort by the X-axis column (release time) to ensure the line is drawn sequentially
    df_clean = df_clean.sort_values(by=x_col)

    if plt is None:
        print("[ERROR] matplotlib is not installed. Cannot generate the chart.")
        print("Please install it using: pip install matplotlib pandas")
        return

    print(f"Generating linear chart: '{y_col}' vs. '{x_col}'...")
    
    # Set up modern aesthetics
    plt.figure(figsize=(12, 7))
    
    if group_col:
        unique_groups = df_clean[group_col].unique()
        try:
            colormap = plt.colormaps['tab20']
        except Exception:
            try:
                colormap = plt.cm.get_cmap('tab20')
            except Exception:
                colormap = None
        
        for idx, group_name in enumerate(unique_groups):
            group_df = df_clean[df_clean[group_col] == group_name].sort_values(by=x_col)
            if len(group_df) == 0:
                continue
            
            color = colormap(idx % 20) if colormap else None
            
            if window_size > 1:
                # Plot the original data very faintly
                plt.plot(
                    group_df[x_col], 
                    group_df[y_col], 
                    linestyle='--', 
                    color=color, 
                    linewidth=0.8, 
                    alpha=0.25
                )
                
                # Calculate smoothed line (moving average)
                smoothed_y = group_df[y_col].rolling(window=window_size, min_periods=1, center=True).mean()
                
                # Plot the smoothed data
                plt.plot(
                    group_df[x_col], 
                    smoothed_y, 
                    linestyle='-', 
                    color=color, 
                    linewidth=2, 
                    label=f"{group_name} (Smoothed)"
                )
            else:
                # Plot original data without smoothing
                plt.plot(
                    group_df[x_col], 
                    group_df[y_col], 
                    marker='o', 
                    linestyle='-', 
                    color=color, 
                    linewidth=2, 
                    markersize=4,
                    label=group_name
                )
        plt.legend(bbox_to_anchor=(1.02, 1), loc='upper left', borderaxespad=0., fontsize=9)
    else:
        if window_size > 1:
            # Plot the original unsmoothed data faintly
            plt.plot(
                df_clean[x_col], 
                df_clean[y_col], 
                marker='o', 
                linestyle='--', 
                color='#1f77b4', 
                linewidth=1, 
                markersize=4,
                alpha=0.4,
                label=f"{y_col} (Original)"
            )
            
            # Calculate smoothed line (moving average)
            smoothed_y = df_clean[y_col].rolling(window=window_size, min_periods=1, center=True).mean()
            
            # Plot the smoothed data with a thicker solid line
            plt.plot(
                df_clean[x_col], 
                smoothed_y, 
                marker='', 
                linestyle='-', 
                color='#ff7f0e', 
                linewidth=2.5, 
                label=f"{y_col} (Smoothed, window={window_size})"
            )
        else:
            # Plot the original data without smoothing
            plt.plot(
                df_clean[x_col], 
                df_clean[y_col], 
                marker='o', 
                linestyle='-', 
                color='#1f77b4', 
                linewidth=2, 
                markersize=6,
                label=y_col
            )
        plt.legend(loc='best')

    # Style elements
    title = f"{y_col} over {x_col}"
    if group_col:
        title += f" (grouped by {group_col})"
    plt.title(title, fontsize=14, fontweight='bold', pad=15)
    plt.xlabel(x_col, fontsize=12, labelpad=10)
    plt.ylabel(y_col, fontsize=12, labelpad=10)
    plt.grid(True, linestyle='--', alpha=0.6)
    plt.tight_layout()

    # Save chart
    try:
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        print(f"[SUCCESS] Chart saved successfully to '{output_path}'")
    except Exception as e:
        print(f"[ERROR] Failed to save plot to '{output_path}': {e}")

def main():
    parser = argparse.ArgumentParser(description="Generate linear charts for time series data.")
    parser.add_argument("csv_path", nargs="?", default="time-data.csv", help="Path to the input CSV file (default: time-data.csv)")
    parser.add_argument("--x", default="release time", help="Column name for the X-axis (default: 'release time')")
    parser.add_argument("--y", default=None, help="Column name for the Y-axis (will prompt interactively if not provided)")
    parser.add_argument("--output", default="time_series_plot.png", help="Path to save the generated plot image (default: time_series_plot.png)")
    parser.add_argument("--window", type=int, default=3, help="Window size for rolling mean smoothing (default: 3). Set to 1 to disable smoothing.")
    parser.add_argument("--group", default=None, help="Column name to group data by (default: 'Object' if present, otherwise None). Pass 'None' to disable.")
    
    args = parser.parse_args()

    if plt is None:
        print("[WARNING] The 'matplotlib' library is required to generate charts.")
        print("Please ensure it is installed: pip install matplotlib pandas\n")

    # Read the headers of the CSV to detect available columns and determine defaults
    try:
        temp_df = pd.read_csv(args.csv_path, nrows=0)
        available_cols = list(temp_df.columns)
    except Exception:
        available_cols = []

    # Smart defaults based on available columns
    x_col = args.x
    if x_col == "release time" and "release time" not in available_cols:
        if "Month" in available_cols:
            x_col = "Month"
        elif "releasetime" in available_cols:
            x_col = "releasetime"

    group_col = args.group
    if group_col == "None":
        group_col = None
    elif group_col is None:
        if "Object" in available_cols:
            group_col = "Object"

    y_col = args.y
    if y_col is None:
        # Smart default search or fallback to input
        if not available_cols:
            y_col = "object count"
        else:
            defaults = ["object count", "CountOfObjectPerFile", "ReleaseCount"]
            matched_default = None
            for d in defaults:
                if d in available_cols:
                    matched_default = d
                    break
            
            if matched_default:
                y_col = matched_default
                print(f"Using default Y-axis column: '{y_col}'")
            else:
                print(f"Available columns in '{args.csv_path}': {available_cols}")
                y_col = input("Enter the Y-axis column name: ").strip()
                if not y_col:
                    y_col = available_cols[0]
                    print(f"No column entered. Using default: '{y_col}'")

    plot_time_series(args.csv_path, x_col, y_col, args.output, window_size=args.window, group_col=group_col)

if __name__ == "__main__":
    main()
