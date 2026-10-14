import pandas as pd
INPUT_CSV = "release_data.csv"
OUTPUT_CSV = "release_cadence_analysis.csv"
SUMMARY_CSV = "release_cadence_summary.csv"
MIN_POST_K8S_RELEASES = 2
NAA_OVERALL = "NAA"
NAA_PRE = "NAA_Pre"
NAA_POST = "NAA_Post"

def avg_cadence(dates):
    dates = sorted(dates)
    if len(dates) < 2:
        return None
    gaps = [(dates[i + 1] - dates[i]).total_seconds() / 86400.0
            for i in range(len(dates) - 1)]
    return round(sum(gaps) / len(gaps), 2)
def post_k8s_release_count(dates, k8s):
    if k8s is None or pd.isna(k8s):
        return 0
    return sum(1 for d in dates if d >= k8s)
def main():
    df = pd.read_csv(INPUT_CSV)
    df["RDATE"] = pd.to_datetime(df["RELEASEDATE"], utc=True, errors="coerce")
    df["K8SDT"] = pd.to_datetime(df["K8SFIRSTCOMMITDATE"], utc=True, errors="coerce")
    releases_by_repo = (
        df.dropna(subset=["RDATE"]).groupby("REPO")["RDATE"].apply(list)
    )
    k8s_by_repo = (
        df.dropna(subset=["K8SDT"]).groupby("REPO")["K8SDT"].first()
    )
    candidate_repos = sorted(releases_by_repo.index)
    all_repos = []
    dropped = 0
    for repo in candidate_repos:
        dates = releases_by_repo.get(repo, [])
        k8s = k8s_by_repo.get(repo, None)
        if post_k8s_release_count(dates, k8s) > MIN_POST_K8S_RELEASES:
            all_repos.append(repo)
        else:
            dropped += 1

    rows = []
    c = {"overall_actual": 0, "overall_naa": 0,
         "post_actual": 0, "post_naa": 0,
         "pre_actual": 0, "pre_naa": 0}

    for repo in all_repos:
        dates = releases_by_repo.get(repo, [])
        k8s = k8s_by_repo.get(repo, None)
        overall_val = avg_cadence(dates)
        if overall_val is None:
            overall = NAA_OVERALL
            c["overall_naa"] += 1
        else:
            overall = overall_val
            c["overall_actual"] += 1
        if k8s is None or pd.isna(k8s):
            post = NAA_POST
            pre = NAA_PRE
            c["post_naa"] += 1
            c["pre_naa"] += 1
        else:
            post_val = avg_cadence([d for d in dates if d >= k8s])
            pre_val = avg_cadence([d for d in dates if d < k8s])

            if post_val is None:
                post = NAA_POST
                c["post_naa"] += 1
            else:
                post = post_val
                c["post_actual"] += 1

            if pre_val is None:
                pre = NAA_PRE
                c["pre_naa"] += 1
            else:
                pre = pre_val
                c["pre_actual"] += 1

        rows.append({
            "REPO": repo,
            "OVERALLRELEASECADENCE": overall,
            "POSTK8SRELEASECADENCE": post,
            "PREK8SRELEASECADENCE": pre,
            "LANG": "",  
        })

    out = pd.DataFrame(rows, columns=[
        "REPO", "OVERALLRELEASECADENCE", "POSTK8SRELEASECADENCE",
        "PREK8SRELEASECADENCE", "LANG",
    ])
    out.to_csv(OUTPUT_CSV, index=False)
    total = len(out)

    def pct(n):
        return round(100.0 * n / total, 2) if total else 0.0

    summary = pd.DataFrame([
        {"COLUMN": "OVERALLRELEASECADENCE",
         "ACTUAL_COUNT": c["overall_actual"], "ACTUAL_PCT": pct(c["overall_actual"]),
         "NA_LABEL": NAA_OVERALL,
         "NA_COUNT": c["overall_naa"], "NA_PCT": pct(c["overall_naa"])},
        {"COLUMN": "POSTK8SRELEASECADENCE",
         "ACTUAL_COUNT": c["post_actual"], "ACTUAL_PCT": pct(c["post_actual"]),
         "NA_LABEL": NAA_POST,
         "NA_COUNT": c["post_naa"], "NA_PCT": pct(c["post_naa"])},
        {"COLUMN": "PREK8SRELEASECADENCE",
         "ACTUAL_COUNT": c["pre_actual"], "ACTUAL_PCT": pct(c["pre_actual"]),
         "NA_LABEL": NAA_PRE,
         "NA_COUNT": c["pre_naa"], "NA_PCT": pct(c["pre_naa"])},
    ], columns=["COLUMN", "ACTUAL_COUNT", "ACTUAL_PCT",
                "NA_LABEL", "NA_COUNT", "NA_PCT"])
    summary.to_csv(SUMMARY_CSV, index=False)
    print(f"Candidate repos (>= 1 release): {len(candidate_repos)}")
    print(f"Dropped (<= {MIN_POST_K8S_RELEASES} post-K8S releases): {dropped}")
    print(f"Total repos written (criterion 5, > {MIN_POST_K8S_RELEASES} post-K8S): {total}")
    print(f"  Saved: {OUTPUT_CSV}")
    print(f"  Saved: {SUMMARY_CSV}\n")
    print(summary.to_string(index=False))
    if c["overall_naa"] or c["post_naa"]:
        print("\n[warn] Unexpected NAA in OVERALL/POST after criterion 5 - "
              "investigate; this should be 0.")


if __name__ == "__main__":
    main()
