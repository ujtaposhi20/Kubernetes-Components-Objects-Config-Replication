import os
import sys
import csv
import json
import time
import subprocess
import pandas as pd

BASE_DIR     = r"D:\new_k8s_analysis"
CLONED_REPOS = os.path.join(BASE_DIR, "cloned_repos")
CADENCE_FILE = os.path.join(BASE_DIR, "ReleaseDataCategorized_postK8Sdata.csv")
RELEASE_DATA = os.path.join(BASE_DIR, "release_data.csv")
SUMMARY_CANDIDATES = [
    os.path.join(BASE_DIR, "scan_output", "repo_summary.csv"),
    os.path.join(BASE_DIR, "repo_summary.csv"),
]
OUT_PER_REPO = os.path.join(BASE_DIR, "repo_attributes_per_repo.csv")
OUT_TABLE_CSV  = os.path.join(BASE_DIR, "repo_attributes_table.csv")
OUT_TABLE_XLSX = os.path.join(BASE_DIR, "repo_attributes_table.xlsx")
STARS_CACHE    = os.path.join(BASE_DIR, "_stars_cache.json")

CONFIG_EXTS  = (".yml", ".yaml")
USE_ALL_REFS = False
FETCH_STARS  = True
TIMEOUT_GIT  = 300

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

def git(repo, args):
    return subprocess.run(["git", "-C", repo] + args, capture_output=True,
                          text=True, errors="replace", timeout=TIMEOUT_GIT).stdout


def list_repos(root):
    """Walk owner/name folders and return [(owner/name, path), ...] for clones."""
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


def count_config_scripts(path):
    """Number of tracked YAML config files in the repo."""
    files = git(path, ["ls-files"]).splitlines()
    return sum(1 for f in files if f.lower().endswith(CONFIG_EXTS))


def repo_git_stats(path):
    """Return (commit_count, set_of_emails, min_month, max_month) from one git log."""
    ref = ["--all"] if USE_ALL_REFS else ["HEAD"]
    out = git(path, ["log", *ref, "--format=%aI%x09%ae"])
    commits = 0
    emails = set()
    mn = mx = None
    for line in out.splitlines():
        if "\t" not in line:
            continue
        iso, _, email = line.partition("\t")
        commits += 1
        e = email.strip().lower()
        if e:
            emails.add(e)
        mo = iso[:7]
        if len(mo) == 7:
            if mn is None or mo < mn:
                mn = mo
            if mx is None or mo > mx:
                mx = mo
    return commits, emails, mn, mx

def load_cache():
    if os.path.exists(STARS_CACHE):
        try:
            with open(STARS_CACHE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_cache(cache):
    with open(STARS_CACHE, "w", encoding="utf-8") as f:
        json.dump(cache, f)
def fetch_stars(repo_key, token):
    import urllib.request
    import urllib.error
    url = "https://api.github.com/repos/" + repo_key
    headers = {"Accept": "application/vnd.github+json",
               "User-Agent": "repo-attr-script"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.load(r)
            return int(data.get("stargazers_count", 0)), None
    except urllib.error.HTTPError as e:
        if e.code == 403 and e.headers.get("X-RateLimit-Remaining") == "0":
            reset = int(e.headers.get("X-RateLimit-Reset", "0"))
            wait = max(0, reset - int(time.time())) + 2
            return None, ("ratelimit", wait)
        return 0, ("http", e.code)
    except Exception as e:
        return 0, ("err", str(e))
def release_span(release_csv, wanted):
    rd = pd.read_csv(release_csv)
    rd = rd[rd["REPO"].isin(wanted)]
    rel = pd.to_datetime(rd["RELEASEDATE"], utc=True, errors="coerce")
    k8s = pd.to_datetime(rd["K8SFIRSTCOMMITDATE"], utc=True, errors="coerce")
    keep = rel.notna() & k8s.notna() & (rel >= k8s)
    months = rel[keep].dt.strftime("%Y-%m")
    if months.empty:
        return None, None
    return months.min(), months.max()

def resolve_summary_file():
    for p in SUMMARY_CANDIDATES:
        if os.path.isfile(p):
            return p
    return None
def total_pes(wanted):
    summary_file = resolve_summary_file()
    if not summary_file:
        print(f"(repo_summary.csv not found in {SUMMARY_CANDIDATES}; PEs = n/a)",
              flush=True)
        return None
    summ = pd.read_csv(summary_file)
    objc = [c for c in summ.columns if c.startswith("objcnt::")]
    if not objc:
        print(f"(no objcnt:: columns in {summary_file}; PEs = n/a)", flush=True)
        return None
    sub = summ[summ["repo"].isin(wanted)]
    matched = sub["repo"].nunique()
    if matched != len(wanted):
        print(f"(note: {matched}/{len(wanted)} cohort repos found in "
              f"{os.path.basename(summary_file)} for PEs)", flush=True)
    val = sub[objc].apply(pd.to_numeric, errors="coerce").fillna(0).values.sum()
    return int(val)
def fmt_span(m):
    return m.replace("-", "/") if m else "?"
def main():
    if not os.path.isdir(CLONED_REPOS):
        sys.exit(f"Clone dir not found: {CLONED_REPOS}")

    wanted = set(pd.read_csv(CADENCE_FILE)["REPO"])
    print(f"Repos in cadence CSV: {len(wanted)}", flush=True)

    repos = [(k, p) for (k, p) in list_repos(CLONED_REPOS) if k in wanted]
    print(f"Found on disk: {len(repos)}", flush=True)
    missing = wanted - {k for k, _ in repos}
    if missing:
        print(f"  (not found on disk: {len(missing)})", flush=True)

    total_commits = 0
    total_config_scripts = 0
    all_emails = set()
    g_min = g_max = None
    per_repo = {}

    for i, (key, path) in enumerate(repos, 1):
        try:
            c, emails, mn, mx = repo_git_stats(path)
        except Exception as e:
            print(f"  skip {key}: {e}", file=sys.stderr, flush=True)
            c, emails, mn, mx = 0, set(), None, None
        total_commits += c
        all_emails |= emails
        try:
            cfg = count_config_scripts(path)
        except Exception:
            cfg = 0
        total_config_scripts += cfg
        if mn and (g_min is None or mn < g_min):
            g_min = mn
        if mx and (g_max is None or mx > g_max):
            g_max = mx
        per_repo[key] = {"commits": c, "contributors": len(emails),
                         "first_month": mn, "last_month": mx, "stars": "",
                         "config_scripts": cfg}
        if i % 50 == 0:
            print(f"  git: {i}/{len(repos)}", flush=True)

    total_stars = None
    if FETCH_STARS:
        if not GITHUB_TOKEN:
            print("\nWARNING: GITHUB_TOKEN not set. Without a token the API allows "
                  "only ~60 calls/hour, not enough for 593 repos. Set GITHUB_TOKEN "
                  "in your terminal, or set FETCH_STARS=False.", flush=True)
        cache = load_cache()
        total_stars = 0
        for i, (key, _) in enumerate(repos, 1):
            if key in cache:
                stars = cache[key]
            else:
                while True:
                    stars, err = fetch_stars(key, GITHUB_TOKEN)
                    if err and err[0] == "ratelimit":
                        print(f"  rate limited; sleeping {err[1]}s...", flush=True)
                        time.sleep(err[1])
                        continue
                    break
                cache[key] = stars if stars is not None else 0
                if i % 25 == 0:
                    save_cache(cache)
                    print(f"  stars: {i}/{len(repos)}", flush=True)
            total_stars += cache[key]
            if key in per_repo:
                per_repo[key]["stars"] = cache[key]
        save_cache(cache)

    with open(OUT_PER_REPO, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["repo", "commits", "contributors", "first_month",
                    "last_month", "stars", "config_scripts"])
        for k in sorted(per_repo):
            d = per_repo[k]
            w.writerow([k, d["commits"], d["contributors"], d["first_month"],
                        d["last_month"], d["stars"], d["config_scripts"]])

    pes = total_pes(wanted)

    rmn = rmx = None
    try:
        rmn, rmx = release_span(RELEASE_DATA, wanted)
    except Exception as e:                                      # noqa: BLE001
        print(f"(could not read release dates for time span: {e})", flush=True)
    time_span = f"{fmt_span(rmn)}-{fmt_span(rmx)}"
    rows = [
        ("Total Repositories", len(repos)),
        ("Total Commits", total_commits),
        ("Total Contributors (Unique)", len(all_emails)),
        ("Total Count of Stars", total_stars),
        ("Total Count of PEs", pes),
        ("Total Count of Config. Scripts", total_config_scripts),
        ("Time Span", time_span),
    ]

    def disp(v):
        if v is None:
            return "(n/a)"
        return f"{v:,}" if isinstance(v, int) else str(v)

    print("\n================ Table II ================")
    width = max(len(a) for a, _ in rows)
    for attr, val in rows:
        print(f"{attr.ljust(width)} : {disp(val)}")
    print("==========================================")
    print(f"(commit-history span, for reference: "
          f"{fmt_span(g_min)}-{fmt_span(g_max)})")

    with open(OUT_TABLE_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Attribute", "Data"])
        for attr, val in rows:
            w.writerow([attr, "" if val is None else val])
    print(f"\nTable written to {OUT_TABLE_CSV}")

    try:
        out_df = pd.DataFrame(
            [(a, ("" if v is None else v)) for a, v in rows],
            columns=["Attribute", "Data"],
        )
        out_df.to_excel(OUT_TABLE_XLSX, index=False)
        print(f"Table written to {OUT_TABLE_XLSX}")
    except Exception as e:
        print(f"(could not write xlsx: {e})", flush=True)

    print(f"Per-repo detail written to {OUT_PER_REPO}")


if __name__ == "__main__":
    main()
