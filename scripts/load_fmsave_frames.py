#!/usr/bin/env python3
"""Open FM saves with fmsave and build a players DataFrame for each.

Fill in SAVES, then run::

    .venv/bin/python scripts/load_fmsave_frames.py
"""

from pathlib import Path

import fmsave

ROOT = Path(__file__).resolve().parents[1]
COMPETITION_NAMES = ROOT / "data" / "competition-names.csv"

# Fill these in yourself (absolute paths or ~/… to .fm files).
SAVES = [
    "/Users/albertwshen/Library/Application Support/Sports Interactive/Football Manager 26/games/Romania Test Year 1 End (v02).fm",
    "/Users/albertwshen/Library/Application Support/Sports Interactive/Football Manager 26/games/Romania Test Year 1 End (v03).fm",
    "/Users/albertwshen/Library/Application Support/Sports Interactive/Football Manager 26/games/Romania Test Year 1 End (v04).fm",
    "/Users/albertwshen/Library/Application Support/Sports Interactive/Football Manager 26/games/Romania Test Year 1 End (v05).fm",
    "/Users/albertwshen/Library/Application Support/Sports Interactive/Football Manager 26/games/Romania Test Year 1 End (v06).fm",
    "/Users/albertwshen/Library/Application Support/Sports Interactive/Football Manager 26/games/Romania Test Year 1 End.fm",
    "/Users/albertwshen/Library/Application Support/Sports Interactive/Football Manager 26/games/Romania Test.fm",
]

frames: dict[str, object] = {}

for save_path in SAVES:
    path = Path(save_path).expanduser()
    label = path.stem
    print(f"Opening {path}…")
    with fmsave.open(
        path,
        competition_names=COMPETITION_NAMES if COMPETITION_NAMES.is_file() else None,
    ) as save:
        # Swap / filter as you like, e.g.:
        #   club = save.managed_clubs()[0]
        #   df = save.players().where(club_uid=club.club_uid).to_pandas()
        df = save.players().to_pandas()
    frames[label] = df
    print(f"  {label}: {df.shape[0]} rows × {df.shape[1]} cols")

# frames["save_stem"] is a pandas DataFrame — build on it below.
for label, df in frames.items():
    print(label, df.head(3))
