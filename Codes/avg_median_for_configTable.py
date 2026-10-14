import os
import re
import csv
import pandas as pd

BASE         = r"D:\new_k8s_analysis"
CLONES_DIR   = os.path.join(BASE, "cloned_repos")
CADENCE_FILE = os.path.join(BASE, "ReleaseDataCategorized_postK8Sdata.csv")
CHECKPOINT   = os.path.join(BASE, "config_method_scan_checkpoint.csv")
OUT_CSV      = os.path.join(BASE, "table_ix_config_method.csv")

METHOD_TOOLS = {
    "GitOps":         ["ArgoCD", "Flux"],
    "IaC":            ["Ansible", "Terraform"],
    "PackageManager": ["Helm"],
}
TOOLS = ["Helm", "ArgoCD", "Flux", "Terraform", "Ansible"]
METHODS = list(METHOD_TOOLS.keys())
CADENCE_ORDER = ["rapid+", "rapid", "modern", "slow"]

SKIP_DIRS = {".git", "node_modules", "vendor", ".terraform", "dist", "build"}
MAX_FILE_BYTES = 512 * 1024


def read_text(path, cap=MAX_FILE_BYTES):
    """Read a file as UTF-8, ignoring undecodable bytes. Never raises."""
    try:
        with open(path, "rb") as f:
            return f.read(cap).decode("utf-8", errors="ignore")
    except Exception:
        return ""


def parse_owner_name(url):
    """Turn a github remote URL into 'owner/name'. Handles ssh and https."""
    url = url.strip()
    if url.endswith(".git"):
        url = url[:-4]
    m = re.search(r"github\.com[:/]+([^/\s]+)/([^/\s]+)$", url)
    return f"{m.group(1)}/{m.group(2)}" if m else None


def repo_id(repo_dir, owner_folder, name_folder):
    """Canonical owner/name from .git/config; fall back to folder layout."""
    cfg = os.path.join(repo_dir, ".git", "config")
    if os.path.isfile(cfg):
        m = re.search(r"url\s*=\s*(.+)", read_text(cfg))
        if m:
            rid = parse_owner_name(m.group(1))
            if rid:
                return rid
    return f"{owner_folder}/{name_folder}"


def detect_tools(repo_dir):
    """Walk one repo and return a dict of tool -> 0/1."""
    found = {t: 0 for t in TOOLS}
    for root, dirs, files in os.walk(repo_dir):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        if os.path.basename(root).lower() == "roles":
            found["Ansible"] = 1
        for fn in files:
            fl = fn.lower()
            if fl in ("chart.yaml", "chart.yml"):
                found["Helm"] = 1
            elif fl.endswith(".tf"):
                found["Terraform"] = 1
            elif fl == "ansible.cfg" or fl in (
                "site.yml", "site.yaml", "playbook.yml", "playbook.yaml"
            ):
                found["Ansible"] = 1
            elif fl.endswith((".yaml", ".yml")):
                if not (found["ArgoCD"] and found["Flux"]):
                    text = read_text(os.path.join(root, fn))
                    if "argoproj.io" in text:
                        found["ArgoCD"] = 1
                    if "fluxcd.io" in text:
                        found["Flux"] = 1
        if all(found.values()):
            break
    return found


def load_checkpoint():
    done = {}
    if os.path.isfile(CHECKPOINT):
        with open(CHECKPOINT, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                done[row["repo"]] = {t: int(row[t]) for t in TOOLS}
    return done


def main():
    cad = pd.read_csv(CADENCE_FILE)
    cohort = set(cad["REPO"])
    print(f"Cohort repos: {len(cohort)}")
    clone_path = {}
    for owner in os.listdir(CLONES_DIR):
        owner_dir = os.path.join(CLONES_DIR, owner)
        if not os.path.isdir(owner_dir):
            continue
        for name in os.listdir(owner_dir):
            rdir = os.path.join(owner_dir, name)
            if os.path.isdir(rdir):
                clone_path[repo_id(rdir, owner, name)] = rdir

    found_in_clones = cohort & set(clone_path)
    missing = sorted(cohort - set(clone_path))
    print(f"Cohort clones located: {len(found_in_clones)}")
    if missing:
        print(f"WARNING: {len(missing)} cohort repos have no clone on disk "
              f"(treated as no-method):")
        for r in missing[:20]:
            print(f"    {r}")
    print()
    results = load_checkpoint()
    if results:
        print(f"Resuming: {len(results)} repos already scanned.\n")
    todo = [r for r in sorted(found_in_clones) if r not in results]

    write_header = not os.path.isfile(CHECKPOINT)
    with open(CHECKPOINT, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if write_header:
            w.writerow(["repo"] + TOOLS)
        for i, rid in enumerate(todo, 1):
            flags = detect_tools(clone_path[rid])
            results[rid] = flags
            w.writerow([rid] + [flags[t] for t in TOOLS])
            f.flush()
            if i % 25 == 0 or i == len(todo):
                print(f"  scanned {i}/{len(todo)}")
    print()

    rows = []
    for rid in cohort:
        flags = results.get(rid, {t: 0 for t in TOOLS})
        rows.append({"repo": rid, **flags})
    scan = pd.DataFrame(rows)
    for method, tools in METHOD_TOOLS.items():
        scan[method] = (scan[tools].sum(axis=1) > 0).astype(int)

    merged = cad.merge(scan[["repo"] + METHODS],
                       left_on="REPO", right_on="repo", how="left")
    merged[METHODS] = merged[METHODS].fillna(0).astype(int)

    print("Repos per cadence group:")
    for g in CADENCE_ORDER:
        print(f"    {g:8s} {int((merged['CADENCEGROUP'] == g).sum())}")
    print()

    agg = (merged.groupby("CADENCEGROUP")[METHODS]
                 .agg(["mean", "median"])
                 .reindex(CADENCE_ORDER))

    header = f"{'Category':10s}" + "".join(f"{m + ' (Avg., Med.)':26s}" for m in METHODS)
    print(header)
    print("-" * len(header))
    out = []
    for g in CADENCE_ORDER:
        cells, row = [], {"Category": g}
        for m in METHODS:
            avg = agg.loc[g, (m, "mean")]
            med = agg.loc[g, (m, "median")]
            cells.append(f"{avg:.1f}, {med:.1f}".ljust(26))
            row[f"{m}_avg"] = round(float(avg), 4)
            row[f"{m}_median"] = float(med)
        print(f"{g:10s}" + "".join(cells))
        out.append(row)

    pd.DataFrame(out).to_csv(OUT_CSV, index=False)
    print(f"\nSaved table:      {OUT_CSV}")
    print(f"Per-repo scan:    {CHECKPOINT}")


if __name__ == "__main__":
    main()
