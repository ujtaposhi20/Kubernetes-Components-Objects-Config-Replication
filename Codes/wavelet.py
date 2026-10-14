import argparse
import os
import pandas as pd
import numpy as np

# Safe imports
try:
    import matplotlib.pyplot as plt
except ImportError:
    plt = None

try:
    import pycwt as wavelet
except ImportError:
    wavelet = None

def check_wavelet_assumptions(df, col1, col2):
    """
    Checks the mathematical and data assumptions required for Wavelet Coherence analysis.
    """
    print("=" * 75)
    print("Checking Wavelet Coherence Assumptions:")
    print("=" * 75)

    # 1. Existence of columns
    for col in [col1, col2]:
        if col not in df.columns:
            print(f"  [ERROR] Column '{col}' not found in the CSV file.")
            return False

    # Drop NaNs to ensure alignment of valid data
    initial_len = len(df)
    clean_df = df.dropna(subset=[col1, col2])
    dropped = initial_len - len(clean_df)
    
    # 2. No missing values
    print(f"  - No Missing Values Check: {'WARNING' if dropped > 0 else 'PASSED'}")
    if dropped > 0:
        print(f"    [NOTE] Dropped {dropped} rows with missing values to align time series.")

    # 3. Numeric Data Type Check
    is_num1 = pd.api.types.is_numeric_dtype(clean_df[col1])
    is_num2 = pd.api.types.is_numeric_dtype(clean_df[col2])
    print(f"  - Numeric Type Check ('{col1}'): {'PASSED' if is_num1 else 'FAILED'}")
    print(f"  - Numeric Type Check ('{col2}'): {'PASSED' if is_num2 else 'FAILED'}")
    if not (is_num1 and is_num2):
        print("    [ERROR] Wavelet Coherence requires both time series to be numeric.")
        return False

    s1 = clean_df[col1].values
    s2 = clean_df[col2].values

    # 4. Same Length Check
    print(f"  - Equal Length Check (N={len(s1)}): PASSED")

    # 5. Sufficient Observations (typically wavelet needs longer series, N >= 20 recommended)
    has_min_obs = len(s1) >= 20
    print(f"  - Sufficient Length (N >= 20): {'PASSED' if has_min_obs else 'WARNING'} (N={len(s1)})")
    if not has_min_obs:
        print("    [WARNING] Time series is very short. Wavelet results might have large edge effects.")

    # 6. Non-zero Variance Check
    var1 = np.var(s1)
    var2 = np.var(s2)
    has_var1 = var1 > 1e-9
    has_var2 = var2 > 1e-9
    print(f"  - Non-Zero Variance ('{col1}'): {'PASSED' if has_var1 else 'FAILED'} (var={var1:.4e})")
    print(f"  - Non-Zero Variance ('{col2}'): {'PASSED' if has_var2 else 'FAILED'} (var={var2:.4e})")
    if not (has_var1 and has_var2):
        print("    [ERROR] Both series must have non-constant values (variance > 0).")
        return False

    print("  - Non-Stationarity Assumption: PASSED (Wavelet coherence is specifically designed for non-stationary signals)")
    print("=" * 75 + "\n")
    return True

def print_general_assumptions():
    print("=" * 75)
    print("Wavelet Coherence Test Assumptions & Requirements Reference")
    print("=" * 75)
    print("1. Regular Sampling Interval (dt):")
    print("   Data must be sampled at a constant rate. Gaps or irregular steps introduce noise.")
    print("2. Temporal Alignment:")
    print("   Observations at index 'i' must correspond to the exact same time step in both series.")
    print("3. No Missing Values:")
    print("   Wavelet transformations cannot compute over NaNs; they must be dropped or interpolated.")
    print("4. Signal Length & Edge Effects:")
    print("   Due to boundary stretching, values outside the Cone of Influence (COI) are affected by")
    print("   zero-padding edge effects and are statistically unreliable.")
    print("5. Stationarity NOT Required:")
    print("   Unlike Fourier coherence, wavelet coherence allows analyzing localized time-varying correlation.")
    print("=" * 75 + "\n")

def plot_wavelet_coherence_contour(x_vals, WCT, period, coi, sig, has_sig, output_path, col1, col2, object_name=None, mean_coherence=0.0):
    """
    Generates a 2D time-frequency contour plot of the Wavelet Coherence.
    """
    if plt is None:
        print("[ERROR] matplotlib is not installed. Cannot generate the contour plot.")
        return

    try:
        fig, ax = plt.subplots(figsize=(12, 7))
        
        # Color contour of coherence R^2
        levels = np.linspace(0, 1, 11)
        time_indices = np.arange(len(x_vals))
        im = ax.contourf(time_indices, np.log2(period), WCT, levels=levels, cmap='RdBu_r', extend='both')
        
        # Draw significance contour if calculated successfully
        if has_sig and sig is not None:
            try:
                ax.contour(time_indices, np.log2(period), sig, [-99, 1], colors='k', linewidths=2)
            except Exception as sig_plot_err:
                print(f"  [NOTE] Skipping significance contour plot: {sig_plot_err}")
        
        # Draw Cone of Influence (COI) line and mask
        ax.plot(time_indices, np.log2(coi), 'k--', linewidth=1.5)
        ax.fill_between(time_indices, np.log2(coi), np.log2(period[-1]), color='gray', alpha=0.3)
        
        # Format axes
        yticklabels = [5, 25, 50, 75, 100]        
        yticklabels = [t for t in yticklabels if period[-1] <= t <= period[0]]
        ax.set_yticks(np.log2(yticklabels))
        ax.set_yticklabels(yticklabels)
        ax.invert_yaxis()
        
        ax.set_ylabel("Month_Intervals", fontsize=12)
        ax.set_xlabel("Month", fontsize=12)
        
        # Set clean X-axis ticks
        step = max(1, len(x_vals) // 10)
        ax.set_xticks(np.arange(0, len(x_vals), step))
        ax.set_xticklabels(x_vals[::step], rotation=45)
        
        title = f"Wavelet Coherence: {col1} vs {col2}"
        if object_name:
            title += f" (Object: {object_name})"
        title += f"\nMean Coherence $R^2$ = {mean_coherence:.4f}"
        ax.set_title(title, fontsize=14, fontweight='bold', pad=15)
        
        # Colorbar
        cbar = fig.colorbar(im, ax=ax, orientation='vertical', pad=0.03)
        cbar.set_label("Wavelet Coherence $R^2$", fontsize=11)
        
        # Save output
        plt.tight_layout()
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        print(f"[SUCCESS] Wavelet coherence contour plot saved to '{output_path}'")
        plt.close(fig)
        
    except Exception as e:
        print(f"[ERROR] Contour plotting failed: {e}")

def plot_wtc_line_only(x_vals, WCT, output_path, col1, col2, object_name=None):
    """
    Plots the scale-averaged Wavelet Coherence (WTC) line against months.
    """
    if plt is None:
        print("[ERROR] matplotlib is not installed. Cannot generate the line plot.")
        return

    # Average along the scale axis to get a 1D coherence time-series
    wtc_line = np.mean(WCT, axis=0)

    try:
        fig, ax = plt.subplots(figsize=(12, 6))
        time_indices = np.arange(len(x_vals))
        ax.plot(time_indices, wtc_line, color='#1f77b4', linewidth=2.5, marker='o', markersize=4, label='Scale-averaged Coherence')

        '''
        Data to plugin for R
        '''
        print('*'*100)
        # print(wtc_line) 
        # print(x_vals)
        df1 = pd.DataFrame(x_vals, columns=['Month'])
        df2 = pd.DataFrame(wtc_line, columns=['CountPerFile'])        
        plotDF = pd.concat([df1, df2], axis=1, ignore_index=True)
        plotDF.to_csv("../data/monthly_object_release_cadence_line.csv", header=False, index=False)
        print('*'*100)    

        # Formatting
        # title = f"Scale-averaged Wavelet Coherence: {col1} vs {col2}"
        # if object_name:
        #      title += f" (Object: {object_name})"
        # ax.set_title(title, fontsize=13, fontweight='bold', pad=15)
        ax.set_xlabel("Month", fontsize=11, labelpad=10)
        ax.set_ylabel("Coherence-$R^2$", fontsize=11, labelpad=10)
        ax.grid(True, linestyle='--', alpha=0.6)
        ax.set_ylim(0, 1.05)

        # Set X-axis tick positions and labels
        step = max(1, len(x_vals) // 10)
        ax.set_xticks(np.arange(0, len(x_vals), step))
        ax.set_xticklabels(x_vals[::step], rotation=45)
        
        # ax.legend(loc='best')
        plt.tight_layout()

        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        print(f"[SUCCESS] Scale-averaged WTC line plot saved to '{output_path}'")
        plt.close(fig)
    except Exception as e:
        print(f"[ERROR] Line plotting failed: {e}")

def main():
    parser = argparse.ArgumentParser(description="Perform Wavelet Coherence analysis on CSV columns.")
    parser.add_argument("csv_path", nargs="?", default="../data/monthly_object_release_cadence.csv", 
                        help="Path to the input CSV file (default: ../data/monthly_object_release_cadence.csv)")
    parser.add_argument("--cols", nargs="+", default=["CountOfObjectPerFile", "ReleaseCount"],
                        help="The two columns to perform the coherence test on (default: CountOfObjectPerFile, ReleaseCount)")
    parser.add_argument("--x", default="Month", help="Column name representing the time step (default: Month)")
    parser.add_argument("--object", default="all", help="Object type to filter (e.g. 'Deployment'). Default is 'all' (aggregates by Month).")
    parser.add_argument("--output", default="wavelet_coherence.png", help="Path to save the coherence plot (default: wavelet_coherence.png)")
    parser.add_argument("--plot-type", default="line", choices=["line", "contour", "both"],
                        help="Plot type to generate: 'line', 'contour', or 'both' (default: line)")
    
    args = parser.parse_args()

    # Verify dependencies
    if wavelet is None:
        print("[ERROR] The 'pycwt' library is required to perform the wavelet coherence test.")
        print("Please install it using: pip install pycwt")
        return

    if plt is None:
        print("[ERROR] The 'matplotlib' library is required to generate the coherence plot.")
        print("Please install it using: pip install matplotlib")
        return

    # Resolve CSV path relative to current script
    csv_path = args.csv_path
    if not os.path.isabs(csv_path):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        csv_path = os.path.join(script_dir, csv_path)

    if not os.path.exists(csv_path):
        csv_path = os.path.abspath(args.csv_path)

    print(f"Reading CSV file: '{csv_path}'...")
    try:
        df = pd.read_csv(csv_path)
    except FileNotFoundError:
        print(f"[ERROR] File not found at '{csv_path}'")
        return
    except Exception as e:
        print(f"[ERROR] Failed to read CSV file: {e}")
        return

    col1, col2 = args.cols[0], args.cols[1]

    # Pre-process multi-object data
    if "Object" in df.columns:
        if args.object.lower() == "all":
            print("Aggregating data across all Objects by Month...")
            df_processed = df.groupby(args.x)[[col1, col2]].sum().reset_index()
        else:
            print(f"Filtering data for Object: '{args.object}'...")
            df_processed = df[df["Object"] == args.object].copy()
            if len(df_processed) == 0:
                print(f"[ERROR] Object '{args.object}' not found in the CSV.")
                print(f"Available objects: {list(df['Object'].unique())}")
                return
    else:
        df_processed = df.copy()

    # Sort chronologically by time-step column
    if args.x in df_processed.columns:
        df_processed = df_processed.sort_values(by=args.x)
    else:
        print(f"[WARNING] Time column '{args.x}' not found. Sorting skipped.")

    # Print theoretical assumptions reference
    print_general_assumptions()

    # Verify assumptions on processed data
    if not check_wavelet_assumptions(df_processed, col1, col2):
        print("[ERROR] Assumption checks failed. Aborting wavelet coherence analysis.")
        return

    # Extract cleaned arrays
    df_clean = df_processed.dropna(subset=[col1, col2])
    x_vals = df_clean[args.x].values if args.x in df_clean.columns else np.arange(len(df_clean))
    y1 = df_clean[col1].values
    y2 = df_clean[col2].values

    # Normalize the signals (zero mean, unit variance)
    y1_norm = (y1 - np.mean(y1)) / np.std(y1)
    y2_norm = (y2 - np.mean(y2)) / np.std(y2)

    # Perform Wavelet Coherence
    print("Performing Wavelet Coherence (WCT) analysis...")
    
    # 1. Apply linear detrending to handle the 'trend too large' issue
    try:
        from scipy import signal
        y1_clean = signal.detrend(y1_norm)
        y2_clean = signal.detrend(y2_norm)
        print("  - Applied linear detrending to handle trends.")
    except Exception as e:
        y1_clean = y1_norm
        y2_clean = y2_norm
        print(f"  [NOTE] Detrending skipped: {e}")

    # 2. Run Wavelet Coherence with significance testing, falling back to sig=False if it fails
    has_sig = False
    try:
        mother = wavelet.Morlet(6)
        dt = 1.0  # Time step = 1 month
        dj = 1/12
        s0 = 2 * dt
        J = -1
        
        WCT, aWCT, coi, freqs, sig = wavelet.wct(
            y1_clean, y2_clean, dt,
            dj=dj, s0=s0, J=J,
            significance_level=0.95,
            wavelet=mother,
            sig=True
        )
        has_sig = True
        period = 1 / freqs

    except Exception as e:
        print(f"  [WARNING] Wavelet significance calculation failed (e.g. series too short or trend too large): {e}")
        print("  Retrying wavelet coherence calculation without significance testing...")
        try:
            WCT, aWCT, coi, freqs, sig = wavelet.wct(
                y1_clean, y2_clean, dt,
                dj=dj, s0=s0, J=J,
                wavelet=mother,
                sig=False
            )
            period = 1 / freqs
        except Exception as retry_err:
            print(f"[ERROR] Wavelet coherence computation failed completely: {retry_err}")
            return

    # Calculate and report mean wavelet coherence
    mean_coherence = np.mean(WCT)
    median_coherence = np.median(WCT)
    print("=" * 75)
    print("Wavelet Coherence Results Summary:")
    print(f"  - Mean Wavelet Coherence Score (R^2): {mean_coherence:.4f}")
    print(f"  - Median Wavelet Coherence Score (R^2): {median_coherence:.4f}")
    print(WCT) 
    print("=" * 75 + "\n")

    # Visualizing Wavelet Coherence
    print("Generating wavelet coherence plot(s)...")
    if args.plot_type in ["contour", "both"]:
        contour_out = args.output if args.plot_type == "contour" else args.output.replace(".png", "_contour.png")
        plot_wavelet_coherence_contour(x_vals, WCT, period, coi, sig, has_sig, contour_out, col1, col2, args.object, mean_coherence)
        
    if args.plot_type in ["line", "both"]:
        line_out = args.output if args.plot_type == "line" else args.output.replace(".png", "_line.png")
        plot_wtc_line_only(x_vals, WCT, line_out, col1, col2, args.object)

if __name__ == "__main__":
    main()
