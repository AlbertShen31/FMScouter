#!/usr/bin/env python3
"""Generate Romania player population reports across tiers and yearly snapshots.

Standalone::

    .venv/bin/python scripts/generate_romania_tier_reports.py \\
        --input-dir "scripts/exports/YR 100" \\
        --output-dir "scripts/exports/YR 100/reports"

After a fresh export from load_fmsave_frames::

    .venv/bin/python scripts/run_romania_tier_pipeline.py \\
        -n 164 --export-names "scripts/exports/YR 100/100yr_romania_year.csv"
"""
from pathlib import Path
import argparse
import pandas as pd

TIERS = (100, 120, 130, 140)
YEARS = range(1, 11)
UNASSIGNED = "(Unassigned)"


def resolve_year_csv(input_dir: Path, tier: int, year: int) -> Path:
    """Resolve YR-60 (`tier100_romania_year_1.csv`) or tagged (`tier100_100yr_romania_year_1.csv`) names."""
    plain = input_dir / f"tier{tier}_romania_year_{year}.csv"
    if plain.exists():
        return plain
    matches = sorted(input_dir.glob(f"tier{tier}_*_romania_year_{year}.csv"))
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        names = ", ".join(p.name for p in matches)
        raise FileNotFoundError(
            f"Ambiguous input for tier {tier} year {year} in {input_dir}: {names}"
        )
    raise FileNotFoundError(
        f"Missing input for tier {tier} year {year} in {input_dir} "
        f"(expected tier{tier}_romania_year_{year}.csv or tier{tier}_*_romania_year_{year}.csv)"
    )


def generate(input_dir: Path, output_dir: Path, tiers=TIERS):
    output_dir.mkdir(parents=True, exist_ok=True)
    count_rows, id_rows, nation_rows = [], [], []

    for tier in tiers:
        yearly = {}
        for year in YEARS:
            path = resolve_year_csv(input_dir, tier, year)
            df = pd.read_csv(path, dtype={"uid": "string"})
            for column in ("uid", "competition_nation"):
                if column not in df.columns:
                    raise ValueError(f"Missing '{column}' in {path}")
            if df["uid"].isna().any() or df["uid"].duplicated().any():
                raise ValueError(f"Missing or duplicated uid in {path}")
            df["competition_nation"] = df["competition_nation"].fillna(UNASSIGNED)
            df.loc[df["competition_nation"].astype(str).str.strip() == "", "competition_nation"] = UNASSIGNED
            yearly[year] = df

        nations = sorted(set().union(*(set(df["competition_nation"]) for df in yearly.values())))
        for nation in nations:
            row = {"Tier": tier, "Competition nation": nation}
            for year in YEARS:
                row[f"Year {year}"] = int((yearly[year]["competition_nation"] == nation).sum())
            row["Change Y1-Y10"] = row["Year 10"] - row["Year 1"]
            count_rows.append(row)

        previous_ids = None
        previous_nation_ids = None
        for year, df in yearly.items():
            ids = set(df["uid"])
            nation_ids = {nation: set(group["uid"]) for nation, group in df.groupby("competition_nation")}
            id_rows.append({
                "Tier": tier, "Year": year, "Total IDs": len(ids),
                "Added IDs": len(ids - previous_ids) if previous_ids is not None else None,
                "Removed IDs": len(previous_ids - ids) if previous_ids is not None else None,
                "Net change": len(ids) - len(previous_ids) if previous_ids is not None else None,
                "Retained IDs": len(ids & previous_ids) if previous_ids is not None else None,
            })
            for nation in sorted(set(nation_ids) | (set(previous_nation_ids) if previous_nation_ids is not None else set())):
                current = nation_ids.get(nation, set())
                prior = previous_nation_ids.get(nation, set()) if previous_nation_ids is not None else None
                nation_rows.append({
                    "Tier": tier, "Competition nation": nation, "Year": year,
                    "Total": len(current),
                    "Added in nation": len(current - prior) if prior is not None else None,
                    "Removed from nation": len(prior - current) if prior is not None else None,
                    "Net change": len(current) - len(prior) if prior is not None else None,
                })
            previous_ids, previous_nation_ids = ids, nation_ids

    outputs = {
        "romania_tier_competition_nation_counts.csv": pd.DataFrame(count_rows),
        "romania_tier_player_id_changes.csv": pd.DataFrame(id_rows),
        "romania_tier_nation_id_changes.csv": pd.DataFrame(nation_rows),
    }
    for name, df in outputs.items():
        df.to_csv(output_dir / name, index=False)
        print(f"Saved {output_dir / name}: {len(df)} rows")
    return outputs


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=Path("."))
    parser.add_argument("--output-dir", type=Path, default=Path("."))
    parser.add_argument("--tiers", type=int, nargs="+", default=list(TIERS))
    args = parser.parse_args()
    generate(args.input_dir, args.output_dir, args.tiers)
