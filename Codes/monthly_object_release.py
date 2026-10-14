import os
import re
import subprocess
import sys
import pandas as pd

CLONED_REPOS = r"D:\new_k8s_analysis\cloned_repos"
RELEASE_DATA = r"D:\new_k8s_analysis\release_data.csv"
CADENCE_FILE = r"D:\new_k8s_analysis\ReleaseDataCategorized_postK8Sdata.csv"  
PARTIAL      = r"D:\new_k8s_analysis\_object_month_partial_cadence.csv"   
DONE_FILE    = r"D:\new_k8s_analysis\_done_repos_cadence.txt" 
OUT_FINAL    = r"D:\new_k8s_analysis\monthly_object_release_cadence.csv"

OBJECTS = {
    "Autoscaler", "ConfigMap", "CustomResourceDefinition", "DaemonSet", "Deployment",
    "EndpointSlice", "Ingress", "LimitRange", "Namespace", "NetworkPolicy",
    "PersistentVolume", "PersistentVolumeClaim", "Pod", "ReplicaSet", "Secret",
    "Service", "StatefulSet",
}
KIND_ALIASES = {"HorizontalPodAutoscaler": "Autoscaler", "VerticalPodAutoscaler": "Autoscaler"}

TIMEOUT_LOG  = 300
TIMEOUT_SHOW = 30
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
def parse_kinds(content):
    kinds = []
    if HAS_YAML:
        try:
            for doc in yaml.safe_load_all(content):
                if isinstance(doc, dict) and doc.get("kind"):
                    kinds.append(str(doc["kind"]))
        except Exception:
            pass
    else:
        for doc in re.split(r'^---.*$', content, flags=re.MULTILINE):
            for line in doc.splitlines():
                mt = re.match(r'^\s*kind\s*:\s*(.+?)\s*$', line)
                if mt:
                    kinds.append(mt.group(1).strip().strip('"\''))
                    break
    out = []
    for k in kinds:
        k = KIND_ALIASES.get(k, k)
        if OBJECTS is None or k in OBJECTS:
            out.append(k)
    return out


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


def added_counts(repo_path, cutoff_month):
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
        try:
            kinds = parse_kinds(git(repo_path, ["show", f"{cur_hash}:{path}"], TIMEOUT_SHOW))
        except Exception:
            kinds = []
        for k in kinds:
            counts[(cur_month, k)] = counts.get((cur_month, k), 0) + 1
    return counts


def release_counts(release_csv, repo_subset):
    rd = pd.read_csv(release_csv)
    rd = rd[rd["REPO"].isin(repo_subset)]          # only the cadence repos
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
        if repo_key in done:
            continue
        cm = cutoff_month.get(repo_key)
        print(f"  [{i}/{total}] {repo_key}", flush=True)
        if cm is None:
            df_lock.write(repo_key + "\n"); df_lock.flush()
            continue
        try:
            counts = added_counts(path, cm)
        except subprocess.TimeoutExpired:
            print(f"      TIMEOUT on {repo_key} -- skipped (not marked done)", file=sys.stderr, flush=True)
            continue
        except Exception as e:
            print(f"      skip {repo_key}: {e}", file=sys.stderr, flush=True)
            df_lock.write(repo_key + "\n"); df_lock.flush()
            continue
        for (mo, k), c in counts.items():
            pf.write(f'"{repo_key}",{mo},{k},{c}\n')
        pf.flush()
        df_lock.write(repo_key + "\n"); df_lock.flush()
    pf.close(); df_lock.close()
    part = pd.read_csv(PARTIAL)
    agg = (part.groupby(["Month", "Object"])["count"].sum()
               .rename("CountOfObjectPerFile").reset_index())

    if FILL_ZERO_MONTHS:
        objs = sorted(OBJECTS) if OBJECTS else sorted(agg["Object"].unique())
        grid = pd.MultiIndex.from_product([rc["Month"], objs],
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
