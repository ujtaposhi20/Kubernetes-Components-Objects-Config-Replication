import csv
import os

BASE = r"D:\new_k8s_analysis"
COHORT_FILE  = os.path.join(BASE, "ReleaseDataCategorized_postK8Sdata.csv")
SUMMARY_FILE = os.path.join(BASE, "repo_summary.csv")
OUT_FILE     = os.path.join(BASE, "config_cadence.csv")

CATEGORY_TOOLS = {
    "GITOPS": ["iac::ArgoCD", "iac::Flux"],
    "IAC":    ["iac::Ansible", "iac::Terraform"],
    "PKG":    ["iac::Helm"],
}

RECLASSIFIED_IAC = {"manusa/yakc", "manusa/yakd"}

cohort = {}
with open(COHORT_FILE, newline="", encoding="utf-8-sig") as f:
    for row in csv.DictReader(f):
        cohort[row["REPO"].strip()] = row["CADENCEGROUP"].strip().lower()
summ = {}
with open(SUMMARY_FILE, newline="", encoding="utf-8-sig") as f:
    for row in csv.DictReader(f):
        summ[row["repo"].strip()] = row

rows = []
missing = []
for repo, cadence in cohort.items():
    if repo not in summ:
        missing.append(repo)
        continue
    s = summ[repo]
    cats = set()
    for cat, tools in CATEGORY_TOOLS.items():
        if any(s.get(t, "0") == "1" for t in tools):
            cats.add(cat)
    if repo in RECLASSIFIED_IAC:
        cats.add("IAC")
    for cat in cats:
        rows.append((cat, cadence))

cat_order = {"GITOPS": 0, "IAC": 1, "PKG": 2}
cad_order = {"rapid+": 0, "rapid": 1, "modern": 2, "slow": 3}
rows.sort(key=lambda r: (cat_order[r[0]], cad_order.get(r[1], 99)))

with open(OUT_FILE, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["CONFIGMGMT", "CADENCEGROUP"])
    w.writerows(rows)

print(f"Wrote {len(rows)} rows -> {OUT_FILE}")
if missing:
    print(f"WARNING: {len(missing)} cohort repos not found in repo_summary, e.g. {missing[:5]}")