"""
Compute "PE Per Month [x, t] (%)" per Formula (2):

    PE Per Month [x, t] (%) = ( # of PEs of type x in scripts for month t )
                              -----------------------------------------------
                              ( Total count of PEs in scripts for month t )

"Total count of PEs in scripts for month t" is the sum over ALL 19 PEs
(16 objects + 3 scheduling features) for that month. So PEPerMonth_pct is a
true share of every PE seen that month, and the 19 PEs sum to 100% per month.

Inputs (aggregated monthly series, schema: Month,Object,CountOfObjectPerFile,ReleaseCount):
  - monthly_object_release_cadence.csv      (16 objects after dropping EndpointSlice)
  - monthly_scheduling_release_cadence.csv  (Node Affinity, Pod Anti-Affinity, Taints)

Output columns (pe_per_month.csv, long/tidy):
  Month, PE, Category, Count,
  AllPETotal_t   -> Formula (2) denominator: sum of all 19 PE counts in month t
  ObjectTotal_t  -> sum of the 16 object counts in month t (reference only)
  ReleaseCount_t,
  PEPerMonth_pct -> Formula (2): 100 * Count / AllPETotal_t

When a month's denominator is 0 (no tracked PEs that month) the pct is 0.0;
the raw Count / total columns are kept so 0/0 months can be re-set to NaN if preferred.
"""

import csv
import os
from collections import defaultdict

# ---------------------------- CONFIG ----------------------------
IN_DIR   = r"D:\new_k8s_analysis"
OUT_DIR  = r"D:\new_k8s_analysis"
OBJ_FILE = os.path.join(IN_DIR, "monthly_object_release_cadence.csv")
SCH_FILE = os.path.join(IN_DIR, "monthly_scheduling_release_cadence.csv")

DROP_OBJECTS = {"EndpointSlice"}   # excluded everywhere per project decision

# Figure 2 panel order
OBJECT_ORDER = [
    "Autoscaler", "ConfigMap", "CustomResourceDefinition", "DaemonSet",
    "Deployment", "Ingress", "LimitRange", "Namespace", "NetworkPolicy",
    "PersistentVolume", "PersistentVolumeClaim", "Pod", "ReplicaSet",
    "Secret", "Service", "StatefulSet",
]
SCHED_ORDER = ["Node Affinity", "Pod Anti-Affinity", "Taints"]

OUT_LONG = os.path.join(OUT_DIR, "pe_per_month.csv")
OUT_WIDE = os.path.join(OUT_DIR, "pe_per_month_wide.csv")
# ----------------------------------------------------------------


def read_series(path, drop=None):
    drop = drop or set()
    counts = defaultdict(float)   # (month, object) -> count
    releases = {}                 # month -> ReleaseCount
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            obj = row["Object"]
            if obj in drop:
                continue
            m = row["Month"]
            counts[(m, obj)] += float(row["CountOfObjectPerFile"])
            releases[m] = float(row["ReleaseCount"])
    return counts, releases


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    obj_counts, obj_rel = read_series(OBJ_FILE, drop=DROP_OBJECTS)
    sch_counts, sch_rel = read_series(SCH_FILE)

    months = sorted(set(obj_rel) | set(sch_rel))
    releases = {m: obj_rel.get(m, sch_rel.get(m)) for m in months}

    pes = [(o, "object") for o in OBJECT_ORDER] + [(s, "scheduling") for s in SCHED_ORDER]

    def count_of(pe, cat, m):
        return (obj_counts if cat == "object" else sch_counts).get((m, pe), 0.0)

    # Per-month totals
    obj_total = {m: sum(obj_counts.get((m, o), 0.0) for o in OBJECT_ORDER) for m in months}
    all_total = {m: obj_total[m] + sum(sch_counts.get((m, s), 0.0) for s in SCHED_ORDER)
                 for m in months}   # Formula (2) denominator

    def pct(num, den):
        return round(100.0 * num / den, 4) if den else 0.0

    # ---- long (tidy) format ----
    with open(OUT_LONG, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "Month", "PE", "Category", "Count",
            "AllPETotal_t", "ObjectTotal_t", "ReleaseCount_t", "PEPerMonth_pct",
        ])
        for m in months:
            for pe, cat in pes:
                c = count_of(pe, cat, m)
                w.writerow([
                    m, pe, cat, int(c) if c == int(c) else c,
                    int(all_total[m]), int(obj_total[m]), int(releases[m]),
                    pct(c, all_total[m]),
                ])

    # ---- wide format: one PEPerMonth_pct column per PE ----
    with open(OUT_WIDE, "w", newline="") as f:
        w = csv.writer(f)
        header = ["Month"] + [pe for pe, _ in pes] + ["ReleaseCount_t", "AllPETotal_t"]
        w.writerow(header)
        for m in months:
            r = [m] + [pct(count_of(pe, cat, m), all_total[m]) for pe, cat in pes]
            r += [int(releases[m]), int(all_total[m])]
            w.writerow(r)

    # ---- console sanity summary ----
    print("months:", len(months), "(", months[0], "->", months[-1], ")")
    print("PEs:", len(pes), "( 16 objects + 3 scheduling )  denominator = all 19 PEs")
    print("EndpointSlice dropped:", DROP_OBJECTS)
    nz = [m for m in months if all_total[m] > 0]
    # verify the 19 PEs sum to ~100% in non-zero months
    worst = 0.0
    for m in nz:
        s = sum(pct(count_of(pe, cat, m), all_total[m]) for pe, cat in pes)
        worst = max(worst, abs(s - 100.0))
    print("months with non-zero PE total:", len(nz), "; zero-denominator months:",
          len(months) - len(nz))
    print("max deviation of per-month sum from 100%%: %.4f" % worst)
    print("wrote:", OUT_LONG)
    print("wrote:", OUT_WIDE)


if __name__ == "__main__":
    main()
