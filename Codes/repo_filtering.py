import os
import sys
import json
import time
import datetime as dt
import requests
import pandas as pd

BASE_DIR     = os.environ.get("K8S_BASE_DIR", os.path.dirname(os.path.abspath(__file__)))
OUTPUT_XLSX  = os.path.join(BASE_DIR, "repo_filtering_criterion1to4.xlsx")
CACHE_JSON   = os.path.join(BASE_DIR, "_repo_crawl_cache.json")

BASE_QUERY   = "topic:kubernetes" 
PER_PAGE     = 100
PAGE_CAP     = 10
WINDOW_CAP   = 1000

MIN_STARS    = 0
INITIAL_WIN  = 4
MAX_WIN      = 100000

GITHUB_API   = "https://api.github.com/search/repositories"
TIMEOUT      = 30

TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()
HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}
if TOKEN:
    HEADERS["Authorization"] = f"Bearer {TOKEN}"

SESSION = requests.Session()
SESSION.headers.update(HEADERS)

def gh_get(params, max_retries=8):
    """One Search API call with retry + rate-limit / secondary-limit handling."""
    for attempt in range(max_retries):
        try:
            r = SESSION.get(GITHUB_API, params=params, timeout=TIMEOUT)
        except requests.RequestException as e:
            wait = min(60, 2 ** attempt)
            print(f"  network error ({e}); retrying in {wait}s", flush=True)
            time.sleep(wait)
            continue

        if r.status_code == 200:
            remaining = int(r.headers.get("X-RateLimit-Remaining", "1"))
            if remaining <= 1:
                reset = int(r.headers.get("X-RateLimit-Reset", "0"))
                wait = max(1, reset - int(time.time()) + 2)
                print(f"  search quota exhausted; sleeping {wait}s", flush=True)
                time.sleep(wait)
            return r.json()

        if r.status_code in (403, 429):
            retry_after = r.headers.get("Retry-After")
            if retry_after:
                wait = int(retry_after) + 1
            else:
                reset = int(r.headers.get("X-RateLimit-Reset", "0"))
                wait = max(5, reset - int(time.time()) + 2)
            print(f"  rate-limited (HTTP {r.status_code}); sleeping {wait}s", flush=True)
            time.sleep(wait)
            continue

        if r.status_code >= 500:
            wait = min(60, 2 ** attempt)
            print(f"  server error {r.status_code}; retrying in {wait}s", flush=True)
            time.sleep(wait)
            continue
        raise RuntimeError(f"GitHub API {r.status_code}: {r.text[:300]}")

    raise RuntimeError("Exceeded max retries on GitHub Search API")


def search_count(query):
    """total_count for a query (uses a 1-result probe page)."""
    data = gh_get({"q": query, "per_page": 1, "sort": "stars", "order": "asc"})
    return data.get("total_count", 0)


def fetch_window(lo, hi):
    """Page through one star window (<=1000 hits) and yield raw repo items."""
    span = f"{lo}..{hi}" if hi is not None else f">={lo}"
    query = f"{BASE_QUERY} stars:{span}"
    items = []
    for page in range(1, PAGE_CAP + 1):
        data = gh_get({
            "q": query, "per_page": PER_PAGE, "page": page,
            "sort": "stars", "order": "asc",
        })
        batch = data.get("items", [])
        items.extend(batch)
        if len(batch) < PER_PAGE:
            break
    return items

def load_cache():
    if os.path.exists(CACHE_JSON):
        try:
            with open(CACHE_JSON, "r", encoding="utf-8") as f:
                c = json.load(f)
            print(f"Resuming: {len(c['repos'])} repos cached, next lo={c['next_lo']}")
            return c
        except Exception as e:
            print(f"  cache unreadable ({e}); starting fresh")
    return {"repos": {}, "next_lo": MIN_STARS}


def save_cache(cache):
    tmp = CACHE_JSON + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f)
    os.replace(tmp, CACHE_JSON)


def crawl():
    cache = load_cache()
    repos = cache["repos"]
    lo = cache["next_lo"]
    window = INITIAL_WIN

    while True: 
        if search_count(f"{BASE_QUERY} stars:>={lo}") == 0:
            print(f"No repos with stars >= {lo}; crawl complete.")
            break

        hi = lo + window
        total = search_count(f"{BASE_QUERY} stars:{lo}..{hi}")

        if total > WINDOW_CAP:
            if window == 0:
                print(f"  WARN: stars=={lo} has {total} repos (>1000); "
                      f"capturing first {WINDOW_CAP}")
                for it in fetch_window(lo, lo):
                    repos[str(it["id"])] = it
                lo += 1
                window = INITIAL_WIN
            else:
                window = max(0, window // 2)
            continue
        got = fetch_window(lo, hi)
        for it in got:
            repos[str(it["id"])] = it
        print(f"  stars {lo}..{hi}: total={total}, fetched={len(got)}, "
              f"unique so far={len(repos)}", flush=True)

        lo = hi + 1
        cache["next_lo"] = lo
        save_cache(cache)

        if total < WINDOW_CAP // 4:
            window = min(MAX_WIN, max(1, window * 2))
        elif total > (WINDOW_CAP * 3) // 4:
            window = max(1, window // 2)

    return list(repos.values())

COLUMNS = [
    "id", "full_name", "html_url", "description", "language",
    "stargazers_count", "forks_count", "open_issues_count", "watchers_count",
    "created_at", "pushed_at", "archived", "has_issues", "license", "topics",
    "duration_days", "commit_activity_positive", "age_days",
]


def _parse_dt(s):
    if not s:
        return None
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def normalise(items, now):
    rows = []
    for it in items:
        created = _parse_dt(it.get("created_at"))
        pushed  = _parse_dt(it.get("pushed_at"))
        duration_days = (pushed - created).days if (created and pushed) else None
        age_days      = (now - created).days if created else None
        commit_pos = (
            (now - pushed).days <= 30 if pushed else False
        )
        lic = it.get("license") or {}
        rows.append({
            "id": it.get("id"),
            "full_name": it.get("full_name"),
            "html_url": it.get("html_url"),
            "description": it.get("description"),
            "language": it.get("language"),
            "stargazers_count": it.get("stargazers_count"),
            "forks_count": it.get("forks_count"),
            "open_issues_count": it.get("open_issues_count"),
            "watchers_count": it.get("watchers_count"),
            "created_at": created.isoformat(sep=" ") if created else None,
            "pushed_at": pushed.isoformat(sep=" ") if pushed else None,
            "archived": bool(it.get("archived", False)),
            "has_issues": bool(it.get("has_issues", False)),
            "license": lic.get("spdx_id"),
            "topics": ";".join(it.get("topics", []) or []),
            "duration_days": duration_days,
            "commit_activity_positive": commit_pos,
            "age_days": age_days,
            "_private": bool(it.get("private", False)), 
        })
    df = pd.DataFrame(rows)
    df = df.drop_duplicates(subset=["id"]).reset_index(drop=True)
    return df

def build_workbook(df):
    all_dedup = df[COLUMNS].copy()

    c1 = df[~df["_private"]] 
    c2 = c1[~c1["archived"]] 
    c3 = c2[c2["open_issues_count"] > 10]
    c4 = c3[c3["duration_days"] > 365]

    sheets = {
        "all_k8s_repos_dedup": all_dedup,
        "is-public":           c1[COLUMNS].copy(),
        "not-archived":        c2[COLUMNS].copy(),
        "issues-more-than-10": c3[COLUMNS].copy(),
        "duration>365days":    c4[COLUMNS].copy(),
    }

    with pd.ExcelWriter(OUTPUT_XLSX, engine="openpyxl") as xw:
        for name, sheet in sheets.items():
            sheet.to_excel(xw, sheet_name=name, index=False)

    print("\nWrote", OUTPUT_XLSX)
    for name, sheet in sheets.items():
        print(f"  {name:<22} {len(sheet):>6} rows")
    return sheets

def main():
    if not TOKEN:
        print("WARNING: GITHUB_TOKEN not set. Unauthenticated search is limited "
              "to 10 req/min and will be very slow / may fail. "
              "Set it with:  setx GITHUB_TOKEN <your_token>", file=sys.stderr)

    now = dt.datetime.now(dt.timezone.utc)
    print(f"Collection time (now): {now.isoformat()}")
    print(f"Population query: {BASE_QUERY}\n")

    raw_items = crawl()
    print(f"\nCrawl finished: {len(raw_items)} raw repos")

    df = normalise(raw_items, now)
    print(f"After dedup: {len(df)} repos")

    build_workbook(df)


if __name__ == "__main__":
    main()
