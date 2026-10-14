import argparse, csv, os, re, sys, time, json, asyncio, pathlib, shutil
from typing import List, Dict, Optional, Tuple


POSSIBLE_COLS = [
    "clone_url","https_url","html_url","repo_url","url",
    "ssh_url","git_url","git","remote",
    "full_name","name_with_owner","repo","repository","path"
]

def sanitize_repo_dir(name: str) -> str:
    name = name.strip().strip("/").replace("\\","/").replace(" ", "_")
    # keep owner/repo path structure for tidy folders
    name = re.sub(r"[^A-Za-z0-9._/\-]", "_", name)
    return name

def to_owner_repo(s: str) -> Optional[str]:
    s = s.strip()
    if not s:
        return None
    # SSH form
    m = re.match(r"^git@github\.com:([^/\s]+)/([^/\s]+?)(?:\.git)?$", s, re.I)
    if m:
        return f"{m.group(1)}/{m.group(2)}"

    # HTTPS with github.com
    m = re.search(r"github\.com/([^/\s]+)/([^/\s]+?)(?:\.git)?(?:[/?#].*)?$", s, re.I)
    if m:
        return f"{m.group(1)}/{m.group(2)}"

    # Plain owner/repo
    m = re.match(r"^([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)$", s)
    if m:
        return f"{m.group(1)}/{m.group(2)}"

    return None

def ensure_https_git_url(s: str) -> Optional[str]:
    orp = to_owner_repo(s)
    if not orp:
        return None
    return f"https://github.com/{orp}.git"

def detect_column(header: List[str]) -> Optional[str]:
    lower = [h.strip().lower() for h in header]
    for cand in POSSIBLE_COLS:
        if cand in lower:
            return header[lower.index(cand)]
    return None

def make_dest(root: pathlib.Path, owner_repo: str) -> pathlib.Path:
    safe = sanitize_repo_dir(owner_repo)
    return root / safe

def is_git_repo(p: pathlib.Path) -> bool:
    return (p / ".git").exists()

def tail_text(s: str, n: int = 1200) -> str:
    s = s or ""
    return s[-n:]

def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())

async def run_git(cmd: List[str], cwd: Optional[pathlib.Path]=None, env: Optional[Dict[str,str]]=None, timeout: int = 0) -> Tuple[int, str, str]:
 
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(cwd) if cwd else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    try:
        if timeout and timeout > 0:
            stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        else:
            stdout_b, stderr_b = await proc.communicate()
    except asyncio.TimeoutError:
        proc.kill()
        return 124, "", f"Timeout after {timeout}s"
    rc = proc.returncode
    out = stdout_b.decode(errors="ignore")
    err = stderr_b.decode(errors="ignore")
    return rc, out, err

def git_base_config(token: Optional[str]) -> List[str]:
    base = ["git", "-c", "core.longpaths=true"]
    # Use header auth for private/ratelimited pulls (not saved to config)
    if token:
        # Note: value must not include extra quotes
        base += ["-c", f"http.extraheader=AUTHORIZATION: bearer {token}"]
    # Be resilient to slow networks
    base += ["-c", "http.lowSpeedLimit=1000", "-c", "http.lowSpeedTime=30"]
    return base

async def clone_repo(url: str, dest: pathlib.Path, token: Optional[str], retries: int = 2) -> Tuple[bool, str, str, int]:
    """
    Full clone with working tree, tags, and all refs on default remote.
    Retries on transient failures.
    """
    attempt = 0
    while True:
        attempt += 1
        dest.parent.mkdir(parents=True, exist_ok=True)
        cmd = git_base_config(token) + [
            "clone",
            "--recursive",
            "--no-single-branch",  
            "--progress",
            url,
            str(dest)
        ]
        t0 = time.time()
        rc, out, err = await run_git(cmd)
        dur = time.time() - t0
        if rc == 0 and is_git_repo(dest):
            # Fetch tags/cleanup just in case
            fcmd = git_base_config(token) + ["-C", str(dest), "fetch", "--all", "--tags", "--prune"]
            await run_git(fcmd)
            return True, out, err, attempt
        if attempt > retries:
            return False, out, err, attempt
        # backoff
        await asyncio.sleep(min(6 * attempt, 20))

async def update_repo(dest: pathlib.Path, url: str, token: Optional[str]) -> Tuple[bool, str, str]:
    seturl = git_base_config(token) + ["-C", str(dest), "remote", "set-url", "origin", url]
    await run_git(seturl)
    # Fetch everything
    fcmd = git_base_config(token) + ["-C", str(dest), "fetch", "--all", "--tags", "--prune"]
    rc, out, err = await run_git(fcmd)
    if rc == 0:
        return True, out, err
    return False, out, err

def load_targets(csv_path: pathlib.Path, column_override: Optional[str]) -> List[Dict[str,str]]:
    with csv_path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames or []
        if not header:
            print(f"[error] CSV has no header: {csv_path}")
            sys.exit(1)
        col = column_override or detect_column(header)
        if not col:
            print(f"[error] Could not detect URL/owner column. Provide --col explicitly. Columns = {header}")
            sys.exit(1)
        rows = list(reader)

    out: List[Dict[str,str]] = []
    for r in rows:
        raw = (r.get(col) or "").strip()
        if not raw:
            continue
        url = ensure_https_git_url(raw)
        if not url:
            for k,v in r.items():
                if v and "github.com" in v:
                    url = ensure_https_git_url(v)
                    if url: break
        if not url:
            # Skip bad lines, but note them
            out.append({"name": "", "url": "", "bad": raw})
            continue
        name = to_owner_repo(url)  
        out.append({"name": name, "url": url})
    return out

def unique_repos(recs: List[Dict[str,str]]) -> List[Dict[str,str]]:
    seen = set()
    uniq = []
    for r in recs:
        name = r.get("name") or ""
        url = r.get("url") or ""
        if not name or not url:
            continue
        if name not in seen:
            seen.add(name)
            uniq.append(r)
    return uniq
async def process_all(targets: List[Dict[str,str]], out_root: pathlib.Path, concurrency: int, token: Optional[str],
                      log_path: pathlib.Path, success_csv: pathlib.Path, fail_csv: pathlib.Path):
    sem = asyncio.Semaphore(concurrency)
    out_root.mkdir(parents=True, exist_ok=True)
    log_f = log_path.open("a", encoding="utf-8")

    results = {"cloned":0, "updated":0, "skipped":0, "errors":0, "exists_non_git":0}
    successes: List[Dict[str,str]] = []
    failures: List[Dict[str,str]] = []

    async def handle_one(idx: int, total: int, rec: Dict[str,str]):
        nonlocal results
        name = rec["name"]
        url  = rec["url"]
        dest = make_dest(out_root, name)
        started = time.time()

        async with sem:
            entry = {
                "ts": now_iso(), "name": name, "url": url, "dest": str(dest),
                "action": "", "status": "", "rc": None, "dur_s": None,
                "stdout_tail": "", "stderr_tail": "", "attempts": 0
            }
            try:
                if dest.exists():
                    if is_git_repo(dest):
                        ok, out, err = await update_repo(dest, url, token)
                        entry.update({
                            "action": "update",
                            "status": "ok" if ok else "error",
                            "rc": 0 if ok else 1,
                            "dur_s": round(time.time()-started, 2),
                            "stdout_tail": tail_text(out),
                            "stderr_tail": tail_text(err)
                        })
                        if ok:
                            results["updated"] += 1
                            successes.append({"name": name, "url": url, "dest": str(dest), "status": "updated"})
                        else:
                            results["errors"] += 1
                            failures.append({"name": name, "url": url, "reason": "fetch_failed", "stderr": tail_text(err)})
                    else:
                        # existing non-git folder — move aside and clone fresh
                        results["exists_non_git"] += 1
                        moved = dest.parent / (dest.name + f"__nongit_{int(time.time())}")
                        dest.rename(moved)
                        ok, out, err, attempts = await clone_repo(url, dest, token)
                        entry.update({
                            "action": "clone(nongit_replaced)",
                            "status": "ok" if ok else "error",
                            "rc": 0 if ok else 1,
                            "dur_s": round(time.time()-started, 2),
                            "stdout_tail": tail_text(out),
                            "stderr_tail": tail_text(err),
                            "attempts": attempts
                        })
                        if ok:
                            results["cloned"] += 1
                            successes.append({"name": name, "url": url, "dest": str(dest), "status": "cloned"})
                        else:
                            results["errors"] += 1
                            failures.append({"name": name, "url": url, "reason": "clone_failed", "stderr": tail_text(err)})
                else:
                    ok, out, err, attempts = await clone_repo(url, dest, token)
                    entry.update({
                        "action": "clone",
                        "status": "ok" if ok else "error",
                        "rc": 0 if ok else 1,
                        "dur_s": round(time.time()-started, 2),
                        "stdout_tail": tail_text(out),
                        "stderr_tail": tail_text(err),
                        "attempts": attempts
                    })
                    if ok:
                        results["cloned"] += 1
                        successes.append({"name": name, "url": url, "dest": str(dest), "status": "cloned"})
                    else:
                        results["errors"] += 1
                        failures.append({"name": name, "url": url, "reason": "clone_failed", "stderr": tail_text(err)})
            except Exception as e:
                entry.update({
                    "action": entry.get("action") or "unknown",
                    "status": "exception",
                    "rc": 2,
                    "dur_s": round(time.time()-started, 2),
                    "stderr_tail": f"{type(e).__name__}: {e}"
                })
                results["errors"] += 1
                failures.append({"name": name, "url": url, "reason": "exception", "stderr": f"{type(e).__name__}: {e}"})
            finally:
                log_f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                log_f.flush()
                done = results["cloned"] + results["updated"] + results["errors"]
                print(f"[progress] {done}/{total}  last={name}  action={entry['action']}  status={entry['status']}")

    tasks = [asyncio.create_task(handle_one(i+1, len(targets), rec)) for i,rec in enumerate(targets)]
    await asyncio.gather(*tasks)
    log_f.close()

    # Write success/fail CSVs
    def write_csv(path: pathlib.Path, rows: List[Dict[str,str]], header: List[str]):
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=header)
            w.writeheader()
            for r in rows:
                w.writerow({k: r.get(k,"") for k in header})

    write_csv(success_csv, successes, ["name","url","dest","status"])
    write_csv(fail_csv, failures, ["name","url","reason","stderr"])
    return results

def main():
    ap = argparse.ArgumentParser(description="Clone/update GitHub repos from CSV into a folder (full working copies).")
    ap.add_argument("--csv", required=True, help="Path to CSV (e.g., filtered_repos_final.csv or failed_repos.csv)")
    ap.add_argument("--out", required=True, help="Output folder for cloned repos")
    ap.add_argument("--concurrency", type=int, default=8, help="Parallel clones/updates (default 8)")
    ap.add_argument("--col", default=None, help="Explicit column name containing repo URLs or owner/repo")
    ap.add_argument("--retries", type=int, default=2, help="Retries per repo on failure (default 2)")
    args = ap.parse_args()

    csv_path = pathlib.Path(args.csv).expanduser().resolve()
    out_root = pathlib.Path(args.out).expanduser().resolve()
    out_root.mkdir(parents=True, exist_ok=True)
    token = os.environ.get("GITHUB_TOKEN", "").strip() or None
    if token:
        print("[info] Using GITHUB_TOKEN from environment (sent as HTTP header; not saved to disk).")
    else:
        print("[info] No GITHUB_TOKEN found. Public repos will clone; private might fail or be slower.")

    records = load_targets(csv_path, args.col)
    bad = [r for r in records if not r.get("url")]
    uniq = unique_repos([r for r in records if r.get("url")])
    total_csv = len(records)
    total_uniq = len(uniq)
    total_bad = len(bad)

    print(f"[info] CSV rows read:       {total_csv}")
    print(f"[info] Unique valid repos:  {total_uniq}")
    print(f"[info] Unusable rows:       {total_bad}")
    if total_bad:
        bad_path = out_root / "bad_rows.jsonl"
        with bad_path.open("w", encoding="utf-8") as bf:
            for b in bad:
                bf.write(json.dumps(b, ensure_ascii=False)+"\n")
        print(f"[info] Wrote bad rows (no valid repo) to: {bad_path}")
    log_path = out_root / "clone_log.jsonl"
    success_csv = out_root / "success_repos.csv"
    fail_csv = out_root / "failed_repos.csv"

    t0 = time.time()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    results = loop.run_until_complete(
        process_all(uniq, out_root, args.concurrency, token, log_path, success_csv, fail_csv)
    )
    dur = time.time() - t0

    git_dirs = 0
    for r in uniq:
        dest = make_dest(out_root, r["name"])
        if is_git_repo(dest):
            git_dirs += 1

    summary = {
        "csv_rows": total_csv,
        "unique_repos": total_uniq,
        "bad_rows": total_bad,
        "cloned": results["cloned"],
        "updated": results["updated"],
        "errors": results["errors"],
        "exists_non_git": results["exists_non_git"],
        "git_dirs_present": git_dirs,
        "duration_sec": round(dur, 2),
        "out_root": str(out_root),
        "completed_at": now_iso()
    }
    summ_path = out_root / "summary.json"
    with summ_path.open("w", encoding="utf-8") as sf:
        json.dump(summary, sf, indent=2)
    print("\n===== SUMMARY =====")
    for k,v in summary.items():
        print(f"{k:>20}: {v}")
    print("===================\n")
    if summary["unique_repos"] == summary["git_dirs_present"]:
        print("[OK] Perfect match: every unique repo has a .git working copy.")
    else:
        print("[WARN] Some repos missing .git. See failed_repos.csv and clone_log.jsonl.")

if __name__ == "__main__":
    main()
