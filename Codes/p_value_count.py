import pandas as pd
from scipy.stats import kruskal

REPO_SUMMARY  = r"D:\new_k8s_analysis\repo_summary.csv"
CADENCE_FILE  = r"D:\new_k8s_analysis\CadenceDataCategory.xlsx"
SCHED_PARTIAL = r"D:\new_k8s_analysis\_sched_month_partial_cadence.csv" 
OUT_CSV       = r"D:\new_k8s_analysis\obj_p_value.csv"

GROUPS = ["rapid+", "rapid", "modern", "slow"]
ALPHA, N_TESTS = 0.05, 20
THRESHOLD = ALPHA / N_TESTS

OBJ17 = ["Autoscaler", "ConfigMap", "CustomResourceDefinition", "DaemonSet",
         "Deployment", "EndpointSlice", "Ingress", "LimitRange", "Namespace",
         "NetworkPolicy", "PersistentVolume", "PersistentVolumeClaim", "Pod",
         "ReplicaSet", "Secret", "Service", "StatefulSet"]
FEATURES = [("Node affinity", "Node Affinity"),
            ("Pod anti-affinity", "Pod Anti-Affinity"),
            ("Taints", "Taints and tolerations")]


def kw_pvalue(samples):
    try:
        return float(kruskal(*samples).pvalue)
    except ValueError:
        return float("nan")


def main():
    cad = pd.read_excel(CADENCE_FILE)[["REPO", "CADENCEGROUP"]]
    rs = pd.read_csv(REPO_SUMMARY)
    sch = pd.read_csv(SCHED_PARTIAL)
    base = cad.merge(rs, left_on="REPO", right_on="repo", how="left")
    fc = (sch.groupby(["repo", "Object"])["count"].sum()
             .unstack(fill_value=0)
             .reindex(cad["REPO"]).fillna(0))
    cad_idx = cad.set_index("REPO")

    rows = []
    for o in OBJ17:
        col = "objcnt::" + o
        sums = {g: int(base.loc[base.CADENCEGROUP == g, col].sum()) for g in GROUPS}
        p = kw_pvalue([base.loc[base.CADENCEGROUP == g, col].values for g in GROUPS])
        rows.append([o] + [sums[g] for g in GROUPS] + [p, (p < THRESHOLD)])

    for disp, key in FEATURES:
        series = fc[key] if key in fc.columns else pd.Series(0, index=cad["REPO"])
        tmp = cad_idx.join(series.rename("v")).fillna({"v": 0})
        sums = {g: int(tmp.loc[tmp.CADENCEGROUP == g, "v"].sum()) for g in GROUPS}
        p = kw_pvalue([tmp.loc[tmp.CADENCEGROUP == g, "v"].values for g in GROUPS])
        rows.append([disp] + [sums[g] for g in GROUPS] + [p, (p < THRESHOLD)])

    out = pd.DataFrame(rows, columns=["Object", "rapid+", "rapid", "modern", "slow",
                                      "p_value", "sig_bonf"])
    out.to_csv(OUT_CSV, index=False)

    print(f"Bonferroni threshold: {THRESHOLD}")
    print("Significant:", out.loc[out["sig_bonf"], "Object"].tolist())
    print(f"Wrote {OUT_CSV}")


if __name__ == "__main__":
    main()
