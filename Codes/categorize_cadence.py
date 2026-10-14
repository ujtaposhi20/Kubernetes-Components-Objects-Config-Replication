import pandas as pd

INPUT_CSV = "release_cadence_analysis.csv"
OUTPUT_CSV = "ReleaseDataCategorized_postK8Sdata.csv"

RAPID_PLUS_MAX = 7
RAPID_MAX = 30
MODERN_MAX = 90 


def cadence_group(days: float) -> str:
    if days < RAPID_PLUS_MAX:
        return "rapid+"
    if days < RAPID_MAX:
        return "rapid"
    if days < MODERN_MAX:
        return "modern"
    return "slow"


def main():
    df = pd.read_csv(INPUT_CSV)
    df["POSTK8SRELEASECADENCE"] = pd.to_numeric(
        df["POSTK8SRELEASECADENCE"], errors="coerce"
    )
    kept = df.dropna(subset=["POSTK8SRELEASECADENCE"]).copy()
    dropped = len(df) - len(kept)

    kept["CADENCEGROUP"] = kept["POSTK8SRELEASECADENCE"].apply(cadence_group)

    out = kept[["REPO", "POSTK8SRELEASECADENCE", "CADENCEGROUP"]]
    out = out.sort_values("REPO").reset_index(drop=True)
    out.to_csv(OUTPUT_CSV, index=False)

    print(f"Input rows:            {len(df)}")
    print(f"Dropped (no numeric post cadence): {dropped}")
    print(f"Categorized rows:      {len(out)}")
    print(f"  Saved: {OUTPUT_CSV}\n")
    print(out["CADENCEGROUP"].value_counts().to_string())


if __name__ == "__main__":
    main()
