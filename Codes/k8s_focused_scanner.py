from __future__ import annotations
import argparse
import csv
import os
import re
import sys
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import OrderedDict, defaultdict
from typing import Dict, List, Tuple, Iterable, Optional
import time

try:
    from tqdm import tqdm
except Exception:
    tqdm = None

try:
    import yaml
except ImportError:
    yaml = None

from collections import OrderedDict

KIND_GROUPS = OrderedDict({
    "Deployment": {"Deployment"},
    "StatefulSet": {"StatefulSet"},
    "DaemonSet": {"DaemonSet"},
    "ReplicaSet": {"ReplicaSet"},
    "Pod": {"Pod"},
    "Service": {"Service"},
    "EndpointSlice": {"Endpoints", "EndpointSlice"},
    "Ingress": {"Ingress", "IngressClass"},
    "ConfigMap": {"ConfigMap"},
    "Secret": {"Secret"},
    "Namespace": {"Namespace"},
    "NetworkPolicy": {"NetworkPolicy"},
    "PersistentVolume": {"PersistentVolume"},
    "PersistentVolumeClaim": {"PersistentVolumeClaim"},
    "Autoscaler": {"HorizontalPodAutoscaler", "VerticalPodAutoscaler"},
    "LimitRange": {"LimitRange"},
    "CustomResourceDefinition": {"CustomResourceDefinition"},
})

KIND_GROUPS_ALL = set().union(*KIND_GROUPS.values())

COMPONENTS = [
    "Operators",
    "Controllers",
    "Scheduler",
    "Node Planner",
    "Kube-DNS",
    "etcd",
    "kube-scheduler",
    "kube-controller-manager",
    "cloud-controller-manager",
    "kubelet",
]

COMPONENT_PATTERNS: Dict[str, re.Pattern] = {
    "Operators": re.compile(
        r"\boperator-sdk\b|"
        r"\bkubebuilder\b|"
        r"\boperator-framework\b|"
        r"\bkubernetes[-_ ]operator\b|"
        r"\boperator\b",
        re.IGNORECASE
    ),
    "Controllers": re.compile(
        r"\bcontroller-runtime\b|"
        r"\bcontroller\b",
        re.IGNORECASE
    ),

    "Scheduler": re.compile(
        r"\bscheduler\s+extender\b|"
        r"\bcustom\s+scheduler\b|"
        r"\bkube-scheduler\.config\b",
        re.IGNORECASE
    ),
    "Node Planner": re.compile(
        r"\bnodeselector\b",
        re.IGNORECASE
    ),
    "Kube-DNS": re.compile(
        r"\bkube[-_ ]dns\b|"
        r"\bcoredns\b",
        re.IGNORECASE
    ),
    "etcd": re.compile(
        r"\betcd\b",
        re.IGNORECASE
    ),
    "kube-scheduler": re.compile(
        r"\bkube[-_ ]scheduler\b",
        re.IGNORECASE
    ),
    "kube-controller-manager": re.compile(
        r"\bkube[-_ ]controller[-_ ]manager\b",
        re.IGNORECASE
    ),
    "cloud-controller-manager": re.compile(
        r"\bcloud[-_ ]controller[-_ ]manager\b",
        re.IGNORECASE
    ),
    "kubelet": re.compile(
        r"\bkubelet\b",
        re.IGNORECASE
    ),
}

SCHED_FEATURES = [
    "Node Affinity",
    "Taints and tolerations",
    "Pod Anti-Affinity",
]


SCHED_FEATURE_PATTERNS: Dict[str, re.Pattern] = {
    "Node Affinity": re.compile(
        r"\bnodeAffinity\b|"
        r"\brequiredDuringSchedulingIgnoredDuringExecution\b|"
        r"\bpreferredDuringSchedulingIgnoredDuringExecution\b",
        re.IGNORECASE
    ),
    "Pod Anti-Affinity": re.compile(
        r"\bpodAntiAffinity\b|"
        r"\bpodAffinity\b|"
        r"\btopologyKey\b",
        re.IGNORECASE
    ),
    "Taints and tolerations": re.compile(
        r"\btaints\b|"
        r"\btolerations\b|"
        r"\bNoSchedule\b|"
        r"\bPreferNoSchedule\b|"
        r"\bNoExecute\b",
        re.IGNORECASE
    ),
}
LOG_MON = [
    "Prometheus",
    "Datadog",
    "KubeDB",
    "Lens",
    "Grafana",
    "Vector",
    "OpenSearch",
]

LOG_MON_PATTERNS: Dict[str, re.Pattern] = {
    name: re.compile(rf"\b{re.escape(name)}\b", re.IGNORECASE)
    for name in LOG_MON
}
IAC = [
    "Terraform",
    "Helm",
    "Ansible",
    "ArgoCD",
    "Flux",
]

IAC_PATTERNS: Dict[str, re.Pattern] = {

    # 1 Terraform
    "Terraform": re.compile(
        r"\bterraform\b|\.tf\b",
        re.IGNORECASE
    ),

    # 2 Helm
    "Helm": re.compile(
        r"\bhelm\b|"
        r"\bChart\.ya?ml\b|"
        r"\bvalues\.ya?ml\b",
        re.IGNORECASE
    ),

    # 3 Ansible
    "Ansible": re.compile(
        r"\bansible\b|"
        r"\bplaybook\b|"
        r"\bplaybook\.ya?ml\b",
        re.IGNORECASE
    ),

    # 4 ArgoCD
    "ArgoCD": re.compile(
        r"\bargocd\b|"
        r"\bargoproj\.io\b",
        re.IGNORECASE
    ),

    # 5 Flux
    "Flux": re.compile(
        r"\bfluxcd\b|"
        r"\bflux\b",
        re.IGNORECASE
    ),
}

WORKLOADS = [
    "Databases (StatefulSets)",
    "Web applications",
    "Data pipelines",
    "Batch jobs",
]
import re
from typing import Dict

WORKLOAD_PATTERNS: Dict[str, re.Pattern] = {
    "Databases (StatefulSets)": re.compile(
        r"\bstatefulset\b|"
        r"\bpostgres\b|"
        r"\bmysql\b|"
        r"\bmariadb\b|"
        r"\bmongodb\b|"
        r"\bredis\b|"
        r"\bcassandra\b|"
        r"\bcockroachdb\b",
        re.IGNORECASE
    ),
    "Data pipelines": re.compile(
        r"\bdata\s+pipeline(s)?\b",
        re.IGNORECASE
    ),
    "Batch jobs": re.compile(
        r"\bjob\b|\bcron\s*job\b",
        re.IGNORECASE
    ),
}

SDK_SIGNALS = {
    "go": [
        re.compile(r"k8s\.io/client-go"),
        re.compile(r"sigs\.k8s\.io/controller-runtime"),
        re.compile(r"k8s\.io/api"),
        re.compile(r"k8s\.io/apimachinery"),
    ],
    "ts": [
        re.compile(r"@kubernetes/client-node"),
        re.compile(r"kubernetes-client"),
        re.compile(r"kube[-_]?client"),
    ],
}

TEXT_EXTS = {".md", ".txt"}
CODE_EXTS = {".go", ".ts"}
YAML_EXTS = {".yaml", ".yml"}
OTHER_EXTS_FOR_HINTS = {".tf"}

IGNORE_DIRS = {".git", ".github", ".gitlab", "node_modules", "venv", ".venv", "dist", "build", "target", ".idea", ".vscode"}
KIND_REGEX = re.compile(r"^\s*kind\s*:\s*([A-Za-z0-9]+)\s*$", re.IGNORECASE | re.MULTILINE)
NODE_AFFINITY_KEYS = (("spec", "template", "spec", "affinity", "nodeAffinity"), ("spec", "affinity", "nodeAffinity"))
POD_ANTI_AFFINITY_KEYS = (("spec", "template", "spec", "affinity", "podAntiAffinity"), ("spec", "affinity", "podAntiAffinity"))
TOLERATIONS_KEYS = (("spec", "template", "spec", "tolerations"), ("spec", "tolerations"))


def is_yaml(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in YAML_EXTS


def is_text_like(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in TEXT_EXTS


def is_code_like(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in CODE_EXTS


def should_skip_dir(dirname: str) -> bool:
    base = os.path.basename(dirname).lower()
    return base in {d.lower() for d in IGNORE_DIRS}

MAX_BYTES = 2_000_000

def safe_read(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read(MAX_BYTES)
    except Exception:
        return ""

def _owner_name_from_url(url: str) -> Optional[str]:
    url = url.strip()
    if url.endswith(".git"):
        url = url[:-4]
    url = url.replace(":", "/")
    parts = [p for p in url.split("/") if p]
    return parts[-2] + "/" + parts[-1] if len(parts) >= 2 else None


def repo_full_name(repo_dir: str) -> str:
    """Return 'owner/name' from the repo's .git/config; fall back to folder name."""
    cfg = os.path.join(repo_dir, ".git", "config")
    try:
        with open(cfg, "r", encoding="utf-8", errors="ignore") as f:
            txt = f.read()
        m = re.search(r"url\s*=\s*(.+)", txt)
        if m:
            fn = _owner_name_from_url(m.group(1))
            if fn:
                return fn
    except Exception:
        pass
    return os.path.basename(repo_dir)


def walk_files(root: str) -> Iterable[str]:
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not should_skip_dir(os.path.join(dirpath, d))]
        for fn in filenames:
            fp = os.path.join(dirpath, fn)
            ext = os.path.splitext(fn)[1].lower()
            if ext in YAML_EXTS or ext in TEXT_EXTS or ext in CODE_EXTS or ext in OTHER_EXTS_FOR_HINTS:
                yield fp
def yaml_documents(text: str) -> Iterable[dict]:
    if not text.strip():
        return []
    docs: List[dict] = []
    if yaml is not None:
        try:
            for doc in yaml.safe_load_all(text):
                if isinstance(doc, dict):
                    docs.append(doc)
        except Exception:
            pass
    if not docs:
        for m in KIND_REGEX.finditer(text):
            kind = m.group(1)
            if kind:
                docs.append({"kind": kind})
    return docs


def has_key_path(obj: dict, paths: Tuple[Tuple[str, ...], ...]) -> bool:
    for path in paths:
        cur = obj
        ok = True
        for k in path:
            if not isinstance(cur, dict) or k not in cur:
                ok = False
                break
            cur = cur[k]
        if ok:
            return True
    return False
def scan_repo(repo_dir: str, evidence_cap: int = 2) -> dict:
    """Return metrics dict for a single repo.
    evidence_cap: store up to N matched lines/files per label for human spot-checking.
    """
    repo_rel = repo_full_name(repo_dir)
    object_counts = {k: 0 for k in KIND_GROUPS.keys()}
    components_flags = {k: 0 for k in COMPONENTS}
    sched_flags = {k: 0 for k in SCHED_FEATURES}
    logmon_flags = {k: 0 for k in LOG_MON}
    iac_flags = {k: 0 for k in IAC}
    workloads_flags = {k: 0 for k in WORKLOADS}
    sdk_flags = {"go": 0, "ts": 0}
    saw_deployment = False
    saw_service = False
    evidence = defaultdict(list)

    for fp in walk_files(repo_dir):
        try:
            ext = os.path.splitext(fp)[1].lower()
            txt = safe_read(fp)
            if not txt and ext not in YAML_EXTS:
                continue
            if ext in YAML_EXTS:
                for doc in yaml_documents(txt):
                    kind = str(doc.get("kind", "")).strip()
                    if kind:
                        for group_name, kinds in KIND_GROUPS.items():
                            if kind in kinds:
                                object_counts[group_name] += 1
                                if len(evidence[group_name]) < evidence_cap:
                                    evidence[group_name].append(f"{fp}: kind={kind}")
                        if kind == "Deployment":
                            saw_deployment = True
                        if kind == "Service":
                            saw_service = True
                    if has_key_path(doc, NODE_AFFINITY_KEYS):
                        sched_flags["Node Affinity"] = 1
                        if len(evidence["Node Affinity"]) < evidence_cap:
                            evidence["Node Affinity"].append(f"{fp}: nodeAffinity present")
                    if has_key_path(doc, TOLERATIONS_KEYS):
                        sched_flags["Taints and tolerations"] = 1
                        if len(evidence["Taints and tolerations"]) < evidence_cap:
                            evidence["Taints and tolerations"].append(f"{fp}: tolerations present")
                    if has_key_path(doc, POD_ANTI_AFFINITY_KEYS):
                        sched_flags["Pod Anti-Affinity"] = 1
                        if len(evidence["Pod Anti-Affinity"]) < evidence_cap:
                            evidence["Pod Anti-Affinity"].append(f"{fp}: podAntiAffinity present")
                if IAC_PATTERNS["Helm"].search(fp):
                    iac_flags["Helm"] = 1
                    if len(evidence["Helm"]) < evidence_cap:
                        evidence["Helm"].append(f"{fp}: helm path")
            if ext == ".go":
                for rx in SDK_SIGNALS["go"]:
                    if rx.search(txt):
                        sdk_flags["go"] = 1
                        if len(evidence["sdk-go"]) < evidence_cap:
                            evidence["sdk-go"].append(f"{fp}: {rx.pattern}")
                        break
            elif ext == ".ts":
                for rx in SDK_SIGNALS["ts"]:
                    if rx.search(txt):
                        sdk_flags["ts"] = 1
                        if len(evidence["sdk-ts"]) < evidence_cap:
                            evidence["sdk-ts"].append(f"{fp}: {rx.pattern}")
                        break
            if ext in TEXT_EXTS or ext in CODE_EXTS or ext in YAML_EXTS or ext in OTHER_EXTS_FOR_HINTS:
                for name, rx in COMPONENT_PATTERNS.items():
                    if components_flags[name]:
                        continue
                    if rx.search(txt) or rx.search(fp):
                        components_flags[name] = 1
                        if len(evidence[name]) < evidence_cap:
                            hit = f"{fp}: match '{name}'"
                            evidence[name].append(hit)
                for name, rx in LOG_MON_PATTERNS.items():
                    if logmon_flags[name]:
                        continue
                    if rx.search(txt) or rx.search(fp):
                        logmon_flags[name] = 1
                        if len(evidence[name]) < evidence_cap:
                            evidence[name].append(f"{fp}: match '{name}'")

                for name, rx in IAC_PATTERNS.items():
                    if iac_flags[name]:
                        continue
                    if rx.search(txt) or rx.search(fp):
                        iac_flags[name] = 1
                        if len(evidence[name]) < evidence_cap:
                            evidence[name].append(f"{fp}: match '{name}'")
                for name, rx in WORKLOAD_PATTERNS.items():
                    if name == "Web applications":
                        continue
                    if not workloads_flags[name] and rx.search(txt):
                        workloads_flags[name] = 1
                        if len(evidence[name]) < evidence_cap:
                            evidence[name].append(f"{fp}: match '{name}'")
        except Exception as e:
            continue
    if saw_deployment and saw_service:
        workloads_flags["Web applications"] = 1
        if len(evidence["Web applications"]) < evidence_cap:
            evidence["Web applications"].append("repo-level: Deployment+Service present")
    if object_counts.get("StatefulSet", 0) > 0:
        workloads_flags["Databases (StatefulSets)"] = 1

    object_flags = {k: 1 if v > 0 else 0 for k, v in object_counts.items()}

    return {
        "repo": repo_rel,
        "object_counts": object_counts,
        "object_flags": object_flags,
        "components_flags": components_flags,
        "sched_flags": sched_flags,
        "logmon_flags": logmon_flags,
        "iac_flags": iac_flags,
        "workloads_flags": workloads_flags,
        "sdk_flags": sdk_flags,
        "evidence": dict(evidence),
    }

def empty_result(repo_dir: str, error: Optional[str] = None) -> dict:
    repo_rel = repo_full_name(repo_dir)
    res = {
        "repo": repo_rel,
        "object_counts": {k: 0 for k in KIND_GROUPS.keys()},
        "object_flags": {k: 0 for k in KIND_GROUPS.keys()},
        "components_flags": {k: 0 for k in COMPONENTS},
        "sched_flags": {k: 0 for k in SCHED_FEATURES},
        "logmon_flags": {k: 0 for k in LOG_MON},
        "iac_flags": {k: 0 for k in IAC},
        "workloads_flags": {k: 0 for k in WORKLOADS},
        "sdk_flags": {"go": 0, "ts": 0},
        "evidence": {},
    }
    if error:
        res["error"] = error
    return res


def scan_repo_safe(repo_dir: str, retries: int = 2) -> dict:
    last_err = None
    for attempt in range(retries + 1):
        try:
            return scan_repo(repo_dir)
        except Exception as e:
            last_err = e
    return empty_result(repo_dir, error=str(last_err))

def _classify_output_file(path: str) -> str:
    """Classify file for output bucketing: yaml | readme | go | ts | other."""
    base = os.path.basename(path).lower()
    ext = os.path.splitext(base)[1]
    if ext in YAML_EXTS:
        return "yaml"
    if base.startswith("readme") and ext in {".md", ".txt", ".rst"}:
        return "readme"
    if ext == ".go":
        return "go"
    if ext == ".ts":
        return "ts"
    return "other"

def ensure_out(out_dir: str):
    os.makedirs(out_dir, exist_ok=True)

def write_csv(path: str, rows: List[Dict[str, object]], fieldnames: List[str]):
    """Windows-friendly CSV writer.
    - Write to temp file then atomically replace target.
    - If target is locked (e.g., Excel open), write a timestamped fallback instead.
    - Log any issue to write_errors.log in the same folder.
    """
    out_dir = os.path.dirname(path)
    os.makedirs(out_dir, exist_ok=True)
    tmp_path = path + ".tmp"
    try:
        # write to temp
        with open(tmp_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            for r in rows:
                w.writerow(r)
        # try atomic replace
        try:
            os.replace(tmp_path, path)
        except PermissionError:
            # target is locked -> write fallback
            base, ext = os.path.splitext(path)
            fallback = f"{base}.{int(time.time())}{ext}"
            with open(fallback, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=fieldnames)
                w.writeheader()
                for r in rows:
                    w.writerow(r)
            with open(os.path.join(out_dir, "write_errors.log"), "a", encoding="utf-8") as lf:
                lf.write(f"[PermissionError] '{path}' locked; wrote '{fallback}' instead.\n")
        except Exception as e:
            with open(os.path.join(out_dir, "write_errors.log"), "a", encoding="utf-8") as lf:
                lf.write(f"[ReplaceError] {path}: {e}\n")
    except Exception as e:
        # clean temp if present
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass
        with open(os.path.join(out_dir, "write_errors.log"), "a", encoding="utf-8") as lf:
            lf.write(f"[WriteError] {path}: {e}\n")


def flatten_repo_row(res: dict) -> dict:
    row = {"repo": res["repo"]}
    # object counts
    for k in KIND_GROUPS.keys():
        row[f"objcnt::{k}"] = res["object_counts"].get(k, 0)
        row[f"objhas::{k}"] = res["object_flags"].get(k, 0)
    # components
    for k in COMPONENTS:
        row[f"comp::{k}"] = res["components_flags"].get(k, 0)
    # sched
    for k in SCHED_FEATURES:
        row[f"sched::{k}"] = res["sched_flags"].get(k, 0)
    # log/mon
    for k in LOG_MON:
        row[f"logmon::{k}"] = res["logmon_flags"].get(k, 0)
    # iac
    for k in IAC:
        row[f"iac::{k}"] = res["iac_flags"].get(k, 0)
    # workloads
    for k in WORKLOADS:
        row[f"workload::{k}"] = res["workloads_flags"].get(k, 0)
    # sdk
    row["sdk::go"] = res["sdk_flags"].get("go", 0)
    row["sdk::ts"] = res["sdk_flags"].get("ts", 0)
    return row


def aggregate_counts(all_results: List[dict]) -> Dict[str, Dict[str, int]]:
    tot = {
        "objects": {k: 0 for k in KIND_GROUPS.keys()},
        "components": {k: 0 for k in COMPONENTS},
        "scheduling": {k: 0 for k in SCHED_FEATURES},
        "logmon": {k: 0 for k in LOG_MON},
        "iac": {k: 0 for k in IAC},
        "workloads": {k: 0 for k in WORKLOADS},
        "sdk": {"go": 0, "ts": 0},
    }
    for res in all_results:
        for k in KIND_GROUPS.keys():
            tot["objects"][k] += res["object_counts"].get(k, 0)
        for k in COMPONENTS:
            tot["components"][k] += res["components_flags"].get(k, 0)
        for k in SCHED_FEATURES:
            tot["scheduling"][k] += res["sched_flags"].get(k, 0)
        for k in LOG_MON:
            tot["logmon"][k] += res["logmon_flags"].get(k, 0)
        for k in IAC:
            tot["iac"][k] += res["iac_flags"].get(k, 0)
        for k in WORKLOADS:
            tot["workloads"][k] += res["workloads_flags"].get(k, 0)
        for k in ("go", "ts"):
            tot["sdk"][k] += res["sdk_flags"].get(k, 0)
    return tot


def write_outputs(out_dir: str, all_results: List[dict]):
    ensure_out(out_dir)

    # (1) repo_summary.csv
    rows = [flatten_repo_row(r) for r in all_results]
    fieldnames = sorted(rows[0].keys()) if rows else ["repo"]
    fieldnames = ["repo"] + [fn for fn in fieldnames if fn != "repo"]
    write_csv(os.path.join(out_dir, "repo_summary.csv"), rows, fieldnames)

    # (2) object_counts.csv (global totals)
    tot = aggregate_counts(all_results)
    write_csv(
        os.path.join(out_dir, "object_counts.csv"),
        [{"object": k, "total_occurrences": v} for k, v in tot["objects"].items()],
        ["object", "total_occurrences"],
    )

    # (3) components_counts.csv
    write_csv(
        os.path.join(out_dir, "components_counts.csv"),
        [{"component": k, "repos_with_signal": v} for k, v in tot["components"].items()],
        ["component", "repos_with_signal"],
    )

    # (4) scheduling_features_counts.csv
    write_csv(
        os.path.join(out_dir, "scheduling_features_counts.csv"),
        [{"feature": k, "repos_with_signal": v} for k, v in tot["scheduling"].items()],
        ["feature", "repos_with_signal"],
    )

    # (5) logging_monitoring_counts.csv
    write_csv(
        os.path.join(out_dir, "logging_monitoring_counts.csv"),
        [{"tool": k, "repos_with_signal": v} for k, v in tot["logmon"].items()],
        ["tool", "repos_with_signal"],
    )

    # (6) iac_counts.csv
    write_csv(
        os.path.join(out_dir, "iac_counts.csv"),
        [{"tool": k, "repos_with_signal": v} for k, v in tot["iac"].items()],
        ["tool", "repos_with_signal"],
    )

    # (7) workloads_counts.csv
    write_csv(
        os.path.join(out_dir, "workloads_counts.csv"),
        [{"workload": k, "repos_with_signal": v} for k, v in tot["workloads"].items()],
        ["workload", "repos_with_signal"],
    )

    # (8) sdk_counts.csv
    write_csv(
        os.path.join(out_dir, "sdk_counts.csv"),
        [{"language": k, "repos_with_signal": v} for k, v in tot["sdk"].items()],
        ["language", "repos_with_signal"],
    )

    # (9) evidence_samples.csv — compact for manual spot-check
    ev_rows = []
    for r in all_results:
        repo = r["repo"]
        for label, items in r.get("evidence", {}).items():
            for it in items:
                ev_rows.append({"repo": repo, "label": label, "evidence": it})
    if ev_rows:
        write_csv(
            os.path.join(out_dir, "evidence_samples.csv"),
            ev_rows,
            ["repo", "label", "evidence"],
        )

    # (10) Split evidence into file buckets + write per-file hit lists
    yaml_rows, readme_rows, go_rows, ts_rows = [], [], [], []
    seen = set()
    for r in all_results:
        repo = r["repo"]
        for label, items in r.get("evidence", {}).items():
            for it in items:
                path, sep, note = it.partition(": ")  # Windows-safe split (keeps C:\)
                if not sep:
                    continue  # skip repo-level synthetic notes
                bucket = _classify_output_file(path)
                key = (repo, label, path, note)
                if key in seen:
                    continue
                seen.add(key)
                row = {"repo": repo, "label": label, "file": path, "evidence": note}
                if bucket == "yaml":
                    yaml_rows.append(row)
                elif bucket == "readme":
                    readme_rows.append(row)
                elif bucket == "go":
                    go_rows.append(row)
                elif bucket == "ts":
                    ts_rows.append(row)
                # ignore 'other'

    if yaml_rows:
        write_csv(os.path.join(out_dir, "yaml_hits.csv"), yaml_rows, ["repo", "label", "file", "evidence"])
    if readme_rows:
        write_csv(os.path.join(out_dir, "readme_hits.csv"), readme_rows, ["repo", "label", "file", "evidence"])
    if go_rows:
        write_csv(os.path.join(out_dir, "go_hits.csv"), go_rows, ["repo", "label", "file", "evidence"])
    if ts_rows:
        write_csv(os.path.join(out_dir, "ts_hits.csv"), ts_rows, ["repo", "label", "file", "evidence"])

    # (11) Matrices per bucket: rows=labels, columns=repos (0/1 presence)
    def write_matrix_csv(path: str, labels: List[str], repos: List[str], present: Dict[str, set]):
        # present: label -> {repo,...}
        fieldnames = ["label"] + repos
        matrix_rows = []
        for lab in labels:
            row = {"label": lab}
            pres = present.get(lab, set())
            for repo in repos:
                row[repo] = 1 if repo in pres else 0
            matrix_rows.append(row)
        write_csv(path, matrix_rows, fieldnames)

    # Gather repo order from results
    repo_order = [r["repo"] for r in all_results]

    # Build presence maps from hit rows
    def build_presence(rows: List[Dict[str, str]]) -> Dict[str, set]:
        mp: Dict[str, set] = defaultdict(set)
        for r in rows:
            mp[r["label"]].add(r["repo"])
        return mp

    yaml_present = build_presence(yaml_rows)
    readme_present = build_presence(readme_rows)
    go_present = build_presence(go_rows)
    ts_present = build_presence(ts_rows)

    # Enrich YAML bucket with structured flags that might not have file evidence lines
    for r in all_results:
        repo = r["repo"]
        # Object kinds
        for k, flag in r["object_flags"].items():
            if flag:
                yaml_present.setdefault(k, set()).add(repo)
        # Scheduling
        for k, flag in r["sched_flags"].items():
            if flag:
                yaml_present.setdefault(k, set()).add(repo)
        # Workloads derived from YAML (Web applications, Databases (StatefulSets))
        for k in ("Web applications", "Databases (StatefulSets)"):
            if r["workloads_flags"].get(k, 0):
                yaml_present.setdefault(k, set()).add(repo)

    # Define label lists per bucket
    yaml_labels = list({
        *KIND_GROUPS.keys(),
        *SCHED_FEATURES,
        *LOG_MON,  # YAML text hits for these
        *IAC,      # YAML text hits for these
        *COMPONENTS,  # YAML text hits for these
        *WORKLOADS,
    })
    readme_labels = list({*COMPONENTS, *LOG_MON, *IAC, *WORKLOADS})
    go_labels = list({*COMPONENTS, *LOG_MON, *IAC, *WORKLOADS, "sdk-go"})
    ts_labels = list({*COMPONENTS, *LOG_MON, *IAC, *WORKLOADS, "sdk-ts"})

    write_matrix_csv(os.path.join(out_dir, "yaml_matrix.csv"), sorted(yaml_labels), repo_order, yaml_present)
    write_matrix_csv(os.path.join(out_dir, "readme_matrix.csv"), sorted(readme_labels), repo_order, readme_present)
    write_matrix_csv(os.path.join(out_dir, "go_matrix.csv"), sorted(go_labels), repo_order, go_present)
    write_matrix_csv(os.path.join(out_dir, "ts_matrix.csv"), sorted(ts_labels), repo_order, ts_present)

    # (12) errors.csv — repos that returned an error but still counted as scanned
    err_rows = [{"repo": r["repo"], "error": r["error"]} for r in all_results if r.get("error")]
    if err_rows:
        write_csv(os.path.join(out_dir, "errors.csv"), err_rows, ["repo", "error"])

ALL_LABELS_FOR_EVAL = (
    # Object groups
    list(KIND_GROUPS.keys())
    + COMPONENTS
    + SCHED_FEATURES
    + LOG_MON
    + IAC
    + WORKLOADS
    + ["sdk-go", "sdk-ts"]
)

def compute_predictions_long(all_results: List[dict]) -> List[Tuple[str, str, int]]:
    """Return list of (repo, label, pred) with pred in {0,1} for ALL_LABELS_FOR_EVAL."""
    out = []
    for r in all_results:
        repo = r["repo"]
        # objects
        for k in KIND_GROUPS.keys():
            out.append((repo, k, 1 if r["object_flags"].get(k, 0) else 0))
        # components
        for k in COMPONENTS:
            out.append((repo, k, 1 if r["components_flags"].get(k, 0) else 0))
        # sched
        for k in SCHED_FEATURES:
            out.append((repo, k, 1 if r["sched_flags"].get(k, 0) else 0))
        # log/mon
        for k in LOG_MON:
            out.append((repo, k, 1 if r["logmon_flags"].get(k, 0) else 0))
        # iac
        for k in IAC:
            out.append((repo, k, 1 if r["iac_flags"].get(k, 0) else 0))
        # workloads
        for k in WORKLOADS:
            out.append((repo, k, 1 if r["workloads_flags"].get(k, 0) else 0))
        # sdk
        out.append((repo, "sdk-go", 1 if r["sdk_flags"].get("go", 0) else 0))
        out.append((repo, "sdk-ts", 1 if r["sdk_flags"].get("ts", 0) else 0))
    return out


def load_gold_long(path: str) -> Dict[Tuple[str, str], int]:
    """Expect CSV with columns: repo,label,truth where truth in {0,1}."""
    gold = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            repo = row.get("repo", "").strip()
            label = row.get("label", "").strip()
            truth = int(row.get("truth", 0))
            if repo and label:
                gold[(repo, label)] = 1 if truth else 0
    return gold


def eval_metrics(all_results: List[dict], gold_path: str, out_dir: str):
    preds = compute_predictions_long(all_results)
    gold = load_gold_long(gold_path)

    # Confusion counts per label
    counts = defaultdict(lambda: {"TP": 0, "FP": 0, "FN": 0, "TN": 0})

    # Collect all repos + labels present anywhere
    repos = sorted({r["repo"] for r in all_results})
    labels = set(l for _, l, _ in preds)

    # For each label, iterate all repos and compare
    pred_map = {(repo, label): p for repo, label, p in preds}
    for label in labels:
        for repo in repos:
            p = pred_map.get((repo, label), 0)
            t = gold.get((repo, label), 0)
            if p == 1 and t == 1:
                counts[label]["TP"] += 1
            elif p == 1 and t == 0:
                counts[label]["FP"] += 1
            elif p == 0 and t == 1:
                counts[label]["FN"] += 1
            else:
                counts[label]["TN"] += 1

    # Compute metrics
    metrics_rows = []
    conf_rows = []
    for label in sorted(labels):
        TP = counts[label]["TP"]; FP = counts[label]["FP"]; FN = counts[label]["FN"]; TN = counts[label]["TN"]
        prec = TP / (TP + FP) if (TP + FP) > 0 else 0.0
        rec = TP / (TP + FN) if (TP + FN) > 0 else 0.0
        f1 = (2 * prec * rec / (prec + rec)) if (prec + rec) > 0 else 0.0
        metrics_rows.append({"label": label, "precision": round(prec, 4), "recall": round(rec, 4), "f1": round(f1, 4), "support": TP + FN})
        conf_rows.append({"label": label, "TP": TP, "FP": FP, "FN": FN, "TN": TN})

    write_csv(os.path.join(out_dir, "evaluation_metrics.csv"), metrics_rows, ["label", "precision", "recall", "f1", "support"])
    write_csv(os.path.join(out_dir, "evaluation_confusion.csv"), conf_rows, ["label", "TP", "FP", "FN", "TN"])
def parse_args():
    ap = argparse.ArgumentParser(description="Focused Kubernetes scanner (STRICT)")
    ap.add_argument("--dir", default=r"D:\new_k8s_analysis\cloned_repos",
                    help="Path to root folder that contains ALL cloned repos (each repo in a subfolder)")
    ap.add_argument("--out", default=r"D:\new_k8s_analysis\scan_output",
                    help="Output folder for CSVs")
    ap.add_argument("--workers", type=int, default=16, help="Thread workers (I/O heavy, threads are fine)")
    ap.add_argument("--sample", type=int, default=0, help="Optionally scan only first N repos (for quick test)")
    ap.add_argument("--eval-gold", default=None, help="Path to gold CSV (repo,label,truth). If provided, compute precision/recall/F1")
    ap.add_argument("--max-bytes", type=int, default=2_000_000, help="Max bytes to read per file (default 2MB) to avoid huge blobs")
    ap.add_argument("--no-tqdm", action="store_true", help="Disable tqdm progress bar (fallback to plain text progress)")
    return ap.parse_args()


def has_git_dir(p: str) -> bool:
    return os.path.isdir(os.path.join(p, ".git"))

def list_repos(root: str, mode: str = "auto") -> List[str]:
    entries: List[str] = []
    try:
        if mode in ("git", "auto"):
            # Search depth <= 2 for folders containing .git
            # 1) root/*
            for name in os.listdir(root):
                p1 = os.path.join(root, name)
                if os.path.isdir(p1) and has_git_dir(p1):
                    entries.append(p1)
            # 2) root/*/*
            for name in os.listdir(root):
                p1 = os.path.join(root, name)
                if not os.path.isdir(p1):
                    continue
                for name2 in os.listdir(p1):
                    p2 = os.path.join(p1, name2)
                    if os.path.isdir(p2) and has_git_dir(p2):
                        entries.append(p2)
            # dedupe while preserving order
            seen = set()
            entries = [e for e in entries if not (e in seen or seen.add(e))]
            if mode == "git" or entries:
                return entries
        # Fallback to flat: each immediate subfolder is a repo folder
        for name in os.listdir(root):
            p = os.path.join(root, name)
            if os.path.isdir(p):
                entries.append(p)
    except FileNotFoundError:
        print(f"[error] Directory not found: {root}")
        return []
    return sorted(entries)


def main():
    args = parse_args()
    ensure_out(args.out)
    global MAX_BYTES
    MAX_BYTES = args.max_bytes

    print(f"[info] Reading cloned repos from: {args.dir}")
    print(f"[info] Writing CSV output to:     {args.out}")

    repos = list_repos(args.dir, "auto")

    if args.sample and args.sample > 0:
        repos = repos[: args.sample]

    # dump pre-scan list for debugging
    try:
        with open(os.path.join(args.out, "repos_list.txt"), "w", encoding="utf-8") as rf:
            for r in repos:
                rf.write(r + "\n")
    except Exception:
        pass

    print(f"[info] Found {len(repos)} repos (discovery={getattr(args, 'repo_discovery', 'auto')}). Scanning with {args.workers} workers...")

    results: List[dict] = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        future_map = {ex.submit(scan_repo_safe, r): r for r in repos}
        total = len(repos)
        completed = 0
        errors = 0

        if (tqdm is not None) and (not args.no_tqdm):
            pbar = tqdm(total=total, desc="Scanning repos", unit="repo", dynamic_ncols=True)
            for fut in as_completed(future_map):
                res = fut.result()
                results.append(res)
                if "error" in res and res["error"]:
                    errors += 1
                completed += 1
                pbar.update(1)
            pbar.close()
            sys.stdout.write(f"[summary] scanned={completed} | errors={errors} (see errors.csv if present)")
            sys.stdout.flush()
        else:
            # plain text progress
            for fut in as_completed(future_map):
                res = fut.result()
                results.append(res)
                if "error" in res and res["error"]:
                    errors += 1
                completed += 1
                left = total - completed
                pct = (completed / total * 100.0) if total > 0 else 0.0
                sys.stdout.write("[progress] %d/%d scanned | %d left | %.1f%%" % (completed, total, left, pct))
                sys.stdout.flush()
            sys.stdout.write("[summary] scanned=%d | errors=%d (see errors.csv if present)" % (completed, errors))
            sys.stdout.flush()

    # Write outputs
    if results:
        write_outputs(args.out, results)
        print(f"[done] CSVs written to: {args.out}")
    else:
        print("[warn] No results — nothing written.")

    # Optional evaluation
    if args.eval_gold:
        try:
            eval_metrics(results, args.eval_gold, args.out)
            print("[done] Evaluation metrics written.")
        except Exception as e:
            print(f"[warn] Evaluation failed: {e}")

if __name__ == "__main__":
    main()
