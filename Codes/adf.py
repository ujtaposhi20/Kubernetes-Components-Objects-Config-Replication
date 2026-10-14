import argparse
import os
import pandas as pd

# Safe import of statsmodels
try:
    from statsmodels.tsa.stattools import adfuller
except ImportError:
    adfuller = None

def check_assumptions_and_run_adf(df, col):
    """
    Checks the assumptions for ADF test on a column and runs it.
    """
    print("=" * 70)
    print(f"Conducting Augmented Dickey-Fuller (ADF) Test on Column: '{col}'")
    print("=" * 70)

    # 1. Check if column exists
    if col not in df.columns:
        print(f"[ERROR] Column '{col}' not found in the DataFrame. Available columns: {list(df.columns)}")
        print("=" * 70 + "\n")
        return

    # Extract series and drop NaNs
    series = df[col].dropna()
    missing_count = df[col].isnull().sum()
    
    # Report basic details
    print(f"Total rows in dataset: {len(df)}")
    print(f"Valid (non-null) observations: {len(series)}")
    if missing_count > 0:
        print(f"[NOTE] Found {missing_count} missing values (NaNs). These were dropped for the test.")

    # 2. Check ADF assumptions
    print("\nChecking ADF Test Assumptions:")
    
    # Assumption A: Numeric data
    is_numeric = pd.api.types.is_numeric_dtype(series)
    print(f"  - Numeric Data Type: {'PASSED' if is_numeric else 'FAILED'}")
    if not is_numeric:
        print(f"    [ERROR] Column '{col}' is not numeric. ADF test requires numeric time-series data.")
        print("=" * 70 + "\n")
        return

    # Assumption B: Sufficient sample size
    has_min_obs = len(series) >= 10
    print(f"  - Sufficient Sample Size (N >= 10): {'PASSED' if has_min_obs else 'FAILED'} (N={len(series)})")
    if not has_min_obs:
        print(f"    [ERROR] Insufficient data. At least 10 observations are recommended.")
        print("=" * 70 + "\n")
        return

    # Assumption C: Non-constant variance (variance > 0)
    is_not_constant = series.nunique() > 1
    print(f"  - Variance > 0 (Non-constant values): {'PASSED' if is_not_constant else 'FAILED'}")
    if not is_not_constant:
        print(f"    [ERROR] Column '{col}' contains constant values. ADF test cannot be computed.")
        print("=" * 70 + "\n")
        return

    # Assumption D: Temporal ordering
    print("  - Temporal Ordering: PASSED (Assumed that rows are ordered chronologically by time step)")

    if adfuller is None:
        print("\n[ERROR] statsmodels package is not installed.")
        print("Please install it using: pip install statsmodels")
        print("=" * 70 + "\n")
        return

    print("\nRunning ADF Test...")
    print("Hypotheses:")
    print("  - H0 (Null Hypothesis): The series has a unit root (is non-stationary).")
    print("  - H1 (Alternative Hypothesis): The series is stationary (does not have a unit root).\n")

    try:
        # Perform Augmented Dickey-Fuller test with automatic lag selection based on AIC
        result = adfuller(series, autolag='AIC')
        
        adf_statistic = result[0]
        p_value = result[1]
        lags_used = result[2]
        n_obs = result[3]
        critical_values = result[4]

        print(f"ADF Test Statistic:      {adf_statistic:.6f}")
        print(f"p-value:                 {p_value:.6f}")
        print(f"Lags Used:               {lags_used}")
        print(f"Observations Count:      {n_obs}")
        
        print("\nCritical Values:")
        for key, value in critical_values.items():
            print(f"  {key}: {value:.6f}")

        # Interpretation
        alpha = 0.05
        print(f"\nInterpretation at alpha = {alpha}:")
        if p_value < alpha:
            print(f"  - Since p-value ({p_value:.6f}) < alpha ({alpha}), we REJECT the null hypothesis (H0).")
            print(f"  - The series '{col}' is STATIONARY.")
        else:
            print(f"  - Since p-value ({p_value:.6f}) >= alpha ({alpha}), we FAIL to reject the null hypothesis (H0).")
            print(f"  - The series '{col}' is NON-STATIONARY (it has a unit root / time-dependent structure).")

        # Compare statistic directly with 5% critical value
        if adf_statistic < critical_values['5%']:
            print(f"  - The ADF statistic ({adf_statistic:.6f}) is less than the 5% critical value ({critical_values['5%']:.6f}).")
            print("    This statistical evidence supports stationarity.")
        else:
            print(f"  - The ADF statistic ({adf_statistic:.6f}) is greater than or equal to the 5% critical value ({critical_values['5%']:.6f}).")
            print("    This does not support rejecting non-stationarity at the 5% level.")

    except Exception as e:
        print(f"[ERROR] ADF test failed: {e}")

    print("=" * 70 + "\n")

def print_general_assumptions():
    print("=" * 70)
    print("ADF (Augmented Dickey-Fuller) Test Assumptions Reference")
    print("=" * 70)
    print("1. Independence & Identically Distributed (i.i.d.) Residuals:")
    print("   The test uses lag terms to account for autocorrelation. The autolag='AIC'")
    print("   criterion selects the optimal number of lags to make residuals resemble white noise.")
    print("2. Stationarity of Differenced Series:")
    print("   The underlying model assumes the data generator is an AR(p) process.")
    print("3. Linear Relationship:")
    print("   The relationship modeled in the regression is linear.")
    print("4. Sufficient Sample Size:")
    print("   Requires enough data points to compute lags and critical values correctly.")
    print("5. No Structural Breaks:")
    print("   The test assumes there are no sudden structural breaks in the series.")
    print("=" * 70 + "\n")

def main():
    parser = argparse.ArgumentParser(description="Perform Augmented Dickey-Fuller (ADF) tests on CSV columns.")
    parser.add_argument("csv_path", nargs="?", default="../data/monthly_object_release_cadence.csv", 
                        help="Path to the input CSV file (default: ../data/monthly_object_release_cadence.csv)")
    parser.add_argument("--cols", nargs="+", default=["CountOfObjectPerFile", "ReleaseCount"],
                        help="Columns to perform the ADF test on (default: CountOfObjectPerFile, ReleaseCount)")
    
    args = parser.parse_args()

    if adfuller is None:
        print("[WARNING] The 'statsmodels' library is required to run the ADF test.")
        print("Please ensure it is installed: pip install statsmodels pandas numpy\n")

    # Resolve relative paths relative to current script location
    csv_path = args.csv_path
    if not os.path.isabs(csv_path):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        csv_path = os.path.join(script_dir, csv_path)

    if not os.path.exists(csv_path):
        # Try relative to Cwd as fallback
        csv_path = os.path.abspath(args.csv_path)

    print(f"Attempting to read CSV file: '{csv_path}'...")
    try:
        df = pd.read_csv(csv_path)
    except FileNotFoundError:
        print(f"[ERROR] File not found at '{csv_path}'")
        return
    except Exception as e:
        print(f"[ERROR] Failed to read CSV file: {e}")
        return

    # Print theoretical assumptions first
    print_general_assumptions()

    # Run tests on requested columns
    for col in args.cols:
        check_assumptions_and_run_adf(df, col)

if __name__ == "__main__":
    main()
