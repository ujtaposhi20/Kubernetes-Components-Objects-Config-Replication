import pandas as pd

SUMMARY_FILE  = r"D:\new_k8s_analysis\repo_summary.csv"
CADENCE_FILE  = r"D:\new_k8s_analysis\ReleaseDataCategorized_postK8Sdata.csv"
OUT_FILE      = r"D:\new_k8s_analysis\repo_percent.csv"

OBJECTS = ["Autoscaler", "ConfigMap", "CustomResourceDefinition", "DaemonSet",
           "Deployment", "Ingress", "LimitRange", "Namespace", "NetworkPolicy",
           "PersistentVolume", "PersistentVolumeClaim", "Pod", "ReplicaSet",
           "Secret", "Service", "StatefulSet"]
SCHED = ["Node Affinity", "Pod Anti-Affinity", "Taints and tolerations"]

def col_for(df, name, prefixes):
    for p in prefixes:
        if p + name in df.columns:
            return p + name
    return None

def main():
    cohort = set(pd.read_csv(CADENCE_FILE)["REPO"].astype(str))

    df = pd.read_csv(SUMMARY_FILE)
    df["repo"] = df["repo"].astype(str)
    cohort_df = df[df["repo"].isin(cohort)]

    n = len(cohort_df)
    matched = cohort_df["repo"].nunique()
    print(f"Cohort listed: {len(cohort)} | matched in repo_summary: {matched} | rows used: {n}")
    if matched != len(cohort):
        missing = sorted(cohort - set(cohort_df["repo"]))
        print(f"WARNING: {len(missing)} cohort repos not found in repo_summary "
              f"(owner/name mismatch). e.g. {missing[:5]}")
    print()

    rows = []
    for o in OBJECTS:
        col = col_for(cohort_df, o, ["objhas::", "objcnt::"])
        if col is None:
            print(f"  (skipped {o}: no objhas::/objcnt:: column)")
            continue
        present = (pd.to_numeric(cohort_df[col], errors="coerce").fillna(0) > 0).sum()
        rows.append((o, int(present), round(present / n * 100, 1)))
    for s in SCHED:
        col = col_for(cohort_df, s, ["sched::"])
        if col is None:
            print(f"  (skipped {s}: no sched:: column)")
            continue
        present = (pd.to_numeric(cohort_df[col], errors="coerce").fillna(0) > 0).sum()
        rows.append((s, int(present), round(present / n * 100, 1)))

    out = pd.DataFrame(rows, columns=["Object", "ReposUsing", "RepoPct"])
    out.to_csv(OUT_FILE, index=False)
    print(out.to_string(index=False))
    print(f"\nWritten -> {OUT_FILE}")


if __name__ == "__main__":
    main()