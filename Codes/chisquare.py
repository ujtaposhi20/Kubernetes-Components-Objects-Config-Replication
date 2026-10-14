import argparse
import pandas as pd
import numpy as np
from scipy import stats

def check_assumptions_and_run_chi2(df, col1, col2):
    print("=" * 60)
    print(f"Conducting Chi-Square Test of Independence on: '{col1}' and '{col2}'")
    print("=" * 60)
    missing_col1 = df[col1].isnull().sum()
    missing_col2 = df[col2].isnull().sum()
    if missing_col1 > 0 or missing_col2 > 0:
        print(f"Warning: Found missing values (NaNs).")
        print(f"  - '{col1}': {missing_col1} missing values")
        print(f"  - '{col2}': {missing_col2} missing values")
        print("These rows will be dropped for the analysis.\n")
        df_clean = df.dropna(subset=[col1, col2])
    else:
        df_clean = df

    unique_col1 = df_clean[col1].nunique()
    unique_col2 = df_clean[col2].nunique()
    print("Assumption Check 1: Categorical Data")
    print(f"  - '{col1}' has {unique_col1} unique categories: {list(df_clean[col1].unique())}")
    print(f"  - '{col2}' has {unique_col2} unique categories: {list(df_clean[col2].unique())}")
    if unique_col1 < 2 or unique_col2 < 2:
        print("\n[ERROR] Both columns must have at least 2 categories to run a Chi-Square test.")
        return
    print("  -> PASS: Both variables are categorical with at least 2 groups.\n")

    contingency_table = pd.crosstab(df_clean[col1], df_clean[col2])
    print("Observed Frequencies (Contingency Table):")
    print(contingency_table)
    print()

    total_obs = contingency_table.values.sum()
    print("Assumption Check 2: Independence of Observations")
    print(f"  - Total observations: {total_obs}")
    print("  - Note: Each subject/observation must contribute to exactly one cell in the table.")
    print("  - If your data has repeated measures or paired observations, a Chi-Square test is NOT appropriate.")
    print("    (Consider using McNemar's test instead for paired binary data.)\n")

    chi2, p_val, dof, expected = stats.chi2_contingency(contingency_table)
    
    expected_df = pd.DataFrame(expected, index=contingency_table.index, columns=contingency_table.columns)
    print("Expected Frequencies (under Null Hypothesis):")
    print(expected_df.round(2))
    print()
    print("Assumption Check 3: Expected Cell Counts")
    total_cells = expected.size
    cells_below_5 = np.sum(expected < 5)
    pct_below_5 = (cells_below_5 / total_cells) * 100
    min_expected = expected.min()

    print(f"  - Minimum expected frequency: {min_expected:.2f}")
    print(f"  - Percentage of cells with expected frequency < 5: {pct_below_5:.1f}% ({cells_below_5} out of {total_cells} cells)")

    assumption_passed = True
    if min_expected < 1:
        print("  -> FAIL: At least one cell has an expected frequency less than 1.")
        assumption_passed = False
    elif contingency_table.shape == (2, 2) and min_expected < 5:
        print("  -> FAIL: For a 2x2 table, all expected counts should be >= 5.")
        assumption_passed = False
    elif pct_below_5 > 20:
        print("  -> FAIL: More than 20% of cells have expected counts less than 5.")
        assumption_passed = False

    if not assumption_passed:
        print("\n[WARNING] Chi-Square test assumptions are violated because of low expected frequencies.")
        if contingency_table.shape == (2, 2):
            print("  -> Recommendation: Use Fisher's Exact Test instead.")
        else:
            print("  -> Recommendation: Consider combining categories or collecting more data.")
        print()
    else:
        print("  -> PASS: Expected cell count assumptions are satisfied.\n")

    is_2x2 = contingency_table.shape == (2, 2)
    print("=" * 60)
    print("Chi-Square Test Results:")
    print("=" * 60)
    print(f"Chi-Square Statistic: {chi2:.4f}")
    print(f"p-value:              {p_val:.6f}")
    print(f"Degrees of Freedom:   {dof}")
    if is_2x2:
        print("Note: Yates' correction for continuity was applied because this is a 2x2 table.")
    print()

    alpha = 0.05
    if p_val < alpha:
        print(f"Since p-value ({p_val:.6f}) < alpha ({alpha}), we REJECT the null hypothesis.")
        print(f"There is a statistically significant association between '{col1}' and '{col2}'.")
    else:
        print(f"Since p-value ({p_val:.6f}) >= alpha ({alpha}), we FAIL to reject the null hypothesis.")
        print(f"There is no statistically significant association between '{col1}' and '{col2}'.")
    print("=" * 60)

def main():
    parser = argparse.ArgumentParser(description="Run Chi-Square Test of Independence on a CSV file.")
    parser.add_argument("csv_path", help="Path to the input CSV file")
    parser.add_argument("col1", help="First categorical column name")
    parser.add_argument("col2", help="Second categorical column name")
    
    args = parser.parse_args()
    
    try:
        df = pd.read_csv(args.csv_path)
    except FileNotFoundError:
        print(f"Error: File not found at '{args.csv_path}'")
        return
    except Exception as e:
        print(f"Error reading CSV file: {e}")
        return
        
    if args.col1 not in df.columns:
        print(f"Error: Column '{args.col1}' not found in CSV. Available columns: {list(df.columns)}")
        return
    if args.col2 not in df.columns:
        print(f"Error: Column '{args.col2}' not found in CSV. Available columns: {list(df.columns)}")
        return

    check_assumptions_and_run_chi2(df, args.col1, args.col2)

if __name__ == "__main__":
    main()
