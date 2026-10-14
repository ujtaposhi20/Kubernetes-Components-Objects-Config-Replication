import os
import re
import sys
import csv
import yaml
import pandas as pd

# ---------------- config ----------------
CLONED_REPOS   = r"D:\new_k8s_analysis\cloned_repos"
REPO_LIST_FILE = r"D:\new_k8s_analysis\ReleaseDataCategorized_postK8Sdata.csv"
OUT_DIR        = r"D:\new_k8s_analysis"
PER_REPO_FILE  = os.path.join(OUT_DIR, "repo_object_counts_by_category.csv")
HEATMAP_FILE   = os.path.join(OUT_DIR, "object_usage_heatmap.csv")
DONE_FILE      = os.path.join(OUT_DIR, "_heatmap_scan_done.txt")

MAX_FILE_BYTES = 2_000_000
YAML_EXTS      = (".yml", ".yaml")

KIND_GROUPS = {
    "Autoscaler":    {"HorizontalPodAutoscaler", "VerticalPodAutoscaler"},
    "ConfigMap":     {"ConfigMap"},
    "CRD":           {"CustomResourceDefinition"},
    "DaemonSet":     {"DaemonSet"},
    "Deployment":    {"Deployment"},
    "EndpointSlice": {"Endpoints", "EndpointSlice"},
    "Ingress":       {"Ingress", "IngressClass"},
    "LimitRange":    {"LimitRange"},
    "Namespace":     {"Namespace"},
    "NetworkPolicy": {"NetworkPolicy"},
    "PV":            {"PersistentVolume"},
    "PVC":           {"PersistentVolumeClaim"},
    "Pod":           {"Pod"},
    "ReplicaSet":    {"ReplicaSet"},
    "Secret":        {"Secret"},
    "Service":       {"Service"},
    "StatefulSet":   {"StatefulSet"},
}
OBJECT_ORDER  = list(KIND_GROUPS.keys())
KIND_TO_GROUP = {k: g for g, ks in KIND_GROUPS.items() for k in ks}

SCHED_GROUPS = {
    "Node Affinity":          {"nodeaffinity"},
    "Pod Anti-Affinity":      {"podantiaffinity"},
    "Taints and tolerations": {"tolerations", "taints"},
}
SCHED_ORDER    = list(SCHED_GROUPS.keys())
ALL_SCHED_KEYS = {k: name for name, ks in SCHED_GROUPS.items() for k in ks}

ALL_OBJECTS = OBJECT_ORDER + SCHED_ORDER  

APP_ORDER = ["Web Application", "Batch Application", "AI Application", "Database Applications"]
IMG_KEYWORDS = {
    "Database Applications": ["postgres", "mysql", "mariadb", "mongo", "redis", "cassandra",
                              "cockroach", "couchdb", "clickhouse", "influxdb", "neo4j",
                              "timescale", "memcached", "minio", "etcd"],
    "AI Application":        ["tensorflow", "pytorch", "keras", "jupyter", "cuda", "nvidia",
                              "huggingface", "mlflow", "kubeflow", "triton", "onnx", "vllm",
                              "scikit"],
    "Batch Application":     ["spark", "airflow", "flink", "hadoop", "beam", "nifi",
                              "celery", "kafka"],
    "Web Application":       ["nginx", "httpd", "caddy", "traefik", "node", "php",
                              "wordpress", "tomcat", "gunicorn", "uvicorn", "envoy"],
}
TEXT_KEYWORDS = {
    "Database Applications": ["postgres", "mysql", "mongodb", "sqlalchemy", "database", "jdbc"],
    "AI Application":        ["tensorflow", "pytorch", "transformers", "scikit-learn",
                              "langchain", "openai", "machine learning", "deep learning"],
    "Batch Application":     ["spark", "airflow", "flink", "etl", "batch job", "data pipeline"],
    "Web Application":       ["flask", "django", "fastapi", "express", "spring-boot",
                              "react", "angular", "vue", "rails", "frontend"],
}
PROJECT_FILES = ["readme", "requirements.txt", "package.json", "go.mod", "pipfile",
                 "pom.xml", "setup.py", "environment.yml", "dockerfile"]
W_IMG, W_TEXT, W_KIND, W_IPYNB = 2, 1, 2, 3

KIND_RE  = re.compile(r"^\s*kind:\s*[\"']?([A-Za-z0-9]+)", re.MULTILINE)
IMAGE_RE = re.compile(r"image:\s*[\"']?([^\s\"'#]+)", re.IGNORECASE)
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

def load_repo_names(path):
    try:
        df = pd.read_csv(path)
        for col in ("REPO", "repo", "Repo"):
            if col in df.columns:
                return set(df[col].dropna().astype(str))
        return set(df.iloc[:, 0].dropna().astype(str))
    except Exception:
        return set(l.strip() for l in open(path, encoding="utf-8") if l.strip())

def read_text(path):
    try:
        if os.path.getsize(path) > MAX_FILE_BYTES:
            return ""
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception:
        return ""

def walk_doc(node, counts, kinds, images):
    if isinstance(node, dict):
        for k, v in node.items():
            kl = str(k).lower()
            if kl == "kind" and isinstance(v, str):
                kk = v.strip()
                kinds.add(kk)
                g = KIND_TO_GROUP.get(kk)
                if g:
                    counts[g] += 1
            elif kl == "image" and isinstance(v, str):
                images.append(v.lower())
            elif kl in ALL_SCHED_KEYS:
                counts[ALL_SCHED_KEYS[kl]] += 1
            walk_doc(v, counts, kinds, images)
    elif isinstance(node, list):
        for item in node:
            walk_doc(item, counts, kinds, images)

def scan_repo(path):
    counts = {g: 0 for g in ALL_OBJECTS}
    kinds, images, text_blob = set(), [], []
    has_ipynb = False

    for dirpath, dirnames, filenames in os.walk(path):
        if ".git" in dirnames:
            dirnames.remove(".git")
        for fn in filenames:
            low = fn.lower()
            full = os.path.join(dirpath, fn)
            if low.endswith(".ipynb"):
                has_ipynb = True
            if low.endswith(YAML_EXTS):
                txt = read_text(full)
                if not txt:
                    continue
                ok = False
                try:
                    for doc in yaml.safe_load_all(txt):
                        if doc is not None:
                            walk_doc(doc, counts, kinds, images)
                            ok = True
                except Exception:
                    ok = False
                if not ok:
                    for m in KIND_RE.findall(txt):
                        kinds.add(m)
                        g = KIND_TO_GROUP.get(m)
                        if g:
                            counts[g] += 1
                    for m in IMAGE_RE.findall(txt):
                        images.append(m.lower())
                    tl = txt.lower()
                    for key, name in ALL_SCHED_KEYS.items():
                        c = tl.count(key)
                        if c:
                            counts[name] += c
            elif any(low == pf or low.startswith(pf) for pf in PROJECT_FILES):
                text_blob.append(read_text(full).lower())

    blob = "\n".join(text_blob)
    scores = {a: 0 for a in APP_ORDER}
    img_text = " ".join(images)
    for app in APP_ORDER:
        for kw in IMG_KEYWORDS[app]:
            scores[app] += W_IMG * img_text.count(kw)
        for kw in TEXT_KEYWORDS[app]:
            if kw in blob:
                scores[app] += W_TEXT
    if "Job" in kinds or "CronJob" in kinds:
        scores["Batch Application"] += W_KIND * (("Job" in kinds) + ("CronJob" in kinds))
    if "Ingress" in kinds:
        scores["Web Application"] += W_KIND
    if "StatefulSet" in kinds:
        scores["Database Applications"] += 1
    if has_ipynb:
        scores["AI Application"] += W_IPYNB

    best = max(scores, key=lambda a: scores[a])
    app = best if scores[best] > 0 else "Unknown"
    return app, scores, counts

def load_done():
    if os.path.exists(DONE_FILE):
        return set(x.strip() for x in open(DONE_FILE, encoding="utf-8") if x.strip())
    return set()

def main():
    if not os.path.isdir(CLONED_REPOS):
        sys.exit(f"Clone dir not found: {CLONED_REPOS}")
    wanted = load_repo_names(REPO_LIST_FILE)
    repos = [(k, p) for (k, p) in list_repos(CLONED_REPOS) if k in wanted]
    total = len(repos)
    done = load_done()
    print(f"Repo names given: {len(wanted)} | found on disk: {total} | already done: {len(done)}", flush=True)
    miss = wanted - {k for k, _ in repos}
    if miss:
        print(f"  (not found on disk: {len(miss)})", flush=True)

    score_cols = ["score_" + a.split()[0].lower() for a in APP_ORDER]
    header = ["repo", "Application"] + score_cols + ALL_OBJECTS

    need_header = not os.path.exists(PER_REPO_FILE)
    pf = open(PER_REPO_FILE, "a", encoding="utf-8", newline="")
    dl = open(DONE_FILE, "a", encoding="utf-8")
    w = csv.writer(pf)
    if need_header:
        w.writerow(header)

    for i, (key, path) in enumerate(repos, 1):
        if key in done:
            continue
        try:
            app, scores, counts = scan_repo(path)
        except Exception as e:
            print(f"  skip {key}: {e}", file=sys.stderr, flush=True)
            dl.write(key + "\n"); dl.flush()
            continue
        w.writerow([key, app] + [scores[a] for a in APP_ORDER] + [counts[g] for g in ALL_OBJECTS])
        pf.flush(); dl.write(key + "\n"); dl.flush()
        if i % 25 == 0:
            print(f"  {i}/{total}", flush=True)
    pf.close(); dl.close()


    df = pd.read_csv(PER_REPO_FILE).drop_duplicates("repo", keep="last")
    df.to_csv(PER_REPO_FILE, index=False)
    print("\nCategory counts:")
    print(df["Application"].value_counts())
    n_unknown = int((df["Application"] == "Unknown").sum())
    if n_unknown:
        print(f"  ({n_unknown} repos are 'Unknown' and are NOT included in the heatmap)")

    rows = []
    for app in APP_ORDER:
        sub = df[df["Application"] == app]
        sums = {g: sub[g].sum() for g in ALL_OBJECTS}
        grand = sum(sums.values())
        for g in ALL_OBJECTS:
            val = (sums[g] / grand * 100.0) if grand > 0 else 0.0
            rows.append({"Application": app, "Object": g, "Value": round(val, 1)})
    out = pd.DataFrame(rows, columns=["Application", "Object", "Value"])
    out.to_csv(HEATMAP_FILE, index=False)

    print("\nValue sum per application (should be ~100):")
    print(out.groupby("Application")["Value"].sum().reindex(APP_ORDER))
    print(f"\nPer-repo detail -> {PER_REPO_FILE}\nHeatmap        -> {HEATMAP_FILE}")

if __name__ == "__main__":
    main()
