"""Export FM26 save players to Moneyball-compatible CSV via fmsave."""
from __future__ import annotations

import io
import sys
import time
import warnings
from datetime import date
from pathlib import Path
from typing import Any, Literal

import pandas as pd

Scope = Literal["squad", "all", "filtered"]

# Intentionally blank in v1 — save has no display labels / name maps.
BLANK_COLUMNS: tuple[str, ...] = (
    "Personality",
    "Media Handling",
    "Nation",
    "Based In",
    "Division",
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


def _combine_positions(codes: tuple[str, ...] | list[str] | None) -> str:
    """Turn ('AML','AMR') into ``AM (LR)``-style Moneyball Position text."""
    if not codes:
        return ""
    labels = [_pos_label(c) for c in codes]
    # Group by stem before " ("
    groups: dict[str, list[str]] = {}
    order: list[str] = []
    for label in labels:
        if label in {"GK", "SW", "DM"} or " (" not in label:
            if label not in groups:
                groups[label] = []
                order.append(label)
            continue
        stem, rest = label.split(" (", 1)
        side = rest.rstrip(")")
        if stem not in groups:
            groups[stem] = []
            order.append(stem)
        if side and side not in groups[stem]:
            groups[stem].append(side)
    parts: list[str] = []
    for stem in order:
        sides = groups[stem]
        if not sides:
            parts.append(stem)
        else:
            # Prefer L then C then R order
            ranked = sorted(
                sides,
                key=lambda s: {"L": 0, "C": 1, "R": 2}.get(s, 9),
            )
            parts.append(f"{stem} ({''.join(ranked)})")
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

    groups = filters.get("position_groups") or []
    if groups and not _player_in_pos_groups(player.natural_positions, list(groups)):
        return False

    return True


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


def _identity_columns(player: Any) -> dict[str, str]:
    ability = getattr(player, "ability", None)
    reputation = getattr(player, "reputation", None)
    return {
        "Player": player.name or "",
        "Unique ID": "" if player.unique_id is None else str(player.unique_id),
        "Age": "" if player.age is None else str(player.age),
        "Club": player.club_name or "",
        "Best Pos": _best_pos(player.natural_positions),
        "Position": _combine_positions(player.natural_positions),
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


def _player_row(player: Any, season: Any | None) -> dict[str, str]:
    row: dict[str, str] = {}
    row.update(_identity_columns(player))
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


def export_moneyball_csv(
    save_path: str,
    *,
    scope: Scope = "squad",
    filters: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Return ``(csv_text, meta)`` with Moneyball headers (``;`` delimiter)."""
    import fmsave
    from fmsave.models.season_stats import SeasonStatsKind
    from services.export_library import classify_eligibility

    path = Path(save_path).expanduser()
    if not path.is_file():
        raise FileNotFoundError(f"Save file not found: {path}")

    started = time.perf_counter()
    rows: list[dict[str, str]] = []

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with fmsave.open(path) as career_save:
            if scope == "squad":
                managed = career_save.managed_clubs()
                if not managed:
                    raise ValueError(
                        "No managed club in this save (between jobs?). "
                        "Use All players or Filtered instead."
                    )
                club_uid = managed[0].club_uid
                players = career_save.players().where(club_uid=club_uid)
            else:
                players = career_save.players()
                if scope == "filtered":
                    players = players.filter(
                        lambda player: _passes_filters(player, filters)
                    )

            player_list = list(players)
            uid_set = {p.uid for p in player_list}

            season_by_uid: dict[int, list[Any]] = {}
            for record in career_save.player_season_stats():
                if record.player_uid not in uid_set:
                    continue
                if record.kind != SeasonStatsKind.OVERALL:
                    continue
                season_by_uid.setdefault(record.player_uid, []).append(record)

            for player in player_list:
                season = _pick_season_row(
                    season_by_uid.get(player.uid, []),
                    club_uid=player.club_uid,
                )
                rows.append(_player_row(player, season))

    if not rows:
        raise ValueError("No players matched the selected scope/filters.")

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
        "scope": scope,
        "save_path": str(path),
        "eligibility": eligibility,
        "mapped_columns": mapped,
        "blank_columns": list(BLANK_COLUMNS),
        "filename": f"fmsave_{scope}_{path.stem}.csv",
    }
    return csv_text, meta
