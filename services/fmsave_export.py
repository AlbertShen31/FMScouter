"""Export FM26 save players to Moneyball-compatible CSV via fmsave."""
from __future__ import annotations

import io
import subprocess
import sys
import time
import warnings
from collections import Counter, defaultdict
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Any, Literal

import pandas as pd

from config.paths import COMPETITION_NAMES_PATH

Scope = Literal["squad", "all"]
# Back-compat alias accepted by export_moneyball_csv (treated as "all").
_LEGACY_FILTERED_SCOPE = "filtered"

# fmsave ships no nation names; club_nation_id / nation_id are integers only.
# Labels below are curated from FM26 club samples (Based In / league nation).
CLUB_NATION_OPTIONS: tuple[tuple[int, str], ...] = (
    (120, "U.S.A."),
    (129, "Austria"),
    (131, "Belgium"),
    (134, "Bulgaria"),
    (135, "Croatia"),
    (137, "Czechia"),
    (138, "Denmark"),
    (139, "England"),
    (142, "Finland"),
    (143, "France"),
    (145, "Germany"),
    (146, "Greece"),
    (147, "Hungary"),
    (149, "Israel"),
    (150, "Italy"),
    (157, "Moldova"),
    (158, "Netherlands"),
    (159, "Scotland"),
    (160, "Norway"),
    (161, "Poland"),
    (162, "Portugal"),
    (163, "Ireland"),
    (164, "Romania"),
    (165, "Russia"),
    (170, "Spain"),
    (171, "Sweden"),
    (172, "Switzerland"),
    (173, "Türkiye"),
    (174, "Ukraine"),
    (175, "Wales"),
    (176, "Serbia"),
    (177, "Australia"),
    (189, "Brazil"),
    (191, "Colombia"),
)

# Intentionally blank in v1 — save has no display labels / name maps.
# Division is filled separately from league tables + competition-names.csv.
BLANK_COLUMNS: tuple[str, ...] = (
    "Personality",
    "Media Handling",
    "Nation",
    "Based In",
    "2nd Nat",
    "Best Role",
    "Style",
    "Picked",
    "Ability Gold",
    "Ability Silver",
    "Potential Gold",
    "Potential Silver",
    "World Reputation Gold",
    "World Reputation Silver",
)

# Soft-penalize these when voting a club's domestic division from fixtures.
_CUPISH_NAME_PARTS: tuple[str, ...] = (
    "cup",
    "cupa",
    "copa",
    "taça",
    "taca",
    "supercup",
    "super cup",
    "champions",
    "europa",
    "conference",
    "qualification",
    "playoff",
    "play-off",
    "friendly",
    "shield",
    "trophy",
    "wcl",
)

# fmsave Attributes field → Moneyball CSV header (ATTR_MAP full names).
ATTR_FIELD_TO_CSV: dict[str, str] = {
    "aerial_reach": "Aerial Reach",
    "command_of_area": "Command of Area",
    "communication": "Communication",
    "eccentricity": "Eccentricity",
    "handling": "Handling",
    "kicking": "Kicking",
    "one_on_ones": "One On Ones",
    "punching": "Punching",
    "reflexes": "Reflexes",
    "rushing_out": "Rushing Out (Tendency)",
    "throwing": "Throwing",
    "aggression": "Aggression",
    "anticipation": "Anticipation",
    "bravery": "Bravery",
    "concentration": "Concentration",
    "composure": "Composure",
    "decisions": "Decisions",
    "determination": "Determination",
    "flair": "Flair",
    "leadership": "Leadership",
    "off_the_ball": "Off The Ball",
    "positioning": "Positioning",
    "teamwork": "Team Work",
    "vision": "Vision",
    "work_rate": "Work Rate",
    "acceleration": "Acceleration",
    "agility": "Agility",
    "balance": "Balance",
    "jumping_reach": "Jumping Reach",
    "natural_fitness": "Natural Fitness",
    "pace": "Pace",
    "stamina": "Stamina",
    "strength": "Strength",
    "corners": "Corners",
    "crossing": "Crossing",
    "dribbling": "Dribbling",
    "finishing": "Finishing",
    "first_touch": "First Touch",
    "free_kick_taking": "Free Kick Taking",
    "heading": "Heading",
    "long_shots": "Long Shots",
    "long_throws": "Long Throws",
    "marking": "Marking",
    "passing": "Passing",
    "penalty_taking": "Penalty Taking",
    "tackling": "Tackling",
    "technique": "Technique",
}

# fmsave short codes → Moneyball Best Pos style.
_POS_CODE_TO_LABEL: dict[str, str] = {
    "GK": "GK",
    "SW": "SW",
    "DL": "D (L)",
    "DC": "D (C)",
    "DR": "D (R)",
    "WBL": "WB (L)",
    "WBR": "WB (R)",
    "DM": "DM",
    "ML": "M (L)",
    "MC": "M (C)",
    "MR": "M (R)",
    "AML": "AM (L)",
    "AMC": "AM (C)",
    "AMR": "AM (R)",
    "STC": "ST (C)",
}

_POS_GROUP_CODES: dict[str, frozenset[str]] = {
    "gk": frozenset({"GK"}),
    "def": frozenset({"SW", "DL", "DC", "DR", "WBL", "WBR"}),
    "mid": frozenset({"DM", "ML", "MC", "MR", "AML", "AMC", "AMR"}),
    "fwd": frozenset({"STC"}),
}

# ClauseKind name → Moneyball finance column.
_CLAUSE_TO_CSV: dict[str, str] = {
    "MINIMUM_FEE_RELEASE": "Minimum Fee Release Clause",
    "RELEGATION_RELEASE": "Relegation Release Clause",
    "NON_PROMOTION_RELEASE": "Non Promotion Release Clause",
    "MINIMUM_FEE_RELEASE_FOREIGN": "Minimum Fee Release Clause (Foreign Clubs)",
    "MINIMUM_FEE_RELEASE_DOMESTIC": "Minimum Fee Release Clause (Domestic Clubs)",
    "MINIMUM_FEE_RELEASE_DOMESTIC_HIGHER_DIVISION": (
        "Minimum Fee Release Clause (Domestic Clubs in Higher Division)"
    ),
    "APPEARANCE_FEE": "Appearance Fee",
    "UNUSED_SUBSTITUTE_FEE": "Unused Substitute Fee",
    "SHUTOUT_BONUS": "Shutout Bonus",
    "INTERNATIONAL_CAP_BONUS": "Int Cap Bonus",
    "TOP_DIVISION_RELEGATION_SALARY_DROP": "Top Division Relegation Salary Drop",
}

_FOOT_BANDS: tuple[tuple[int, str], ...] = (
    (20, "Very Strong"),
    (17, "Strong"),
    (13, "Fairly Strong"),
    (9, "Reasonable"),
    (5, "Weak"),
    (1, "Very Weak"),
)


def default_fm26_games_dir() -> Path | None:
    """Return the usual FM26 games folder for this OS, or None if unknown."""
    home = Path.home()
    if sys.platform == "darwin":
        return (
            home
            / "Library"
            / "Application Support"
            / "Sports Interactive"
            / "Football Manager 26"
            / "games"
        )
    if sys.platform == "win32":
        return (
            home
            / "Documents"
            / "Sports Interactive"
            / "Football Manager 26"
            / "games"
        )
    return None


def default_save_path() -> str:
    """Newest ``*.fm`` under the OS games dir, else the dir path, else ``\"\"``."""
    games = default_fm26_games_dir()
    if games is None:
        return ""
    if not games.is_dir():
        return str(games)
    saves = sorted(
        (p for p in games.glob("*.fm") if p.is_file()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if saves:
        return str(saves[0])
    return str(games)


def _dialog_initial_dir(preferred: str | Path | None = None) -> Path:
    """Existing folder to open in the save picker (preferred → OS games → home)."""

    def _existing_dir(path: Path) -> Path | None:
        if path.is_file():
            return path.parent if path.parent.is_dir() else None
        if path.is_dir():
            return path
        for parent in path.parents:
            if parent.is_dir():
                return parent
        return None

    if preferred:
        found = _existing_dir(Path(str(preferred)).expanduser())
        if found is not None:
            return found
    games = default_fm26_games_dir()
    if games is not None:
        found = _existing_dir(games)
        if found is not None:
            return found
    return Path.home()


def pick_fm_save_file(initial_dir: str | Path | None = None) -> str | None:
    """Open a native file dialog for a ``.fm`` save. Returns path or None if cancelled."""
    start = _dialog_initial_dir(initial_dir)
    start_s = str(start)

    if sys.platform == "darwin":
        # AppleScript from a worker thread (Dash threaded=True); avoid tkinter.
        escaped = start_s.replace("\\", "\\\\").replace('"', '\\"')
        script = (
            f'set defaultLoc to POSIX file "{escaped}"\n'
            "try\n"
            '  set theFile to choose file with prompt '
            '"Select Football Manager save" default location defaultLoc\n'
            "  return POSIX path of theFile\n"
            "on error\n"
            '  return ""\n'
            "end try"
        )
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                check=False,
                timeout=300,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        path = (result.stdout or "").strip()
        return path or None

    if sys.platform == "win32":
        ps_dir = start_s.replace("'", "''")
        ps = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "$d = New-Object System.Windows.Forms.OpenFileDialog; "
            "$d.Filter = 'FM Save (*.fm)|*.fm|All files (*.*)|*.*'; "
            f"$d.InitialDirectory = '{ps_dir}'; "
            "$d.Title = 'Select Football Manager save'; "
            "if ($d.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) "
            "{ [Console]::Out.Write($d.FileName) }"
        )
        try:
            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    ps,
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=300,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        path = (result.stdout or "").strip()
        return path or None

    # Linux / other: zenity, then kdialog.
    for cmd in (
        [
            "zenity",
            "--file-selection",
            "--title=Select Football Manager save",
            f"--filename={start_s}/",
            "--file-filter=FM Save | *.fm",
            "--file-filter=All files | *",
        ],
        [
            "kdialog",
            "--getopenfilename",
            start_s,
            "*.fm|FM Save",
        ],
    ):
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                timeout=300,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if result.returncode == 0:
            path = (result.stdout or "").strip()
            if path:
                return path
    return None


def _format_money(amount: float | int | None, *, annual: bool = False) -> str:
    if amount is None:
        return ""
    try:
        value = float(amount)
    except (TypeError, ValueError):
        return ""
    if annual:
        suffix = " p/a"
    else:
        suffix = ""
    abs_v = abs(value)
    if abs_v >= 1_000_000_000:
        return f"${value / 1_000_000_000:.2f}B{suffix}"
    if abs_v >= 1_000_000:
        return f"${value / 1_000_000:.2f}M{suffix}"
    if abs_v >= 1_000:
        return f"${value / 1_000:.2f}K{suffix}"
    if abs_v == int(abs_v):
        return f"${int(value)}{suffix}"
    return f"${value:.2f}{suffix}"


def _format_height_cm(cm: int | None) -> str:
    if not cm:
        return ""
    try:
        total_inches = round(float(cm) / 2.54)
    except (TypeError, ValueError):
        return ""
    feet, inches = divmod(total_inches, 12)
    return f"{feet}'{inches}\""


def _format_foot(raw: int | None) -> str:
    if raw is None:
        return ""
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return ""
    for threshold, label in _FOOT_BANDS:
        if value >= threshold:
            return label
    return "Very Weak"


def _pos_label(code: str) -> str:
    return _POS_CODE_TO_LABEL.get(str(code).upper(), str(code))


# Pitch order matching Moneyball Position strings (D before WB before DM …).
_STEM_ORDER: dict[str, int] = {
    "GK": 0,
    "SW": 1,
    "D": 2,
    "WB": 3,
    "DM": 4,
    "M": 5,
    "AM": 6,
    "ST": 7,
}

# Stems that can share a slash token when their side sets match exactly.
_MERGEABLE_STEMS: frozenset[str] = frozenset({"D", "WB", "M", "AM"})
# Bare tokens — no (sides), never slash-merged.
_SIDELESS_STEMS: frozenset[str] = frozenset({"GK", "SW", "DM"})


def _merge_position_codes(
    *groups: tuple[str, ...] | list[str] | None,
) -> list[str]:
    """Dedupe position codes, keeping first-seen order across groups."""
    seen: set[str] = set()
    out: list[str] = []
    for group in groups:
        if not group:
            continue
        for code in group:
            key = str(code).upper()
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(key)
    return out


def _format_side_letters(sides: list[str] | set[str] | frozenset[str]) -> str:
    """Moneyball / FM export convention: R, then L, then C."""
    return "".join(
        sorted(sides, key=lambda s: {"R": 0, "L": 1, "C": 2}.get(s, 9))
    )


def _normalize_stem_sides(stem: str, sides: list[str]) -> list[str]:
    """Apply FM side constraints per stem."""
    if stem in _SIDELESS_STEMS:
        return []
    if stem == "ST":
        # ST only ever appears as ST (C); never merges with other stems.
        return ["C"]
    if stem == "WB":
        # Wing-back has no centre side in Moneyball exports.
        return [s for s in sides if s in "RL"]
    return [s for s in sides if s in "RLC"]


def _combine_positions(codes: tuple[str, ...] | list[str] | None) -> str:
    """Turn codes into Moneyball Position text (``D/WB (L)``, ``AM (RL)``, …)."""
    if not codes:
        return ""
    # stem → unique side letters (pre-normalization).
    groups: dict[str, list[str]] = {}
    for code in codes:
        label = _pos_label(code)
        if label in _SIDELESS_STEMS or " (" not in label:
            groups.setdefault(label, [])
            continue
        stem, rest = label.split(" (", 1)
        bucket = groups.setdefault(stem, [])
        for ch in rest.rstrip(")"):
            if ch in "RLC" and ch not in bucket:
                bucket.append(ch)

    normalized: dict[str, list[str]] = {}
    for stem, sides in groups.items():
        norm = _normalize_stem_sides(stem, sides)
        if stem in _SIDELESS_STEMS:
            normalized[stem] = []
        elif norm:
            normalized[stem] = norm

    # Walk pitch order. Slash-merge only contiguous mergeable stems that share
    # the exact same side set (DM / ST / mismatched sides break the run).
    parts: list[str] = []
    run_stems: list[str] = []
    run_sides: frozenset[str] | None = None

    def flush_run() -> None:
        nonlocal run_stems, run_sides
        if not run_stems or run_sides is None:
            run_stems = []
            run_sides = None
            return
        parts.append(
            f"{'/'.join(run_stems)} ({_format_side_letters(run_sides)})"
        )
        run_stems = []
        run_sides = None

    for stem in sorted(normalized, key=lambda s: _STEM_ORDER.get(s, 50)):
        sides = normalized[stem]
        if (
            stem in _SIDELESS_STEMS
            or stem == "ST"
            or stem not in _MERGEABLE_STEMS
            or not sides
        ):
            flush_run()
            if stem in _SIDELESS_STEMS or not sides:
                parts.append(stem)
            else:
                parts.append(f"{stem} ({_format_side_letters(sides)})")
            continue
        side_key = frozenset(sides)
        if run_stems and run_sides == side_key:
            run_stems.append(stem)
        else:
            flush_run()
            run_stems = [stem]
            run_sides = side_key
    flush_run()
    return ", ".join(parts)


def _best_pos(natural: tuple[str, ...] | None) -> str:
    if not natural:
        return ""
    return _pos_label(natural[0])


def _clause_kind_name(clause: Any) -> str | None:
    kind = getattr(clause, "kind", None)
    if kind is None:
        return None
    label = getattr(kind, "label", kind)
    name = getattr(label, "name", None)
    if isinstance(name, str) and name != "UNKNOWN":
        return name
    return None


def _num(value: Any, *, digits: int | None = None) -> str:
    if value is None:
        return ""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    if digits is None:
        if number == int(number):
            return str(int(number))
        return str(number)
    return f"{number:.{digits}f}".rstrip("0").rstrip(".")


def _pct(value: Any) -> str:
    if value is None:
        return ""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    # fmsave stores 0–100 style percentages already for pass_completion_percent etc.
    return f"{number:.2f}".rstrip("0").rstrip(".")


def _expires(end: date | None) -> str:
    if end is None:
        return ""
    return f"{end.month}/{end.day}/{end.year}"


def _player_in_pos_groups(natural: tuple[str, ...] | None, groups: list[str]) -> bool:
    if not groups:
        return True
    codes = {str(c).upper() for c in (natural or ())}
    for group in groups:
        allowed = _POS_GROUP_CODES.get(str(group).lower())
        if allowed and codes & allowed:
            return True
    return False


def _passes_filters(player: Any, filters: dict[str, Any] | None) -> bool:
    if not filters:
        return True
    age = player.age
    age_min = filters.get("age_min")
    age_max = filters.get("age_max")
    if age_min is not None and age is not None and age < int(age_min):
        return False
    if age_max is not None and age is not None and age > int(age_max):
        return False

    min_ca = filters.get("min_ca")
    if min_ca is not None:
        ca = getattr(getattr(player, "ability", None), "current", None)
        if ca is None or ca < int(min_ca):
            return False

    min_rep = filters.get("min_club_reputation")
    if min_rep is not None:
        rep = player.club_reputation
        if rep is None or rep < int(min_rep):
            return False

    club_contains = (filters.get("club_contains") or "").strip().casefold()
    if club_contains:
        club = (player.club_name or "").casefold()
        if club_contains not in club:
            return False

    club_nations = filters.get("club_nation_ids") or []
    if club_nations:
        wanted = {int(n) for n in club_nations}
        club_nation = player.club_nation_id
        if club_nation is None or int(club_nation) not in wanted:
            return False

    player_nations = filters.get("nation_ids") or []
    if player_nations:
        wanted = {int(n) for n in player_nations}
        nation = player.nation_id
        if nation is None or int(nation) not in wanted:
            return False

    groups = filters.get("position_groups") or []
    if groups and not _player_in_pos_groups(player.natural_positions, list(groups)):
        return False

    return True


def _filters_active(filters: dict[str, Any] | None) -> bool:
    """True when at least one filter constraint is set."""
    if not filters:
        return False
    if filters.get("age_min") is not None or filters.get("age_max") is not None:
        return True
    if filters.get("min_ca") is not None or filters.get("min_club_reputation") is not None:
        return True
    if (filters.get("club_contains") or "").strip():
        return True
    if filters.get("club_nation_ids") or filters.get("nation_ids"):
        return True
    if filters.get("position_groups"):
        return True
    return False


def _normalize_scope(scope: str) -> Scope:
    if scope == _LEGACY_FILTERED_SCOPE:
        return "all"
    if scope in {"squad", "all"}:
        return scope  # type: ignore[return-value]
    return "squad"


def _pick_season_row(
    rows: list[Any],
    *,
    club_uid: int | None,
) -> Any | None:
    if not rows:
        return None
    if club_uid is not None:
        same = [r for r in rows if r.club_uid == club_uid]
        if same:
            return max(same, key=lambda r: int(r.minutes or 0))
    return max(rows, key=lambda r: int(r.minutes or 0))


def _is_division_shaped(table: Any) -> bool:
    """True for a domestic league standings group (widened from fmsave's 18–26 note)."""
    rows = getattr(table, "rows", None) or ()
    if not rows:
        return False
    n = int(getattr(table, "club_count", 0) or 0)
    rpv = getattr(rows[0], "rounds_per_venue", None)
    if rpv is None:
        return False
    return 10 <= n <= 30 and int(rpv) == n - 1


def _pick_named_competition(counts: Counter[tuple[int | None, str | None]]) -> str:
    """Choose a display name from fixture (competition_id, name) counts."""
    scored: list[tuple[int, int, str]] = []
    for (_cid, name), n in counts.items():
        label = (name or "").strip()
        if not label:
            continue
        low = label.casefold()
        pen = 1 if any(part in low for part in _CUPISH_NAME_PARTS) else 0
        scored.append((pen, -int(n), label))
    if not scored:
        return ""
    scored.sort()
    return scored[0][2]


def _build_club_divisions(career_save: Any) -> dict[int, str]:
    """Map club_uid → domestic Division label for Moneyball.

    League tables do not store a competition; fmsave votes one from fixtures, and that vote
    often lands on an unnamed id. Prefer division-shaped first-team tables, revoting the name
    from member fixtures when needed, then fall back to each club's slot-0 fixture majority.
    """
    fx_by_team: dict[int, Counter[tuple[int | None, str | None]]] = defaultdict(Counter)
    for fixture in career_save.fixtures():
        for team_id, competition_id, competition_name in (
            (fixture.home_team_id, fixture.competition_id, fixture.competition_name),
            (fixture.away_team_id, fixture.competition_id, fixture.competition_name),
        ):
            if team_id is None or competition_id is None:
                continue
            fx_by_team[int(team_id)][(competition_id, competition_name)] += 1

    club_division: dict[int, str] = {}
    for table in career_save.league_tables():
        if not _is_division_shaped(table):
            continue
        rows = tuple(table.rows or ())
        slot0 = [row for row in rows if getattr(row, "team_slot", None) == 0]
        n = int(getattr(table, "club_count", 0) or 0)
        if len(slot0) < max(8, n // 2):
            continue
        name = (getattr(table, "competition_name", None) or "").strip()
        if not name:
            member_counts: Counter[tuple[int | None, str | None]] = Counter()
            for row in slot0:
                team_id = getattr(row, "team_id", None)
                if team_id is None:
                    continue
                team_fx = fx_by_team.get(int(team_id))
                if team_fx:
                    member_counts.update(team_fx)
            name = _pick_named_competition(member_counts)
        if not name:
            continue
        for row in slot0:
            club_uid = getattr(row, "club_uid", None)
            if club_uid is None:
                continue
            club_division.setdefault(int(club_uid), name)

    for club in career_save.clubs():
        club_uid = getattr(club, "uid", None)
        if club_uid is None or int(club_uid) in club_division:
            continue
        for team in getattr(club, "teams", None) or ():
            if getattr(team, "slot", None) != 0:
                continue
            team_id = getattr(team, "team_id", None)
            if team_id is None:
                break
            name = _pick_named_competition(fx_by_team.get(int(team_id), Counter()))
            if name:
                club_division[int(club_uid)] = name
            break

    return club_division


def _season_columns(stats: Any | None) -> dict[str, str]:
    empty = {
        "Appearances": "",
        "Minutes": "",
        "Goals": "",
        "Goals per 90 minutes": "",
        "Assists": "",
        "Asts/90": "",
        "xG": "",
        "xG/90": "",
        "xA": "",
        "xA/90": "",
        "Shots": "",
        "Shot/90": "",
        "Shots on Target": "",
        "SOT/90": "",
        "Conv %": "",
        "Key Passes": "",
        "Key Passes per 90": "",
        "Dribbles": "",
        "Dribbles per 90": "",
        "Passes Attempted": "",
        "Passes Attempted per 90": "",
        "Pass Completion Ratio": "",
        "Progressive Passes per 90": "",
        "PsP": "",
        "Possession Won per 90": "",
        "Interceptions": "",
        "Interceptions per 90": "",
        "Clearances": "",
        "Clearances per 90": "",
        "Blk": "",
        "Blk/90": "",
        "Headers Won": "",
        "Headers Won per 90": "",
        "Headers Attempted": "",
        "Headers Attempted per 90": "",
        "Headers Won Percentage": "",
        "Tackles Attempted": "",
        "Tackles Completed": "",
        "Tackles Completed per 90": "",
        "Tackle Completion Percentage": "",
        "Pressures Completed": "",
        "Pressures Completed per 90": "",
        "Pressures Attempted": "",
        "Pressures Attempted per 90": "",
        "Crosses Completed": "",
        "Open Play Crosses Completed": "",
        "OP Cr C/90": "",
        "Sprints": "",
        "Sprints per 90": "",
        "Goals Allowed": "",
        "xGP": "",
        "xGP/90": "",
        "Rating": "",
        "Yellow Cards": "",
        "Red Cards": "",
        "Fouls Made": "",
        "Fouls Made per 90": "",
    }
    if stats is None:
        return empty

    apps = int(stats.starts or 0) + int(stats.substitute_appearances or 0)
    progressive = getattr(stats, "progressive_passes", None)
    progressive_90 = getattr(stats, "progressive_passes_per_90", None)
    blocks = getattr(stats, "blocks", None)
    blocks_90 = getattr(stats, "blocks_per_90", None)
    headers_att = getattr(stats, "aerial_challenges_attempted", None)
    headers_att_90 = getattr(stats, "aerial_challenges_attempted_per_90", None)
    op_cross = getattr(stats, "open_play_crosses_completed", None)
    op_cross_90 = getattr(stats, "open_play_crosses_completed_per_90", None)
    sprints = getattr(stats, "high_intensity_sprints", None)
    sprints_90 = getattr(stats, "high_intensity_sprints_per_90", None)
    fouls_90 = None
    minutes = int(stats.minutes or 0)
    if minutes > 0 and stats.fouls_made is not None:
        fouls_90 = (float(stats.fouls_made) * 90.0) / minutes

    return {
        "Appearances": _num(apps),
        "Minutes": _num(stats.minutes),
        "Goals": _num(stats.goals),
        "Goals per 90 minutes": _num(stats.goals_per_90, digits=3),
        "Assists": _num(stats.assists),
        "Asts/90": _num(stats.assists_per_90, digits=3),
        "xG": _num(stats.expected_goals, digits=2),
        "xG/90": _num(stats.expected_goals_per_90, digits=3),
        "xA": _num(stats.expected_assists, digits=2),
        "xA/90": _num(stats.expected_assists_per_90, digits=3),
        "Shots": _num(stats.shots),
        "Shot/90": _num(stats.shots_per_90, digits=3),
        "Shots on Target": _num(stats.shots_on_target),
        "SOT/90": _num(stats.shots_on_target_per_90, digits=3),
        "Conv %": _pct(stats.conversion_percent),
        "Key Passes": _num(stats.key_passes),
        "Key Passes per 90": _num(stats.key_passes_per_90, digits=3),
        "Dribbles": _num(stats.dribbles),
        "Dribbles per 90": _num(stats.dribbles_per_90, digits=3),
        "Passes Attempted": _num(stats.passes_attempted),
        "Passes Attempted per 90": _num(stats.passes_attempted_per_90, digits=3),
        "Pass Completion Ratio": _pct(stats.pass_completion_percent),
        "Progressive Passes per 90": _num(progressive_90, digits=3),
        "PsP": _num(progressive),
        "Possession Won per 90": _num(stats.possession_won_per_90, digits=3),
        "Interceptions": _num(stats.interceptions),
        "Interceptions per 90": _num(stats.interceptions_per_90, digits=3),
        "Clearances": _num(stats.clearances),
        "Clearances per 90": _num(stats.clearances_per_90, digits=3),
        "Blk": _num(blocks),
        "Blk/90": _num(blocks_90, digits=3),
        "Headers Won": _num(stats.headers_won),
        "Headers Won per 90": _num(stats.headers_won_per_90, digits=3),
        "Headers Attempted": _num(headers_att),
        "Headers Attempted per 90": _num(headers_att_90, digits=3),
        "Headers Won Percentage": _pct(stats.headers_won_percent),
        "Tackles Attempted": _num(stats.tackles_attempted),
        "Tackles Completed": _num(stats.tackles_completed),
        "Tackles Completed per 90": _num(stats.tackles_completed_per_90, digits=3),
        "Tackle Completion Percentage": _pct(stats.tackle_completion_percent),
        "Pressures Completed": _num(stats.pressures_completed),
        "Pressures Completed per 90": _num(stats.pressures_completed_per_90, digits=3),
        "Pressures Attempted": _num(stats.pressures_attempted),
        "Pressures Attempted per 90": _num(stats.pressures_attempted_per_90, digits=3),
        "Crosses Completed": _num(stats.crosses_completed),
        "Open Play Crosses Completed": _num(op_cross),
        "OP Cr C/90": _num(op_cross_90, digits=3),
        "Sprints": _num(sprints),
        "Sprints per 90": _num(sprints_90, digits=3),
        "Goals Allowed": _num(stats.goals_allowed),
        "xGP": _num(stats.expected_goals_prevented, digits=2),
        "xGP/90": _num(stats.expected_goals_prevented_per_90, digits=3),
        "Rating": _num(stats.average_rating, digits=2),
        "Yellow Cards": _num(stats.yellow_cards),
        "Red Cards": _num(stats.red_cards),
        "Fouls Made": _num(stats.fouls_made),
        "Fouls Made per 90": _num(fouls_90, digits=3),
    }


def _finance_columns(player: Any) -> dict[str, str]:
    out: dict[str, str] = {
        "Salary": "",
        "Appearance Fee": "",
        "Unused Substitute Fee": "",
        "Transfer Value": "",
        "Expires": "",
        "Shutout Bonus": "",
        "Int Cap Bonus": "",
        "Minimum Fee Release Clause": "",
        "Relegation Release Clause": "",
        "Non Promotion Release Clause": "",
        "Minimum Fee Release Clause (Foreign Clubs)": "",
        "Minimum Fee Release Clause (Domestic Clubs)": "",
        "Minimum Fee Release Clause (Domestic Clubs in Higher Division)": "",
        "Top Division Relegation Salary Drop": "",
    }
    contract = player.contract
    if contract is not None:
        if contract.wage is not None:
            out["Salary"] = _format_money(float(contract.wage) * 52.0, annual=True)
        out["Expires"] = _expires(contract.end)
        for clause in contract.clauses or ():
            name = _clause_kind_name(clause)
            if not name:
                continue
            col = _CLAUSE_TO_CSV.get(name)
            if not col:
                continue
            if name == "TOP_DIVISION_RELEGATION_SALARY_DROP":
                param = clause.parameter
                if param is not None:
                    out[col] = f"{param}%"
                continue
            out[col] = _format_money(clause.value)
    if player.transfer_value is not None:
        out["Transfer Value"] = _format_money(player.transfer_value)
    return out


def _identity_columns(player: Any, *, division: str = "") -> dict[str, str]:
    ability = getattr(player, "ability", None)
    reputation = getattr(player, "reputation", None)
    return {
        "Player": player.name or "",
        "Unique ID": "" if player.unique_id is None else str(player.unique_id),
        "Age": "" if player.age is None else str(player.age),
        "Club": player.club_name or "",
        "Division": division or "",
        "Best Pos": _best_pos(player.natural_positions),
        # Natural + accomplished in Position (Moneyball-style); accomplished alone in Sec.
        "Position": _combine_positions(
            _merge_position_codes(
                player.natural_positions,
                player.accomplished_positions,
            )
        ),
        "Sec. Position": _combine_positions(player.accomplished_positions),
        "Height": _format_height_cm(player.height_cm),
        "Left Foot": _format_foot(player.left_foot),
        "Right Foot": _format_foot(player.right_foot),
        "Ability": "" if ability is None or ability.current is None else str(ability.current),
        "Potential": (
            "" if ability is None or ability.potential is None else str(ability.potential)
        ),
        "World Reputation": (
            ""
            if reputation is None or getattr(reputation, "world", None) is None
            else str(reputation.world)
        ),
        **{col: "" for col in BLANK_COLUMNS},
    }


def _attribute_columns(player: Any) -> dict[str, str]:
    attrs = player.attributes
    out: dict[str, str] = {}
    for field, header in ATTR_FIELD_TO_CSV.items():
        value = getattr(attrs, field, None)
        out[header] = "" if value is None else str(value)
    return out


def _player_row(
    player: Any,
    season: Any | None,
    *,
    division: str = "",
) -> dict[str, str]:
    row: dict[str, str] = {}
    row.update(_identity_columns(player, division=division))
    row.update(_attribute_columns(player))
    row.update(_finance_columns(player))
    row.update(_season_columns(season))
    return row


def _column_order(sample: dict[str, str]) -> list[str]:
    preferred = [
        "Player",
        "Unique ID",
        "Age",
        "Club",
        "Division",
        "Nation",
        "Based In",
        "Best Pos",
        "Position",
        "Sec. Position",
        "Height",
        "Personality",
        "Left Foot",
        "Right Foot",
        "Ability",
        "Potential",
        "World Reputation",
        *ATTR_FIELD_TO_CSV.values(),
        "Salary",
        "Appearance Fee",
        "Unused Substitute Fee",
        "Transfer Value",
        "Expires",
        "Minimum Fee Release Clause",
        "Relegation Release Clause",
        "Non Promotion Release Clause",
        "Minimum Fee Release Clause (Foreign Clubs)",
        "Minimum Fee Release Clause (Domestic Clubs)",
        "Minimum Fee Release Clause (Domestic Clubs in Higher Division)",
        "Top Division Relegation Salary Drop",
        "Shutout Bonus",
        "Int Cap Bonus",
        "Appearances",
        "Minutes",
        "Goals",
        "Goals per 90 minutes",
        "Assists",
        "Asts/90",
        "xG",
        "xG/90",
        "xA",
        "xA/90",
        "Shots",
        "Shot/90",
        "Shots on Target",
        "SOT/90",
        "Conv %",
        "Key Passes",
        "Key Passes per 90",
        "Dribbles",
        "Dribbles per 90",
        "Passes Attempted",
        "Passes Attempted per 90",
        "Pass Completion Ratio",
        "PsP",
        "Progressive Passes per 90",
        "Possession Won per 90",
        "Interceptions",
        "Interceptions per 90",
        "Clearances",
        "Clearances per 90",
        "Blk",
        "Blk/90",
        "Headers Won",
        "Headers Won per 90",
        "Headers Attempted",
        "Headers Attempted per 90",
        "Headers Won Percentage",
        "Tackles Attempted",
        "Tackles Completed",
        "Tackles Completed per 90",
        "Tackle Completion Percentage",
        "Pressures Completed",
        "Pressures Completed per 90",
        "Pressures Attempted",
        "Pressures Attempted per 90",
        "Crosses Completed",
        "Open Play Crosses Completed",
        "OP Cr C/90",
        "Sprints",
        "Sprints per 90",
        "Goals Allowed",
        "xGP",
        "xGP/90",
        "Rating",
        "Yellow Cards",
        "Red Cards",
        "Fouls Made",
        "Fouls Made per 90",
        *BLANK_COLUMNS,
    ]
    seen: set[str] = set()
    ordered: list[str] = []
    for col in preferred:
        if col in sample and col not in seen:
            ordered.append(col)
            seen.add(col)
    for col in sample:
        if col not in seen:
            ordered.append(col)
            seen.add(col)
    return ordered


def _progress_step(total: int) -> int:
    """Throttle UI ticks on large tables (same cadence as export loops)."""
    return 1 if total <= 200 else max(1, total // 40)


@contextmanager
def _track_player_load_progress() -> Iterator[None]:
    """Publish decode percentage while fmsave builds the players table.

    fmsave has no progress callback; it locates every player record then decodes
    each one. Hook those two private steps so the busy bar can show
    ``done / total`` instead of an indeterminate spinner for the long phase.
    """
    from fmsave._context import SaveContext
    from fmsave.readers.players import PlayerDecoder

    import services.compute_progress as compute_progress

    state = {"done": 0, "total": 0, "step": 1}
    orig_build = SaveContext._build_player_records
    orig_decode = PlayerDecoder.decode

    def build_player_records(self):  # noqa: ANN001 — mirrors fmsave signature
        records = orig_build(self)
        total = len(records.record_offsets)
        state["total"] = total
        state["done"] = 0
        state["step"] = _progress_step(total)
        compute_progress.update(phase="Loading players…", done=0, total=total)
        return records

    def decode(self, *args, **kwargs):  # noqa: ANN001 — mirrors fmsave signature
        result = orig_decode(self, *args, **kwargs)
        state["done"] += 1
        done = state["done"]
        total = state["total"]
        step = state["step"]
        if total > 0 and (done == 1 or done >= total or done % step == 0):
            compute_progress.tick(done, total, phase="Loading players…")
        return result

    SaveContext._build_player_records = build_player_records  # type: ignore[method-assign]
    PlayerDecoder.decode = decode  # type: ignore[method-assign]
    try:
        yield
    finally:
        SaveContext._build_player_records = orig_build  # type: ignore[method-assign]
        PlayerDecoder.decode = orig_decode  # type: ignore[method-assign]


def export_moneyball_csv(
    save_path: str,
    *,
    scope: str = "squad",
    filters: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Return ``(csv_text, meta)`` with Moneyball headers (``;`` delimiter)."""
    import fmsave
    from fmsave.models.season_stats import SeasonStatsKind
    from services.export_library import classify_eligibility

    path = Path(save_path).expanduser()
    if not path.is_file():
        raise FileNotFoundError(f"Save file not found: {path}")

    scope_key = _normalize_scope(scope)
    started = time.perf_counter()
    rows: list[dict[str, str]] = []
    competition_names = (
        COMPETITION_NAMES_PATH if COMPETITION_NAMES_PATH.is_file() else None
    )

    import services.compute_progress as compute_progress

    compute_progress.update(phase="Opening save…", done=0, total=0)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with fmsave.open(path, competition_names=competition_names) as career_save:
            compute_progress.update(phase="Loading players…")
            with _track_player_load_progress():
                if scope_key == "squad":
                    managed = career_save.managed_clubs()
                    if not managed:
                        raise ValueError(
                            "No managed club in this save (between jobs?). "
                            "Use All players instead."
                        )
                    club_uid = managed[0].club_uid
                    players = career_save.players().where(club_uid=club_uid)
                else:
                    players = career_save.players()

                if _filters_active(filters):
                    players = players.filter(
                        lambda player: _passes_filters(player, filters)
                    )

                player_list = list(players)
            uid_set = {p.uid for p in player_list}
            club_divisions = _build_club_divisions(career_save)

            compute_progress.update(
                phase="Loading season stats…",
                done=0,
                total=len(player_list),
            )

            season_by_uid: dict[int, list[Any]] = {}
            for record in career_save.player_season_stats():
                if record.player_uid not in uid_set:
                    continue
                if record.kind != SeasonStatsKind.OVERALL:
                    continue
                season_by_uid.setdefault(record.player_uid, []).append(record)

            total_players = len(player_list)
            step = 1 if total_players <= 200 else max(1, total_players // 40)
            compute_progress.update(
                phase="Exporting players…",
                done=0,
                total=total_players,
            )
            for player_idx, player in enumerate(player_list, start=1):
                season = _pick_season_row(
                    season_by_uid.get(player.uid, []),
                    club_uid=player.club_uid,
                )
                division = ""
                if player.club_uid is not None:
                    division = club_divisions.get(int(player.club_uid), "")
                rows.append(_player_row(player, season, division=division))
                if (
                    player_idx == 1
                    or player_idx == total_players
                    or player_idx % step == 0
                ):
                    compute_progress.tick(
                        player_idx,
                        total_players,
                        phase="Exporting players…",
                    )

    if not rows:
        raise ValueError("No players matched the selected scope/filters.")

    compute_progress.update(phase="Writing CSV…", done=len(rows), total=len(rows))
    columns = _column_order(rows[0])
    frame = pd.DataFrame(rows, columns=columns)
    buffer = io.StringIO()
    frame.to_csv(buffer, sep=";", index=False)
    csv_text = buffer.getvalue()

    eligibility = classify_eligibility(csv_text)
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    mapped = [c for c in columns if c not in BLANK_COLUMNS]
    meta: dict[str, Any] = {
        "row_count": len(rows),
        "column_count": len(columns),
        "elapsed_ms": elapsed_ms,
        "scope": scope_key,
        "filters_active": _filters_active(filters),
        "save_path": str(path),
        "eligibility": eligibility,
        "mapped_columns": mapped,
        "blank_columns": list(BLANK_COLUMNS),
        "filename": f"fmsave_{scope_key}_{path.stem}.csv",
    }
    return csv_text, meta
