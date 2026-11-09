"""Export FM26 / FM27 save players to Moneyball-compatible CSV via fmsave."""
from __future__ import annotations

import csv
import io
import subprocess
import sys
import threading
import time
import warnings
from collections import Counter, defaultdict
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Literal

import pandas as pd

from config.paths import COMPETITION_NAMES_PATH, NATION_NAMES_PATH
from services.division_catalog import nation_abbreviation

Scope = Literal["squad", "all"]
# Back-compat alias accepted by export_moneyball_csv (treated as "all").
_LEGACY_FILTERED_SCOPE = "filtered"

# Prefer the newest edition that has a games folder on disk.
_FM_GAMES_EDITIONS: tuple[str, ...] = (
    "Football Manager 27",
    "Football Manager 26",
)

# fmsave ships no nation names; club_nation_id / nation_id are integers only.
# Labels below are curated from FM club samples (Based In / league nation).
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
    (159, "Northern Ireland"),
    (160, "Norway"),
    (161, "Poland"),
    (162, "Portugal"),
    (163, "Ireland"),
    (164, "Romania"),
    (165, "Russia"),
    (167, "Scotland"),
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


@lru_cache(maxsize=1)
def nation_name_map() -> dict[int, str]:
    """FM nation_id / club_nation_id → display name (CSV, then curated fallback)."""
    out = dict(CLUB_NATION_OPTIONS)
    path = NATION_NAMES_PATH
    if path.is_file():
        with path.open(encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                raw_id = (row.get("database_id") or "").strip()
                name = (row.get("name") or "").strip()
                if not raw_id or not name:
                    continue
                try:
                    out[int(raw_id)] = name
                except ValueError:
                    continue
    return out


@lru_cache(maxsize=1)
def competition_name_map() -> dict[int, str]:
    """Editor database_id → competition display name.

    Our CSV also has a ``type`` column; fmsave only accepts a 2-column file,
    so we load the map ourselves and pass the dict into ``fmsave.open``.
    """
    path = COMPETITION_NAMES_PATH
    out: dict[int, str] = {}
    if not path.is_file():
        return out
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            raw_id = (row.get("database_id") or "").strip()
            name = (row.get("name") or "").strip()
            if not raw_id or not name:
                continue
            try:
                out[int(raw_id)] = name
            except ValueError:
                continue
    return out


def nation_filter_options() -> tuple[tuple[int, str], ...]:
    """Sorted (id, label) pairs for Save-export nationality filters."""
    return tuple(
        sorted(nation_name_map().items(), key=lambda item: item[1].casefold())
    )


def _nation_display_name(nation_id: int | None) -> str:
    if nation_id is None:
        return ""
    try:
        nid = int(nation_id)
    except (TypeError, ValueError):
        return ""
    return nation_name_map().get(nid, "")


def _nation_code(nation_id: int | None) -> str:
    label = _nation_display_name(nation_id)
    if not label:
        return ""
    return nation_abbreviation(label) or label


def _second_nation_codes(ids: tuple[int, ...] | list[int] | None) -> str:
    codes: list[str] = []
    seen: set[str] = set()
    for raw in ids or ():
        code = _nation_code(raw)
        if code and code not in seen:
            seen.add(code)
            codes.append(code)
    return "/".join(codes)

# Display labels the save still does not store (hidden attrs ≠ Personality string).
# Nation / Based In / 2nd Nat come from nation-names.csv + nation_id fields.
# Division is filled separately from league tables + competition-names.csv.
BLANK_COLUMNS: tuple[str, ...] = (
    "Personality",
    "Media Handling",
    "Best Role",
    "Style",
    "Picked",
    "Ability Gold",
    "Ability Silver",
    "Potential Gold",
    "Potential Silver",
    "World Reputation Gold",
    "World Reputation Silver",
    # fmsave injury table has no recurring flag (Moneyball column kept empty).
    "Recurring Injury",
)

_INJURY_COLUMNS: tuple[str, ...] = (
    "Injury",
    "Injured On",
    "Time Missed",
    "Recurring Injury",
)

# Exclude these when voting a club's domestic division from fixtures / tables.
# Continental tokens are full competition phrases so "Championship" ≠ "Champions League".
_CUPISH_NAME_PARTS: tuple[str, ...] = (
    "cup",
    "cupa",
    "copa",
    "taça",
    "taca",
    "supercup",
    "super cup",
    "qualification",
    "playoff",
    "play-off",
    "friendly",
    "shield",
    "trophy",
    "testimonial",
    # Continental / intercontinental (full names)
    "champions league",
    "champions' cup",
    "champions cup",
    "europa league",
    "conference league",
    "uefa wcl",
    "uefa super cup",
    "leagues cup",
    "club world cup",
    "club world championship",
    "copa libertadores",
    "copa sudamericana",
    "recopa sudamericana",
    "supercopa sudamericana",
    "concacaf champions",
    "concacaf league",
    "afc champions league",
    "caf champions league",
    "ofc champions league",
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


def _fm_games_dir_for_edition(edition_folder: str) -> Path | None:
    """Usual Sports Interactive games folder for one FM edition, or None."""
    home = Path.home()
    if sys.platform == "darwin":
        return (
            home
            / "Library"
            / "Application Support"
            / "Sports Interactive"
            / edition_folder
            / "games"
        )
    if sys.platform == "win32":
        return (
            home
            / "Documents"
            / "Sports Interactive"
            / edition_folder
            / "games"
        )
    return None


def default_fm_games_dirs() -> tuple[Path, ...]:
    """Games folders for supported editions that exist on disk (FM27 first)."""
    found: list[Path] = []
    for edition in _FM_GAMES_EDITIONS:
        path = _fm_games_dir_for_edition(edition)
        if path is not None and path.is_dir():
            found.append(path)
    return tuple(found)


def default_fm_games_dir() -> Path | None:
    """Preferred games folder: existing FM27/FM26 dir, else the FM27 path, else None."""
    existing = default_fm_games_dirs()
    if existing:
        return existing[0]
    return _fm_games_dir_for_edition(_FM_GAMES_EDITIONS[0])


def default_fm26_games_dir() -> Path | None:
    """Back-compat alias for :func:`default_fm_games_dir` (FM26 or FM27)."""
    return default_fm_games_dir()


def default_save_path() -> str:
    """Newest ``*.fm`` under FM27/FM26 games dirs, else a games path, else ``\"\"``."""
    games_dirs = list(default_fm_games_dirs())
    if not games_dirs:
        games = default_fm_games_dir()
        return str(games) if games is not None else ""
    saves = sorted(
        (p for games in games_dirs for p in games.glob("*.fm") if p.is_file()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if saves:
        return str(saves[0])
    return str(games_dirs[0])


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
    for games in default_fm_games_dirs():
        found = _existing_dir(games)
        if found is not None:
            return found
    games = default_fm_games_dir()
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


# fmsave layout height_range_cm (FM26+); export Height labels use round(cm/2.54).
HEIGHT_CM_MIN = 150
HEIGHT_CM_MAX = 210
HEIGHT_IN_MIN = round(HEIGHT_CM_MIN / 2.54)  # 59 → 4'11"
HEIGHT_IN_MAX = round(HEIGHT_CM_MAX / 2.54)  # 83 → 6'11"


def _height_total_inches(cm: int | float | None) -> int | None:
    """Round cm → total inches the same way export Height strings are built."""
    if not cm:
        return None
    try:
        return round(float(cm) / 2.54)
    except (TypeError, ValueError):
        return None


def format_height_inches(total_inches: int) -> str:
    feet, inches = divmod(int(total_inches), 12)
    return f"{feet}'{inches}\""


def _format_club_display(player: Any) -> str:
    """Active club; when on loan, ``Loaned Club (Parent Club)``."""
    club = str(getattr(player, "club_name", None) or "").strip()
    if not getattr(player, "on_loan", False):
        return club
    parent = str(getattr(player, "loan_parent_club_name", None) or "").strip()
    if not parent or parent.casefold() == club.casefold():
        return club
    if club:
        return f"{club} ({parent})"
    return f"({parent})"


def _club_search_text(player: Any) -> str:
    """Club text for contains-filter: active club plus loan parent when present."""
    parts = [str(getattr(player, "club_name", None) or "")]
    parent = getattr(player, "loan_parent_club_name", None)
    if parent:
        parts.append(str(parent))
    return " ".join(parts).casefold()


def _format_height_cm(cm: int | None) -> str:
    total_inches = _height_total_inches(cm)
    if total_inches is None:
        return ""
    return format_height_inches(total_inches)


def height_select_options() -> list[dict[str, str]]:
    """Select options for every inch from FM min height to max height."""
    return [
        {"label": format_height_inches(total), "value": str(total)}
        for total in range(HEIGHT_IN_MIN, HEIGHT_IN_MAX + 1)
    ]


def parse_height_select(value) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def normalize_height_bounds(height_min, height_max) -> tuple[int | None, int | None]:
    """Drop full-range bounds so default selects do not count as an active filter."""
    lo = parse_height_select(height_min)
    hi = parse_height_select(height_max)
    if lo is None and hi is None:
        return None, None
    if lo is None:
        lo = HEIGHT_IN_MIN
    if hi is None:
        hi = HEIGHT_IN_MAX
    if lo <= HEIGHT_IN_MIN and hi >= HEIGHT_IN_MAX:
        return None, None
    return lo, hi


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


def _player_in_pos_groups(
    natural: tuple[str, ...] | None,
    groups: list[str] | tuple[str, ...] | frozenset[str],
) -> bool:
    if not groups:
        return True
    codes = {str(c).upper() for c in (natural or ())}
    for group in groups:
        allowed = _POS_GROUP_CODES.get(str(group).lower())
        if allowed and codes & allowed:
            return True
    return False


def prepare_filters(filters: dict[str, Any] | None) -> dict[str, Any] | None:
    """Normalize filter payload once per callback (sets / casefold / groups)."""
    if not filters:
        return None
    if filters.get("_prepared"):
        return filters
    club_nations = filters.get("club_nation_ids") or ()
    player_nations = filters.get("nation_ids") or ()
    groups = filters.get("position_groups") or ()
    return {
        "age_min": filters.get("age_min"),
        "age_max": filters.get("age_max"),
        "height_min_in": filters.get("height_min_in"),
        "height_max_in": filters.get("height_max_in"),
        "club_contains": (filters.get("club_contains") or "").strip().casefold(),
        "club_nation_ids": frozenset(int(n) for n in club_nations),
        "nation_ids": frozenset(int(n) for n in player_nations),
        "position_groups": tuple(str(g).lower() for g in groups if g),
        "_prepared": True,
    }


def _passes_filters(player: Any, filters: dict[str, Any] | None) -> bool:
    if not filters:
        return True
    prepared = filters if filters.get("_prepared") else prepare_filters(filters)
    if not prepared:
        return True

    age = player.age
    age_min = prepared.get("age_min")
    age_max = prepared.get("age_max")
    if age_min is not None and age is not None and age < int(age_min):
        return False
    if age_max is not None and age is not None and age > int(age_max):
        return False

    height_in = _height_total_inches(getattr(player, "height_cm", None))
    height_min = prepared.get("height_min_in")
    height_max = prepared.get("height_max_in")
    if height_min is not None and height_in is not None and height_in < int(height_min):
        return False
    if height_max is not None and height_in is not None and height_in > int(height_max):
        return False

    club_contains = prepared.get("club_contains") or ""
    if club_contains:
        if club_contains not in _club_search_text(player):
            return False

    club_nations = prepared.get("club_nation_ids") or frozenset()
    if club_nations:
        club_nation = player.club_nation_id
        if club_nation is None or int(club_nation) not in club_nations:
            return False

    player_nations = prepared.get("nation_ids") or frozenset()
    if player_nations:
        nation = player.nation_id
        if nation is None or int(nation) not in player_nations:
            return False

    groups = prepared.get("position_groups") or ()
    if groups and not _player_in_pos_groups(player.natural_positions, groups):
        return False

    return True


def _filters_active(filters: dict[str, Any] | None) -> bool:
    """True when at least one filter constraint is set."""
    if not filters:
        return False
    prepared = filters if filters.get("_prepared") else filters
    if prepared.get("age_min") is not None or prepared.get("age_max") is not None:
        return True
    if prepared.get("height_min_in") is not None or prepared.get("height_max_in") is not None:
        return True
    club = prepared.get("club_contains") or ""
    if isinstance(club, str) and club.strip():
        return True
    if prepared.get("club_nation_ids") or prepared.get("nation_ids"):
        return True
    if prepared.get("position_groups"):
        return True
    return False


def _normalize_scope(scope: str) -> Scope:
    if scope == _LEGACY_FILTERED_SCOPE:
        return "all"
    if scope in {"squad", "all"}:
        return scope  # type: ignore[return-value]
    return "squad"


# Export-ready player records from the last preloaded save (not Dash-storeable).
# fmsave hands out dataclasses that remain valid after the save context closes.
_preload_lock = threading.Lock()
_preload_cache: dict[str, Any] | None = None
_SCOPED_DIVISION_CLUB_LIMIT = 32


def clear_preload_cache() -> None:
    global _preload_cache
    with _preload_lock:
        _preload_cache = None


def _player_filter_snapshot(player: Any) -> SimpleNamespace:
    """Test helper: lightweight stand-in with the fields live counts need."""
    return SimpleNamespace(
        age=getattr(player, "age", None),
        height_cm=getattr(player, "height_cm", None),
        club_name=getattr(player, "club_name", None) or "",
        on_loan=bool(getattr(player, "on_loan", False)),
        loan_parent_club_name=getattr(player, "loan_parent_club_name", None) or "",
        club_nation_id=getattr(player, "club_nation_id", None),
        nation_id=getattr(player, "nation_id", None),
        natural_positions=tuple(getattr(player, "natural_positions", None) or ()),
        club_uid=getattr(player, "club_uid", None),
    )


def _preload_cache_key(path: Path) -> tuple[str, int]:
    return str(path.resolve()), int(path.stat().st_mtime_ns)


def _preload_public_meta(entry: dict[str, Any]) -> dict[str, Any]:
    return dict(entry.get("meta") or {})


def _players_for_club(players: list[Any], club_uid: int | None) -> list[Any]:
    if club_uid is None:
        return []
    wanted = int(club_uid)
    return [
        player
        for player in players
        if getattr(player, "club_uid", None) is not None
        and int(player.club_uid) == wanted
    ]


def _scope_player_list(
    entry: dict[str, Any],
    *,
    scope_key: Scope,
) -> list[Any]:
    """Return the cached all/squad list without copying."""
    by_scope = entry.get("by_scope") or {}
    scoped = by_scope.get(scope_key)
    if scoped is not None:
        return scoped
    players = entry.get("players") or []
    if scope_key != "squad":
        return players
    return _players_for_club(players, entry.get("managed_club_uid"))


def _export_ready_players(entry: dict[str, Any]) -> bool:
    """True when preload kept full fmsave Player records (not test snapshots)."""
    if entry.get("export_ready"):
        return True
    players = entry.get("players") or []
    if not players:
        return False
    sample = players[0]
    return hasattr(sample, "attributes") and hasattr(sample, "uid")


def get_preloaded_save(save_path: str) -> dict[str, Any] | None:
    """Return public preload meta when ``save_path`` matches the in-memory cache."""
    path = Path(save_path).expanduser()
    if not path.is_file():
        return None
    key = _preload_cache_key(path)
    with _preload_lock:
        entry = _preload_cache
    if not entry or entry.get("key") != key:
        return None
    return _preload_public_meta(entry)


def preload_save_players(save_path: str) -> dict[str, Any]:
    """Open a save once and cache export-ready players for live counts + generate.

    Returns public meta (no player payloads). Raises on I/O / fmsave errors.
    """
    global _preload_cache
    import fmsave

    path = Path(save_path).expanduser()
    if not path.is_file():
        raise FileNotFoundError(f"Save file not found: {path}")

    key = _preload_cache_key(path)
    with _preload_lock:
        entry = _preload_cache
    if entry and entry.get("key") == key:
        return _preload_public_meta(entry)

    import services.compute_progress as compute_progress

    compute_progress.update(phase="Opening save…", done=0, total=0)
    competition_names = competition_name_map() or None
    started = time.perf_counter()

    managed_club_uid = None
    managed_club_name = ""
    game_date = None
    game_label = ""
    game_build = ""
    players: list[Any] = []

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with fmsave.open(path, competition_names=competition_names) as career_save:
            info = career_save.info
            game_date = info.game_date
            game_label = str(getattr(info, "game", "") or "")
            game_build = str(getattr(info, "build", "") or "")
            managed = career_save.managed_clubs()
            if managed:
                managed_club_uid = managed[0].club_uid
                managed_club_name = str(
                    getattr(managed[0], "club_name", None)
                    or getattr(managed[0], "name", None)
                    or ""
                )
            compute_progress.update(phase="Loading players…")
            with _track_player_load_progress():
                # Materialize full Player dataclasses; they remain valid after close.
                players = list(career_save.players())

    squad_players = _players_for_club(players, managed_club_uid)
    meta = {
        "ok": True,
        "save_path": str(path.resolve()),
        "save_total": len(players),
        "squad_total": len(squad_players),
        "managed_club_uid": managed_club_uid,
        "managed_club_name": managed_club_name or None,
        "game_date": game_date.isoformat() if game_date else None,
        "game": game_label or None,
        "build": game_build or None,
        "elapsed_ms": int((time.perf_counter() - started) * 1000),
    }
    new_entry = {
        "key": key,
        "players": players,
        "by_scope": {
            "all": players,
            "squad": squad_players,
        },
        "export_ready": True,
        "managed_club_uid": managed_club_uid,
        "meta": meta,
    }
    with _preload_lock:
        _preload_cache = new_entry
    return dict(meta)


def count_matching_players(
    save_path: str,
    *,
    scope: str = "squad",
    filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Count preloaded players that match scope + filters (fast, in-memory)."""
    path = Path(save_path).expanduser()
    if not path.is_file():
        raise FileNotFoundError(f"Save file not found: {path}")
    key = _preload_cache_key(path)
    with _preload_lock:
        entry = _preload_cache
    if not entry or entry.get("key") != key:
        raise LookupError("Save is not preloaded. Choose the save again.")

    scope_key = _normalize_scope(scope)
    managed_club_uid = entry.get("managed_club_uid")
    prepared = prepare_filters(filters)
    if scope_key == "squad" and managed_club_uid is None:
        return {
            "ok": False,
            "error": (
                "No managed club in this save (between jobs?). "
                "Use All players instead."
            ),
            "matched": 0,
            "scope_total": 0,
            "save_total": int((entry.get("meta") or {}).get("save_total") or 0),
            "scope": scope_key,
            "filters_active": _filters_active(prepared),
        }

    scoped = _scope_player_list(entry, scope_key=scope_key)
    if _filters_active(prepared):
        matched = sum(1 for player in scoped if _passes_filters(player, prepared))
    else:
        matched = len(scoped)
    return {
        "ok": True,
        "matched": matched,
        "scope_total": len(scoped),
        "save_total": int((entry.get("meta") or {}).get("save_total") or len(entry["players"])),
        "scope": scope_key,
        "filters_active": _filters_active(prepared),
        "managed_club_name": (entry.get("meta") or {}).get("managed_club_name"),
    }


def _take_preloaded_export_players(
    save_path: str,
    *,
    scope: str,
    filters: dict[str, Any] | None,
) -> list[Any] | None:
    """Return scoped/filtered export-ready players from preload, or None."""
    path = Path(save_path).expanduser()
    if not path.is_file():
        return None
    key = _preload_cache_key(path)
    with _preload_lock:
        entry = _preload_cache
    if not entry or entry.get("key") != key or not _export_ready_players(entry):
        return None

    scope_key = _normalize_scope(scope)
    if scope_key == "squad" and entry.get("managed_club_uid") is None:
        raise ValueError(
            "No managed club in this save (between jobs?). "
            "Use All players instead."
        )

    prepared = prepare_filters(filters)
    scoped = _scope_player_list(entry, scope_key=scope_key)
    if _filters_active(prepared):
        return [player for player in scoped if _passes_filters(player, prepared)]
    return list(scoped)


def _export_filename(
    scope_key: str,
    save_path: Path,
    game_date: date | None,
) -> str:
    """Uploads/download name: ``fmsave_{scope}_{stem}_{YYYY-MM}.csv`` when dated."""
    stem = save_path.stem or "export"
    if game_date is not None:
        return f"fmsave_{scope_key}_{stem}_{game_date.year:04d}-{game_date.month:02d}.csv"
    return f"fmsave_{scope_key}_{stem}.csv"


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


def _season_has_minutes(stats: Any | None) -> bool:
    return stats is not None and int(getattr(stats, "minutes", 0) or 0) > 0


def _pick_history_row(
    rows: list[Any],
    *,
    club_uid: int | None,
) -> Any | None:
    """Newest archived OVERALL row with minutes, preferring the current club."""
    if not rows:
        return None
    usable = [r for r in rows if int(getattr(r, "minutes", 0) or 0) > 0]
    pool = usable or rows

    def _key(row: Any) -> tuple[int, int]:
        return (
            int(getattr(row, "season_year", 0) or 0),
            int(getattr(row, "minutes", 0) or 0),
        )

    if club_uid is not None:
        same = [r for r in pool if getattr(r, "club_uid", None) == club_uid]
        if same:
            return max(same, key=_key)
    return max(pool, key=_key)


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


def _is_cupish_competition_name(name: str | None) -> bool:
    """True for continental / cup / friendly labels that must not become Division."""
    low = (name or "").strip().casefold()
    if not low:
        return False
    return any(part in low for part in _CUPISH_NAME_PARTS)


def _unadded_league_label(nation_id: int | None) -> str:
    """Placeholder Division when no domestic league table/fixture vote exists."""
    nation = _nation_display_name(nation_id).strip()
    if nation:
        return f"Unadded {nation} League"
    return "Unadded League"


def _club_nation_id(club: Any) -> int | None:
    raw = getattr(club, "nation_id", None)
    if raw is None:
        raw = getattr(club, "fa_nation_id", None)
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _pick_named_competition(counts: Counter[tuple[int | None, str | None]]) -> str:
    """Choose a domestic league name from fixture counts (cups/continentals excluded)."""
    scored: list[tuple[int, str]] = []
    for (_cid, name), n in counts.items():
        label = (name or "").strip()
        if not label or _is_cupish_competition_name(label):
            continue
        scored.append((-int(n), label))
    if not scored:
        return ""
    scored.sort()
    return scored[0][1]


def _safe_table(reader: Any, *errors: type[BaseException]) -> Any:
    """Return ``reader()`` or an empty table when FM27/strict checks refuse the section."""
    try:
        return reader()
    except errors:
        return ()


def _club_slot0_team_id(club: Any) -> int | None:
    for team in getattr(club, "teams", None) or ():
        if getattr(team, "slot", None) != 0:
            continue
        team_id = getattr(team, "team_id", None)
        if team_id is None:
            return None
        return int(team_id)
    return None


def _lookup_clubs_by_uid(clubs_table: Any, club_uids: set[int]) -> dict[int, Any]:
    """Resolve club records for a small uid set (indexed lookup when available)."""
    out: dict[int, Any] = {}
    if not club_uids:
        return out
    get_by_uid = getattr(clubs_table, "get_by_uid", None)
    if callable(get_by_uid):
        for uid in club_uids:
            try:
                club = get_by_uid(uid)
            except KeyError:
                club = None
            if club is not None:
                out[uid] = club
        return out
    for club in clubs_table or ():
        club_uid = getattr(club, "uid", None)
        if club_uid is None:
            continue
        uid = int(club_uid)
        if uid in club_uids:
            out[uid] = club
            if len(out) >= len(club_uids):
                break
    return out


def _build_club_divisions_scoped(
    career_save: Any,
    wanted: set[int],
    reader_errors: tuple[type[BaseException], ...],
) -> dict[int, str]:
    """Division labels for a small club set — skip global fixture/club sweeps when possible."""
    club_division: dict[int, str] = {}

    for table in _safe_table(career_save.league_tables, *reader_errors):
        if len(club_division) >= len(wanted):
            break
        if not _is_division_shaped(table):
            continue
        rows = tuple(table.rows or ())
        slot0 = [row for row in rows if getattr(row, "team_slot", None) == 0]
        n = int(getattr(table, "club_count", 0) or 0)
        if len(slot0) < max(8, n // 2):
            continue
        name = (getattr(table, "competition_name", None) or "").strip()
        if not name or _is_cupish_competition_name(name):
            # Nameless / cup tables: defer to per-club domestic fixture fallback.
            continue
        for row in slot0:
            club_uid = getattr(row, "club_uid", None)
            if club_uid is None:
                continue
            uid = int(club_uid)
            if uid in wanted:
                club_division.setdefault(uid, name)

    missing = wanted - club_division.keys()
    if not missing:
        return club_division

    clubs_table = _safe_table(career_save.clubs, *reader_errors)
    clubs_by_uid = _lookup_clubs_by_uid(clubs_table, missing)
    team_to_club: dict[int, int] = {}
    for uid in missing:
        club = clubs_by_uid.get(uid)
        if club is None:
            continue
        team_id = _club_slot0_team_id(club)
        if team_id is not None:
            team_to_club[team_id] = uid

    fx_by_team: dict[int, Counter[tuple[int | None, str | None]]] = defaultdict(Counter)
    if team_to_club:
        interest = frozenset(team_to_club)
        for fixture in _safe_table(career_save.fixtures, *reader_errors):
            for team_id, competition_id, competition_name in (
                (fixture.home_team_id, fixture.competition_id, fixture.competition_name),
                (fixture.away_team_id, fixture.competition_id, fixture.competition_name),
            ):
                if team_id is None or competition_id is None:
                    continue
                tid = int(team_id)
                if tid not in interest:
                    continue
                fx_by_team[tid][(competition_id, competition_name)] += 1

    for team_id, club_uid in team_to_club.items():
        if club_uid in club_division:
            continue
        name = _pick_named_competition(fx_by_team.get(team_id, Counter()))
        if name:
            club_division[club_uid] = name

    for uid in wanted - club_division.keys():
        club = clubs_by_uid.get(uid)
        club_division[uid] = _unadded_league_label(
            _club_nation_id(club) if club is not None else None
        )
    return club_division


def _build_club_divisions(
    career_save: Any,
    club_uids: set[int] | frozenset[int] | None = None,
) -> dict[int, str]:
    """Map club_uid → domestic Division label for Moneyball.

    League tables do not store a competition; fmsave votes one from fixtures, and that vote
    often lands on an unnamed id. Prefer division-shaped first-team tables, revoting the name
    from member fixtures when needed, then fall back to each club's slot-0 fixture majority
    (cups / continentals / friendlies excluded). Clubs still without a domestic league get
    ``Unadded {Nation} League``.

    When ``club_uids`` is a small set (squad / filtered exports), use a scoped path that
    skips unnamed-table fixture voting and only accumulates fixtures for missing clubs.

    On FM27 a failed reader check stops that reader even with ``strict=False``, so fixtures /
    league tables / clubs may raise; leave Division blank rather than aborting the export.
    """
    import fmsave

    reader_errors = (fmsave.ReaderCheckError, fmsave.UnsupportedGameError)
    if club_uids is not None:
        wanted = {int(uid) for uid in club_uids}
        if not wanted:
            return {}
        if len(wanted) <= _SCOPED_DIVISION_CLUB_LIMIT:
            return _build_club_divisions_scoped(career_save, wanted, reader_errors)

    fx_by_team: dict[int, Counter[tuple[int | None, str | None]]] = defaultdict(Counter)
    for fixture in _safe_table(career_save.fixtures, *reader_errors):
        for team_id, competition_id, competition_name in (
            (fixture.home_team_id, fixture.competition_id, fixture.competition_name),
            (fixture.away_team_id, fixture.competition_id, fixture.competition_name),
        ):
            if team_id is None or competition_id is None:
                continue
            fx_by_team[int(team_id)][(competition_id, competition_name)] += 1

    club_division: dict[int, str] = {}
    for table in _safe_table(career_save.league_tables, *reader_errors):
        if not _is_division_shaped(table):
            continue
        rows = tuple(table.rows or ())
        slot0 = [row for row in rows if getattr(row, "team_slot", None) == 0]
        n = int(getattr(table, "club_count", 0) or 0)
        if len(slot0) < max(8, n // 2):
            continue
        name = (getattr(table, "competition_name", None) or "").strip()
        if _is_cupish_competition_name(name):
            continue
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
            uid = int(club_uid)
            if club_uids is not None and uid not in club_uids:
                continue
            club_division.setdefault(uid, name)

    if club_uids is not None and len(club_division) >= len(club_uids):
        return club_division

    for club in _safe_table(career_save.clubs, *reader_errors):
        club_uid = getattr(club, "uid", None)
        if club_uid is None:
            continue
        uid = int(club_uid)
        if club_uids is not None and uid not in club_uids:
            continue
        if uid in club_division:
            continue
        team_id = _club_slot0_team_id(club)
        name = ""
        if team_id is not None:
            name = _pick_named_competition(fx_by_team.get(team_id, Counter()))
        club_division[uid] = name or _unadded_league_label(_club_nation_id(club))
        if club_uids is not None and len(club_division) >= len(club_uids):
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
        "xG-OP": "",
        "NP-xG": "",
        "NP-xG/90": "",
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
        "Possession Lost per 90": "",
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
    fouls_90 = None
    minutes = int(stats.minutes or 0)
    if minutes > 0 and stats.fouls_made is not None:
        fouls_90 = (float(stats.fouls_made) * 90.0) / minutes

    xg_op = None
    if stats.goals is not None and stats.expected_goals is not None:
        xg_op = float(stats.goals) - float(stats.expected_goals)

    return {
        "Appearances": _num(apps),
        "Minutes": _num(stats.minutes),
        "Goals": _num(stats.goals),
        "Goals per 90 minutes": _num(stats.goals_per_90, digits=3),
        "Assists": _num(stats.assists),
        "Asts/90": _num(stats.assists_per_90, digits=3),
        "xG": _num(stats.expected_goals, digits=2),
        "xG/90": _num(stats.expected_goals_per_90, digits=3),
        "xG-OP": _num(xg_op, digits=2),
        "NP-xG": _num(stats.non_penalty_expected_goals, digits=2),
        "NP-xG/90": _num(stats.non_penalty_expected_goals_per_90, digits=3),
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
        "Progressive Passes per 90": _num(stats.progressive_passes_per_90, digits=3),
        "PsP": _num(stats.progressive_passes),
        "Possession Won per 90": _num(stats.possession_won_per_90, digits=3),
        "Possession Lost per 90": _num(stats.possession_lost_per_90, digits=3),
        "Interceptions": _num(stats.interceptions),
        "Interceptions per 90": _num(stats.interceptions_per_90, digits=3),
        "Clearances": _num(stats.clearances),
        "Clearances per 90": _num(stats.clearances_per_90, digits=3),
        "Blk": _num(stats.blocks),
        "Blk/90": _num(stats.blocks_per_90, digits=3),
        "Headers Won": _num(stats.headers_won),
        "Headers Won per 90": _num(stats.headers_won_per_90, digits=3),
        "Headers Attempted": _num(stats.aerial_challenges_attempted),
        "Headers Attempted per 90": _num(
            stats.aerial_challenges_attempted_per_90, digits=3
        ),
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
        "Open Play Crosses Completed": _num(stats.open_play_crosses_completed),
        "OP Cr C/90": _num(stats.open_play_crosses_completed_per_90, digits=3),
        "Sprints": _num(stats.high_intensity_sprints),
        "Sprints per 90": _num(stats.high_intensity_sprints_per_90, digits=3),
        "Goals Allowed": _num(stats.goals_allowed),
        "xGP": _num(stats.expected_goals_prevented, digits=2),
        "xGP/90": _num(stats.expected_goals_prevented_per_90, digits=3),
        "Rating": _num(stats.average_rating, digits=2),
        "Yellow Cards": _num(stats.yellow_cards),
        "Red Cards": _num(stats.red_cards),
        "Fouls Made": _num(stats.fouls_made),
        "Fouls Made per 90": _num(fouls_90, digits=3),
    }


def _format_injury_date(value: date | None) -> str:
    if value is None:
        return ""
    return f"{value.month}/{value.day}/{value.year}"


def _format_time_missed(days: int | None) -> str:
    if days is None or days <= 0:
        return ""
    if days == 1:
        return "1 day"
    if days % 7 == 0:
        weeks = days // 7
        return "1 week" if weeks == 1 else f"{weeks} weeks"
    return f"{days} days"


def _empty_injury_columns() -> dict[str, str]:
    return {col: "" for col in _INJURY_COLUMNS}


def _injury_columns_for_player(
    injury_by_uid: dict[int, dict[str, str]] | None,
    player_uid: int | None,
) -> dict[str, str]:
    if injury_by_uid and player_uid is not None:
        found = injury_by_uid.get(int(player_uid))
        if found:
            return {col: found.get(col, "") for col in _INJURY_COLUMNS}
    return _empty_injury_columns()


def _build_current_injury_by_uid(
    career_save: Any,
    *,
    game_date: date | None,
    uid_set: frozenset[int],
) -> dict[int, dict[str, str]]:
    """Map player uid → Moneyball Injury / Injured On / Time Missed for open injuries.

    Current episodes are fmsave ``TYPED`` rows whose return date is on/after the
    in-game date. ``Injured On`` / ``Time Missed`` come from the latest matching
    ``HISTORY`` row on or before that return date (same pairing fmsave documents).
    """
    if game_date is None or not uid_set:
        return {}
    try:
        import fmsave
        from fmsave.models.injuries import InjuryRecordKind
    except ImportError:
        return {}

    typed_by_uid: dict[int, Any] = {}
    history_by_uid: dict[int, list[Any]] = {}
    try:
        for record in career_save.injuries():
            player_uid = getattr(record, "player_uid", None)
            if player_uid is None or int(player_uid) not in uid_set:
                continue
            uid = int(player_uid)
            kind = getattr(record, "kind", None)
            if kind == InjuryRecordKind.TYPED or kind == "typed":
                ret = getattr(record, "date", None)
                if ret is None or ret < game_date:
                    continue
                previous = typed_by_uid.get(uid)
                # Furthest return date wins when multiple open episodes exist.
                if previous is None or (
                    getattr(previous, "date", None) is not None
                    and ret > previous.date
                ):
                    typed_by_uid[uid] = record
            elif kind == InjuryRecordKind.HISTORY or kind == "history":
                history_by_uid.setdefault(uid, []).append(record)
    except (fmsave.ReaderCheckError, fmsave.UnsupportedGameError, OSError, ValueError):
        # Missing / unreadable injury section: leave Injury blank rather than fail export.
        return {}

    out: dict[int, dict[str, str]] = {}
    for uid, typed in typed_by_uid.items():
        type_name = (getattr(typed, "type_name", None) or "").strip()
        injury_label = type_name or "Injured"
        injured_on = ""
        time_missed = ""
        typed_date = getattr(typed, "date", None)
        before_dates = [
            row.date
            for row in history_by_uid.get(uid, ())
            if getattr(row, "date", None) is not None
            and typed_date is not None
            and row.date <= typed_date
        ]
        if before_dates and typed_date is not None:
            onset = max(before_dates)
            injured_on = _format_injury_date(onset)
            time_missed = _format_time_missed((typed_date - onset).days)
        out[uid] = {
            "Injury": injury_label,
            "Injured On": injured_on,
            "Time Missed": time_missed,
            "Recurring Injury": "",
        }
    return out


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
    based_in = _nation_display_name(getattr(player, "club_fa_nation_id", None))
    if not based_in:
        based_in = _nation_display_name(getattr(player, "club_nation_id", None))
    return {
        "Player": player.name or "",
        "Unique ID": "" if player.unique_id is None else str(player.unique_id),
        "Age": "" if player.age is None else str(player.age),
        "Club": _format_club_display(player),
        "Division": division or "",
        "Nation": _nation_code(getattr(player, "nation_id", None)),
        "Based In": based_in,
        "2nd Nat": _second_nation_codes(getattr(player, "second_nation_ids", None)),
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
    injury_by_uid: dict[int, dict[str, str]] | None = None,
) -> dict[str, str]:
    row: dict[str, str] = {}
    row.update(_identity_columns(player, division=division))
    row.update(
        _injury_columns_for_player(injury_by_uid, getattr(player, "uid", None))
    )
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
        "2nd Nat",
        "Best Pos",
        "Position",
        "Sec. Position",
        "Height",
        "Injury",
        "Injured On",
        "Time Missed",
        "Recurring Injury",
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
        "xG-OP",
        "NP-xG",
        "NP-xG/90",
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
        "Possession Lost per 90",
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
    prepared = prepare_filters(filters)
    started = time.perf_counter()
    rows: list[dict[str, str]] = []
    competition_names = competition_name_map() or None

    import services.compute_progress as compute_progress

    compute_progress.update(phase="Opening save…", done=0, total=0)

    reused_players = _take_preloaded_export_players(
        str(path),
        scope=scope_key,
        filters=prepared,
    )
    players_from_preload = reused_players is not None

    game_date: date | None = None
    game_label = ""
    game_build = ""
    known_build: bool | None = None
    with warnings.catch_warnings():
        # UnknownBuildWarning fires for every FM27 open (fields unconfirmed) and unverified builds.
        warnings.simplefilter("ignore")
        with fmsave.open(path, competition_names=competition_names) as career_save:
            info = career_save.info
            game_date = info.game_date
            game_label = str(getattr(info, "game", "") or "")
            game_build = str(getattr(info, "build", "") or "")
            known_build = getattr(info, "known_build", None)

            if players_from_preload:
                player_list = reused_players or []
                compute_progress.update(
                    phase="Using preloaded players…",
                    done=len(player_list),
                    total=len(player_list),
                )
            else:
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

                    if _filters_active(prepared):
                        players = players.filter(
                            lambda player: _passes_filters(player, prepared)
                        )

                    player_list = list(players)

            uid_set = frozenset(p.uid for p in player_list)
            club_uid_set = {
                int(p.club_uid)
                for p in player_list
                if getattr(p, "club_uid", None) is not None
            }
            compute_progress.update(phase="Resolving divisions…")
            club_divisions = _build_club_divisions(
                career_save,
                club_uid_set if club_uid_set else set(),
            )

            compute_progress.update(
                phase="Loading season stats…",
                done=0,
                total=len(player_list),
            )

            season_by_uid: dict[int, list[Any]] = {}
            try:
                for record in career_save.player_season_stats().where(
                    kind=SeasonStatsKind.OVERALL
                ):
                    if record.player_uid not in uid_set:
                        continue
                    season_by_uid.setdefault(record.player_uid, []).append(record)
            except (fmsave.ReaderCheckError, fmsave.UnsupportedGameError):
                # FM27 stops a failed reader even with strict=False.
                season_by_uid = {}

            history_by_uid: dict[int, list[Any]] = {}
            need_history_uids = {
                player.uid
                for player in player_list
                if not _season_has_minutes(
                    _pick_season_row(
                        season_by_uid.get(player.uid, []),
                        club_uid=player.club_uid,
                    )
                )
            }
            if need_history_uids:
                need_history_uids_frozen = frozenset(need_history_uids)
                compute_progress.update(
                    phase="Loading season history…",
                    done=0,
                    total=len(need_history_uids_frozen),
                )
                try:
                    for record in career_save.player_season_history().where(
                        kind=SeasonStatsKind.OVERALL
                    ):
                        if record.player_uid not in need_history_uids_frozen:
                            continue
                        history_by_uid.setdefault(record.player_uid, []).append(
                            record
                        )
                except (fmsave.ReaderCheckError, fmsave.UnsupportedGameError):
                    history_by_uid = {}

            compute_progress.update(phase="Loading injuries…")
            injury_by_uid = _build_current_injury_by_uid(
                career_save,
                game_date=game_date,
                uid_set=uid_set,
            )

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
                if not _season_has_minutes(season):
                    season = (
                        _pick_history_row(
                            history_by_uid.get(player.uid, []),
                            club_uid=player.club_uid,
                        )
                        or season
                    )
                division = ""
                if player.club_uid is not None:
                    division = club_divisions.get(int(player.club_uid), "")
                rows.append(
                    _player_row(
                        player,
                        season,
                        division=division,
                        injury_by_uid=injury_by_uid,
                    )
                )
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
        "filters_active": _filters_active(prepared),
        "players_from_preload": players_from_preload,
        "save_path": str(path),
        "game_date": game_date.isoformat() if game_date else None,
        "game": game_label or None,
        "build": game_build or None,
        "known_build": known_build,
        "eligibility": eligibility,
        "mapped_columns": mapped,
        "blank_columns": list(BLANK_COLUMNS),
        "filename": _export_filename(scope_key, path, game_date),
    }
    return csv_text, meta
