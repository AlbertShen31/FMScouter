#!/usr/bin/env python3
"""Open FM saves with fmsave and count players by nation × CA/PA tier.

Fill in SAVES, then run::

    .venv/bin/python scripts/load_fmsave_frames.py
"""

from pathlib import Path

import fmsave
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
COMPETITION_NAMES = ROOT / "data" / "competition-names.csv"

# FM nation ids (club/player nationality; see services/fmsave_export.py + save probe).
NATIONS: dict[int, str] = {
    164: "Romania",
    173: "Türkiye",
    152: "Liechtenstein",
    55: "China",
}
TARGET_NATION_IDS = frozenset(NATIONS)
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


def player_nation_ids(player) -> set[int]:
    ids: set[int] = set()
    if player.nation_id is not None:
        ids.add(int(player.nation_id))
    ids.update(int(x) for x in (player.second_nation_ids or ()))
    return ids


def is_target_nation(player) -> bool:
    return bool(player_nation_ids(player) & TARGET_NATION_IDS)


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
        df = save.players().filter(is_target_nation).to_pandas()
    before = len(df)
    df = drop_duplicate_players(df)
    frames[label] = df
    print(f"  {label}: {len(df)} target players (dropped {before - len(df)} dupes)")
    for nation_id, nation_name in NATIONS.items():
        sub = df.loc[nation_mask(df, nation_id)]
        counts = tier_counts(sub)
        rows.append({"save": label, "nation": nation_name, **counts})
        print(f"    {nation_name}: {counts['players']}")
        # for tier in TIERS:
        #     print(f"      >={tier}: CA|PA={counts[f'CA|PA>={tier}']}")

summary = pd.DataFrame(rows)
print("\nSummary")
print(summary.to_string(index=False))
