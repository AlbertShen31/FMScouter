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
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import fmsave
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.fmsave_export import (  # noqa: E402
    CLUB_NATION_OPTIONS,
    _CUPISH_NAME_PARTS,
    _is_division_shaped,
)

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
    # "/Users/albertwshen/Library/Application Support/Sports Interactive/Football Manager 26/games/Romania Test Year 1 End (v02).fm",
    # "/Users/albertwshen/Library/Application Support/Sports Interactive/Football Manager 26/games/Romania Test Year 1 End (v03).fm",
    # "/Users/albertwshen/Library/Application Support/Sports Interactive/Football Manager 26/games/Romania Test Year 1 End (v04).fm",
    # "/Users/albertwshen/Library/Application Support/Sports Interactive/Football Manager 26/games/Romania Test Year 1 End (v05).fm",
    # "/Users/albertwshen/Library/Application Support/Sports Interactive/Football Manager 26/games/Romania Test Year 1 End (v06).fm",
    # "/Users/albertwshen/Library/Application Support/Sports Interactive/Football Manager 26/games/Romania Test Year 1 End (v07).fm",
    # "/Users/albertwshen/Library/Application Support/Sports Interactive/Football Manager 26/games/Romania Test Year 1 End (v08).fm",
    # "/Users/albertwshen/Library/Application Support/Sports Interactive/Football Manager 26/games/Romania Test Year 1 End (v09).fm",
    # "/Users/albertwshen/Library/Application Support/Sports Interactive/Football Manager 26/games/Romania Test.fm",
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


def nation_name_map() -> dict[int, str]:
    """FM nation id → label (club options + script KNOWN_NATIONS)."""
    return {**dict(CLUB_NATION_OPTIONS), **KNOWN_NATIONS}


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


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _series_int(df: pd.DataFrame, column: str) -> pd.Series:
    if column not in df.columns:
        return pd.Series(pd.NA, index=df.index, dtype="Int64")
    return pd.to_numeric(df[column], errors="coerce").astype("Int64")


def _pick_named_competition_entry(
    counts: Counter[tuple[int | None, str | None]],
) -> tuple[int | None, str]:
    """Choose (competition_id, name) from fixture counts; prefer non-cupish names."""
    scored: list[tuple[int, int, str, int | None]] = []
    for (cid, name), n in counts.items():
        label = (name or "").strip()
        if not label:
            continue
        low = label.casefold()
        pen = 1 if any(part in low for part in _CUPISH_NAME_PARTS) else 0
        scored.append((pen, -int(n), label, cid))
    if not scored:
        return None, ""
    scored.sort()
    _pen, _n, label, cid = scored[0]
    return _as_int(cid), label


@dataclass(frozen=True)
class ClubCompetitionInfo:
    competition_name: str
    competition_id: int | None
    competition_database_id: int | None
    club_unique_id: int | None
    club_nation_id: int | None


def build_club_competition_info(career_save: Any) -> dict[int, ClubCompetitionInfo]:
    """Map club_uid → domestic competition name/ids + club unique/nation ids."""
    db_by_comp_id = {
        int(comp.id): _as_int(comp.database_id)
        for comp in career_save.competitions()
        if getattr(comp, "id", None) is not None
    }
    club_meta: dict[int, tuple[int | None, int | None]] = {}
    for club in career_save.clubs():
        club_uid = _as_int(getattr(club, "uid", None))
        if club_uid is None:
            continue
        club_meta[club_uid] = (
            _as_int(getattr(club, "unique_id", None)),
            _as_int(getattr(club, "nation_id", None)),
        )

    fx_by_team: dict[int, Counter[tuple[int | None, str | None]]] = defaultdict(Counter)
    for fixture in career_save.fixtures():
        for team_id, competition_id, competition_name in (
            (fixture.home_team_id, fixture.competition_id, fixture.competition_name),
            (fixture.away_team_id, fixture.competition_id, fixture.competition_name),
        ):
            if team_id is None or competition_id is None:
                continue
            fx_by_team[int(team_id)][(competition_id, competition_name)] += 1

    chosen: dict[int, tuple[str, int | None]] = {}

    for table in career_save.league_tables():
        if not _is_division_shaped(table):
            continue
        rows = tuple(table.rows or ())
        slot0 = [row for row in rows if getattr(row, "team_slot", None) == 0]
        n = int(getattr(table, "club_count", 0) or 0)
        if len(slot0) < max(8, n // 2):
            continue
        name = (getattr(table, "competition_name", None) or "").strip()
        competition_id = _as_int(getattr(table, "competition_id", None))
        if not name:
            member_counts: Counter[tuple[int | None, str | None]] = Counter()
            for row in slot0:
                team_id = getattr(row, "team_id", None)
                if team_id is None:
                    continue
                team_fx = fx_by_team.get(int(team_id))
                if team_fx:
                    member_counts.update(team_fx)
            competition_id, name = _pick_named_competition_entry(member_counts)
        if not name:
            continue
        for row in slot0:
            club_uid = _as_int(getattr(row, "club_uid", None))
            if club_uid is None or club_uid in chosen:
                continue
            chosen[club_uid] = (name, competition_id)

    for club in career_save.clubs():
        club_uid = _as_int(getattr(club, "uid", None))
        if club_uid is None or club_uid in chosen:
            continue
        for team in getattr(club, "teams", None) or ():
            if getattr(team, "slot", None) != 0:
                continue
            team_id = getattr(team, "team_id", None)
            if team_id is None:
                break
            competition_id, name = _pick_named_competition_entry(
                fx_by_team.get(int(team_id), Counter())
            )
            if name:
                chosen[club_uid] = (name, competition_id)
            break

    out: dict[int, ClubCompetitionInfo] = {}
    for club_uid, (name, competition_id) in chosen.items():
        club_unique_id, club_nation_id = club_meta.get(club_uid, (None, None))
        out[club_uid] = ClubCompetitionInfo(
            competition_name=name,
            competition_id=competition_id,
            competition_database_id=(
                db_by_comp_id.get(competition_id) if competition_id is not None else None
            ),
            club_unique_id=club_unique_id,
            club_nation_id=club_nation_id,
        )
    return out


def names_export_frame(
    df: pd.DataFrame,
    *,
    save_label: str,
    nations: dict[int, str],
    tier: int | None,
    club_competition: dict[int, ClubCompetitionInfo] | None = None,
) -> pd.DataFrame:
    sub = df
    if tier is not None:
        sub = sub.loc[tier_mask(sub, tier)]
    labels = nation_name_map()
    club_uids = _series_int(sub, "club_uid")
    info = club_competition or {}

    def _info_field(uid: Any, field: str, default: Any = "") -> Any:
        if pd.isna(uid):
            return default
        row = info.get(int(uid))
        if row is None:
            return default
        value = getattr(row, field)
        return default if value is None else value

    competition = club_uids.map(lambda uid: _info_field(uid, "competition_name", ""))
    competition_id = club_uids.map(lambda uid: _info_field(uid, "competition_id", pd.NA))
    competition_database_id = club_uids.map(
        lambda uid: _info_field(uid, "competition_database_id", pd.NA)
    )
    club_unique_id = club_uids.map(lambda uid: _info_field(uid, "club_unique_id", pd.NA))
    competition_nation_id = club_uids.map(
        lambda uid: _info_field(uid, "club_nation_id", pd.NA)
    )
    # Fallback: player.club_nation_id when club table nation is missing.
    player_club_nation = _series_int(sub, "club_nation_id")
    competition_nation_id = competition_nation_id.where(
        competition_nation_id.notna(), player_club_nation
    )
    competition_nation = competition_nation_id.map(
        lambda nid: labels.get(int(nid), str(int(nid))) if pd.notna(nid) else ""
    )

    cols: dict[str, Any] = {
        "save": save_label,
        "name": sub["name"] if "name" in sub.columns else "",
        "club": sub["club_name"] if "club_name" in sub.columns else "",
        "competition": competition,
        "competition_nation": competition_nation,
        "nation": nation_label(sub, nations),
        "unique_id": _series_int(sub, "unique_id")
        if "unique_id" in sub.columns
        else _series_int(sub, "uid"),
        "uid": _series_int(sub, "uid"),
        "nation_id": _series_int(sub, "nation_id"),
        "club_uid": club_uids,
        "club_unique_id": club_unique_id.astype("Int64"),
        "team_id": _series_int(sub, "team_id"),
        "club_nation_id": player_club_nation,
        "competition_id": competition_id.astype("Int64"),
        "competition_database_id": competition_database_id.astype("Int64"),
        "competition_nation_id": competition_nation_id.astype("Int64"),
    }
    if "ability_current" in sub.columns:
        cols["CA"] = pd.to_numeric(sub["ability_current"], errors="coerce")
    if "ability_potential" in sub.columns:
        cols["PA"] = pd.to_numeric(sub["ability_potential"], errors="coerce")
    out = pd.DataFrame(cols)
    return out.sort_values(
        ["competition_nation", "competition", "club", "name"], kind="stable"
    ).reset_index(drop=True)


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
    club_competitions: dict[str, dict[int, ClubCompetitionInfo]] = {}
    rows: list[dict[str, object]] = []
    export_label = save_paths[0].stem if args.export_names is not None else None

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
            if export_label is not None and label == export_label:
                print("    Resolving club → competition…")
                club_competitions[label] = build_club_competition_info(save)
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
            club_competition=club_competitions.get(latest_label),
        )
        out_path = args.export_names.expanduser()
        if not out_path.is_absolute():
            out_path = ROOT / out_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        export.to_csv(out_path, index=False)
        print(f"\nWrote {len(export)} name rows (latest={latest_label}) → {out_path}")


if __name__ == "__main__":
    main()
