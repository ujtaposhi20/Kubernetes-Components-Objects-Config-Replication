import os
import subprocess
import sys
import pandas as pd

CLONED_REPOS = r"D:\new_k8s_analysis\cloned_repos"
RELEASE_DATA = r"D:\new_k8s_analysis\release_data.csv"
CADENCE_FILE = r"D:\new_k8s_analysis\ReleaseDataCategorized_postK8Sdata.csv"
PARTIAL      = r"D:\new_k8s_analysis\_sched_month_partial_cadence_v2.csv"
DONE_FILE    = r"D:\new_k8s_analysis\_sched_done_repos_cadence_v2.txt"
OUT_FINAL    = r"D:\new_k8s_analysis\monthly_scheduling_release_cadence.csv"

FEATURES = ["Node Affinity", "Pod Anti-Affinity", "Taints"]

TIMEOUT_LOG  = 300
TIMEOUT_SHOW = 30
TIMEOUT_SIZE = 15
MAX_FILE_BYTES = 1_000_000     
MAX_NODES      = 300_000
SKIP_REPOS = set()
FILL_ZERO_MONTHS = True

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


def git(repo, args, timeout):
    return subprocess.run(["git"] + args, cwd=repo, capture_output=True,
                          check=True, encoding="utf-8", errors="replace",
                          timeout=timeout).stdout
def feature_counts(content):
    """Structurally count features in one file's content. Iterative + node-capped."""
    counts = {f: 0 for f in FEATURES}
    if not HAS_YAML:
        return counts
    try:
        docs = list(yaml.safe_load_all(content))
    except Exception:
        return counts
    stack = [(d, None) for d in docs]
    nodes = 0
    while stack:
        node, parent = stack.pop()
        nodes += 1
        if nodes > MAX_NODES:
            break
        if isinstance(node, dict):
            for k, v in node.items():
                if k == "nodeAffinity" and parent == "affinity":
                    counts["Node Affinity"] += 1
                elif k == "podAntiAffinity" and parent == "affinity":
                    counts["Pod Anti-Affinity"] += 1
                elif k == "taints" and isinstance(v, list):
                    counts["Taints"] += 1
                stack.append((v, k))
        elif isinstance(node, list):
            for item in node:
                stack.append((item, parent))
    return counts
def list_repos(root):
    repos = []
    for owner in sorted(os.listdir(root)):
        odir = os.path.join(root, owner)
        if not os.path.isdir(odir):
            continue
        for name in sorted(os.listdir(odir)):
            p = os.path.join(odir, name)
            if os.path.isdir(os.path.join(p, ".git")):
                repos.append((f"{owner}/{name}", p))
    return repos
def blob_size(repo_path, hash_, path):
    try:
        return int(git(repo_path, ["cat-file", "-s", f"{hash_}:{path}"], TIMEOUT_SIZE).strip())
    except Exception:
        return None
def added_feature_counts(repo_path, cutoff_month):
    log = git(repo_path, ["log", "--reverse", "--diff-filter=A", "--name-status",
                          "--pretty=format:C\t%H\t%aI"], TIMEOUT_LOG)
    counts = {}
    cur_hash = cur_month = None
    for line in log.splitlines():
        if line.startswith("C\t"):
            _, cur_hash, iso = line.split("\t", 2)
            cur_month = iso[:7]
            continue
        if "\t" not in line or cur_month is None:
            continue
        path = line.split("\t")[-1]
        if os.path.splitext(path)[1].lower() not in (".yaml", ".yml"):
            continue
        if cur_month < cutoff_month:
            continue
        size = blob_size(repo_path, cur_hash, path)
        if size is None or size > MAX_FILE_BYTES:
            continue
        try:
            fc = feature_counts(git(repo_path, ["show", f"{cur_hash}:{path}"], TIMEOUT_SHOW))
        except Exception:
            fc = {}
        for feat, c in fc.items():
            if c:
                counts[(cur_month, feat)] = counts.get((cur_month, feat), 0) + c
    return counts
def release_counts(release_csv, repo_subset):
    rd = pd.read_csv(release_csv)
    rd = rd[rd["REPO"].isin(repo_subset)]
    rd["rel"] = pd.to_datetime(rd["RELEASEDATE"], utc=True, errors="coerce")
    rd["k8s"] = pd.to_datetime(rd["K8SFIRSTCOMMITDATE"], utc=True, errors="coerce")
    keep = rd["rel"].notna() & rd["k8s"].notna() & (rd["rel"] >= rd["k8s"])
    post = rd[keep].copy()
    post["Month"] = post["rel"].dt.strftime("%Y-%m")
    rc = post.groupby("Month").size().rename("ReleaseCount").reset_index()
    cutoff_month = (rd.dropna(subset=["k8s"]).groupby("REPO")["k8s"].first()
                      .dt.strftime("%Y-%m").to_dict())
    return rc, cutoff_month

def load_done():
    if os.path.exists(DONE_FILE):
        with open(DONE_FILE, encoding="utf-8") as f:
            return set(x.strip() for x in f if x.strip())
    return set()

def main():
    if not HAS_YAML:
        print("PyYAML required (regex fallback removed). pip install pyyaml", file=sys.stderr)
        sys.exit(1)
    if not os.path.isdir(CLONED_REPOS):
        print(f"Clone dir not found: {CLONED_REPOS}", file=sys.stderr)
        sys.exit(1)

    cadence = set(pd.read_csv(CADENCE_FILE)["REPO"])
    print(f"Cadence repos to process: {len(cadence)}", flush=True)

    rc, cutoff_month = release_counts(RELEASE_DATA, cadence)
    print(f"Release months: {len(rc)} ({rc['Month'].min()}..{rc['Month'].max()})", flush=True)

    repos = [(k, p) for (k, p) in list_repos(CLONED_REPOS) if k in cadence]
    total = len(repos)
    done = load_done()
    print(f"Found {total} cadence repos on disk. Already done: {len(done)}. Walking the rest...", flush=True)

    need_header = not os.path.exists(PARTIAL)
    pf = open(PARTIAL, "a", encoding="utf-8", newline="")
    df_lock = open(DONE_FILE, "a", encoding="utf-8")
    if need_header:
        pf.write("repo,Month,Object,count\n")

    for i, (repo_key, path) in enumerate(repos, 1):
        if repo_key in done or repo_key in SKIP_REPOS:
            continue
        cm = cutoff_month.get(repo_key)
        print(f"  [{i}/{total}] {repo_key}", flush=True)
        if cm is None:
            df_lock.write(repo_key + "\n"); df_lock.flush()
            continue
        try:
            counts = added_feature_counts(path, cm)
        except subprocess.TimeoutExpired:
            print(f"      TIMEOUT on {repo_key} -- skipped (not marked done)", file=sys.stderr, flush=True)
            continue
        except Exception as e:
            print(f"      skip {repo_key}: {e}", file=sys.stderr, flush=True)
            df_lock.write(repo_key + "\n"); df_lock.flush()
            continue
        for (mo, feat), c in counts.items():
            pf.write(f'"{repo_key}",{mo},"{feat}",{c}\n')
        pf.flush()
        df_lock.write(repo_key + "\n"); df_lock.flush()
    pf.close(); df_lock.close()

    part = pd.read_csv(PARTIAL)
    agg = (part.groupby(["Month", "Object"])["count"].sum()
               .rename("CountOfObjectPerFile").reset_index())

    if FILL_ZERO_MONTHS:
        grid = pd.MultiIndex.from_product([rc["Month"], FEATURES],
                                          names=["Month", "Object"]).to_frame(index=False)
        agg = grid.merge(agg, on=["Month", "Object"], how="left")
        agg["CountOfObjectPerFile"] = agg["CountOfObjectPerFile"].fillna(0).astype(int)

    final = (agg.merge(rc, on="Month", how="inner")
                .sort_values(["Month", "Object"]))[
        ["Month", "Object", "CountOfObjectPerFile", "ReleaseCount"]]
    final.to_csv(OUT_FINAL, index=False)
    print(f"Wrote {len(final)} rows -> {OUT_FINAL}", flush=True)

if __name__ == "__main__":
    main()