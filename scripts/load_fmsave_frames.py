#!/usr/bin/env python3
"""Open FM saves with fmsave and count players by nation × CA/PA tier.

Fill in SAVES, then run::

    .venv/bin/python scripts/load_fmsave_frames.py
    .venv/bin/python scripts/load_fmsave_frames.py -n 164
    .venv/bin/python scripts/load_fmsave_frames.py -n 164 173 55
    .venv/bin/python scripts/load_fmsave_frames.py -t 130
    .venv/bin/python scripts/load_fmsave_frames.py -t 140 --export-names data/tier140_names.csv
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
# Order: latest first → earliest last (--export-names uses SAVES[0]).
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
    parser.add_argument(
        "-t",
        "--tier",
        type=int,
        choices=TIERS,
        help=f"Only report/export CA|PA>={{tier}}. Choices: {', '.join(map(str, TIERS))}",
    )
    parser.add_argument(
        "--export-names",
        type=Path,
        metavar="CSV",
        help="Write player names from the latest save (SAVES[0]) to this CSV "
        "(filtered to --tier when set).",
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


def tier_mask(df: pd.DataFrame, tier: int) -> pd.Series:
    """True when CA or PA is at/above ``tier``."""
    ca = pd.to_numeric(df.get("ability_current"), errors="coerce")
    pa = pd.to_numeric(df.get("ability_potential"), errors="coerce")
    return (ca >= tier) | (pa >= tier)


def tier_counts(df: pd.DataFrame, tiers: tuple[int, ...] = TIERS) -> dict[str, int]:
    """Counts where CA or PA is at/above each tier."""
    ca = pd.to_numeric(df.get("ability_current"), errors="coerce")
    pa = pd.to_numeric(df.get("ability_potential"), errors="coerce")
    out = {"players": int(len(df))}
    for tier in tiers:
        out[f"CA|PA>={tier}"] = int(((ca >= tier) | (pa >= tier)).sum())
    return out


def nation_label(df: pd.DataFrame, nations: dict[int, str]) -> pd.Series:
    """Best-effort nation name from primary / second nationality."""
    primary = pd.to_numeric(df.get("nation_id"), errors="coerce")
    labels = primary.map(lambda nid: nations.get(int(nid), str(int(nid))) if pd.notna(nid) else "")
    seconds = df.get("second_nation_ids")
    if seconds is None:
        return labels
    for nation_id, nation_name in nations.items():
        hit = seconds.map(
            lambda ids, nid=nation_id: nid in ids if ids is not None else False
        )
        labels = labels.where(~(hit & (labels == "")), nation_name)
    return labels


def names_export_frame(
    df: pd.DataFrame,
    *,
    save_label: str,
    nations: dict[int, str],
    tier: int | None,
) -> pd.DataFrame:
    sub = df
    if tier is not None:
        sub = sub.loc[tier_mask(sub, tier)]
    cols = {
        "save": save_label,
        "name": sub["name"] if "name" in sub.columns else "",
        "club": sub["club_name"] if "club_name" in sub.columns else "",
        "nation": nation_label(sub, nations),
    }
    if "unique_id" in sub.columns:
        cols["unique_id"] = sub["unique_id"]
    elif "uid" in sub.columns:
        cols["unique_id"] = sub["uid"]
    if "ability_current" in sub.columns:
        cols["CA"] = pd.to_numeric(sub["ability_current"], errors="coerce")
    if "ability_potential" in sub.columns:
        cols["PA"] = pd.to_numeric(sub["ability_potential"], errors="coerce")
    out = pd.DataFrame(cols)
    return out.sort_values(["nation", "club", "name"], kind="stable").reset_index(
        drop=True
    )


def main() -> None:
    args = parse_args()
    nations = resolve_nations(args.nations)
    target_ids = frozenset(nations)
    active_tiers = (args.tier,) if args.tier is not None else TIERS

    print("Nations:", ", ".join(f"{name} ({nid})" for nid, name in nations.items()))
    if args.tier is not None:
        print(f"Tier filter: CA|PA>={args.tier}")

    # SAVES is latest→earliest; walk earliest→latest for readable progress.
    save_paths = [Path(p).expanduser() for p in SAVES]
    if not save_paths:
        raise SystemExit("SAVES is empty — add at least one .fm path.")

    frames: dict[str, pd.DataFrame] = {}
    rows: list[dict[str, object]] = []

    for path in reversed(save_paths):
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
        frames[label] = df
        for nation_id, nation_name in nations.items():
            sub = df.loc[nation_mask(df, nation_id)]
            counts = tier_counts(sub, active_tiers)
            rows.append({"save": label, "nation": nation_name, **counts})
            print(f"    {nation_name}: {counts['players']}")
            for tier in active_tiers:
                print(f"      >={tier}: CA|PA={counts[f'CA|PA>={tier}']}")

    summary = pd.DataFrame(rows)
    print("\nSummary")
    print(summary.to_string(index=False))

    if args.export_names is not None:
        latest_label = save_paths[0].stem
        export = names_export_frame(
            frames[latest_label],
            save_label=latest_label,
            nations=nations,
            tier=args.tier,
        )
        out_path = args.export_names.expanduser()
        if not out_path.is_absolute():
            out_path = ROOT / out_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        export.to_csv(out_path, index=False)
        print(f"\nWrote {len(export)} name rows (latest={latest_label}) → {out_path}")


if __name__ == "__main__":
    main()
