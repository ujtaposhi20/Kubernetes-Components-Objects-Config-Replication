import argparse
import csv
import os
import re
import subprocess
import sys
import time
import pathlib
from typing import Dict, List, Optional, Tuple
import requests
import pandas as pd

GITHUB_API = "https://api.github.com"
RE_API = re.compile(r"^\s*apiVersion\s*:\s*\S", re.MULTILINE)
RE_KIND = re.compile(r"^\s*kind\s*:\s*\S", re.MULTILINE)
YAML_EXT = (".yaml", ".yml")
MAX_YAML_BYTES = 2_000_000 


def looks_like_k8s_yaml(text: str) -> bool:
    return bool(RE_API.search(text) and RE_KIND.search(text))

def load_repo_list(excel: Optional[str], csv_path: Optional[str], column: Optional[str]) -> List[str]:
    if excel:
        df = pd.read_excel(excel)
    else:
        df = pd.read_csv(csv_path)
    col = column
    if not col:
        for cand in ("full_name", "repo", "repository", "name_with_owner", "nameWithOwner"):
            if cand in df.columns:
                col = cand
                break
    if not col:
        sys.exit(f"[error] Could not find a repo column. Columns = {list(df.columns)}. "
                 f"Pass --column explicitly.")
    repos = []
    for raw in df[col].dropna().astype(str):
        owner_repo = normalize_owner_repo(raw)
        if owner_repo:
            repos.append(owner_repo)
    # de-dup, keep order
    seen, out = set(), []
    for r in repos:
        if r not in seen:
            seen.add(r)
            out.append(r)
    return out

def normalize_owner_repo(s: str) -> Optional[str]:
    s = s.strip()
    m = re.search(r"github\.com[/:]([^/\s]+)/([^/\s]+?)(?:\.git)?(?:[/?#].*)?$", s, re.I)
    if m:
        return f"{m.group(1)}/{m.group(2)}"
    m = re.match(r"^([A-Za-z0-9_.\-]+)/([A-Za-z0-9_.\-]+)$", s)
    if m:
        return f"{m.group(1)}/{m.group(2)}"
    return None

class GitHub:
    def __init__(self, token: Optional[str]):
        self.s = requests.Session()
        self.s.headers.update({
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "release-k8s-csv-script",
        })
        if token:
            self.s.headers["Authorization"] = f"Bearer {token}"

    def _get(self, url: str, params: Optional[dict] = None, max_retries: int = 5) -> requests.Response:
        for attempt in range(1, max_retries + 1):
            try:
                r = self.s.get(url, params=params, timeout=40)
            except requests.RequestException as e:
                if attempt == max_retries:
                    raise
                time.sleep(min(2 ** attempt, 30))
                continue
            if r.status_code == 403 and r.headers.get("X-RateLimit-Remaining") == "0":
                reset = int(r.headers.get("X-RateLimit-Reset", "0"))
                wait = max(reset - int(time.time()) + 2, 5)
                print(f"  [rate-limit] sleeping {wait}s ...", flush=True)
                time.sleep(wait)
                continue
            if r.status_code in (403, 429):  # secondary rate limit
                retry_after = int(r.headers.get("Retry-After", "10"))
                time.sleep(retry_after)
                continue
            if 500 <= r.status_code < 600:
                if attempt == max_retries:
                    return r
                time.sleep(min(2 ** attempt, 30))
                continue
            return r
        return r  # type: ignore

    def get_releases(self, owner_repo: str) -> Tuple[List[dict], Optional[str]]:
        """Return (releases, error). Paginates fully."""
        owner, repo = owner_repo.split("/", 1)
        url = f"{GITHUB_API}/repos/{owner}/{repo}/releases"
        params = {"per_page": 100}
        out: List[dict] = []
        while url:
            r = self._get(url, params=params)
            params = None  
            if r.status_code == 404:
                return [], "repo_not_found_or_no_access"
            if r.status_code != 200:
                return [], f"http_{r.status_code}"
            out.extend(r.json())
            url = r.links.get("next", {}).get("url")
        return out, None

    def default_branch(self, owner_repo: str) -> Optional[str]:
        owner, repo = owner_repo.split("/", 1)
        r = self._get(f"{GITHUB_API}/repos/{owner}/{repo}")
        if r.status_code == 200:
            return r.json().get("default_branch")
        return None
def find_clone_dir(clones_root: pathlib.Path, owner_repo: str) -> Optional[pathlib.Path]:
    owner, repo = owner_repo.split("/", 1)
    candidates = [
        clones_root / owner / repo,
        clones_root / f"{owner}_{repo}",
        clones_root / f"{owner}__{repo}",
        clones_root / repo,
    ]
    for c in candidates:
        if (c / ".git").exists() or (c.is_dir() and (c / "HEAD").exists()):
            return c
    return None


def run_git(args: List[str], cwd: pathlib.Path, timeout: int = 120) -> Tuple[int, str]:
    try:
        p = subprocess.run(["git", "-C", str(cwd)] + args,
                           capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout
    except subprocess.TimeoutExpired:
        return 124, ""
    except Exception:
        return 1, ""


def k8s_first_commit_date_local(repo_dir: pathlib.Path, date_field: str = "author") -> Optional[str]:
    rc, out = run_git(["ls-files", "-z", "*.yaml", "*.yml", "*.YAML", "*.YML"], repo_dir)
    if rc != 0:
        return None
    files = [f for f in out.split("\0") if f]
    if not files:
        return None
    k8s_files: List[str] = []
    for rel in files:
        fpath = repo_dir / rel
        try:
            if fpath.stat().st_size > MAX_YAML_BYTES:
                continue
            text = fpath.read_text(encoding="utf-8", errors="ignore")
        except (OSError, ValueError):
            continue
        if looks_like_k8s_yaml(text):
            k8s_files.append(rel)
    if not k8s_files:
        return None
    fmt = "%aI" if date_field == "author" else "%cI"
    tmp = repo_dir / ".k8s_paths_tmp.txt"
    try:
        tmp.write_text("\n".join(k8s_files), encoding="utf-8")
        rc, out = run_git(
            ["log", "--all", "--reverse", f"--format={fmt}", f"--pathspec-from-file={tmp}"],
            repo_dir, timeout=300,
        )
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass

    if rc == 0:
        for line in out.splitlines():
            line = line.strip()
            if line:
                return line
    earliest = None
    for rel in k8s_files:
        rc, out = run_git(["log", "--all", "--reverse", f"--format={fmt}", "--", rel], repo_dir)
        if rc == 0:
            for line in out.splitlines():
                line = line.strip()
                if line:
                    if earliest is None or line < earliest:
                        earliest = line
                    break
    return earliest

def k8s_first_commit_date_api(gh: GitHub, owner_repo: str, max_files: int = 200,
                              date_field: str = "author") -> Optional[str]:
    """
    Heavy fallback. Walks the default-branch tree, classifies YAMLs by raw content,
    then for each k8s YAML finds the oldest commit via the commits API. Capped at
    `max_files` classified manifests to stay within rate limits.
    """
    owner, repo = owner_repo.split("/", 1)
    branch = gh.default_branch(owner_repo)
    if not branch:
        return None
    r = gh._get(f"{GITHUB_API}/repos/{owner}/{repo}/git/trees/{branch}",
                params={"recursive": "1"})
    if r.status_code != 200:
        return None
    tree = r.json().get("tree", [])
    yaml_paths = [t["path"] for t in tree
                  if t.get("type") == "blob" and t["path"].lower().endswith(YAML_EXT)]

    k8s_paths: List[str] = []
    for path in yaml_paths:
        if len(k8s_paths) >= max_files:
            break
        raw = gh._get(f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}")
        if raw.status_code == 200 and looks_like_k8s_yaml(raw.text):
            k8s_paths.append(path)
    if not k8s_paths:
        return None

    earliest = None
    field = "author" if date_field == "author" else "committer"
    for path in k8s_paths:
        r = gh._get(f"{GITHUB_API}/repos/{owner}/{repo}/commits",
                    params={"path": path, "per_page": 1})
        if r.status_code != 200 or not r.json():
            continue
        last = r.links.get("last", {}).get("url")
        if last:
            r = gh._get(last)
            if r.status_code != 200 or not r.json():
                continue
        commits = r.json()
        oldest = commits[-1]
        date = oldest.get("commit", {}).get(field, {}).get("date")
        if date and (earliest is None or date < earliest):
            earliest = date
    return earliest

COLUMNS = ["REPO", "RELEASEINDEX", "RELEASEDATE", "K8SFIRSTCOMMITDATE"]

def already_done(out_path: pathlib.Path) -> set:
    done = set()
    if out_path.exists():
        with out_path.open("r", newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("REPO"):
                    done.add(row["REPO"])
    return done


def main():
    ap = argparse.ArgumentParser(description="Generate REPO/RELEASEINDEX/RELEASEDATE/K8SFIRSTCOMMITDATE CSV.")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--excel", help="Path to repo_list.xlsx")
    src.add_argument("--csv", help="Path to a CSV listing repos")
    ap.add_argument("--column", default=None, help="Column with owner/repo or URL (auto-detected if omitted)")
    ap.add_argument("--clones-root", default=None, help="Folder containing your local clones (owner/repo layout)")
    ap.add_argument("--out", required=True, help="Output CSV path")
    ap.add_argument("--token", default=None, help="GitHub token (else uses $GITHUB_TOKEN)")
    ap.add_argument("--date-field", choices=["author", "committer"], default="author",
                    help="Which commit date to use for K8SFIRSTCOMMITDATE (default: author)")
    ap.add_argument("--api-fallback", action="store_true",
                    help="If a local clone is missing, compute K8SFIRSTCOMMITDATE via API (slow).")
    ap.add_argument("--resume", action="store_true", help="Skip repos already present in --out")
    args = ap.parse_args()

    token = args.token or os.environ.get("GITHUB_TOKEN", "").strip() or None
    if not token:
        print("[warn] No token -> 60 requests/hour. Set GITHUB_TOKEN for 5,000/hour.", flush=True)
    gh = GitHub(token)

    clones_root = pathlib.Path(args.clones_root).expanduser().resolve() if args.clones_root else None
    out_path = pathlib.Path(args.out).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    repos = load_repo_list(args.excel, args.csv, args.column)
    print(f"[info] {len(repos)} unique repos to process.", flush=True)

    done = already_done(out_path) if args.resume else set()
    write_header = not out_path.exists() or out_path.stat().st_size == 0

    missing_k8s_log = out_path.with_name(out_path.stem + "_no_k8s_or_clone.txt")

    with out_path.open("a", newline="", encoding="utf-8") as f, \
         missing_k8s_log.open("a", encoding="utf-8") as mlog:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        if write_header:
            w.writeheader()

        for i, repo in enumerate(repos, 1):
            if repo in done:
                continue
            print(f"[{i}/{len(repos)}] {repo}", flush=True)
            k8s_date = None
            clone_dir = find_clone_dir(clones_root, repo) if clones_root else None
            if clone_dir:
                k8s_date = k8s_first_commit_date_local(clone_dir, args.date_field)
            elif args.api_fallback:
                k8s_date = k8s_first_commit_date_api(gh, repo, date_field=args.date_field)
            if not k8s_date:
                why = "no_k8s_yaml_found" if clone_dir else "clone_missing_no_fallback"
                mlog.write(f"{repo}\t{why}\n")
                mlog.flush()
            releases, err = gh.get_releases(repo)
            if err:
                w.writerow({"REPO": repo, "RELEASEINDEX": "", "RELEASEDATE": "",
                            "K8SFIRSTCOMMITDATE": k8s_date or ""})
                f.flush()
                print(f"    releases error: {err}", flush=True)
                continue
            if not releases:
                w.writerow({"REPO": repo, "RELEASEINDEX": "", "RELEASEDATE": "",
                            "K8SFIRSTCOMMITDATE": k8s_date or ""})
            else:
                for rel in releases:
                    w.writerow({
                        "REPO": repo,
                        "RELEASEINDEX": rel.get("url", ""),
                        "RELEASEDATE": rel.get("published_at") or "",
                        "K8SFIRSTCOMMITDATE": k8s_date or "",
                    })
            f.flush()

    print(f"\n[done] CSV -> {out_path}")
    print(f"[done] Repos with no k8s YAML / no clone logged -> {missing_k8s_log}")


if __name__ == "__main__":
    main()
