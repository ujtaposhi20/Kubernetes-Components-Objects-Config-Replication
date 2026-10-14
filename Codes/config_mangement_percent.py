import math
import pandas as pd

SUMMARY_FILE = r"D:\new_k8s_analysis\repo_summary.csv"
CADENCE_FILE = r"D:\new_k8s_analysis\ReleaseDataCategorized_postK8Sdata.csv"
OUT_FILE     = r"D:\new_k8s_analysis\config_method_percent.csv"

TOOLS = [
    ("GitOps",       "Flux",      ["flux"],      27.0),
    ("GitOps",       "ArgoCD",    ["argocd", "argo"], 29.7),
    ("IaC",          "Ansible",   ["ansible"],   29.7),
    ("IaC",          "Terraform", ["terraform"], 56.8),
    ("Pkg. Manager", "Helm",      ["helm"],      65.6),
]
ALIGN_MAX   = 0.20
PARTIAL_MAX = 0.55


def find_col(df, keywords):
    """All columns whose name contains any keyword (case-insensitive)."""
    return [c for c in df.columns if any(k in c.lower() for k in keywords)]
def cohen_h(p1, p2):
    """Cohen's h between two proportions (each in 0..1)."""
    phi = lambda p: 2.0 * math.asin(math.sqrt(max(0.0, min(1.0, p))))
    return abs(phi(p1) - phi(p2))
def interpret(h):
    if h < ALIGN_MAX:
        return "Alignment"
    if h < PARTIAL_MAX:
        return "Partial Alignment"
    return "Divergence"
def main():
    cohort = set(pd.read_csv(CADENCE_FILE)["REPO"].astype(str))

    df = pd.read_csv(SUMMARY_FILE)
    df["repo"] = df["repo"].astype(str)
    cohort_df = df[df["repo"].isin(cohort)]

    n = len(cohort_df)
    print(f"Cohort listed: {len(cohort)} | matched in repo_summary: "
          f"{cohort_df['repo'].nunique()} | rows used: {n}\n")

    rows = []
    for method, tool, keywords, survey_yes in TOOLS:
        matches = find_col(cohort_df, keywords)
        if not matches:
            print(f"  {tool:<10} -> column NOT FOUND (keywords {keywords})")
            rows.append((method, tool, None, None, survey_yes, None, "n/a"))
            continue
        col = matches[0]
        note = "" if len(matches) == 1 else f"  [also matched: {matches[1:]}]"
        print(f"  {tool:<10} -> using column '{col}'{note}")

        present  = (pd.to_numeric(cohort_df[col], errors="coerce").fillna(0) > 0).sum()
        repo_pct = present / n * 100
        h        = cohen_h(survey_yes / 100.0, repo_pct / 100.0)
        rows.append((method, tool, int(present), round(repo_pct, 1),
                     survey_yes, round(h, 2), interpret(h)))

    print()
    out = pd.DataFrame(rows, columns=["Method", "Tool", "ReposUsing", "RepoPct",
                                      "SurveyYesPct", "CohenH", "Interpretation"])
    out.to_csv(OUT_FILE, index=False)
    print(out.to_string(index=False))
    print(f"\nWritten -> {OUT_FILE}")


if __name__ == "__main__":
    main()