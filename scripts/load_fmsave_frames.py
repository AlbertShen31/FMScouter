#!/usr/bin/env python3
"""Open FM saves with fmsave and count players by nation × CA/PA tier.

Fill in SAVES, then run::

    .venv/bin/python scripts/load_fmsave_frames.py
    .venv/bin/python scripts/load_fmsave_frames.py -n 164
    .venv/bin/python scripts/load_fmsave_frames.py -n 164 173 55
"""

from __future__ import annotations

import argparse
from pathlib import Path

import fmsave
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
COMPETITION_NAMES = ROOT / "data" / "competition-names.csv"

# Known FM nation ids → labels (pass any int via -n; unknown ids print as the number).
KNOWN_NATIONS: dict[int, str] = {
    164: "Romania",
    173: "Türkiye",
    152: "Liechtenstein",
    55: "China",
}
TIERS = (100, 120, 130, 140)

# Fill these in yourself (absolute paths or ~/… to .fm files).
SAVES = [
    "/Users/albertwshen/Library/Application Support/Sports Interactive/Football Manager 26/games/Romania Test Year 1 End.fm",
    "/Users/albertwshen/Library/Application Support/Sports Interactive/Football Manager 26/games/Romania Test Year 1 End (v02).fm",
    "/Users/albertwshen/Library/Application Support/Sports Interactive/Football Manager 26/games/Romania Test Year 1 End (v03).fm",
    "/Users/albertwshen/Library/Application Support/Sports Interactive/Football Manager 26/games/Romania Test Year 1 End (v04).fm",
    "/Users/albertwshen/Library/Application Support/Sports Interactive/Football Manager 26/games/Romania Test Year 1 End (v05).fm",
    "/Users/albertwshen/Library/Application Support/Sports Interactive/Football Manager 26/games/Romania Test Year 1 End (v06).fm",
    "/Users/albertwshen/Library/Application Support/Sports Interactive/Football Manager 26/games/Romania Test Year 1 End (v07).fm",
    "/Users/albertwshen/Library/Application Support/Sports Interactive/Football Manager 26/games/Romania Test Year 1 End (v08).fm",
    "/Users/albertwshen/Library/Application Support/Sports Interactive/Football Manager 26/games/Romania Test Year 1 End (v09).fm",
    "/Users/albertwshen/Library/Application Support/Sports Interactive/Football Manager 26/games/Romania Test.fm",
]


def parse_args() -> argparse.Namespace:
    known = ", ".join(f"{nid}={name}" for nid, name in KNOWN_NATIONS.items())
    parser = argparse.ArgumentParser(
        description="Count CA/PA tiers for players of selected nation id(s)."
    )
    parser.add_argument(
        "-n",
        "--nation",
        type=int,
        nargs="+",
        dest="nations",
        metavar="ID",
        help=f"Nation id(s) to include (default: all known). Known: {known}",
    )
    return parser.parse_args()


def resolve_nations(ids: list[int] | None) -> dict[int, str]:
    selected = ids if ids else list(KNOWN_NATIONS)
    return {nid: KNOWN_NATIONS.get(nid, str(nid)) for nid in selected}


def player_nation_ids(player) -> set[int]:
    ids: set[int] = set()
    if player.nation_id is not None:
        ids.add(int(player.nation_id))
    ids.update(int(x) for x in (player.second_nation_ids or ()))
    return ids


def drop_duplicate_players(df: pd.DataFrame) -> pd.DataFrame:
    """Keep one row per player (team-slot duplicates share name + unique_id)."""
    if "unique_id" in df.columns:
        subset = ["unique_id"]
    elif "uid" in df.columns:
        subset = ["uid"]
    else:
        subset = ["name"]
    if "name" in df.columns and subset != ["name"]:
        subset = ["name", *subset]
    return df.drop_duplicates(subset=subset, keep="first")


def nation_mask(df: pd.DataFrame, nation_id: int) -> pd.Series:
    """True when primary or second nationality matches ``nation_id``."""
    primary = pd.to_numeric(df.get("nation_id"), errors="coerce") == nation_id
    seconds = df.get("second_nation_ids")
    if seconds is None:
        return primary
    second = seconds.map(
        lambda ids: nation_id in ids if ids is not None else False
    )
    return primary | second


def tier_counts(df: pd.DataFrame) -> dict[str, int]:
    """Counts where CA or PA is at/above each tier."""
    ca = pd.to_numeric(df.get("ability_current"), errors="coerce")
    pa = pd.to_numeric(df.get("ability_potential"), errors="coerce")
    out = {"players": int(len(df))}
    for tier in TIERS:
        out[f"CA|PA>={tier}"] = int(((ca >= tier) | (pa >= tier)).sum())
    return out


def main() -> None:
    args = parse_args()
    nations = resolve_nations(args.nations)
    target_ids = frozenset(nations)

    print("Nations:", ", ".join(f"{name} ({nid})" for nid, name in nations.items()))

    frames: dict[str, pd.DataFrame] = {}
    rows: list[dict[str, object]] = []

    for save_path in SAVES[::-1]:
        path = Path(save_path).expanduser()
        label = path.stem
        print(f"Opening {path}…")
        with fmsave.open(
            path,
            competition_names=COMPETITION_NAMES if COMPETITION_NAMES.is_file() else None,
        ) as save:
            df = (
                save.players()
                .filter(lambda p: bool(player_nation_ids(p) & target_ids))
                .to_pandas()
            )
        before = len(df)
        # df = drop_duplicate_players(df)
        frames[label] = df
        # print(f"  {label}: {len(df)} target players (dropped {before - len(df)} dupes)")
        for nation_id, nation_name in nations.items():
            sub = df.loc[nation_mask(df, nation_id)]
            counts = tier_counts(sub)
            rows.append({"save": label, "nation": nation_name, **counts})
            print(f"    {nation_name}: {counts['players']}")
            # for tier in TIERS:
            #     print(f"      >={tier}: CA|PA={counts[f'CA|PA>={tier}']}")

    summary = pd.DataFrame(rows)
    print("\nSummary")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
