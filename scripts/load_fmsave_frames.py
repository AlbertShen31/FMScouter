#!/usr/bin/env python3
"""Open FM saves with fmsave and count Romanian players by CA/PA tier.

Fill in SAVES, then run::

    .venv/bin/python scripts/load_fmsave_frames.py
"""

from pathlib import Path

import fmsave
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
COMPETITION_NAMES = ROOT / "data" / "competition-names.csv"

# FM nation id (same as services/fmsave_export.py CLUB_NATION_LABELS).
ROMANIA_NATION_ID = 164
TIERS = (100, 120, 130, 140)

# Fill these in yourself (absolute paths or ~/… to .fm files).
SAVES = [
    "/Users/albertwshen/Library/Application Support/Sports Interactive/Football Manager 26/games/Romania Test.fm",
    "/Users/albertwshen/Library/Application Support/Sports Interactive/Football Manager 26/games/Romania Test Year 1 End.fm",
    "/Users/albertwshen/Library/Application Support/Sports Interactive/Football Manager 26/games/Romania Test Year 1 End (v02).fm",
    "/Users/albertwshen/Library/Application Support/Sports Interactive/Football Manager 26/games/Romania Test Year 1 End (v03).fm",
    "/Users/albertwshen/Library/Application Support/Sports Interactive/Football Manager 26/games/Romania Test Year 1 End (v04).fm",
    "/Users/albertwshen/Library/Application Support/Sports Interactive/Football Manager 26/games/Romania Test Year 1 End (v05).fm",
    "/Users/albertwshen/Library/Application Support/Sports Interactive/Football Manager 26/games/Romania Test Year 1 End (v06).fm",
]


def is_romanian(player) -> bool:
    if player.nation_id == ROMANIA_NATION_ID:
        return True
    return ROMANIA_NATION_ID in (player.second_nation_ids or ())


def tier_counts(df: pd.DataFrame) -> dict[str, int]:
    """Counts where CA or PA is strictly above each tier."""
    ca = pd.to_numeric(df.get("ability_current"), errors="coerce")
    pa = pd.to_numeric(df.get("ability_potential"), errors="coerce")
    out = {"romanian": int(len(df))}
    for tier in TIERS:
        out[f"CA|PA>{tier}"] = int(((ca >= tier) | (pa >= tier)).sum())
    return out


frames: dict[str, pd.DataFrame] = {}
rows: list[dict[str, object]] = []

for save_path in SAVES:
    path = Path(save_path).expanduser()
    label = path.stem
    print(f"Opening {path}…")
    with fmsave.open(
        path,
        competition_names=COMPETITION_NAMES if COMPETITION_NAMES.is_file() else None,
    ) as save:
        df = save.players().filter(is_romanian).to_pandas()
    frames[label] = df
    counts = tier_counts(df)
    rows.append({"save": label, **counts})
    print(f"  {label}: {counts['romanian']} Romanian")
    for tier in TIERS:
        print(
            f"    >{tier}: CA|PA={counts[f'CA|PA>{tier}']}  "
        )

summary = pd.DataFrame(rows)
print("\nSummary")
print(summary.to_string(index=False))
