"""Saved player profiles from Role scores."""
from __future__ import annotations

import re
import time
import uuid
from html import escape as html_escape

from dash import ALL, Input, Output, State, callback, clientside_callback, ctx, dcc, html, no_update, register_page
import dash_bootstrap_components as dbc
import dash_mantine_components as dmc

from components.player_filters import help_icon
from components.player_detail import (
    player_attributes,
    player_role_fit_section,
    role_player_detail_card,
)
from components.player_modal import player_detail_body, player_modal
from components.player_table import (
    IDENTITY_TEXT_COLS,
    default_page_size_value,
    feet_cell,
    feet_sort_key,
    identity_data_styles,
    identity_header_name,
    injury_cell,
    injury_tooltip_entry,
    is_dark_theme,
    page_size_select_data,
    player_data_table,
    rec_grade_style,
    rec_sort_key,
    style_cell,
    style_cell_conditional,
    style_header,
    style_header_conditional,
    table_css,
)
from components.scouting_shell import (
    append_ordered_keys,
    as_list,
    clicked,
    merge_ordered_keys,
    pattern_matching_stubs,
)
from components.stats_compare import (
    compare_control_state,
    compare_status_children,
    compare_title,
    default_compare_eval_group,
    normalize_compare_eval_group,
    normalize_compare_view,
    stats_compare_body,
    stats_compare_modal,
)
from components.stats_player_pane import stats_charts_bottom_pane


def _pattern_click_triggered() -> bool:
    """True only for a real n_clicks change — not when ALL members remount/unmount."""
    if not isinstance(ctx.triggered_id, dict):
        return False
    if not ctx.triggered:
        return False
    item = ctx.triggered[0] or {}
    prop_id = str(item.get("prop_id") or "")
    if not prop_id.endswith(".n_clicks"):
        return False
    value = item.get("value")
    if value is None:
        return False
    try:
        return int(value) > 0
    except (TypeError, ValueError):
        return False
from scoring.comparison import score_display
from scoring.division_tiers import apply_division_tier, classify_division
from scoring.role_scorer import (
    FootStrength,
    apply_set_piece_scores,
    combo_column,
    combo_meta,
    foot_strength,
    group_abbr_tone,
    parse_combo_id,
    role_meta,
    score_band,
    to_int,
)
from scoring.stats_scorer import (
    adaptive_metric_bound_maps,
    category_abbr,
    minutes_color,
    minutes_status,
    percentile_color,
    resolve_player_pos_group,
    scoring_stats,
)
import services.export_library as lib
import services.formations as fm
import services.player_profiles as profiles
import services.ui_settings as us

register_page(__name__, path="/profiles", name="Profiles")

PF_PAGE_TIP = (
    "Each profile library holds its own saved players and depth chart. Create a profile with a "
    "formation, save marked players into it from Role scores, then rank them here. Use Update "
    "from saved file to refresh personal info, role scores, and percentiles from a library export."
)
PF_NEW_PROFILE_TIP = (
    "Name and formation are required. Formation sets the Squad depth layout for the new library."
)
PF_REPLACE_TIP = (
    "Replaces personal info, role scores, and percentiles for saved profiles that match by player "
    "name in the file (club changes are fine). Depth ranking and profile ids are kept. Only "
    "files eligible for Player stats are listed. Compute the file on Uploads first when the "
    "label says Stale."
)
PF_SQUAD_DEPTH_TIP = (
    "One card per formation position (up to 11). Save from Role scores queues exports "
    "until Refresh exports places them on the matching slot (one slot each, bottom of depth). "
    "Click a card to edit that role's depth; click again to return to the XI. "
    "Auto-rank sorts players still on the slot (Score, then Ovr). Removals stay off until "
    "Recently removed restore or a new Role-scores export."
)
PF_DEPTH_CHART_TIP = (
    "Focus a Squad depth card to rank that slot here (drag to reorder; × removes from slot only)."
)
PF_SET_PIECES_TIP = (
    "Top set-piece takers in this library. COR / DFK / IFK split into strong left and right foot "
    "(top 5 each). Slot shows best formation depth rank."
)
PF_STARTING_XI_TIP = (
    "Rank #1 or #2 per formation slot. Updates when slot depth changes or you switch First / "
    "Second XI — not when you focus a slot above."
)
PF_UNDO_TIP = "Restore adds a player back to the bottom of the same slot."

DEPTH_UNDO_MAX_DEFAULT = 10

# Skip reloading stats cohorts when library + percentile-related settings
# have not changed since the last refresh in this process.
_PF_PCT_FP: str | None = None
_PF_PCT_LOCK = __import__("threading").Lock()


FILTER_SORT_RESET_IDS = frozenset(
    {
        "pf-focus-role",
        "pf-formation-select",
    }
)


def _depth_heading(label: str, tip: str, help_id: str) -> html.Div:
    return html.Div(
        [
            html.Span(label, className="rs-depth-heading-label"),
            *help_icon(tip, help_id),
        ],
        className="rs-depth-heading-title-row",
    )


def _percentile_settings_fingerprint(settings) -> str:
    """Fingerprint for when stored profile Ovr/category % need a recompute."""
    import json

    settings = us.normalize(settings)
    payload = {
        "library": profiles.active_library_id() or "",
        "stats_thresholds": settings.get("stats_thresholds"),
        # Band cuts tint stored *_color fields on profile rows.
        "bands": settings.get("bands"),
    }
    return json.dumps(payload, sort_keys=True, default=str)


def _ensure_profile_percentiles(settings) -> None:
    """Refresh stored percentiles only when the fingerprint changes."""
    global _PF_PCT_FP
    fp = _percentile_settings_fingerprint(settings)
    if fp == _PF_PCT_FP:
        return
    with _PF_PCT_LOCK:
        if fp == _PF_PCT_FP:
            return
        try:
            profiles.refresh_profile_percentiles(settings)
        except Exception:
            pass
        _PF_PCT_FP = fp

PCT_COLS = ("overall", "defending", "final_third", "possession")
OVERALL_PCT_COL = {"id": "overall", "label": "Overall average", "abbr": "Ovr"}


def _pct_header_name(col_id: str) -> str:
    """Compact headers aligned with Player stats (Ovr, Def, F3 / GK, Poss)."""
    if col_id == OVERALL_PCT_COL["id"]:
        return OVERALL_PCT_COL["abbr"]
    text = category_abbr(col_id, group=None, dual_final_third=True)
    # Keep F3 / GK on one line; other dual labels can still wrap if needed.
    if col_id == "final_third":
        return text.replace(" / ", "/")
    return text.replace(" / ", " /\n")


TABLE_TEXT_COLS = IDENTITY_TEXT_COLS | {"Role"}


def _depth_rank_value(entry_or_row) -> int | None:
    if not isinstance(entry_or_row, dict):
        return None
    raw = entry_or_row.get("depth_rank")
    if raw in (None, "", "-", "—"):
        # Table rows stash the parsed rank on _rank_raw.
        raw = entry_or_row.get("_rank_raw")
    if raw in (None, "", "-", "—"):
        return None
    try:
        rank = int(raw)
    except (TypeError, ValueError):
        return None
    return rank if rank > 0 else None


def _strip_cell(value) -> str:
    text = "" if value is None else str(value)
    if "<" in text:
        text = re.sub(r"<[^>]+>", "", text)
    return text


def _cell_number(value) -> float:
    text = _strip_cell(value).strip()
    if not text or text in ("-", "—"):
        return float("nan")
    if "(" in text:
        text = text.split("(", 1)[0].strip()
    match = re.search(r"-?\d+(?:\.\d+)?", text.replace("%", ""))
    if not match:
        return float("nan")
    try:
        return float(match.group(0))
    except ValueError:
        return float("nan")


def _raw_float(value) -> float | None:
    if value in (None, "", "-", "—"):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:
        return None
    return number


def _profile_sort_key(column_id: str, row: dict) -> tuple:
    if column_id == "Role":
        text = str(row.get("_role_column") or row.get("Role") or "").strip()
        if not text or text in ("-", "—"):
            return (1, "\uffff")
        return (0, text.casefold())
    if column_id == "Rank":
        rank = row.get("_rank_raw")
        if rank is None:
            return (1, float("inf"))
        return (0, int(rank))
    if column_id == "Score":
        number = row.get("_score_raw")
    elif column_id == "Minutes":
        number = row.get("_minutes_raw")
    elif column_id in PCT_COLS:
        number = row.get(f"_{column_id}_raw")
    else:
        if column_id == "Feet":
            return feet_sort_key(row)
        if column_id == "Rec":
            return rec_sort_key(row.get(column_id))
        if column_id in TABLE_TEXT_COLS:
            text = _strip_cell(row.get(column_id)).strip()
            if not text or text in ("-", "—"):
                return (1, "\uffff")
            return (0, text.casefold())
        number = _cell_number(row.get(column_id))
    if number is None:
        return (1, float("inf"))
    try:
        number = float(number)
    except (TypeError, ValueError):
        return (1, float("inf"))
    if number != number:
        return (1, float("inf"))
    return (0, number)


def _is_percentile_sort_column(column_id: str) -> bool:
    if not column_id or column_id in TABLE_TEXT_COLS:
        return False
    if column_id in ("Feet", "Rec", "Minutes", "Age", "Height"):
        return False
    return column_id in PCT_COLS or column_id in ("Score",)


def _sort_profile_rows(rows: list[dict], sort_by, *, mode: str) -> list[dict]:
    out = list(rows)
    if sort_by:
        item = sort_by[0]
        column = item.get("column_id")
        reverse = item.get("direction") == "desc"
        if column == "Slot":

            def slot_key(row, *, _desc=reverse):
                order = row.get("_slot_order")
                if order is None:
                    label = str(row.get("Slot") or "").casefold()
                    return (1, 0, label)
                try:
                    value = int(order)
                except (TypeError, ValueError):
                    return (1, 0, str(order))
                return (0, -value if _desc else value, "")

            out.sort(key=slot_key)
            return out
        if column == "Rank":

            def rank_key(row, *, _desc=reverse):
                rank = row.get("_rank_raw")
                if rank is None:
                    return (1, 0)
                return (0, -int(rank) if _desc else int(rank))

            out.sort(key=rank_key)
            return out
        if _is_percentile_sort_column(column):

            def pct_key(row, *, _col=column, _desc=reverse):
                _prefix, number = _profile_sort_key(_col, row)
                if _prefix:
                    return (1, 0.0)
                return (0, -number if _desc else number)

            out.sort(key=pct_key)
            return out
        out.sort(
            key=lambda row: _profile_sort_key(column, row),
            reverse=reverse,
        )
        return out
    if mode == "formation":
        return sorted(
            out,
            key=lambda row: (
                1 if row.get("_slot_order") is None else 0,
                int(row.get("_slot_order") or 0),
            ),
        )
    if mode == "roles":
        return _sort_role_rows(out)
    return out


def _default_sort_by(mode: str) -> list[dict]:
    """Empty sort_by → mode default in _sort_profile_rows (roles: role/score/ovr)."""
    del mode
    return []


def _sort_by_signature(sort_by) -> tuple:
    """Comparable fingerprint so we can avoid echoing sort_by back to the table."""
    if not sort_by:
        return ()
    item = sort_by[0] if isinstance(sort_by, (list, tuple)) else sort_by
    if not isinstance(item, dict):
        return ()
    return (str(item.get("column_id") or ""), str(item.get("direction") or ""))


def _coerce_sort_by(
    sort_by,
    mode: str,
    column_ids: set[str],
    *,
    triggered_id,
    previous,
    reset_default: bool = False,
) -> list[dict]:
    default = _default_sort_by(mode)
    if reset_default:
        return default
    if not sort_by:
        if triggered_id == "pf-table":
            prev = (previous or [None])[0] or {}
            col = prev.get("column_id")
            if col in column_ids:
                return [{"column_id": col, "direction": "asc"}]
        return default
    column = (sort_by[0] or {}).get("column_id")
    if column in column_ids:
        return list(sort_by)
    return default

_ROLE_COLUMN_META: dict[str, dict] | None = None


def _pct_markdown(percentile, color=None) -> str:
    if percentile is None:
        return "—"
    text = f"{float(percentile):.0f}%"
    if not color:
        return (
            f'<span style="font-weight:750;font-variant-numeric:tabular-nums">'
            f"{text}</span>"
        )
    return (
        f'<span style="color:{color};font-weight:750;font-variant-numeric:tabular-nums">'
        f"{text}</span>"
    )


def _score_markdown(score, settings, theme=None) -> str:
    if score is None:
        return "—"
    settings = us.normalize(settings)
    try:
        band = score_band(float(score), **settings["bands"])
    except (TypeError, ValueError):
        return str(score)
    color = us.band_text_colors(settings, theme=theme).get(band)
    return score_display(score, None, enabled=False, color=color)


def _blank(value) -> str:
    if value in (None, "", "-", "—"):
        return "—"
    return str(value)


_PHASE_DISPLAY_SUFFIXES = ("-IP", "-OOP", "-GK")


def _strip_phase_suffix(label: str) -> str:
    """Drop -IP / -OOP / -GK from a display label (data id stays unchanged)."""
    text = str(label or "")
    for suffix in _PHASE_DISPLAY_SUFFIXES:
        if text.endswith(suffix):
            return text[: -len(suffix)]
    return text


def _role_display_label(column: str) -> str:
    """Short role label without phase tags (e.g. CF, CF+CM)."""
    text = str(column or "").strip()
    if not text or text in ("-", "—"):
        return "—"
    if "+" in text:
        ip, _, oop = text.partition("+")
        return f"{_strip_phase_suffix(ip)}+{_strip_phase_suffix(oop)}"
    return _strip_phase_suffix(text)


def _role_phase_colors(theme=None) -> dict[str, str]:
    """Match Role scores: IP green / OOP red / hybrid purple / GK amber."""
    dark = is_dark_theme(theme)
    return {
        "ip": "#3dff88" if dark else "#15803d",
        "oop": "#f87171" if dark else "#b91c1c",
        "gk": "#fbbf24" if dark else "#b45309",
        "combo": "#c4b5fd" if dark else "#6d28d9",
    }


def _role_cell_markdown(column: str, theme=None) -> str:
    label = _role_display_label(column)
    if label == "—":
        return "—"
    meta = _role_column_meta(column)
    tone = str(meta.get("tone") or "").strip().lower()
    if tone.startswith("ip"):
        tone = "ip"
    elif tone.startswith("oop"):
        tone = "oop"
    elif tone in ("combo", "hybrid"):
        tone = "combo"
    elif tone != "gk":
        tone = "gk" if not tone else tone
    color = _role_phase_colors(theme).get(tone) or _role_phase_colors(theme)["gk"]
    safe = (
        label.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    return (
        f'<span class="pf-role-cell pf-role-{tone}" style="color:{color}">'
        f"{safe}</span>"
    )


def _resolve_minutes_required(value, settings=None) -> float:
    settings = us.normalize(settings)
    if value is not None:
        try:
            return float(value)
        except (TypeError, ValueError):
            pass
    return float(us.default_minutes_required(settings))


def _minutes_cell(mins_raw, settings, *, minutes_required=None) -> str:
    if mins_raw in (None, "", "-", "—", "undefined", "null", "None"):
        return "—"
    try:
        mins_f = float(mins_raw)
    except (TypeError, ValueError):
        return _blank(mins_raw)
    if mins_f != mins_f:  # NaN
        return "—"
    required = _resolve_minutes_required(minutes_required, settings)
    status = minutes_status(mins_f, required)
    text = f"{int(mins_f):,}"
    color = minutes_color(status)
    if not color:
        return text
    return (
        f'<span style="color:{color};font-weight:650;font-variant-numeric:tabular-nums">'
        f"{text}</span>"
    )


def _profile_minutes_raw(entry: dict, raw: dict) -> Any:
    for source in (
        raw.get("Minutes"),
        raw.get("minutes"),
    ):
        if source not in (None, "", "-", "—", "undefined", "null", "None"):
            return source
    player = entry.get("player")
    if isinstance(player, dict):
        mins = player.get("minutes")
        if mins not in (None, "", "-", "—", "undefined", "null", "None"):
            return mins
    return None


def _focus_slot(value) -> dict | None:
    """Focused Squad depth slot: {slot, role, label} (at most one)."""
    if value is None or value == "":
        return None
    if isinstance(value, dict):
        role = str(value.get("role") or "").strip()
        if not role:
            return None
        try:
            slot = int(value.get("slot"))
        except (TypeError, ValueError):
            slot = 0
        return {
            "slot": slot,
            "role": role,
            "label": str(value.get("label") or "").strip(),
        }
    if isinstance(value, str):
        text = value.strip()
        return {"slot": -1, "role": text, "label": ""} if text else None
    if isinstance(value, (list, tuple)) and value:
        return _focus_slot(value[0])
    return None


def _focus_roles(value) -> list[str]:
    """Focused Squad depth role columns (at most one)."""
    slot = _focus_slot(value)
    return [slot["role"]] if slot else []


def _formation_slots(formation_id: str | None) -> list[dict]:
    """Filled formation slots in lineup order (up to 11), including duplicates."""
    if not formation_id or not fm.exists(formation_id):
        return []
    formation = fm.load(formation_id, persist=False)
    slots: list[dict] = []
    for index, raw in enumerate(formation.get("slots") or []):
        ip = str(raw.get("ip") or "").strip()
        oop = str(raw.get("oop") or "").strip()
        if not ip or not oop:
            continue
        column = combo_column(ip, oop)
        label = str(raw.get("label") or "").strip()
        if not label:
            label = str(raw.get("ip_pos") or "POS").strip().upper() or "POS"
        slots.append(
            {
                "index": index,
                "label": label,
                "column": column,
                "ip": ip,
                "oop": oop,
                "ip_pos": str(raw.get("ip_pos") or ""),
                "oop_pos": str(raw.get("oop_pos") or ""),
            }
        )
    label_counts: dict[str, int] = {}
    for slot in slots:
        label_counts[slot["label"]] = label_counts.get(slot["label"], 0) + 1
    label_seen: dict[str, int] = {}
    for slot in slots:
        label = slot["label"]
        label_seen[label] = label_seen.get(label, 0) + 1
        if label_counts[label] > 1:
            slot["display_label"] = f"{label} ({label_seen[label]})"
        else:
            slot["display_label"] = label
    return slots


def _entry_player_key(entry: dict | None) -> str:
    if not isinstance(entry, dict):
        return ""
    key = str(entry.get("player_key") or "").strip()
    if key:
        return key
    name, club = profiles.profile_identity(entry)
    if name:
        return f"{name}|{club}"
    return str(entry.get("id") or "").strip()


def _normalize_xi_view(value) -> str:
    """``first`` or ``second`` XI overview."""
    raw = str(value or "").strip().lower()
    return "second" if raw in ("2", "second", "xi2") else "first"


def _xi_rank(value) -> int:
    """1-based depth rank for the selected XI (First=1, Second=2)."""
    return 2 if _normalize_xi_view(value) == "second" else 1


def _xi_rank_index(value) -> int:
    return _xi_rank(value) - 1


def _xi_view_label(value) -> str:
    return "Second XI" if _normalize_xi_view(value) == "second" else "Starting XI"


def _xi_view_switcher(active=None) -> html.Div:
    current = _normalize_xi_view(active)
    buttons = []
    for value, label in (("first", "First XI"), ("second", "Second XI")):
        buttons.append(
            html.Button(
                label,
                id={"type": "pf-xi-view", "view": value},
                n_clicks=0,
                type="button",
                className="st-player-seg-btn"
                + (" active" if current == value else ""),
            )
        )
    return html.Div(
        buttons,
        className="st-player-seg pf-xi-view-seg",
        role="group",
        **{"aria-label": "Starting XI view"},
    )


SET_PIECE_TOP_N = 10
SET_PIECE_FOOT_TOP_N = 5
# Delivery / kick categories: split into left / right strong(+) takers.
SET_PIECE_FOOTED_IDS = frozenset({"corners", "dfk", "ifk"})
SET_PIECE_FOOT_MIN = FootStrength.STRONG


def _setpiece_profile_list(settings=None) -> list[dict]:
    return list(us.set_piece_profiles(settings))


def _normalize_setpiece_view(value, settings=None) -> str:
    pieces = _setpiece_profile_list(settings)
    ids = [str(p.get("id") or "") for p in pieces if p.get("id")]
    raw = str(value or "").strip().lower()
    if raw in ids:
        return raw
    return ids[0] if ids else "corners"


def _setpiece_profile(piece_id: str, settings=None) -> dict | None:
    target = _normalize_setpiece_view(piece_id, settings)
    for profile in _setpiece_profile_list(settings):
        if str(profile.get("id") or "") == target:
            return profile
    return None


def _setpiece_view_switcher(active=None, settings=None) -> html.Div:
    current = _normalize_setpiece_view(active, settings)
    buttons = []
    for profile in _setpiece_profile_list(settings):
        piece_id = str(profile.get("id") or "").strip()
        if not piece_id:
            continue
        abbr = str(profile.get("abbr") or profile.get("label") or piece_id).strip()
        label = str(profile.get("label") or abbr).strip()
        buttons.append(
            html.Button(
                abbr,
                id={"type": "pf-setpiece-view", "view": piece_id},
                n_clicks=0,
                type="button",
                title=label,
                className="st-player-seg-btn"
                + (" active" if piece_id == current else ""),
            )
        )
    return html.Div(
        buttons,
        className="st-player-seg pf-setpiece-view-seg",
        role="group",
        **{"aria-label": "Set piece category"},
    )


def _try_float_score(value) -> float | None:
    if value is None or value in ("", "-", "—"):
        return None
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    if score != score:  # NaN
        return None
    return score


def _entry_setpiece_score(entry: dict, score_col: str, *, settings=None) -> float | None:
    """Prefer snapshot score; recompute from stored attrs when missing."""
    if not score_col:
        return None
    row = entry.get("row") or {}
    parsed = _try_float_score(row.get(score_col))
    if parsed is not None:
        return parsed
    player = entry.get("player") if isinstance(entry.get("player"), dict) else None
    attrs = (player or {}).get("attrs") or {}
    if not isinstance(attrs, dict) or not attrs:
        return None
    settings = us.normalize(settings)
    temp: dict = {}
    apply_set_piece_scores(
        temp,
        attrs,
        tier_weights=us.tier_weights(settings),
        profiles=us.set_piece_profiles(settings),
    )
    return _try_float_score(temp.get(score_col))


def _unique_setpiece_entries(
    entries: list[dict] | None = None,
    *,
    score_col: str = "",
    settings=None,
) -> list[dict]:
    """One entry per player_key; prefer the row with a real set-piece score."""
    by_key: dict[str, tuple[float, dict]] = {}
    for entry in entries or []:
        key = _entry_player_key(entry)
        if not key:
            continue
        score = _entry_setpiece_score(entry, score_col, settings=settings)
        rank = score if score is not None else float("-inf")
        prev = by_key.get(key)
        if prev is None or rank > prev[0]:
            by_key[key] = (rank, entry)
    return [item for _, item in by_key.values()]


def _entry_strong_feet(entry: dict) -> tuple[bool, bool]:
    """Return (left_strong, right_strong) for Strong or better from snapshot/player."""
    row = entry.get("row") if isinstance(entry.get("row"), dict) else {}
    player = entry.get("player") if isinstance(entry.get("player"), dict) else {}
    left_raw = row.get("Left Foot")
    right_raw = row.get("Right Foot")
    if left_raw in (None, "", "-", "—"):
        left_raw = player.get("left_foot")
    if right_raw in (None, "", "-", "—"):
        right_raw = player.get("right_foot")
    left = foot_strength(left_raw or "")
    right = foot_strength(right_raw or "")
    return (
        left is not None and left >= SET_PIECE_FOOT_MIN,
        right is not None and right >= SET_PIECE_FOOT_MIN,
    )


def _best_slot_by_player_key(
    formation_id: str | None,
    slots: list[dict] | None,
    *,
    cache: _PfProfileCache | None = None,
) -> dict[str, tuple[int, str]]:
    """Best depth rank per player across formation slots.

    Rank 1 is best. On tied ranks, keep the earlier Starting XI slot.
    """
    best: dict[str, tuple[int, str]] = {}
    if not formation_id or not slots:
        return best
    for slot in slots:
        label = str(slot.get("display_label") or slot.get("label") or "—").strip() or "—"
        if cache is not None:
            ordered = cache.ordered_for_slot(
                formation_id, slot["index"], slot.get("column") or ""
            )
        else:
            ordered = profiles.ordered_profiles_for_slot(
                formation_id, slot["index"], slot.get("column") or ""
            )
        for index, entry in enumerate(ordered):
            key = _entry_player_key(entry)
            if not key:
                continue
            rank = index + 1
            prev = best.get(key)
            if prev is None or rank < prev[0]:
                best[key] = (rank, label)
    return best


def _top_setpiece_entries(
    piece_id: str,
    *,
    settings=None,
    limit: int = SET_PIECE_TOP_N,
    foot_side: str | None = None,
    cache: _PfProfileCache | None = None,
) -> tuple[dict | None, list[tuple[dict, float | None]]]:
    """Return (profile meta, [(entry, score), ...]) ranked for the category.

    ``foot_side`` of ``left`` / ``right`` keeps only Strong+ on that foot.
    """
    settings = us.normalize(settings)
    profile = _setpiece_profile(piece_id, settings)
    score_col = str((profile or {}).get("score") or "").strip()
    if cache is not None:
        entries = cache.list_role_profiles()
    else:
        entries = profiles.list_role_profiles()
    unique = _unique_setpiece_entries(
        entries, score_col=score_col, settings=settings
    )
    side = str(foot_side or "").strip().lower()
    ranked: list[tuple[dict, float | None]] = []
    for entry in unique:
        if side in ("left", "right"):
            left_ok, right_ok = _entry_strong_feet(entry)
            if side == "left" and not left_ok:
                continue
            if side == "right" and not right_ok:
                continue
        ranked.append(
            (entry, _entry_setpiece_score(entry, score_col, settings=settings))
        )
    ranked.sort(
        key=lambda item: (
            item[1] is None,
            -(item[1] if item[1] is not None else 0.0),
            (profiles.profile_identity(item[0])[0] or "").lower(),
        )
    )
    return profile, ranked[: max(0, int(limit or 0))]


def _profiles_busy_overlay(overlay_id: str, label: str, *, on: bool = False) -> html.Div:
    """Blocking spinner overlay (same chrome as shortlist busy)."""
    return html.Div(
        [
            html.Div(className="rs-shortlist-busy-spinner", **{"aria-hidden": "true"}),
            html.Span(label, className="rs-shortlist-busy-label"),
        ],
        id=overlay_id,
        className="rs-shortlist-busy" + (" is-on" if on else ""),
        role="status",
        **{"aria-live": "polite"},
    )


class _PfProfileCache:
    """Per-request memo for role-profile index and slot/role order lists."""

    __slots__ = ("_entries", "_ordered_slot", "_ordered_role")

    def __init__(self, entries: list[dict] | None = None):
        self._entries = entries
        self._ordered_slot: dict[tuple[str, str, str], list[dict]] = {}
        self._ordered_role: dict[str, list[dict]] = {}

    def list_role_profiles(self) -> list[dict]:
        if self._entries is None:
            self._entries = profiles.list_role_profiles()
        return self._entries

    def ordered_for_slot(
        self,
        formation_id: str | None,
        slot_index,
        role_column: str,
    ) -> list[dict]:
        key = (
            str(formation_id or ""),
            str(slot_index),
            str(role_column or ""),
        )
        hit = self._ordered_slot.get(key)
        if hit is not None:
            return hit
        ordered = profiles.ordered_profiles_for_slot(
            formation_id,
            slot_index,
            role_column,
            entries=self.list_role_profiles(),
        )
        self._ordered_slot[key] = ordered
        return ordered

    def ordered_for_role(self, role_column: str) -> list[dict]:
        role = str(role_column or "")
        hit = self._ordered_role.get(role)
        if hit is not None:
            return hit
        ordered = profiles.ordered_profiles_for_role(
            role, entries=self.list_role_profiles()
        )
        self._ordered_role[role] = ordered
        return ordered


def _formation_xi_entry(
    formation_id: str | None,
    slot: dict,
    *,
    xi_view=None,
    cache: _PfProfileCache | None = None,
) -> dict | None:
    """Profile at the selected XI rank for one formation slot, if any."""
    if cache is not None:
        ordered = cache.ordered_for_slot(
            formation_id, slot["index"], slot["column"]
        )
    else:
        ordered = profiles.ordered_profiles_for_slot(
            formation_id, slot["index"], slot["column"]
        )
    index = _xi_rank_index(xi_view)
    if index < 0 or index >= len(ordered):
        return None
    return ordered[index]


def _formation_starter_slot_maps(
    formation_id: str | None,
    slots: list[dict],
    *,
    xi_view=None,
    cache: _PfProfileCache | None = None,
) -> tuple[dict[int, str], set[str], set[int], set[int]]:
    """XI player keys per slot, plus multi/unique slot indexes.

    Conflicts are based on each slot’s current player at the selected XI rank
    only, so they update when the XI changes (remove, restore, reorder, auto-rank).
    """
    rank_i = _xi_rank_index(xi_view)
    starters: dict[int, str] = {}
    key_slots: dict[str, set[int]] = {}
    for slot in slots:
        index = int(slot["index"])
        if cache is not None:
            ordered = cache.ordered_for_slot(
                formation_id, index, slot["column"]
            )
        else:
            ordered = profiles.ordered_profiles_for_slot(
                formation_id, index, slot["column"]
            )
        entry = ordered[rank_i] if len(ordered) > rank_i else None
        key = _entry_player_key(entry) if entry else ""
        starters[index] = key
        if key:
            key_slots.setdefault(key, set()).add(index)
    multi_starters = {key for key, indexes in key_slots.items() if len(indexes) > 1}
    conflicted_slots = {
        index
        for index, key in starters.items()
        if key and key in multi_starters
    }
    unique_slots = {
        index
        for index, key in starters.items()
        if key and key not in multi_starters
    }
    return starters, multi_starters, conflicted_slots, unique_slots


def _slot_status_class(*, conflicted: bool = False, unique: bool = False) -> str:
    if conflicted:
        return " is-multi-slot"
    if unique:
        return " is-unique-slot"
    return ""


def _slot_cell_markdown(
    label: str,
    *,
    conflicted: bool = False,
    unique: bool = False,
) -> str:
    text = html_escape(str(label or "—"))
    if conflicted:
        return (
            f'<span class="pf-slot-cell is-multi-slot" '
            f'style="color:#f87171;font-weight:700">{text}</span>'
        )
    if unique:
        return (
            f'<span class="pf-slot-cell is-unique-slot" '
            f'style="color:#4ade80;font-weight:700">{text}</span>'
        )
    return f'<span class="pf-slot-cell">{text}</span>'


def _formation_columns(formation_id: str | None) -> list[str]:
    """Unique hybrid role columns from a formation, in first-seen slot order."""
    seen: set[str] = set()
    columns: list[str] = []
    for slot in _formation_slots(formation_id):
        column = slot["column"]
        if column in seen:
            continue
        seen.add(column)
        columns.append(column)
    return columns


def _colored_group_abbr(abbr: str, *, css: str = "rs-pill-groups"):
    if not abbr:
        return []
    parts = []
    for index, token in enumerate(abbr.split("/")):
        if index:
            parts.append(html.Span("/", className=f"{css}-sep"))
        tone = group_abbr_tone(token)
        class_name = f"{css} {tone}".strip() if tone else css
        parts.append(html.Span(token, className=class_name))
    return html.Span(parts, className="rs-group-abbr")


def _band_legend(settings=None) -> html.Div:
    settings = us.normalize(settings)
    bands = settings["bands"]
    chips = []
    for band, label, text in (
        ("elite", "Elite", f"≥ {us.format_cut(bands['elite'])}"),
        ("good", "Good", f"≥ {us.format_cut(bands['good'])}"),
        ("ok", "OK", f"≥ {us.format_cut(bands['ok'])}"),
        ("poor", "Poor", f"< {us.format_cut(bands['ok'])}"),
    ):
        chips.append(
            html.Span(
                [
                    html.Span(label, className="rs-legend-name"),
                    html.Span(text, className="rs-legend-op"),
                ],
                className=f"rs-legend-chip {band}",
            )
        )
    return html.Div(chips, className="rs-depth-legend")


def _role_column_meta(column: str) -> dict:
    global _ROLE_COLUMN_META
    if _ROLE_COLUMN_META is None:
        import config.role_weights.fm26_role_weight_config as pc

        mapping: dict[str, dict] = {}
        for role_id in pc.all_positions:
            meta = role_meta(role_id)
            mapping[meta["column"]] = {
                **meta,
                "short_label": meta.get("compact_name") or meta["name"],
            }
        for ip in pc.all_positions:
            for oop in pc.all_positions:
                col = combo_column(ip, oop)
                if col not in mapping:
                    mapping[col] = combo_meta(ip, oop)
        _ROLE_COLUMN_META = mapping
    if column in _ROLE_COLUMN_META:
        return _ROLE_COLUMN_META[column]
    label = column or "Role"
    return {
        "id": column,
        "column": column,
        "name": label,
        "short_label": label,
        "phase": "",
        "tone": "mid",
        "group_abbr": "",
        "compact": label,
    }


def _depth_id_column(role_key: str) -> str | None:
    parsed = parse_combo_id(role_key)
    if parsed:
        return combo_column(*parsed)
    if role_key and role_key != "_":
        return role_meta(role_key)["column"]
    return None


def _depth_role_key(meta: dict) -> str:
    return str(meta.get("id") or meta.get("column") or "_")


def _empty_depth_card_stats(meta: dict) -> dict:
    return {
        "meta": meta,
        "avg": None,
        "counts": {"elite": 0, "good": 0, "ok": 0, "poor": 0},
        "total": 0,
        "names": "",
    }


_PITCH_LINE_ORDER = ("att", "mid", "def", "gk")
_PITCH_LINE_LABELS = {
    "gk": "Goalkeeper",
    "def": "Defence",
    "mid": "Midfield",
    "att": "Attack",
}
_POS_TO_PITCH_LINE = {
    "gk": "gk",
    "cb": "def",
    "rb": "def",
    "lb": "def",
    "rwb": "def",
    "lwb": "def",
    "dm": "mid",
    "cm": "mid",
    "am": "mid",
    "rm": "mid",
    "lm": "mid",
    "rw": "att",
    "lw": "att",
    "st": "att",
    # Common slot labels
    "rcb": "def",
    "lcb": "def",
    "fb": "def",
    "wb": "def",
    "mc": "mid",
    "amc": "mid",
    "dmr": "mid",
    "dml": "mid",
    "ram": "mid",
    "lam": "mid",
    "rcm": "mid",
    "lcm": "mid",
    "rdm": "mid",
    "ldm": "mid",
    "wm": "mid",
    "w": "att",
    "cf": "att",
    "rst": "att",
    "lst": "att",
}
_LEFT_IP_POS = frozenset({"lb", "lwb", "lm", "lw"})
_RIGHT_IP_POS = frozenset({"rb", "rwb", "rm", "rw"})
# Slot codes that encode a flank (auto RCB/LCB or IP labels like LB/RW).
_LEFT_SLOT_CODES = frozenset(
    {
        "L",
        "LB",
        "LWB",
        "LCB",
        "LDM",
        "LCM",
        "LAM",
        "LM",
        "LW",
        "LST",
        "DML",
    }
)
_RIGHT_SLOT_CODES = frozenset(
    {
        "R",
        "RB",
        "RWB",
        "RCB",
        "RDM",
        "RCM",
        "RAM",
        "RM",
        "RW",
        "RST",
        "DMR",
    }
)


def _slot_pitch_line(slot: dict) -> str:
    """Map a formation slot to GK / Defence / Midfield / Attack."""
    for key in ("ip_pos", "oop_pos", "label", "display_label"):
        raw = str(slot.get(key) or "").strip().lower()
        if not raw:
            continue
        if raw in _POS_TO_PITCH_LINE:
            return _POS_TO_PITCH_LINE[raw]
        group = fm.group_for_position(raw)
        if group == "gk":
            return "gk"
        if group in ("cb", "fb", "wb"):
            return "def"
        if group in ("dm", "cm", "am", "wm"):
            return "mid"
        if group in ("w", "st"):
            return "att"
    return "mid"


def _normalize_slot_code(value: str | None) -> str:
    text = str(value or "").strip().upper()
    if not text:
        return ""
    # Drop CB (1)-style suffixes from older duplicate labels.
    return re.sub(r"\s*\(\d+\)\s*$", "", text).strip()


def _slot_flank_side(slot: dict) -> int:
    """Horizontal pitch side: -1 left, 0 centre, 1 right (attack at top).

    Callers should sort by ``(side, -slot_index)`` so a lower slot number sits
    further to the right within the same flank.
    """
    for key in ("display_label", "label"):
        code = _normalize_slot_code(slot.get(key))
        if code in _LEFT_SLOT_CODES:
            return -1
        if code in _RIGHT_SLOT_CODES:
            return 1
    for key in ("ip_pos", "oop_pos"):
        pos = str(slot.get(key) or "").strip().lower()
        if pos in _LEFT_IP_POS or pos in {"lcb", "ldm", "lcm", "lam", "lst", "dml"}:
            return -1
        if pos in _RIGHT_IP_POS or pos in {"rcb", "rdm", "rcm", "ram", "rst", "dmr"}:
            return 1
    return 0


def _profile_depth_card_stats(meta: dict, entries: list[dict], bands: dict) -> dict | None:
    column = meta["column"]
    eligible = []
    top_names: list[str] = []
    for entry in entries:
        role = entry.get("role_column") or (entry.get("row") or {}).get("Role")
        if role != column:
            continue
        row = entry.get("row") or {}
        score = row.get("Score")
        try:
            score_f = float(score) if score not in (None, "", "-", "—") else None
        except (TypeError, ValueError):
            score_f = None
        if score_f is None:
            continue
        name = row.get("Name") or profiles.profile_identity(entry)[0] or ""
        eligible.append({"Name": name, column: score_f})
        if len(top_names) < 3 and name:
            top_names.append(name)
    if not eligible:
        return None
    scores = [float(row.get(column) or 0) for row in eligible]
    avg = sum(scores) / len(scores)
    counts = {"elite": 0, "good": 0, "ok": 0, "poor": 0}
    for score in scores:
        counts[score_band(score, **bands)] += 1
    total = len(scores) or 1
    names = " · ".join(top_names)
    return {
        "meta": meta,
        "avg": avg,
        "counts": counts,
        "total": total,
        "names": names,
    }


def _profile_depth_card(
    stats: dict,
    focus_roles,
    bands: dict,
    *,
    slot: dict | None = None,
    slot_conflicted: bool = False,
    slot_unique: bool = False,
) -> html.Button:
    meta = stats["meta"]
    column = meta["column"]
    avg = stats["avg"]
    counts = stats["counts"]
    total = int(stats["total"] or 0)
    empty = total <= 0 or avg is None
    focus = _focus_slot(focus_roles)
    if slot is not None:
        active = (
            " active"
            if focus
            and int(focus.get("slot", -1)) == int(slot["index"])
            and focus.get("role") == column
            else ""
        )
    else:
        active = " active" if column in _focus_roles(focus_roles) else ""
    empty_cls = " is-empty" if empty else ""
    role_label = meta.get("short_label") or meta["name"]
    slot_label = (slot or {}).get("display_label") or (slot or {}).get("label") or ""
    if empty:
        avg_el = html.Span("—", className="rs-depth-avg")
        bar_children = []
    else:
        avg_el = html.Span(
            f"{float(avg):.1f}",
            className=f"rs-depth-avg rs-band-{score_band(float(avg), **bands)}",
        )
        bar_children = [
            html.Div(
                className=f"rs-depth-seg {band}",
                style={"width": f"{counts[band] / total * 100:.1f}%"},
            )
            for band in ("elite", "good", "ok", "poor")
            if counts[band]
        ]
    title_bits = []
    if slot_label:
        title_bits.append(
            html.Div(
                [
                    html.Span("Slot", className="rs-depth-kicker"),
                    html.Span(
                        slot_label,
                        className="rs-depth-slot"
                        + _slot_status_class(
                            conflicted=slot_conflicted, unique=slot_unique
                        ),
                        title=(
                            "Same XI player as another formation slot"
                            if slot_conflicted
                            else (
                                "Unique XI player for this formation slot"
                                if slot_unique
                                else slot_label
                            )
                        ),
                    ),
                ],
                className="rs-depth-slot-row",
            )
        )
    title_bits.append(
        html.Div(
            [
                html.Span("Role", className="rs-depth-kicker"),
                html.Span(role_label, className="rs-depth-name"),
            ],
            className="rs-depth-role-row",
        )
    )
    title_bits.append(
        html.Div(
            [
                _colored_group_abbr(meta.get("group_abbr") or "", css="rs-depth-code"),
                html.Span(
                    meta.get("phase") or "",
                    className=f"rs-phase-tag {meta.get('tone') or 'gk'}",
                ),
            ],
            className="rs-depth-meta",
        )
    )
    player_label = "player" if total == 1 else "players"
    children = [
        html.Div(title_bits, className="rs-depth-title"),
        html.Div(
            [
                html.Span("Avg score", className="rs-depth-avg-label"),
                avg_el,
            ],
            className="rs-depth-avg-row",
        ),
        html.Div(bar_children, className="rs-depth-bar"),
        html.Div(
            [
                html.Div(
                    [
                        html.Div(str(counts[band]), className=f"rs-tier-val {band}"),
                        html.Div(tier_label, className="rs-tier-lbl"),
                    ],
                    className="rs-tier",
                )
                for band, tier_label in (
                    ("elite", "Elite"),
                    ("good", "Good"),
                    ("ok", "OK"),
                    ("poor", "Poor"),
                )
            ],
            className="rs-depth-tiers",
        ),
        html.Div(
            [
                html.Div(
                    [
                        html.Span("Top", className="rs-depth-kicker"),
                        html.Span(
                            f"{total} {player_label}",
                            className="rs-depth-count",
                        ),
                    ],
                    className="rs-depth-players-head",
                ),
                html.Div(
                    stats["names"] or ("No saved players" if empty else "—"),
                    className="rs-depth-players",
                ),
            ],
            className="rs-depth-players-block",
        ),
    ]
    role_key = _depth_role_key(meta)
    if slot is not None:
        button_id = {
            "type": "pf-depth",
            "slot": str(slot["index"]),
            "role": role_key,
        }
    else:
        button_id = {"type": "pf-depth", "slot": "_", "role": role_key}
    return html.Button(
        children,
        id=button_id,
        n_clicks=0,
        className="rs-depth-card" + active + empty_cls,
        title=meta.get("compact") or meta["name"],
        **{"data-rs-role": column, "data-rs-slot": str((slot or {}).get("index", ""))},
    )


def _profile_depth_panel(
    entries: list[dict],
    focus_roles,
    *,
    formation_id: str | None = None,
    formation_slots: list[dict] | None = None,
    settings=None,
    xi_view=None,
    cache: _PfProfileCache | None = None,
) -> list:
    settings = us.normalize(settings)
    bands = settings["bands"]

    if formation_slots is not None:
        if not formation_slots:
            return [
                html.Div(
                    "This formation has no filled IP+OOP slots. Edit it on Formations.",
                    className="text-muted small",
                )
            ]
        _starters, _multi, conflicted_slots, unique_slots = (
            _formation_starter_slot_maps(
                formation_id, formation_slots, xi_view=xi_view, cache=cache
            )
        )
        by_line: dict[str, list[tuple[int, int, object]]] = {
            key: [] for key in _PITCH_LINE_ORDER
        }
        for slot in formation_slots:
            meta = _role_column_meta(slot["column"])
            # Counts / avg / top names must follow this slot's depth list —
            # not every saved profile for the role (shared roles differ per slot).
            if cache is not None:
                slot_entries = cache.ordered_for_slot(
                    formation_id, slot["index"], slot["column"]
                )
            else:
                slot_entries = profiles.ordered_profiles_for_slot(
                    formation_id,
                    slot["index"],
                    slot["column"],
                    entries=entries,
                )
            payload = _profile_depth_card_stats(meta, slot_entries, bands)
            if not payload:
                payload = _empty_depth_card_stats(meta)
            slot_index = int(slot["index"])
            card = _profile_depth_card(
                payload,
                focus_roles,
                bands,
                slot=slot,
                slot_conflicted=slot_index in conflicted_slots,
                slot_unique=slot_index in unique_slots,
            )
            line_id = _slot_pitch_line(slot)
            by_line.setdefault(line_id, []).append(
                (_slot_flank_side(slot), slot_index, card)
            )
        lines = []
        total_slots = len(formation_slots)
        for line_id in _PITCH_LINE_ORDER:
            # Left → centre → right; within a flank, lower slot # sits further right.
            ranked = sorted(
                by_line.get(line_id) or [],
                key=lambda item: (item[0], -item[1]),
            )
            line_cards = [item[2] for item in ranked]
            if not line_cards:
                continue
            count = len(line_cards)
            lines.append(
                html.Div(
                    [
                        html.Div(
                            [
                                html.Span(
                                    _PITCH_LINE_LABELS.get(line_id, line_id),
                                    className="pf-depth-line-label",
                                ),
                                html.Span(
                                    f"{count}",
                                    className="pf-depth-line-count",
                                    title=f"{count} slot{'s' if count != 1 else ''}",
                                ),
                            ],
                            className="pf-depth-line-head",
                        ),
                        html.Div(
                            line_cards,
                            className="pf-depth-line-grid",
                            style={"--pf-line-cols": str(min(max(count, 1), 6))},
                        ),
                    ],
                    className=f"pf-depth-line pf-depth-line-{line_id}",
                )
            )
        return [
            html.Div(
                [
                    html.Div(
                        [
                            html.Span("Formation slots", className="pf-depth-board-kicker"),
                            html.Span(
                                f"{total_slots} of 11",
                                className="pf-depth-board-meta",
                            ),
                        ],
                        className="pf-depth-board-head",
                    ),
                    html.Div(lines, className="pf-depth-lines"),
                ],
                className="pf-depth-board",
            )
        ]

    if not entries:
        return []
    roles_seen: dict[str, dict] = {}
    for entry in entries:
        role = str(entry.get("role_column") or (entry.get("row") or {}).get("Role") or "").strip()
        if not role:
            continue
        if role not in roles_seen:
            roles_seen[role] = _role_column_meta(role)
    stats_list = []
    for meta in roles_seen.values():
        payload = _profile_depth_card_stats(meta, entries, bands)
        if payload:
            stats_list.append(payload)
    stats_list.sort(key=lambda item: item["meta"].get("name") or item["meta"]["column"])
    return [_profile_depth_card(stats, focus_roles, bands) for stats in stats_list]


def _profile_identity_columns(page: str, settings) -> list[str]:
    """Shortlist identity columns, always including Division (stats-style tiers)."""
    cols = list(us.shortlist_columns_for(page, settings))
    if "Division" in cols:
        return cols
    if "Club" in cols:
        cols.insert(cols.index("Club") + 1, "Division")
    elif "Position" in cols:
        cols.insert(cols.index("Position") + 1, "Division")
    else:
        cols.append("Division")
    return cols


def _limited_tracking_divisions() -> set[str]:
    """Union of limited-stat leagues recorded across the upload library."""
    import services.export_library as lib

    return set(lib.list_limited_tracking_divisions())


def _apply_profile_division(
    item: dict,
    raw: dict,
    *,
    limited_divisions: set[str] | frozenset[str] | list[str] | None = None,
) -> None:
    """Ensure Division / Personality highlight helper columns."""
    from scoring.personality_tiers import apply_personality_tier
    from components.player_table import apply_division_limited_flag

    if "Division" not in item:
        item["Division"] = _blank(raw.get("Division"))
    tier_row = {
        "Division": raw.get("Division") if raw.get("Division") not in (None, "", "-", "—")
        else item.get("Division"),
        "Nation": raw.get("Nation"),
    }
    apply_division_tier(tier_row)
    apply_division_limited_flag(
        tier_row, limited_divisions if limited_divisions is not None else _limited_tracking_divisions()
    )
    item["DivisionTier"] = tier_row.get("DivisionTier") or ""
    item["DivisionLimited"] = tier_row.get("DivisionLimited") or "no"

    pers = item.get("Personality")
    if pers in (None, "", "-", "—"):
        pers = raw.get("Personality")
    if pers not in (None, "", "-", "—") and "Personality" not in item:
        item["Personality"] = _blank(pers)
    pers_row = {"Personality": item.get("Personality") or pers}
    apply_personality_tier(pers_row)
    item["PersonalityTier"] = pers_row.get("PersonalityTier") or ""


def _depth_score_cell(score, settings, theme=None):
    """Score pill using the same band colors as the Profiles table."""
    if score is None or score in ("", "-", "—"):
        return html.Span("—", className="pf-depth-chart-metric")
    settings = us.normalize(settings)
    try:
        score_f = float(score)
        band = score_band(score_f, **settings["bands"])
    except (TypeError, ValueError):
        return html.Span(str(score), className="pf-depth-chart-metric")
    return html.Span(
        f"{score_f:.1f}",
        className=f"pf-depth-chart-score-pill is-{band}",
        title=f"Score {score_f:.1f} ({band})",
    )


def _depth_ovr_cell(percentile, color=None, *, pill: bool = False):
    """Colored overall percentile; optional pill when ``pill`` is True."""
    if percentile is None or percentile in ("", "-", "—"):
        return html.Span("—", className="pf-depth-chart-metric")
    try:
        pct_f = float(percentile)
    except (TypeError, ValueError):
        return html.Span(str(percentile), className="pf-depth-chart-metric")
    tint = color or percentile_color(pct_f)
    if pill:
        if pct_f >= 80:
            tier = "high"
        elif pct_f >= 60:
            tier = "mid-high"
        elif pct_f >= 40:
            tier = "mid"
        else:
            tier = "low"
        style = {"color": tint} if tint else None
        return html.Span(
            f"{pct_f:.0f}%",
            className=f"pf-depth-chart-ovr-pill is-{tier}",
            style=style,
            title=f"Overall {pct_f:.0f}%",
        )
    style = {"fontWeight": 750, "fontVariantNumeric": "tabular-nums"}
    if tint:
        style["color"] = tint
    return html.Span(f"{pct_f:.0f}%", className="pf-depth-chart-metric", style=style)


def _depth_plain_cell(value, class_name: str) -> html.Span:
    text = _blank(value)
    return html.Span(
        text,
        className=class_name,
        title="" if text == "—" else text,
    )


def _depth_mins_cell(value, settings=None, *, minutes_required=None) -> html.Span:
    """Mins cell colored like the Profiles table (meet / half / fail)."""
    if value in (None, "", "-", "—"):
        return html.Span("—", className="pf-depth-chart-mins")
    try:
        mins_f = float(value)
        if mins_f != mins_f:
            return html.Span("—", className="pf-depth-chart-mins")
        text = f"{int(mins_f):,}"
    except (TypeError, ValueError):
        return html.Span(str(value), className="pf-depth-chart-mins", title=str(value))
    required = _resolve_minutes_required(minutes_required, settings)
    status = minutes_status(mins_f, required)
    tint = minutes_color(status)
    style = {
        "fontWeight": 650,
        "fontVariantNumeric": "tabular-nums",
    }
    if tint:
        style["color"] = tint
    return html.Span(
        text,
        className=f"pf-depth-chart-mins is-{status}",
        style=style,
        title=f"{text} mins · limit {int(required):,} ({status})",
    )


def _depth_rec_cell(value, theme=None) -> html.Span:
    text = _blank(value)
    style = rec_grade_style(text, theme) if text != "—" else None
    props = {
        "className": "pf-depth-chart-rec" + (" is-graded" if style else ""),
        "title": "" if text == "—" else text,
    }
    if style:
        props["style"] = style
    return html.Span(text, **props)


def _depth_role_cell(column: str, theme=None) -> html.Span:
    label = _role_display_label(column)
    if label == "—":
        return html.Span("—", className="pf-depth-chart-role is-empty")
    meta = _role_column_meta(column)
    tone = str(meta.get("tone") or "").strip().lower()
    if tone.startswith("ip"):
        tone = "ip"
    elif tone.startswith("oop"):
        tone = "oop"
    elif tone in ("combo", "hybrid"):
        tone = "combo"
    elif tone != "gk":
        tone = "gk" if not tone else tone
    color = _role_phase_colors(theme).get(tone) or _role_phase_colors(theme)["gk"]
    return html.Span(
        label,
        className=f"pf-depth-chart-role pf-role-{tone}",
        style={"color": color, "fontWeight": 700},
        title=meta.get("compact") or meta.get("name") or label,
    )


def _depth_chart_player_row(
    entry: dict | None,
    *,
    index: int,
    total: int,
    settings,
    theme=None,
    slot_label: str = "",
    slot_index: int | str | None = None,
    role_column: str = "",
    slot_conflicted: bool = False,
    slot_unique: bool = False,
    draggable: bool = True,
    removable: bool = True,
    selectable: bool = False,
    minutes_required=None,
    name_src: str = "depth",
) -> html.Div:
    del total  # kept for call-site compatibility
    settings = us.normalize(settings)
    mins_limit = _resolve_minutes_required(minutes_required, settings)
    remove_cell = html.Span("", className="pf-depth-chart-remove")
    slot_class = "pf-depth-chart-slot" + _slot_status_class(
        conflicted=slot_conflicted, unique=slot_unique
    )
    slot_title = (
        "Same XI player as another formation slot"
        if slot_conflicted
        else (
            "Unique XI player for this formation slot"
            if slot_unique
            else slot_label
        )
    )
    role_col = str(role_column or "").strip()
    name_src = str(name_src or "depth").strip() or "depth"

    def check_cell(profile_id: str = "") -> html.Span | dmc.Checkbox:
        if not selectable:
            return html.Span("", className="pf-depth-chart-check-slot")
        if not profile_id or slot_index is None:
            return html.Span("", className="pf-depth-chart-check-slot")
        return dmc.Checkbox(
            id={
                "type": "pf-depth-check",
                "id": profile_id,
                "slot": str(slot_index),
            },
            checked=False,
            size="xs",
            className="pf-depth-chart-check",
            **{"aria-label": "Select player for compare or bulk remove"},
        )

    def empty_row_cells() -> list:
        return [
            html.Div(
                [
                    check_cell(""),
                    html.Span("", className="pf-depth-chart-grip", **{"aria-hidden": "true"}),
                    html.Span(str(index + 1), className="pf-depth-chart-rank"),
                ],
                className="pf-depth-chart-rank-cell",
            ),
            html.Span("—", className="pf-depth-chart-name is-empty"),
            html.Span("—", className="pf-depth-chart-age"),
            html.Span("—", className="pf-depth-chart-height"),
            html.Span("—", className="pf-depth-chart-pos"),
            html.Span(slot_label or "—", className=slot_class, title=slot_title),
            _depth_role_cell(role_col, theme=theme)
            if role_col
            else html.Span("—", className="pf-depth-chart-role is-empty"),
            html.Span("—", className="pf-depth-chart-feet"),
            html.Span("—", className="pf-depth-chart-club"),
            html.Span("—", className="pf-depth-chart-div"),
            html.Span("—", className="pf-depth-chart-rec"),
            html.Span("—", className="pf-depth-chart-injury"),
            html.Div(
                html.Span("—", className="pf-depth-chart-metric"),
                className="pf-depth-chart-score",
            ),
            html.Span("—", className="pf-depth-chart-mins"),
            html.Div(
                html.Span("—", className="pf-depth-chart-metric"),
                className="pf-depth-chart-ovr",
            ),
            html.Div(
                html.Span("—", className="pf-depth-chart-metric"),
                className="pf-depth-chart-def",
            ),
            html.Div(
                html.Span("—", className="pf-depth-chart-metric"),
                className="pf-depth-chart-f3",
            ),
            html.Div(
                html.Span("—", className="pf-depth-chart-metric"),
                className="pf-depth-chart-poss",
            ),
            remove_cell,
        ]

    if entry is None:
        return html.Div(
            empty_row_cells(),
            className="pf-depth-chart-row is-empty" + (" is-odd" if index % 2 else ""),
        )
    row = entry.get("row") or {}
    profile_id = str(entry.get("id") or "").strip()
    if not role_col:
        role_col = str(
            entry.get("role_column") or row.get("Role") or ""
        ).strip()
    name, club = profiles.profile_identity(entry)
    display_rank = index + 1
    position = _blank(row.get("Position"))
    if position == "—":
        position = _blank(row.get("Best Pos"))
    division = _blank(row.get("Division"))
    tier = classify_division(row.get("Division"), row.get("Nation"))
    from scoring.stats_availability import (
        LIMITED_DIVISION_TITLE,
        division_has_limited_tracking,
    )

    limited = division_has_limited_tracking(
        row.get("Division"), _limited_tracking_divisions()
    )
    div_class = "pf-depth-chart-div"
    if tier:
        div_class = f"{div_class} pf-div-{tier}"
    if limited:
        div_class = f"{div_class} pf-div-limited"
    div_title = (
        f"{division} — {LIMITED_DIVISION_TITLE}" if limited and division != "—" else division
    )
    if removable and profile_id and slot_index is not None:
        remove_cell = html.Button(
            "×",
            id={
                "type": "pf-depth-remove",
                "id": profile_id,
                "slot": str(slot_index),
                "src": name_src,
            },
            n_clicks=0,
            className="pf-depth-chart-remove-btn",
            type="button",
            title=(
                f"Remove from {slot_label or 'this slot'} only "
                "(other slots keep this player)"
            ),
            draggable="false",
            **{
                "aria-label": (
                    f"Remove {name or 'player'} from "
                    f"{slot_label or 'this formation slot'}"
                )
            },
        )
    props = {
        "className": (
            "pf-depth-chart-row"
            + (" is-odd" if index % 2 else "")
            + (" is-sortable" if draggable and profile_id else "")
        ),
        **({"data-profile-id": profile_id} if profile_id else {}),
    }
    injury_html = injury_cell(row.get("Injury"))
    return html.Div(
        [
            html.Div(
                [
                    check_cell(profile_id),
                    html.Span(
                        "⋮⋮" if draggable else "",
                        className="pf-depth-chart-grip",
                        **{"aria-hidden": "true"},
                    ),
                    html.Span(str(display_rank), className="pf-depth-chart-rank"),
                ],
                className="pf-depth-chart-rank-cell",
            ),
            (
                html.Button(
                    name or "Player",
                    id={
                        "type": "pf-depth-name",
                        "id": profile_id,
                        "src": name_src,
                        "slot": (
                            str(slot_index)
                            if slot_index is not None
                            else "0"
                        ),
                    },
                    n_clicks=0,
                    className="pf-depth-chart-name",
                    title="Open player details",
                    draggable="false",
                    type="button",
                )
                if profile_id
                else html.Span("—", className="pf-depth-chart-name is-empty")
            ),
            _depth_plain_cell(row.get("Age"), "pf-depth-chart-age"),
            _depth_plain_cell(row.get("Height"), "pf-depth-chart-height"),
            html.Span(position, className="pf-depth-chart-pos", title=position),
            html.Span(slot_label or "—", className=slot_class, title=slot_title),
            _depth_role_cell(role_col, theme=theme),
            dcc.Markdown(
                feet_cell(row),
                dangerously_allow_html=True,
                className="pf-depth-chart-feet",
            ),
            html.Span(club or "—", className="pf-depth-chart-club", title=club or ""),
            html.Span(division, className=div_class, title=div_title),
            _depth_rec_cell(row.get("Rec"), theme=theme),
            (
                dcc.Markdown(
                    injury_html,
                    dangerously_allow_html=True,
                    className="pf-depth-chart-injury",
                )
                if injury_html and injury_html not in ("—", "-", "")
                else html.Span("—", className="pf-depth-chart-injury")
            ),
            html.Div(
                _depth_score_cell(row.get("Score"), settings, theme=theme),
                className="pf-depth-chart-score",
            ),
            _depth_mins_cell(
                _profile_minutes_raw(entry, row),
                settings,
                minutes_required=mins_limit,
            ),
            html.Div(
                _depth_ovr_cell(
                    row.get("overall"), row.get("overall_color"), pill=True
                ),
                className="pf-depth-chart-ovr",
            ),
            html.Div(
                _depth_ovr_cell(row.get("defending"), row.get("defending_color")),
                className="pf-depth-chart-def",
            ),
            html.Div(
                _depth_ovr_cell(row.get("final_third"), row.get("final_third_color")),
                className="pf-depth-chart-f3",
            ),
            html.Div(
                _depth_ovr_cell(row.get("possession"), row.get("possession_color")),
                className="pf-depth-chart-poss",
            ),
            remove_cell,
        ],
        key=f"pf-drow-{index}-{profile_id or 'x'}",
        **props,
    )


def _depth_chart_col_headers(*, selectable: bool = False, slot_index=None) -> html.Div:
    """Mirror Profiles table order; keep Position / Slot / Role grouped."""
    if selectable and slot_index is not None:
        rank_head = html.Div(
            [
                dmc.Checkbox(
                    id={"type": "pf-depth-select-all", "slot": str(slot_index)},
                    checked=False,
                    size="xs",
                    className="pf-depth-chart-check",
                    **{"aria-label": "Select all players in this slot"},
                ),
                html.Span("", className="pf-depth-chart-grip", **{"aria-hidden": "true"}),
                html.Span("#", className="pf-depth-chart-rank"),
            ],
            className="pf-depth-chart-rank-cell",
        )
    else:
        rank_head = html.Span("#", className="pf-depth-chart-rank")
    return html.Div(
        [
            rank_head,
            html.Span("Name", className="pf-depth-chart-name-label"),
            html.Span("Age", className="pf-depth-chart-age"),
            html.Span("Ht", className="pf-depth-chart-height", title="Height"),
            html.Span("Pos", className="pf-depth-chart-pos"),
            html.Span("Slot", className="pf-depth-chart-slot"),
            html.Span("Role", className="pf-depth-chart-role"),
            html.Span("Feet", className="pf-depth-chart-feet"),
            html.Span("Club", className="pf-depth-chart-club"),
            html.Span("Division", className="pf-depth-chart-div"),
            html.Span("Rec", className="pf-depth-chart-rec"),
            html.Span("INJ", className="pf-depth-chart-injury", title="Injury"),
            html.Span("Score", className="pf-depth-chart-score"),
            html.Span("Mins", className="pf-depth-chart-mins"),
            html.Span("Ovr", className="pf-depth-chart-ovr"),
            html.Span("Def", className="pf-depth-chart-def"),
            html.Span("F3", className="pf-depth-chart-f3", title="Final third"),
            html.Span("Poss", className="pf-depth-chart-poss"),
            html.Span("", className="pf-depth-chart-remove", **{"aria-hidden": "true"}),
        ],
        className="pf-depth-chart-cols",
    )


def _starting_xi_scores(
    slots: list[dict],
    *,
    formation_id: str | None,
    xi_view=None,
    cache: _PfProfileCache | None = None,
) -> list[float]:
    """Role scores for each filled XI slot at the selected depth rank."""
    scores: list[float] = []
    for slot in slots:
        entry = _formation_xi_entry(
            formation_id, slot, xi_view=xi_view, cache=cache
        )
        if not entry:
            continue
        score = (entry.get("row") or {}).get("Score")
        try:
            score_f = float(score) if score not in (None, "", "-", "—") else None
        except (TypeError, ValueError):
            score_f = None
        if score_f is not None:
            scores.append(score_f)
    return scores


def _starting_xi_avg_chip(
    scores: list[float], settings, *, xi_view=None
) -> html.Span | None:
    if not scores:
        return None
    settings = us.normalize(settings)
    avg = sum(scores) / len(scores)
    band = score_band(avg, **settings["bands"])
    n = len(scores)
    xi_name = _xi_view_label(xi_view)
    return html.Span(
        [
            html.Span("Avg score", className="rs-depth-avg-label"),
            html.Span(f"{avg:.1f}", className=f"rs-depth-avg rs-band-{band}"),
        ],
        className="pf-depth-chart-xi-avg-wrap",
        title=f"Average role score across {n} {xi_name} player{'s' if n != 1 else ''}",
    )


def _build_formation_xi_chart(
    slots: list[dict],
    *,
    formation_id: str | None = None,
    settings=None,
    theme=None,
    minutes_required=None,
    xi_view=None,
    cache: _PfProfileCache | None = None,
) -> html.Div:
    """One player per formation slot at the selected XI depth rank (read-only)."""
    settings = us.normalize(settings)
    mins_limit = _resolve_minutes_required(minutes_required, settings)
    xi_view = _normalize_xi_view(xi_view)
    xi_rank = _xi_rank(xi_view)
    xi_label = _xi_view_label(xi_view)
    if not slots:
        return html.Div(
            "This formation has no filled IP+OOP slots.",
            className="text-muted small",
        )
    _starters, multi_starters, conflicted_slots, unique_slots = (
        _formation_starter_slot_maps(
            formation_id, slots, xi_view=xi_view, cache=cache
        )
    )
    xi_scores = _starting_xi_scores(
        slots, formation_id=formation_id, xi_view=xi_view, cache=cache
    )
    xi_avg_chip = _starting_xi_avg_chip(xi_scores, settings, xi_view=xi_view)
    filled = sum(
        1
        for slot in slots
        if _formation_xi_entry(
            formation_id, slot, xi_view=xi_view, cache=cache
        )
        is not None
    )
    rows = []
    for index, slot in enumerate(slots):
        entry = _formation_xi_entry(
            formation_id, slot, xi_view=xi_view, cache=cache
        )
        slot_index = int(slot["index"])
        rows.append(
            _depth_chart_player_row(
                entry,
                index=index,
                total=len(slots),
                settings=settings,
                theme=theme,
                slot_label=slot.get("display_label") or slot.get("label") or "",
                slot_index=slot["index"],
                role_column=slot.get("column") or "",
                slot_conflicted=slot_index in conflicted_slots,
                slot_unique=slot_index in unique_slots,
                draggable=False,
                removable=True,
                minutes_required=mins_limit,
                name_src="xi",
            )
        )
    hint = (
        f"Rank #{xi_rank} player for each formation slot. "
        "× removes that player from the slot only (Recently removed). "
        "Click a Squad depth card above to edit depth."
    )
    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Span(
                                xi_label,
                                className="pf-depth-chart-role-name",
                            ),
                            html.Span(
                                f"{filled}/{len(slots)}",
                                className="pf-depth-chart-count",
                                title=f"{filled} filled of {len(slots)} slots",
                            ),
                            xi_avg_chip,
                        ],
                        className="pf-depth-chart-role-title",
                    ),
                    html.Span(
                        hint,
                        className="text-muted small",
                    ),
                ],
                className="pf-depth-chart-role-head",
            ),
            _depth_chart_col_headers(),
            html.Div(rows, className="pf-depth-chart-list pf-depth-chart-xi"),
        ],
        className="pf-depth-chart-section",
    )


def _setpiece_chart_col_headers(*, show_height: bool, score_abbr: str) -> html.Div:
    cells = [
        html.Span("#", className="pf-depth-chart-rank"),
        html.Span("Name", className="pf-depth-chart-name-label"),
        html.Span("Age", className="pf-depth-chart-age"),
    ]
    if show_height:
        cells.append(
            html.Span("Ht", className="pf-depth-chart-height", title="Height")
        )
    cells.extend(
        [
            html.Span("Pos", className="pf-depth-chart-pos"),
            html.Span("Feet", className="pf-depth-chart-feet"),
            html.Span("Club", className="pf-depth-chart-club"),
            html.Span("Division", className="pf-depth-chart-div"),
            html.Span("Rec", className="pf-depth-chart-rec"),
            html.Span("INJ", className="pf-depth-chart-injury", title="Injury"),
            html.Span(
                score_abbr or "Score",
                className="pf-depth-chart-score",
                title=score_abbr or "Set piece score",
            ),
            html.Span(
                "Slot",
                className="pf-setpiece-chart-slot",
                title="Highest-ranked formation slot (Starting XI order breaks ties)",
            ),
            html.Span(
                "Rk",
                className="pf-setpiece-chart-slot-rank",
                title="Depth rank in that slot",
            ),
        ]
    )
    return html.Div(cells, className="pf-setpiece-chart-cols")


def _setpiece_chart_player_row(
    entry: dict | None,
    *,
    index: int,
    score: float | None,
    settings,
    theme=None,
    show_height: bool = False,
    slot_label: str | None = None,
    slot_rank: int | None = None,
) -> html.Div:
    """Read-only depth-style row for the set-piece leaderboard."""
    settings = us.normalize(settings)
    odd = " is-odd" if index % 2 else ""
    slot_text = _blank(slot_label) if slot_label not in (None, "") else "—"
    rank_text = str(slot_rank) if isinstance(slot_rank, int) and slot_rank > 0 else "—"

    if entry is None:
        cells = [
            html.Span(str(index + 1), className="pf-depth-chart-rank"),
            html.Span("—", className="pf-depth-chart-name is-empty"),
            html.Span("—", className="pf-depth-chart-age"),
        ]
        if show_height:
            cells.append(html.Span("—", className="pf-depth-chart-height"))
        cells.extend(
            [
                html.Span("—", className="pf-depth-chart-pos"),
                html.Span("—", className="pf-depth-chart-feet"),
                html.Span("—", className="pf-depth-chart-club"),
                html.Span("—", className="pf-depth-chart-div"),
                html.Span("—", className="pf-depth-chart-rec"),
                html.Span("—", className="pf-depth-chart-injury"),
                html.Div(
                    html.Span("—", className="pf-depth-chart-metric"),
                    className="pf-depth-chart-score",
                ),
                html.Span("—", className="pf-setpiece-chart-slot"),
                html.Span("—", className="pf-setpiece-chart-slot-rank"),
            ]
        )
        return html.Div(
            cells,
            className="pf-setpiece-chart-row is-empty" + odd,
        )

    row = entry.get("row") or {}
    profile_id = str(entry.get("id") or "").strip()
    name, club = profiles.profile_identity(entry)
    player = entry.get("player") if isinstance(entry.get("player"), dict) else {}
    feet_row = dict(row)
    if feet_row.get("Left Foot") in (None, "", "-", "—") and player.get("left_foot"):
        feet_row["Left Foot"] = player.get("left_foot")
    if feet_row.get("Right Foot") in (None, "", "-", "—") and player.get("right_foot"):
        feet_row["Right Foot"] = player.get("right_foot")
    position = _blank(row.get("Position"))
    if position == "—":
        position = _blank(row.get("Best Pos"))
    division = _blank(row.get("Division"))
    tier = classify_division(row.get("Division"), row.get("Nation"))
    from scoring.stats_availability import (
        LIMITED_DIVISION_TITLE,
        division_has_limited_tracking,
    )

    limited = division_has_limited_tracking(
        row.get("Division"), _limited_tracking_divisions()
    )
    div_class = "pf-depth-chart-div"
    if tier:
        div_class = f"{div_class} pf-div-{tier}"
    if limited:
        div_class = f"{div_class} pf-div-limited"
    div_title = (
        f"{division} — {LIMITED_DIVISION_TITLE}" if limited and division != "—" else division
    )
    injury_html = injury_cell(row.get("Injury"))
    cells = [
        html.Span(str(index + 1), className="pf-depth-chart-rank"),
        (
            html.Button(
                name or "Player",
                id={
                    "type": "pf-depth-name",
                    "id": profile_id,
                    "src": "setpiece",
                    "slot": str(index),
                },
                n_clicks=0,
                className="pf-depth-chart-name",
                title="Open player details",
                type="button",
            )
            if profile_id
            else html.Span("—", className="pf-depth-chart-name is-empty")
        ),
        _depth_plain_cell(row.get("Age"), "pf-depth-chart-age"),
    ]
    if show_height:
        cells.append(_depth_plain_cell(row.get("Height"), "pf-depth-chart-height"))
    cells.extend(
        [
            html.Span(position, className="pf-depth-chart-pos", title=position),
            dcc.Markdown(
                feet_cell(feet_row),
                dangerously_allow_html=True,
                className="pf-depth-chart-feet",
            ),
            html.Span(club or "—", className="pf-depth-chart-club", title=club or ""),
            html.Span(division, className=div_class, title=div_title),
            _depth_rec_cell(row.get("Rec"), theme=theme),
            (
                dcc.Markdown(
                    injury_html,
                    dangerously_allow_html=True,
                    className="pf-depth-chart-injury",
                )
                if injury_html and injury_html not in ("—", "-", "")
                else html.Span("—", className="pf-depth-chart-injury")
            ),
            html.Div(
                _depth_score_cell(score, settings, theme=theme),
                className="pf-depth-chart-score",
            ),
            html.Span(
                slot_text,
                className="pf-setpiece-chart-slot",
                title=slot_text if slot_text != "—" else "Not in any formation slot",
            ),
            html.Span(
                rank_text,
                className="pf-setpiece-chart-slot-rank",
                title=(
                    f"Depth rank #{rank_text} in {slot_text}"
                    if rank_text != "—"
                    else "Not in any formation slot"
                ),
            ),
        ]
    )
    return html.Div(
        cells,
        className="pf-setpiece-chart-row" + odd,
        key=f"pf-sp-{index}-{profile_id or 'x'}",
        **({"data-profile-id": profile_id} if profile_id else {}),
    )


def _setpiece_ranked_table(
    ranked: list[tuple[dict, float | None]],
    *,
    settings,
    theme=None,
    show_height: bool = False,
    score_abbr: str = "Score",
    slot_map: dict[str, tuple[int, str]] | None = None,
    empty_message: str = "No matching players.",
) -> html.Div:
    if not ranked:
        return html.Div(empty_message, className="text-muted small pf-setpiece-empty")
    slot_map = slot_map or {}
    rows = []
    for index, (entry, score) in enumerate(ranked):
        key = _entry_player_key(entry)
        placement = slot_map.get(key)
        slot_rank = placement[0] if placement else None
        slot_label = placement[1] if placement else None
        rows.append(
            _setpiece_chart_player_row(
                entry,
                index=index,
                score=score,
                settings=settings,
                theme=theme,
                show_height=show_height,
                slot_label=slot_label,
                slot_rank=slot_rank,
            )
        )
    return html.Div(
        [
            _setpiece_chart_col_headers(
                show_height=show_height, score_abbr=score_abbr
            ),
            html.Div(rows, className="pf-setpiece-chart-list"),
        ]
    )


def _setpiece_group_section(
    *,
    title: str,
    count_label: str,
    count_title: str,
    hint: str,
    table: html.Div,
    show_height: bool = False,
    help_id: str | None = None,
) -> html.Div:
    title_row: list = [
        html.Span(title, className="pf-depth-chart-role-name"),
        html.Span(
            count_label,
            className="pf-depth-chart-count",
            title=count_title,
        ),
    ]
    if hint:
        hid = help_id or f"pf-help-setpiece-{re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')}"
        title_row.extend(help_icon(hint, hid))
    return html.Div(
        [
            html.Div(
                html.Div(title_row, className="pf-depth-chart-role-title"),
                className="pf-depth-chart-role-head",
            ),
            table,
        ],
        className="pf-depth-chart-section pf-setpiece-chart"
        + (" is-aerial" if show_height else ""),
    )


def _build_setpiece_chart(
    piece_id: str | None = None,
    *,
    settings=None,
    theme=None,
    formation_id: str | None = None,
    formation_slots: list[dict] | None = None,
    cache: _PfProfileCache | None = None,
) -> html.Div:
    """Top set-piece scores among unique players in the active library."""
    settings = us.normalize(settings)
    piece_id = _normalize_setpiece_view(piece_id, settings)
    profile = _setpiece_profile(piece_id, settings)
    abbr = str((profile or {}).get("abbr") or (profile or {}).get("label") or "Score")
    label = str((profile or {}).get("label") or abbr)
    show_height = piece_id == "aerial"
    slots = list(formation_slots or [])
    slot_map = _best_slot_by_player_key(formation_id, slots, cache=cache)

    if piece_id in SET_PIECE_FOOTED_IDS:
        _, left_ranked = _top_setpiece_entries(
            piece_id,
            settings=settings,
            limit=SET_PIECE_FOOT_TOP_N,
            foot_side="left",
            cache=cache,
        )
        _, right_ranked = _top_setpiece_entries(
            piece_id,
            settings=settings,
            limit=SET_PIECE_FOOT_TOP_N,
            foot_side="right",
            cache=cache,
        )
        left_table = _setpiece_ranked_table(
            left_ranked,
            settings=settings,
            theme=theme,
            show_height=False,
            score_abbr=abbr,
            slot_map=slot_map,
            empty_message="No strong left-footed takers yet.",
        )
        right_table = _setpiece_ranked_table(
            right_ranked,
            settings=settings,
            theme=theme,
            show_height=False,
            score_abbr=abbr,
            slot_map=slot_map,
            empty_message="No strong right-footed takers yet.",
        )
        return html.Div(
            [
                html.Div(
                    [
                        html.Div(
                            [
                                html.Span(
                                    label,
                                    className="pf-depth-chart-role-name",
                                ),
                                html.Span(
                                    "L/R · Strong",
                                    className="pf-depth-chart-count",
                                    title=(
                                        f"Top {SET_PIECE_FOOT_TOP_N} strong "
                                        "left- and right-footed takers"
                                    ),
                                ),
                                *help_icon(
                                    "Strong foot or better. Slot is the best depth rank "
                                    "across the formation; ties keep the earlier Starting XI slot.",
                                    "pf-help-setpiece-foot-split",
                                ),
                            ],
                            className="pf-depth-chart-role-title",
                        ),
                    ],
                    className="pf-depth-chart-role-head pf-setpiece-chart-head",
                ),
                html.Div(
                    [
                        _setpiece_group_section(
                            title="Left · Strong",
                            count_label=f"Top {len(left_ranked)}",
                            count_title=(
                                f"Top {len(left_ranked)} of up to "
                                f"{SET_PIECE_FOOT_TOP_N} strong left foot"
                            ),
                            hint="Left Foot ≥ Strong",
                            table=left_table,
                        ),
                        _setpiece_group_section(
                            title="Right · Strong",
                            count_label=f"Top {len(right_ranked)}",
                            count_title=(
                                f"Top {len(right_ranked)} of up to "
                                f"{SET_PIECE_FOOT_TOP_N} strong right foot"
                            ),
                            hint="Right Foot ≥ Strong",
                            table=right_table,
                        ),
                    ],
                    className="pf-setpiece-footed-grid",
                ),
            ],
            className="pf-setpiece-chart-shell",
        )

    _, ranked = _top_setpiece_entries(
        piece_id,
        settings=settings,
        limit=SET_PIECE_TOP_N,
        cache=cache,
    )
    table = _setpiece_ranked_table(
        ranked,
        settings=settings,
        theme=theme,
        show_height=show_height,
        score_abbr=abbr,
        slot_map=slot_map,
        empty_message="No saved players in this profile yet.",
    )
    return _setpiece_group_section(
        title=label,
        count_label=f"Top {len(ranked)}" if ranked else "Top 0",
        count_title=(
            f"Top {len(ranked)} of up to {SET_PIECE_TOP_N} by {label} score"
        ),
        hint=(
            "Unique players in this library, ranked by set-piece score. "
            "Slot is the best depth rank across the formation; ties keep the "
            "earlier Starting XI slot. Read-only."
        ),
        table=table,
        show_height=show_height,
    )


def _mount_depth_chart(chart, *, epoch: str | int | None = None) -> html.Div:
    """Wrap chart so Dash must remount after drag DOM mutations / auto-rank."""
    token = str(epoch if epoch is not None else uuid.uuid4().hex)
    return html.Div(
        chart if chart is not None else [],
        id=f"pf-depth-mount-{token}",
        className="pf-depth-chart-mount",
    )


def _build_depth_chart(
    *,
    focus_roles=None,
    formation_id: str | None = None,
    formation_slots: list[dict] | None = None,
    hybrids_only: bool = False,
    settings=None,
    theme=None,
    minutes_required=None,
    xi_view=None,
    cache: _PfProfileCache | None = None,
) -> html.Div:
    settings = us.normalize(settings)
    mins_limit = _resolve_minutes_required(minutes_required, settings)
    focus = _focus_slot(focus_roles)
    slots = list(formation_slots or [])
    xi_view = _normalize_xi_view(xi_view)

    if not focus:
        if slots:
            return html.Div(
                "Click a Squad depth card to rank that slot.",
                className="text-muted small",
            )
        return html.Div(
            "Select a role in Squad depth to edit its ranking.",
            className="text-muted small",
        )

    column = focus["role"]
    slot_index = focus.get("slot", -1)
    slot_label = focus.get("label") or ""
    match = None
    if slots:
        match = next(
            (
                item
                for item in slots
                if int(item["index"]) == int(slot_index)
                and item["column"] == column
            ),
            None,
        )
        if match:
            slot_label = match.get("display_label") or match.get("label") or slot_label
        elif not slot_label:
            match = next((item for item in slots if item["column"] == column), None)
            if match:
                slot_label = match.get("display_label") or match.get("label") or ""
                slot_index = match["index"]

    if hybrids_only and "+" not in column:
        return html.Div(
            "No saved profiles for the focused role.",
            className="text-muted small",
        )

    meta = _role_column_meta(column)
    if cache is not None:
        ordered = cache.ordered_for_slot(formation_id, slot_index, column)
    else:
        ordered = profiles.ordered_profiles_for_slot(
            formation_id, slot_index, column
        )
    if slots:
        _starters, multi_starters, conflicted_slots, unique_slots = (
            _formation_starter_slot_maps(
                formation_id, slots, xi_view=xi_view, cache=cache
            )
        )
    else:
        multi_starters, conflicted_slots, unique_slots = set(), set(), set()
    try:
        focused_slot_index = int(slot_index)
    except (TypeError, ValueError):
        focused_slot_index = -1
    slot_is_conflicted = focused_slot_index in conflicted_slots
    slot_is_unique = focused_slot_index in unique_slots
    if not ordered:
        return html.Div(
            [
                html.Div(
                    [
                        html.Div(
                            [
                                html.Span(
                                    slot_label or _role_display_label(column),
                                    className="pf-depth-chart-role-name",
                                ),
                                html.Span("0", className="pf-depth-chart-count"),
                            ],
                            className="pf-depth-chart-role-title",
                        ),
                    ],
                    className="pf-depth-chart-role-head",
                ),
                html.Div(
                    "No saved profiles for this formation slot’s role.",
                    className="text-muted small px-3 pb-3",
                ),
            ],
            className="pf-depth-chart-section",
        )

    label = _role_display_label(column)
    if label == "—":
        label = meta.get("short_label") or meta.get("name") or column
    tone = str(meta.get("tone") or "").strip().lower()
    if tone.startswith("ip"):
        tone = "ip"
    elif tone.startswith("oop"):
        tone = "oop"
    elif tone in ("combo", "hybrid") or "+" in column:
        tone = "combo"
    elif tone != "gk":
        tone = "gk" if not tone else tone
    role_color = _role_phase_colors(theme).get(tone) or _role_phase_colors(theme)["gk"]
    rows = [
        _depth_chart_player_row(
            entry,
            index=idx,
            total=len(ordered),
            settings=settings,
            theme=theme,
            slot_label=slot_label,
            slot_index=slot_index,
            role_column=column,
            # Slot label reflects this slot’s current starter status; player rows
            # that are starters elsewhere also stay red for quick scanning.
            slot_conflicted=(
                slot_is_conflicted
                or _entry_player_key(entry) in multi_starters
            ),
            slot_unique=(
                slot_is_unique and _entry_player_key(entry) not in multi_starters
            ),
            draggable=True,
            selectable=True,
            minutes_required=mins_limit,
            name_src="depth",
        )
        for idx, entry in enumerate(ordered)
    ]
    title_label = f"{slot_label} · {label}" if slot_label else label
    order_ids = [str(entry.get("id") or "") for entry in ordered if entry.get("id")]
    order_fp = uuid.uuid5(
        uuid.NAMESPACE_OID, f"{formation_id}|{slot_index}|{'|'.join(order_ids)}"
    ).hex[:12]
    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Div(
                                [
                                    _colored_group_abbr(
                                        meta.get("group_abbr") or "",
                                        css="rs-depth-code",
                                    ),
                                    html.Span(
                                        meta.get("phase") or "",
                                        className=f"rs-phase-tag {meta.get('tone') or 'gk'}",
                                    ),
                                    html.Span(
                                        title_label,
                                        className=f"pf-depth-chart-role-name pf-role-{tone}",
                                        style={"color": role_color},
                                    ),
                                    html.Span(
                                        f"{len(ordered)}",
                                        className="pf-depth-chart-count",
                                    ),
                                ],
                                className="pf-depth-chart-role-title",
                            ),
                            html.Div(
                                [
                                    dmc.Button(
                                        "Remove selected",
                                        id={
                                            "type": "pf-depth-remove-selected",
                                            "role": column,
                                            "slot": str(slot_index),
                                        },
                                        size="sm",
                                        variant="filled",
                                        color="red",
                                        n_clicks=0,
                                        disabled=True,
                                        className="pf-depth-role-btn pf-depth-role-btn-remove",
                                    ),
                                    dmc.Button(
                                        "Auto-rank by Score",
                                        id={
                                            "type": "pf-depth-auto-role",
                                            "role": column,
                                            "slot": str(slot_index),
                                        },
                                        size="sm",
                                        variant="filled",
                                        color="teal",
                                        n_clicks=0,
                                        className="pf-depth-role-btn pf-depth-role-btn-rank",
                                    ),
                                ],
                                className="pf-depth-chart-role-actions",
                            ),
                        ],
                        className="pf-depth-chart-role-head",
                    ),
                    _depth_chart_col_headers(
                        selectable=True, slot_index=slot_index
                    ),
                    html.Div(
                        [
                            html.Div(
                                className="pf-depth-chart-drop-line",
                                **{"aria-hidden": "true"},
                            ),
                            *rows,
                            html.Div(
                                className="pf-depth-chart-drop-end",
                                **{"aria-hidden": "true"},
                            ),
                        ],
                        # Fingerprint in the id forces a clean remount when order
                        # changes (auto-rank / remove). Avoids React/DOM desync
                        # after pointer-drag mutates the list in place.
                        id=f"pf-depth-list-{slot_index}-{order_fp}",
                        className="pf-depth-chart-list",
                        **{
                            "data-role": column,
                            "data-slot": str(slot_index),
                            "data-formation": str(formation_id or ""),
                        },
                    ),
                ],
                className="pf-depth-chart-section",
            )
        ],
        className="pf-depth-chart-sections",
        key=f"pf-depth-sections-{slot_index}-{order_fp}",
    )


def _role_table_columns(settings, *, include_slot: bool = False) -> list[dict]:
    settings = us.normalize(settings)
    cols = []
    for col in _profile_identity_columns("role_scores", settings):
        spec = {"name": identity_header_name(col), "id": col}
        if col in ("Feet", "Injury"):
            spec["presentation"] = "markdown"
        cols.append(spec)
    if include_slot:
        cols.append({"name": "Slot", "id": "Slot", "presentation": "markdown"})
    cols.append({"name": "Role", "id": "Role", "presentation": "markdown"})
    cols.append({"name": "Rank", "id": "Rank"})
    cols.append({"name": "Score", "id": "Score", "presentation": "markdown"})
    cols.append({"name": "Mins", "id": "Minutes", "presentation": "markdown"})
    for pct in PCT_COLS:
        cols.append(
            {
                "name": _pct_header_name(pct),
                "id": pct,
                "presentation": "markdown",
            }
        )
    return cols


# Left-aligned identity columns on Profiles (everything else is centered).
_PF_LEFT_COLS = ("Name", "Position", "Club")

# Minimum widths: as tight as headers + typical cell content allow.
# No fixed widths — fill_width can still grow columns into spare space.
_PF_COL_MIN_WIDTHS: dict[str, str] = {
    "Name": "120px",
    "Position": "72px",
    "Club": "88px",
    "Division": "80px",
    "Age": "42px",
    "Height": "44px",
    "Feet": "72px",
    "Rec": "42px",
    "Injury": "40px",
    "Nation": "64px",
    "Inf": "40px",
    "Best Pos": "48px",
    "Slot": "56px",
    "Role": "56px",
    "Rank": "48px",
    "Score": "52px",
    "Minutes": "48px",
    "overall": "44px",
    "defending": "44px",
    "final_third": "72px",
    "possession": "48px",
}


_PF_NOWRAP_COLS = ("Name", "Position", "Club", "Division", "Slot")


def _pf_col_box(column_id: str, *, header: bool = False) -> dict:
    """Shared min-width / wrap / align box for Profiles headers and cells."""
    align = "left" if column_id in _PF_LEFT_COLS else "center"
    nowrap = column_id in _PF_NOWRAP_COLS
    box: dict = {
        "textAlign": align,
        "minWidth": _PF_COL_MIN_WIDTHS.get(column_id, "44px"),
        "whiteSpace": "nowrap" if nowrap else ("pre-line" if header else "normal"),
        "overflow": "visible",
        "lineHeight": "1.15",
        "padding": "6px 4px",
    }
    # Text identity cols grow with content (one line); metrics stay compact.
    if nowrap:
        box["maxWidth"] = "none"
        if column_id == "Name":
            box["padding"] = "6px 10px 6px 6px" if header else "6px 6px"
    else:
        box["width"] = _PF_COL_MIN_WIDTHS.get(column_id, "44px")
        box["maxWidth"] = _PF_COL_MIN_WIDTHS.get(column_id, "44px")
    if header:
        if column_id in _PF_LEFT_COLS:
            box["padding"] = "8px 14px 8px 6px"
        else:
            box["padding"] = "8px 4px"
        if column_id in ("Rank", "Score", "overall", "Age", "Rec"):
            box["fontWeight"] = "700"
        elif column_id not in _PF_LEFT_COLS:
            box["fontWeight"] = "600"
    else:
        if column_id in ("Rank", "Age", "Rec", "Score", "Minutes", *PCT_COLS):
            box["fontVariantNumeric"] = "tabular-nums"
        if column_id in ("Rank", "Rec"):
            box["fontWeight"] = "700"
        elif column_id == "Minutes":
            box["fontWeight"] = "650"
        elif column_id in ("Role", "Division"):
            box["fontWeight"] = "600"
        if column_id == "Feet":
            box["padding"] = "4px 2px"
            box["overflow"] = "visible"
        if column_id == "Injury":
            box["padding"] = "0"
    return box


def _table_header_styles(*, include_role: bool = False, include_score: bool = False) -> list[dict]:
    """Profiles headers: left Name/Pos/Club; center the rest; mins fit titles."""
    col_ids = [
        *_PF_LEFT_COLS,
        "Division",
        "Age",
        "Height",
        "Feet",
        "Rec",
        "Injury",
        "Nation",
        "Inf",
        "Best Pos",
        "Minutes",
        *PCT_COLS,
    ]
    if include_role:
        col_ids.extend(["Slot", "Role", "Rank"])
    if include_score:
        col_ids.append("Score")
    # De-dupe while preserving order
    seen: set[str] = set()
    ordered: list[str] = []
    for col_id in col_ids:
        if col_id not in seen:
            seen.add(col_id)
            ordered.append(col_id)
    return [{"if": {"column_id": col_id}, **_pf_col_box(col_id, header=True)} for col_id in ordered]


def _role_metric_styles() -> list[dict]:
    col_ids = [
        *_PF_LEFT_COLS,
        "Division",
        "Age",
        "Height",
        "Feet",
        "Rec",
        "Injury",
        "Nation",
        "Inf",
        "Best Pos",
        "Slot",
        "Role",
        "Rank",
        "Score",
        "Minutes",
        *PCT_COLS,
    ]
    return [{"if": {"column_id": col_id}, **_pf_col_box(col_id)} for col_id in col_ids]


def _pct_metric_styles() -> list[dict]:
    col_ids = [
        *_PF_LEFT_COLS,
        "Division",
        "Age",
        "Height",
        "Feet",
        "Rec",
        "Injury",
        "Nation",
        "Inf",
        "Best Pos",
        "Minutes",
        *PCT_COLS,
    ]
    return [{"if": {"column_id": col_id}, **_pf_col_box(col_id)} for col_id in col_ids]


def _role_table_styles(theme, settings=None) -> tuple[list, list]:
    data = identity_data_styles(theme, settings=settings, extra=_role_metric_styles())
    # Override shared left-align for Division/Nation/Inf — Profiles centers those.
    header = style_header_conditional(
        extra=_table_header_styles(include_role=True, include_score=True)
    )
    return data, header


def _resolve_profile_id(row_id) -> str:
    """Map table/depth row ids back to a stored profile id."""
    text = str(row_id or "").strip()
    if not text or text.endswith("-empty"):
        return ""
    if text.startswith("slot-"):
        # slot-{index}-{profile_id}
        parts = text.split("-", 2)
        if len(parts) < 3:
            return ""
        pid = parts[2].strip()
        return "" if pid in ("empty", "player", "") else pid
    return text


def _entry_to_role_table_row(
    entry: dict,
    *,
    settings,
    theme=None,
    slot_label: str = "—",
    slot_conflicted: bool = False,
    slot_unique: bool = False,
    row_id: str | None = None,
    depth_rank: int | None = None,
    minutes_required=None,
) -> tuple[dict, dict]:
    """Build one profiles table row from a role profile entry."""
    settings = us.normalize(settings)
    identity = _profile_identity_columns("role_scores", settings)
    raw = dict(entry.get("row") or {})
    if not raw.get("Role"):
        raw["Role"] = entry.get("role_column") or ""
    role_column = str(raw.get("Role") or entry.get("role_column") or "").strip()
    score_raw = raw.get("Score")
    try:
        score_f = (
            float(score_raw) if score_raw not in (None, "", "-", "—") else None
        )
    except (TypeError, ValueError):
        score_f = None
    overall_raw = _raw_float(raw.get("overall"))
    pct_raw = {pct: _raw_float(raw.get(pct)) for pct in PCT_COLS}
    # Prefer explicit slot/list position; fall back to persisted depth_rank.
    if depth_rank is not None:
        try:
            rank_raw = int(depth_rank)
        except (TypeError, ValueError):
            rank_raw = None
        if rank_raw is not None and rank_raw <= 0:
            rank_raw = None
    else:
        rank_raw = _depth_rank_value(entry)
    profile_id = str(entry.get("id") or "").strip()
    item: dict = {
        "id": row_id or profile_id,
        "_key": row_id or profile_id,
        "_profile_id": profile_id,
        "_role_column": role_column,
        "_rank_raw": rank_raw,
        "_score_raw": score_f,
        "_overall_raw": overall_raw,
        **{f"_{pct}_raw": pct_raw[pct] for pct in PCT_COLS},
    }
    for col in identity:
        if col == "Feet":
            item[col] = feet_cell(raw)
        elif col == "Injury":
            item[col] = injury_cell(raw.get("Injury"))
        else:
            item[col] = _blank(raw.get(col))
    _apply_profile_division(item, raw)
    item["Slot"] = _slot_cell_markdown(
        slot_label or "—",
        conflicted=slot_conflicted,
        unique=slot_unique,
    )
    item["Role"] = _role_cell_markdown(role_column, theme=theme)
    item["Rank"] = str(rank_raw) if rank_raw is not None else "—"
    item["Score"] = _score_markdown(score_raw, settings, theme=theme)
    mins_raw = _profile_minutes_raw(entry, raw)
    item["_minutes_raw"] = mins_raw
    item["Minutes"] = _minutes_cell(
        mins_raw, settings, minutes_required=minutes_required
    )
    for pct in PCT_COLS:
        item[pct] = _pct_markdown(raw.get(pct), raw.get(f"{pct}_color"))
    return item, injury_tooltip_entry(raw.get("Injury"))


def _empty_slot_table_row(
    slot: dict,
    *,
    settings,
    theme=None,
    slot_conflicted: bool = False,
    slot_unique: bool = False,
) -> tuple[dict, dict]:
    settings = us.normalize(settings)
    identity = _profile_identity_columns("role_scores", settings)
    column = slot["column"]
    label = slot.get("display_label") or slot.get("label") or "—"
    item: dict = {
        "id": f"slot-{slot['index']}-empty",
        "_key": f"slot-{slot['index']}-empty",
        "_profile_id": "",
        "_role_column": column,
        "_rank_raw": None,
        "_score_raw": None,
        "_overall_raw": None,
        **{f"_{pct}_raw": None for pct in PCT_COLS},
        "Slot": _slot_cell_markdown(
            label, conflicted=slot_conflicted, unique=slot_unique
        ),
        "Role": _role_cell_markdown(column, theme=theme),
        "Rank": "—",
        "Score": "—",
        "Minutes": "—",
        "_minutes_raw": None,
    }
    for col in identity:
        item[col] = "—"
    item["Division"] = "—"
    item["DivisionTier"] = ""
    item["DivisionLimited"] = "no"
    for pct in PCT_COLS:
        item[pct] = "—"
    return item, {}


def _build_formation_xi_table_rows(
    slots: list[dict],
    *,
    formation_id: str | None = None,
    settings=None,
    theme=None,
    xi_view=None,
    cache: _PfProfileCache | None = None,
) -> tuple[list[dict], list[dict]]:
    """One table row per formation slot using that slot’s selected XI rank."""
    rows = []
    tips = []
    xi_view = _normalize_xi_view(xi_view)
    xi_rank = _xi_rank(xi_view)
    _starters, multi_starters, conflicted_slots, unique_slots = (
        _formation_starter_slot_maps(
            formation_id, slots, xi_view=xi_view, cache=cache
        )
    )
    for slot in slots:
        entry = _formation_xi_entry(
            formation_id, slot, xi_view=xi_view, cache=cache
        )
        label = slot.get("display_label") or slot.get("label") or "—"
        slot_index = int(slot["index"])
        conflicted = slot_index in conflicted_slots
        unique = slot_index in unique_slots
        if entry:
            item, tip = _entry_to_role_table_row(
                entry,
                settings=settings,
                theme=theme,
                slot_label=label,
                slot_conflicted=conflicted,
                slot_unique=unique,
                row_id=f"slot-{slot['index']}-{entry.get('id') or 'player'}",
                depth_rank=xi_rank,
            )
        else:
            item, tip = _empty_slot_table_row(
                slot,
                settings=settings,
                theme=theme,
                slot_conflicted=conflicted,
                slot_unique=unique,
            )
        item["_slot_order"] = slot_index
        rows.append(item)
        tips.append(tip)
    return rows, tips


def _build_role_table_rows(
    settings=None,
    theme=None,
    *,
    cache: _PfProfileCache | None = None,
) -> tuple[list[dict], list[dict]]:
    settings = us.normalize(settings)
    rows = []
    tips = []
    # Prefer list position within each role so Rank stays filled even when
    # persisted depth_rank was never written (slot-depth is source of truth).
    by_role: dict[str, list[dict]] = {}
    entries = (
        cache.list_role_profiles()
        if cache is not None
        else profiles.list_role_profiles()
    )
    for entry in entries:
        role = str(entry.get("role_column") or "").strip()
        by_role.setdefault(role, []).append(entry)
    for role, role_entries in by_role.items():
        if not role:
            ordered = list(role_entries)
        elif cache is not None:
            ordered = cache.ordered_for_role(role)
        else:
            ordered = profiles.ordered_profiles_for_role(role)
        seen = set()
        for index, entry in enumerate(ordered):
            pid = str(entry.get("id") or "").strip()
            if pid:
                seen.add(pid)
            item, tip = _entry_to_role_table_row(
                entry,
                settings=settings,
                theme=theme,
                depth_rank=index + 1,
            )
            rows.append(item)
            tips.append(tip)
        for entry in role_entries:
            pid = str(entry.get("id") or "").strip()
            if pid and pid in seen:
                continue
            item, tip = _entry_to_role_table_row(
                entry, settings=settings, theme=theme
            )
            rows.append(item)
            tips.append(tip)
    return rows, tips


def _sort_role_rows(rows: list[dict]) -> list[dict]:
    """Role asc, Rank asc (unranked last), Score desc, overall percentile desc."""

    def key(row: dict):
        role = str(row.get("_role_column") or row.get("Role") or "").casefold()
        rank = row.get("_rank_raw")
        rank_sort = (0, int(rank)) if rank is not None else (1, 0)
        score = row.get("_score_raw")
        overall = row.get("_overall_raw")
        score_sort = -float(score) if score is not None else float("inf")
        overall_sort = -float(overall) if overall is not None else float("inf")
        return (role, rank_sort, score_sort, overall_sort)

    return sorted(rows, key=key)


def _filter_role_rows(rows: list[dict], *, focus_roles) -> list[dict]:
    """Keep rows for the focused Squad depth role (or all when none focused)."""
    focused = _focus_roles(focus_roles)
    if not focused:
        return list(rows)
    out = []
    for row in rows:
        role_col = str(row.get("_role_column") or row.get("Role") or "").strip()
        if role_col in focused:
            out.append(row)
    return out


def _strip_internal(row: dict) -> dict:
    return {k: v for k, v in row.items() if not k.startswith("_")}


def _table_row_cache_blob(rows, tips, sort_mode: str) -> dict:
    return {
        "rows": list(rows or []),
        "tips": list(tips or []),
        "sort_mode": sort_mode or "roles",
    }


def _display_from_cached_rows(
    rows: list[dict],
    tips: list[dict],
    *,
    settings,
    minutes_required,
) -> tuple[list[dict], list[dict]]:
    display_rows = []
    for row in rows:
        clean = _strip_internal(row)
        clean["Minutes"] = _minutes_cell(
            row.get("_minutes_raw"), settings, minutes_required=minutes_required
        )
        display_rows.append(clean)
    return display_rows, list(tips or [])


def _remint_theme_rows(rows: list[dict], *, settings, theme) -> list[dict]:
    """Refresh Role / Score markdown colors without rebuilding from profiles."""
    out = []
    for row in rows:
        item = dict(row)
        role_col = str(item.get("_role_column") or "").strip()
        if role_col:
            item["Role"] = _role_cell_markdown(role_col, theme=theme)
        item["Score"] = _score_markdown(
            item.get("_score_raw"), settings, theme=theme
        )
        out.append(item)
    return out


def _reorder_tips_for_rows(
    rows: list[dict], tips: list[dict], ordered_rows: list[dict]
) -> list[dict]:
    tip_by_id = {
        str(row.get("id") or ""): tip
        for row, tip in zip(rows, tips)
    }
    return [tip_by_id.get(str(row.get("id") or ""), {}) for row in ordered_rows]


def _depth_undo_limit(settings=None) -> int:
    return us.depth_undo_max(settings)


def _depth_undo_label(item: dict) -> str:
    entries = list(item.get("entries") or [])
    name = ""
    if entries:
        name, _club = profiles.profile_identity(entries[0])
    slot_label = str(item.get("slot_label") or "").strip()
    role = str(item.get("role") or "").strip()
    if not role and entries:
        role = str(
            entries[0].get("role_column")
            or (entries[0].get("row") or {}).get("Role")
            or ""
        ).strip()
    parts = [part for part in (name, slot_label or role) if part]
    return " · ".join(parts) if parts else "Removed player"


def _depth_undo_items(items, *, limit: int | None = None) -> list[dict]:
    max_items = (
        us.normalize_depth_undo_max(limit)
        if limit is not None
        else DEPTH_UNDO_MAX_DEFAULT
    )
    out = []
    for item in list(items or [])[:max_items]:
        if not isinstance(item, dict):
            continue
        undo_id = str(item.get("undo_id") or "").strip()
        if not undo_id:
            continue
        out.append(item)
    return out


def _depth_undo_panel(items, *, limit: int | None = None) -> html.Div:
    rows = []
    valid = _depth_undo_items(items, limit=limit)
    for item in valid:
        undo_id = str(item.get("undo_id") or "").strip()
        slot_label = str(item.get("slot_label") or item.get("role") or "").strip()
        if item.get("source") == "table" or slot_label == "Shortlist":
            meta = "Deleted from shortlist"
        elif slot_label:
            meta = f"Slot {slot_label}"
        else:
            meta = "Formation slot"
        rows.append(
            html.Div(
                [
                    html.Div(
                        [
                            html.Span(
                                _depth_undo_label(item),
                                className="pf-depth-undo-name",
                            ),
                            html.Span(meta, className="pf-depth-undo-meta"),
                        ],
                        className="pf-depth-undo-copy",
                    ),
                    dmc.Button(
                        "Restore",
                        id={"type": "pf-depth-undo-restore", "id": undo_id},
                        size="xs",
                        variant="filled",
                        color="yellow",
                        n_clicks=0,
                    ),
                ],
                className="pf-depth-undo-row",
            )
        )
    if not rows:
        return html.Div(className="pf-depth-undo-panel is-empty")
    count = len(rows)
    return html.Details(
        [
            html.Summary(
                html.Div(
                    [
                        html.Span("Recently removed", className="pf-depth-undo-title"),
                        html.Span(
                            str(count),
                            className="pf-depth-undo-badge",
                            **{"aria-label": f"{count} recently removed"},
                        ),
                        *help_icon(PF_UNDO_TIP, "pf-help-recently-removed"),
                    ],
                    className="pf-depth-undo-title-row",
                ),
                className="pf-depth-undo-summary",
            ),
            html.Div(
                [
                    html.Div(rows, className="pf-depth-undo-list"),
                ],
                className="pf-depth-undo-body",
            ),
        ],
        className="pf-depth-undo-panel",
    )


def _push_depth_undo(undo_items, payload: dict, *, limit: int | None = None) -> list[dict]:
    if not isinstance(payload, dict) or not payload.get("entries"):
        return list(undo_items or [])
    max_items = (
        us.normalize_depth_undo_max(limit)
        if limit is not None
        else DEPTH_UNDO_MAX_DEFAULT
    )
    item = {
        "undo_id": uuid.uuid4().hex[:12],
        **payload,
    }
    next_items = [item]
    for existing in list(undo_items or []):
        if not isinstance(existing, dict):
            continue
        if existing.get("undo_id") == item["undo_id"]:
            continue
        next_items.append(existing)
        if len(next_items) >= max_items:
            break
    return next_items[:max_items]


def _export_staging_notice(count: int):
    if count <= 0:
        return html.Div(className="pf-export-staging-notice is-empty")
    noun = "export" if count == 1 else "exports"
    badge_label = f"{count} staged {noun}"
    return html.Div(
        [
            html.Span(
                str(count),
                className="pf-export-staging-badge",
                **{"aria-label": badge_label},
            ),
            html.Span(
                [
                    html.Strong(f"{count} staged {noun}"),
                    " — use ",
                    html.Strong("Refresh exports"),
                    " to load into squad depth.",
                ],
                className="pf-export-staging-text",
            ),
        ],
        className="pf-export-staging-notice",
        **{"aria-live": "polite"},
    )


def layout(**_kwargs):
    profiles.ensure_dirs()
    settings = us.load()
    mins_req = us.default_minutes_required(settings)
    return dbc.Container(
        [
            dcc.Interval(id="pf-hydrate-tick", interval=50, max_intervals=1),
            dcc.Interval(id="pf-staging-poll", interval=3000, n_intervals=0),
            dcc.Store(id="pf-hydrated", data=False),
            dcc.Store(id="pf-rev", data=0),
            dcc.Store(id="pf-depth-order", data=None),
            dcc.Store(id="pf-depth-order-guard", data=0),
            dcc.Store(id="pf-depth-undo", storage_type="local", data=[]),
            dcc.Store(id="pf-focus-role", data=[]),
            dcc.Store(id="pf-xi-view", storage_type="local", data="first"),
            dcc.Store(id="pf-setpiece-view", storage_type="local", data="corners"),
            dcc.Store(id="pf-formation", storage_type="local", data=None),
            dcc.Store(id="pf-sort-memory", data=None),
            dcc.Store(id="pf-table-row-cache", data=None),
            dcc.Store(id="pf-player-key", data=None),
            dcc.Store(id="pf-compare-keys", data=None),
            dcc.Store(id="pf-selected-order", data=[]),
            dcc.Store(id="pf-depth-compare-order", data=[]),
            dcc.Store(id="pf-compare-view", data="bars", storage_type="local"),
            dcc.Store(id="pf-compare-group", data="mid"),
            pattern_matching_stubs(
                "pf",
                [
                    {"type": "compare-view", "view": "_"},
                    {"type": "compare-group", "group": "_"},
                ],
            ),
            player_modal(prefix="pf"),
            stats_compare_modal(prefix="pf"),
            html.Div(
                [
                    html.H1("Profiles", className="mt-2 mb-0"),
                    *help_icon(PF_PAGE_TIP, "pf-help-page"),
                ],
                className="rs-page-title-row mb-3",
            ),
            dbc.Card(
                [
                    dbc.CardHeader("Profile libraries"),
                    dbc.CardBody(
                        [
                            html.Div(
                                [
                                    html.Div(
                                        [
                                            html.Label(
                                                "Active profile",
                                                className="rs-field-label",
                                            ),
                                            dmc.Select(
                                                id="pf-library-select",
                                                data=profiles.library_options(),
                                                value=profiles.active_library_id() or None,
                                                clearable=False,
                                                searchable=True,
                                                placeholder="Select a profile",
                                                size="sm",
                                            ),
                                        ],
                                        className="pf-library-field",
                                    ),
                                    dmc.Button(
                                        "Delete",
                                        id="pf-library-delete",
                                        size="sm",
                                        variant="light",
                                        color="red",
                                        n_clicks=0,
                                        disabled=len(profiles.list_library_ids()) <= 1,
                                    ),
                                ],
                                className="pf-library-active-row mb-3",
                            ),
                            html.Div(
                                _depth_heading(
                                    "New profile",
                                    PF_NEW_PROFILE_TIP,
                                    "pf-help-new-profile",
                                ),
                                className="rs-depth-heading-copy mb-2",
                            ),
                            html.Div(
                                [
                                    dmc.TextInput(
                                        id="pf-library-name",
                                        label="Name",
                                        placeholder="e.g. Main save · 2026",
                                        size="sm",
                                    ),
                                    dmc.Select(
                                        id="pf-library-formation",
                                        label="Formation",
                                        data=fm.pack_options(),
                                        value=fm.active_id() or None,
                                        clearable=False,
                                        searchable=True,
                                        placeholder="Select a formation",
                                        size="sm",
                                    ),
                                    dmc.Button(
                                        "Create profile",
                                        id="pf-library-create",
                                        size="sm",
                                        n_clicks=0,
                                        disabled=True,
                                    ),
                                ],
                                className="pf-library-create-row",
                            ),
                            html.Div(id="pf-library-status", className="mt-2"),
                        ]
                    ),
                ],
                className="mb-3 rs-section-card",
            ),
            dbc.Card(
                [
                    dbc.CardHeader("Saved players"),
                    dbc.CardBody(
                        [
                            html.Div(
                                [
                                    html.Div(
                                        [
                                            html.Div(
                                                [
                                                    html.Label(
                                                        "Update from saved file",
                                                        className="rs-field-label",
                                                    ),
                                                    *help_icon(
                                                        PF_REPLACE_TIP,
                                                        "pf-help-replace",
                                                    ),
                                                ],
                                                className="rs-field-label-row",
                                            ),
                                            dmc.Select(
                                                id="pf-replace-file",
                                                data=lib.select_options(page="stats"),
                                                value=None,
                                                clearable=True,
                                                searchable=True,
                                                placeholder="Choose a library export",
                                            ),
                                            dmc.Button(
                                                "Replace profile data",
                                                id="pf-replace-btn",
                                                size="sm",
                                                n_clicks=0,
                                                disabled=True,
                                            ),
                                        ],
                                        className="pf-replace-controls",
                                    ),
                                    html.Div(id="pf-replace-status", className="mt-2"),
                                ],
                                className="pf-replace-bar mb-3",
                            ),
                            html.Div(
                                [
                                    html.Div(
                                        [
                                            html.Div(
                                                [
                                                    html.Div(
                                                        [
                                                            html.Div(
                                                                [
                                                                    html.Span(
                                                                        "Squad depth",
                                                                        className="rs-depth-heading-label",
                                                                    ),
                                                                    *help_icon(
                                                                        PF_SQUAD_DEPTH_TIP,
                                                                        "pf-help-squad-depth",
                                                                    ),
                                                                ],
                                                                className="rs-depth-heading-title-row",
                                                            ),
                                                            html.Div(
                                                                [
                                                                    html.Div(
                                                                        id="pf-export-staging-notice",
                                                                        className=(
                                                                            "pf-export-staging-notice-wrap"
                                                                        ),
                                                                    ),
                                                                    html.Span(
                                                                        dmc.Button(
                                                                            [
                                                                                html.Span(
                                                                                    "↻",
                                                                                    className=(
                                                                                        "pf-squad-depth-refresh-icon"
                                                                                    ),
                                                                                    **{
                                                                                        "aria-hidden": "true"
                                                                                    },
                                                                                ),
                                                                                "Refresh exports",
                                                                            ],
                                                                            id="pf-squad-depth-refresh",
                                                                            size="sm",
                                                                            variant="filled",
                                                                            color="teal",
                                                                            n_clicks=0,
                                                                            className=(
                                                                                "pf-squad-depth-refresh "
                                                                                "pf-depth-role-btn "
                                                                                "pf-depth-role-btn-rank"
                                                                            ),
                                                                        ),
                                                                        title=(
                                                                            "Load staged Role scores exports "
                                                                            "into matching slots (keeps current "
                                                                            "ranks; new players append at bottom). "
                                                                            "Players you removed from a slot "
                                                                            "come back when you export them "
                                                                            "again, or via Recently removed."
                                                                        ),
                                                                    ),
                                                                ],
                                                                className=(
                                                                    "pf-squad-depth-refresh-cluster"
                                                                ),
                                                            ),
                                                        ],
                                                        className="pf-squad-depth-title-row",
                                                    ),
                                                ],
                                                className="rs-depth-heading-copy",
                                            ),
                                            html.Div(
                                                [
                                                    html.Div(
                                                        [
                                                            html.Label(
                                                                "Formation",
                                                                className="rs-field-label",
                                                            ),
                                                            html.Div(
                                                                [
                                                                    dmc.Select(
                                                                        id="pf-formation-select",
                                                                        data=fm.pack_options(),
                                                                        value=fm.active_id() or None,
                                                                        placeholder="Select a formation",
                                                                        clearable=False,
                                                                        searchable=True,
                                                                        size="sm",
                                                                        className="pf-formation-dd",
                                                                    ),
                                                                    dcc.Link(
                                                                        "Edit",
                                                                        href="/formations",
                                                                        className="rs-weights-edit",
                                                                        title=(
                                                                            "Open Formations to create "
                                                                            "or edit lineups."
                                                                        ),
                                                                    ),
                                                                ],
                                                                className="pf-formation-row",
                                                            ),
                                                        ],
                                                        className=(
                                                            "pf-squad-depth-field "
                                                            "pf-squad-depth-formation"
                                                        ),
                                                    ),
                                                    html.Div(
                                                        [
                                                            html.Label(
                                                                "Score bands",
                                                                className="rs-field-label",
                                                            ),
                                                            html.Div(
                                                                _band_legend(settings),
                                                                id="pf-band-legend",
                                                            ),
                                                        ],
                                                        className=(
                                                            "pf-squad-depth-field "
                                                            "pf-squad-depth-bands"
                                                        ),
                                                    ),
                                                    html.Div(
                                                        [
                                                            html.Label(
                                                                "Ranking",
                                                                className="rs-field-label",
                                                            ),
                                                            dmc.Button(
                                                                "Auto-rank all roles",
                                                                id="pf-depth-auto-all",
                                                                size="sm",
                                                                variant="filled",
                                                                color="teal",
                                                                n_clicks=0,
                                                                className="pf-depth-role-btn pf-depth-role-btn-rank",
                                                            ),
                                                        ],
                                                        className=(
                                                            "pf-squad-depth-field "
                                                            "pf-squad-depth-ranking"
                                                        ),
                                                    ),
                                                ],
                                                className="pf-squad-depth-actions",
                                            ),
                                        ],
                                        className="rs-depth-heading",
                                    ),
                                    html.Div(id="pf-summary", className="rs-depth-grid"),
                                    _profiles_busy_overlay(
                                        "pf-squad-depth-busy",
                                        "Loading squad depth…",
                                        on=True,
                                    ),
                                ],
                                id="pf-depth-wrap",
                                className="rs-depth-panel mb-2 rs-shortlist-busy-host",
                                hidden=False,
                            ),
                            html.Div(
                                [
                                    html.Div(
                                        [
                                            _depth_heading(
                                                "Depth chart",
                                                PF_DEPTH_CHART_TIP,
                                                "pf-help-depth-chart",
                                            ),
                                            html.Div(
                                                [
                                                    html.Div(
                                                        [
                                                            html.Div(
                                                                [
                                                                    html.Label(
                                                                        "Minutes",
                                                                        className="rs-field-label",
                                                                    ),
                                                                    *help_icon(
                                                                        "Green = meets limit, yellow = ≥ half, "
                                                                        "red = below half. Applies to Mins color "
                                                                        "in the depth chart and Starting XI.",
                                                                        "pf-help-depth-minutes",
                                                                    ),
                                                                ],
                                                                className="rs-field-label-row",
                                                            ),
                                                            dmc.NumberInput(
                                                                id="pf-depth-minutes-required",
                                                                value=mins_req,
                                                                min=0,
                                                                max=20000,
                                                                step=90,
                                                                size="sm",
                                                            ),
                                                        ],
                                                        className=(
                                                            "pf-squad-depth-field "
                                                            "pf-depth-minutes-field"
                                                        ),
                                                    ),
                                                    dmc.Button(
                                                        "Compare selected",
                                                        id="pf-compare-btn",
                                                        size="sm",
                                                        variant="light",
                                                        n_clicks=0,
                                                        disabled=True,
                                                        className="st-compare-btn",
                                                    ),
                                                ],
                                                className="pf-depth-chart-toolbar-actions",
                                            ),
                                        ],
                                        className="pf-depth-chart-toolbar",
                                    ),
                                    html.Div(
                                        id="pf-compare-status",
                                        className="st-compare-status-wrap",
                                    ),
                                    html.Div(id="pf-depth-chart-body"),
                                    html.Div(
                                        id="pf-depth-undo-wrap",
                                        className="pf-depth-undo-wrap",
                                        children=_depth_undo_panel([]),
                                        hidden=True,
                                    ),
                                    _profiles_busy_overlay(
                                        "pf-depth-chart-busy",
                                        "Updating depth chart…",
                                        on=True,
                                    ),
                                ],
                                id="pf-depth-chart-wrap",
                                className="pf-depth-chart-wrap mb-3 rs-shortlist-busy-host",
                                hidden=False,
                            ),
                            html.Div(id="pf-depth-scroll-nudge", hidden=True),
                            html.Div(
                                [
                                    html.Div(
                                        [
                                            _depth_heading(
                                                "Set pieces",
                                                PF_SET_PIECES_TIP,
                                                "pf-help-set-pieces",
                                            ),
                                            html.Div(
                                                [
                                                    html.Label(
                                                        "Category",
                                                        className="rs-field-label",
                                                    ),
                                                    html.Div(
                                                        _setpiece_view_switcher(
                                                            "corners", settings
                                                        ),
                                                        id="pf-setpiece-view-switch",
                                                    ),
                                                ],
                                                className=(
                                                    "pf-squad-depth-field "
                                                    "pf-setpiece-view-field"
                                                ),
                                            ),
                                        ],
                                        className="pf-depth-chart-toolbar",
                                    ),
                                    html.Div(id="pf-setpiece-chart-body"),
                                    _profiles_busy_overlay(
                                        "pf-setpiece-chart-busy",
                                        "Updating set pieces…",
                                        on=True,
                                    ),
                                ],
                                id="pf-setpiece-wrap",
                                className="pf-setpiece-wrap mb-3 rs-shortlist-busy-host",
                            ),
                            html.Div(
                                [
                                    html.Div(
                                        [
                                            _depth_heading(
                                                "Starting XI",
                                                PF_STARTING_XI_TIP,
                                                "pf-help-starting-xi",
                                            ),
                                            html.Div(
                                                [
                                                    html.Label(
                                                        "XI",
                                                        className="rs-field-label",
                                                    ),
                                                    html.Div(
                                                        _xi_view_switcher("first"),
                                                        id="pf-xi-view-switch",
                                                    ),
                                                ],
                                                className=(
                                                    "pf-squad-depth-field "
                                                    "pf-xi-view-field"
                                                ),
                                            ),
                                        ],
                                        className="pf-depth-chart-toolbar",
                                    ),
                                    html.Div(id="pf-xi-chart-body"),
                                    _profiles_busy_overlay(
                                        "pf-xi-chart-busy",
                                        "Updating Starting XI…",
                                        on=True,
                                    ),
                                ],
                                id="pf-xi-wrap",
                                className="pf-xi-wrap mb-3 rs-shortlist-busy-host",
                                hidden=True,
                            ),
                            html.Div(
                                [
                                    html.Div(
                                        [
                                            html.Div(
                                                id="pf-table-empty",
                                                className="rs-table-empty",
                                                hidden=True,
                                            ),
                                            player_data_table(
                                                prefix="pf",
                                                page_size=us.page_size(settings),
                                                style_cell_props=style_cell(
                                                    text_align="right"
                                                ),
                                                style_cell_conditional_rules=style_cell_conditional(),
                                                style_header_props=style_header(),
                                                style_header_conditional_rules=style_header_conditional(),
                                                style_data_conditional_rules=[],
                                                css=table_css(center_non_identity=True),
                                                shell_class_name="rs-table-shell mt-2",
                                            ),
                                        ],
                                        className="rs-table-area",
                                    ),
                                    html.Div(id="pf-table-layout-nudge", hidden=True),
                                    html.Div(
                                        [
                                            html.Div(
                                                id="pf-table-caption",
                                                className="text-muted",
                                            ),
                                            html.Div(
                                                [
                                                    html.Div(
                                                        [
                                                            html.Label(
                                                                "Rows per page",
                                                                className="rs-field-label",
                                                            ),
                                                            dmc.Select(
                                                                id="pf-page-size",
                                                                data=page_size_select_data(
                                                                    settings
                                                                ),
                                                                value=default_page_size_value(
                                                                    settings
                                                                ),
                                                                clearable=False,
                                                                searchable=False,
                                                            ),
                                                        ],
                                                        className="rs-table-page-size",
                                                    ),
                                                    dmc.Button(
                                                        "Select all",
                                                        id="pf-select-all",
                                                        size="sm",
                                                        variant="light",
                                                        n_clicks=0,
                                                        disabled=True,
                                                    ),
                                                    dmc.Button(
                                                        "Delete selected",
                                                        id="pf-delete-selected",
                                                        size="sm",
                                                        variant="light",
                                                        color="red",
                                                        n_clicks=0,
                                                        disabled=True,
                                                        className="rs-squad-clear-btn",
                                                    ),
                                                ],
                                                className="rs-table-caption-actions",
                                            ),
                                        ],
                                        className="rs-table-caption-row mt-2",
                                    ),
                                    _profiles_busy_overlay(
                                        "pf-table-busy",
                                        "Loading profiles…",
                                        on=True,
                                    ),
                                ],
                                id="pf-table-host",
                                className="rs-shortlist-busy-host",
                            ),
                        ]
                    ),
                ],
                className="mb-4 rs-section-card",
            ),
        ],
        fluid=True,
        className="rs-page pf-page",
    )


@callback(
    Output("pf-depth-minutes-required", "value"),
    Input("ui-settings", "data"),
    State("pf-depth-minutes-required", "value"),
)
def sync_pf_minutes_from_settings(settings, depth_minutes):
    settings = us.normalize(settings)
    default_mins = us.default_minutes_required(settings)
    return depth_minutes if depth_minutes is not None else default_mins


@callback(
    Output("pf-hydrated", "data"),
    Input("pf-hydrate-tick", "n_intervals"),
    State("pf-hydrated", "data"),
    prevent_initial_call=True,
)
def hydrate_profiles_page(n_intervals, hydrated):
    """Paint the shell first; unlock the heavy table/depth refresh on the next tick."""
    if hydrated or not n_intervals:
        return no_update
    return True


@callback(
    Output("pf-band-legend", "children"),
    Input("ui-settings", "data"),
)
def sync_band_legend(settings):
    return _band_legend(us.normalize(settings))


@callback(
    Output("pf-formation-select", "data"),
    Output("pf-formation-select", "value"),
    Output("pf-formation", "data", allow_duplicate=True),
    Input("pf-formation", "data"),
    prevent_initial_call="initial_duplicate",
)
def hydrate_pf_formation(stored):
    options = fm.pack_options()
    ids = {opt["value"] for opt in options}
    meta = profiles.get_library()
    preferred = str((meta or {}).get("formation_id") or "").strip()
    if preferred in ids:
        return options, preferred, preferred
    if stored in ids:
        return options, stored, no_update
    active = fm.active_id()
    value = active if active in ids else (options[0]["value"] if options else None)
    return options, value, value


@callback(
    Output("pf-library-create", "disabled"),
    Input("pf-library-name", "value"),
    Input("pf-library-formation", "value"),
)
def toggle_library_create(name, formation_id):
    return not (str(name or "").strip() and str(formation_id or "").strip())


@callback(
    Output("pf-library-select", "data"),
    Output("pf-library-select", "value"),
    Output("pf-library-status", "children"),
    Output("pf-library-name", "value"),
    Output("pf-library-delete", "disabled"),
    Output("pf-rev", "data", allow_duplicate=True),
    Output("pf-formation-select", "value", allow_duplicate=True),
    Output("pf-formation", "data", allow_duplicate=True),
    Output("pf-focus-role", "data", allow_duplicate=True),
    Input("pf-library-create", "n_clicks"),
    State("pf-library-name", "value"),
    State("pf-library-formation", "value"),
    State("pf-rev", "data"),
    prevent_initial_call=True,
)
def create_profile_library(n_clicks, name, formation_id, rev):
    if not n_clicks:
        return (no_update,) * 9
    try:
        meta = profiles.create_library(str(name or ""), str(formation_id or ""))
    except Exception as exc:
        return (
            no_update,
            no_update,
            html.Div(str(exc), className="text-danger small"),
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
        )
    options = profiles.library_options()
    fid = str(meta.get("formation_id") or "")
    if fid and fm.exists(fid):
        fm.load(fid, persist=True)
    msg = html.Div(
        [
            html.Span("✓ ", className="rs-upload-ok"),
            html.Span(f"Created profile “{meta.get('name')}”."),
        ],
        className="up-save-row",
    )
    return (
        options,
        meta["id"],
        msg,
        "",
        len(profiles.list_library_ids()) <= 1,
        int(rev or 0) + 1,
        fid or no_update,
        fid or no_update,
        [],
    )


@callback(
    Output("pf-library-select", "data", allow_duplicate=True),
    Output("pf-library-select", "value", allow_duplicate=True),
    Output("pf-library-status", "children", allow_duplicate=True),
    Output("pf-library-delete", "disabled", allow_duplicate=True),
    Output("pf-rev", "data", allow_duplicate=True),
    Output("pf-formation-select", "value", allow_duplicate=True),
    Output("pf-formation", "data", allow_duplicate=True),
    Output("pf-focus-role", "data", allow_duplicate=True),
    Input("pf-library-delete", "n_clicks"),
    State("pf-library-select", "value"),
    State("pf-rev", "data"),
    prevent_initial_call=True,
)
def delete_profile_library(n_clicks, library_id, rev):
    if not n_clicks:
        return (no_update,) * 8
    try:
        deleted = profiles.delete_library(str(library_id or ""))
    except Exception as exc:
        return (
            no_update,
            no_update,
            html.Div(str(exc), className="text-danger small"),
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
        )
    if not deleted:
        return (
            no_update,
            no_update,
            html.Div("Profile not found.", className="text-danger small"),
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
        )
    options = profiles.library_options()
    active = profiles.active_library_id()
    meta = profiles.get_library(active) or {}
    fid = str(meta.get("formation_id") or "")
    if fid and fm.exists(fid):
        fm.load(fid, persist=True)
    msg = html.Div(
        [
            html.Span("✓ ", className="rs-upload-ok"),
            html.Span("Deleted profile library."),
        ],
        className="up-save-row",
    )
    return (
        options,
        active,
        msg,
        len(profiles.list_library_ids()) <= 1,
        int(rev or 0) + 1,
        fid or no_update,
        fid or no_update,
        [],
    )


@callback(
    Output("pf-rev", "data", allow_duplicate=True),
    Output("pf-formation-select", "value", allow_duplicate=True),
    Output("pf-formation", "data", allow_duplicate=True),
    Output("pf-focus-role", "data", allow_duplicate=True),
    Output("pf-library-status", "children", allow_duplicate=True),
    Input("pf-library-select", "value"),
    State("pf-rev", "data"),
    prevent_initial_call=True,
)
def switch_profile_library(library_id, rev):
    lid = str(library_id or "").strip()
    if not lid:
        return no_update, no_update, no_update, no_update, no_update
    try:
        if lid != profiles.active_library_id():
            profiles.set_active_library(lid)
    except Exception as exc:
        return (
            no_update,
            no_update,
            no_update,
            no_update,
            html.Div(str(exc), className="text-danger small"),
        )
    meta = profiles.get_library(lid) or {}
    fid = str(meta.get("formation_id") or "")
    if fid and fm.exists(fid):
        fm.load(fid, persist=True)
    return int(rev or 0) + 1, fid or no_update, fid or no_update, [], no_update


@callback(
    Output("pf-formation", "data", allow_duplicate=True),
    Output("pf-focus-role", "data", allow_duplicate=True),
    Input("pf-formation-select", "value"),
    State("pf-formation", "data"),
    State("pf-focus-role", "data"),
    prevent_initial_call=True,
)
def persist_pf_formation(value, stored, focus):
    if value and fm.exists(value):
        fm.load(value, persist=True)
        try:
            profiles.update_library_formation(None, value)
        except Exception:
            pass
    slots = _formation_slots(value)
    focused = _focus_slot(focus)
    next_focus = no_update
    if focused:
        match = next(
            (
                slot
                for slot in slots
                if int(slot["index"]) == int(focused.get("slot", -1))
                and slot["column"] == focused.get("role")
            ),
            None,
        )
        if not match:
            next_focus = []
    if value == stored:
        return no_update, next_focus
    return value, next_focus


@callback(
    Output("pf-focus-role", "data", allow_duplicate=True),
    Input({"type": "pf-depth", "slot": ALL, "role": ALL}, "n_clicks"),
    State("pf-focus-role", "data"),
    State("pf-formation-select", "value"),
    prevent_initial_call=True,
)
def focus_profile_role(n_clicks, current_focus, formation_id):
    if not ctx.triggered_id or not clicked(n_clicks):
        return no_update
    role = str(ctx.triggered_id.get("role") or "").strip()
    slot_raw = str(ctx.triggered_id.get("slot") or "").strip()
    if role == "_" or slot_raw == "_":
        return no_update
    column = _depth_id_column(role) or role
    if not column:
        return no_update
    try:
        slot_index = int(slot_raw)
    except (TypeError, ValueError):
        slot_index = -1
    label = ""
    for slot in _formation_slots(formation_id):
        if int(slot["index"]) == slot_index and slot["column"] == column:
            label = slot.get("display_label") or slot.get("label") or ""
            break
    current = _focus_slot(current_focus)
    if (
        current
        and int(current.get("slot", -1)) == slot_index
        and current.get("role") == column
    ):
        return []
    return [{"slot": slot_index, "role": column, "label": label}]


@callback(
    Output("pf-xi-wrap", "hidden"),
    Output("pf-table-host", "hidden"),
    Input("pf-formation-select", "value"),
    Input("pf-hydrated", "data"),
)
def toggle_xi_vs_table(formation_id, hydrated):
    if not hydrated:
        return True, False
    has_formation = bool(_formation_slots(formation_id))
    return not has_formation, has_formation


@callback(
    Output("pf-xi-view", "data"),
    Input({"type": "pf-xi-view", "view": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def set_xi_view(n_clicks):
    if not _pattern_click_triggered() or not clicked(n_clicks):
        return no_update
    view = str((ctx.triggered_id or {}).get("view") or "").strip()
    if view not in ("first", "second"):
        return no_update
    return view


@callback(
    Output("pf-xi-view-switch", "children"),
    Input("pf-xi-view", "data"),
)
def sync_xi_view_switch(view):
    return _xi_view_switcher(view)


@callback(
    Output("pf-setpiece-view", "data"),
    Input({"type": "pf-setpiece-view", "view": ALL}, "n_clicks"),
    State("ui-settings", "data"),
    prevent_initial_call=True,
)
def set_setpiece_view(n_clicks, settings):
    if not _pattern_click_triggered() or not clicked(n_clicks):
        return no_update
    view = str((ctx.triggered_id or {}).get("view") or "").strip()
    settings = us.normalize(settings)
    valid = {str(p.get("id") or "") for p in _setpiece_profile_list(settings)}
    if view not in valid:
        return no_update
    return view


@callback(
    Output("pf-setpiece-view-switch", "children"),
    Input("pf-setpiece-view", "data"),
    Input("ui-settings", "data"),
)
def sync_setpiece_view_switch(view, settings):
    settings = us.normalize(settings)
    return _setpiece_view_switcher(view, settings)


# Squad depth: start with overlay on; hide when cards finish rendering.
# Show again when formation / rev / refresh rebuilds the board (not on XI toggle).
clientside_callback(
    """
    function(formation, rev, refreshClicks) {
        var trig = window.dash_clientside.callback_context.triggered;
        if (!trig || !trig.length) {
            return window.dash_clientside.no_update;
        }
        return "rs-shortlist-busy is-on t-" + String(Date.now());
    }
    """,
    Output("pf-squad-depth-busy", "className"),
    Input("pf-formation-select", "value"),
    Input("pf-rev", "data"),
    Input("pf-squad-depth-refresh", "n_clicks"),
    prevent_initial_call=True,
)

clientside_callback(
    """
    function(_children) {
        var el = document.getElementById("pf-squad-depth-busy");
        if (!el || el.className.indexOf("is-on") === -1) {
            return window.dash_clientside.no_update;
        }
        return "rs-shortlist-busy";
    }
    """,
    Output("pf-squad-depth-busy", "className", allow_duplicate=True),
    Input("pf-summary", "children"),
    prevent_initial_call=True,
)

# Depth chart: spinner while focus / formation / rev / minutes / refresh rebuilds
# (not XI toggle). Refresh also bumps pf-rev after syncing exports.
clientside_callback(
    """
    function(focus, formation, rev, minutes, refreshClicks) {
        var trig = window.dash_clientside.callback_context.triggered;
        if (!trig || !trig.length) {
            return window.dash_clientside.no_update;
        }
        return "rs-shortlist-busy is-on t-" + String(Date.now());
    }
    """,
    Output("pf-depth-chart-busy", "className"),
    Input("pf-focus-role", "data"),
    Input("pf-formation-select", "value"),
    Input("pf-rev", "data"),
    Input("pf-depth-minutes-required", "value"),
    Input("pf-squad-depth-refresh", "n_clicks"),
    prevent_initial_call=True,
)

clientside_callback(
    """
    function(_children) {
        var el = document.getElementById("pf-depth-chart-busy");
        if (!el || el.className.indexOf("is-on") === -1) {
            return window.dash_clientside.no_update;
        }
        return "rs-shortlist-busy";
    }
    """,
    Output("pf-depth-chart-busy", "className", allow_duplicate=True),
    Input("pf-depth-chart-body", "children"),
    prevent_initial_call=True,
)

# Starting XI panel: spinner on XI toggle, formation, rev, minutes (not slot focus).
clientside_callback(
    """
    function(xiView, formation, rev, minutes, hydrated) {
        var trig = window.dash_clientside.callback_context.triggered;
        if (!trig || !trig.length) {
            return window.dash_clientside.no_update;
        }
        return "rs-shortlist-busy is-on t-" + String(Date.now());
    }
    """,
    Output("pf-xi-chart-busy", "className"),
    Input("pf-xi-view", "data"),
    Input("pf-formation-select", "value"),
    Input("pf-rev", "data"),
    Input("pf-depth-minutes-required", "value"),
    Input("pf-hydrated", "data"),
    prevent_initial_call=True,
)

clientside_callback(
    """
    function(_children) {
        var el = document.getElementById("pf-xi-chart-busy");
        if (!el || el.className.indexOf("is-on") === -1) {
            return window.dash_clientside.no_update;
        }
        return "rs-shortlist-busy";
    }
    """,
    Output("pf-xi-chart-busy", "className", allow_duplicate=True),
    Input("pf-xi-chart-body", "children"),
    prevent_initial_call=True,
)

# Set pieces panel: spinner on category / formation / rev / hydrate.
clientside_callback(
    """
    function(pieceView, formation, rev, hydrated) {
        var trig = window.dash_clientside.callback_context.triggered;
        if (!trig || !trig.length) {
            return window.dash_clientside.no_update;
        }
        return "rs-shortlist-busy is-on t-" + String(Date.now());
    }
    """,
    Output("pf-setpiece-chart-busy", "className"),
    Input("pf-setpiece-view", "data"),
    Input("pf-formation-select", "value"),
    Input("pf-rev", "data"),
    Input("pf-hydrated", "data"),
    prevent_initial_call=True,
)

clientside_callback(
    """
    function(_children) {
        var el = document.getElementById("pf-setpiece-chart-busy");
        if (!el || el.className.indexOf("is-on") === -1) {
            return window.dash_clientside.no_update;
        }
        return "rs-shortlist-busy";
    }
    """,
    Output("pf-setpiece-chart-busy", "className", allow_duplicate=True),
    Input("pf-setpiece-chart-body", "children"),
    prevent_initial_call=True,
)

# Table: spinner for hydrate / library / formation / focus rebuilds (not XI toggle).
clientside_callback(
    """
    function(rev, hydrated, formation, focus) {
        var trig = window.dash_clientside.callback_context.triggered;
        if (!trig || !trig.length) {
            return window.dash_clientside.no_update;
        }
        return "rs-shortlist-busy is-on t-" + String(Date.now());
    }
    """,
    Output("pf-table-busy", "className"),
    Input("pf-rev", "data"),
    Input("pf-hydrated", "data"),
    Input("pf-formation-select", "value"),
    Input("pf-focus-role", "data"),
    prevent_initial_call=True,
)

clientside_callback(
    """
    function(_caption) {
        var el = document.getElementById("pf-table-busy");
        if (!el || el.className.indexOf("is-on") === -1) {
            return window.dash_clientside.no_update;
        }
        return "rs-shortlist-busy";
    }
    """,
    Output("pf-table-busy", "className", allow_duplicate=True),
    Input("pf-table-caption", "children"),
    prevent_initial_call=True,
)


clientside_callback(
    """
    function(focus) {
        const hasFocus = Array.isArray(focus) && focus.length > 0;
        if (!hasFocus) {
            return window.dash_clientside.no_update;
        }
        const scrollToChart = function() {
            const el = document.getElementById("pf-depth-chart-wrap");
            if (!el || el.hidden) {
                return;
            }
            el.scrollIntoView({ behavior: "smooth", block: "start" });
        };
        requestAnimationFrame(scrollToChart);
        setTimeout(scrollToChart, 80);
        setTimeout(scrollToChart, 220);
        return String(Date.now());
    }
    """,
    Output("pf-depth-scroll-nudge", "children"),
    Input("pf-focus-role", "data"),
    prevent_initial_call=True,
)


@callback(
    Output("pf-table", "columns"),
    Output("pf-table", "data"),
    Output("pf-table", "tooltip_data"),
    Output("pf-table", "style_data_conditional"),
    Output("pf-table", "style_header_conditional"),
    Output("pf-table", "page_size"),
    Output("pf-table", "page_current"),
    Output("pf-table", "selected_rows"),
    Output("pf-table", "selected_row_ids"),
    Output("pf-table", "sort_by"),
    Output("pf-sort-memory", "data"),
    Output("pf-table-caption", "children"),
    Output("pf-table-empty", "children"),
    Output("pf-table-empty", "hidden"),
    Output("pf-table-shell", "hidden"),
    Output("pf-select-all", "disabled"),
    Output("pf-delete-selected", "disabled"),
    Output("pf-table-row-cache", "data"),
    Input("pf-rev", "data"),
    Input("pf-focus-role", "data"),
    Input("pf-formation-select", "value"),
    Input("pf-depth-minutes-required", "value"),
    Input("pf-page-size", "value"),
    Input("pf-table", "sort_by"),
    Input("ui-settings", "data"),
    Input("theme", "data"),
    Input("pf-hydrated", "data"),
    State("pf-sort-memory", "data"),
    State("pf-table-row-cache", "data"),
)
def refresh_profiles_table(
    _rev,
    focus_role,
    formation_id,
    depth_minutes_required,
    page_size,
    sort_by,
    settings,
    theme,
    hydrated,
    sort_memory,
    row_cache,
):
    """Rebuild the profiles DataTable only (hidden when a formation is active)."""
    if not hydrated:
        return (no_update,) * 18

    settings = us.normalize(settings)
    formation_slots = _formation_slots(formation_id)
    if formation_slots:
        # Starting XI panel owns the formation lineup view.
        return (no_update,) * 14 + (True,) + (True, True, no_update)

    try:
        page_size_i = int(page_size or default_page_size_value(settings))
    except (TypeError, ValueError):
        page_size_i = us.page_size(settings)
    depth_minutes_f = _resolve_minutes_required(depth_minutes_required, settings)
    triggered = {
        (item.get("prop_id") or "").split(".")[0]
        for item in (ctx.triggered or [])
        if item.get("prop_id")
    }
    triggered_props = {
        item.get("prop_id", "") for item in (ctx.triggered or []) if item.get("prop_id")
    }
    cache_blob = row_cache if isinstance(row_cache, dict) else {}
    cached_rows = cache_blob.get("rows") or []
    cached_tips = cache_blob.get("tips") or []
    cached_mode = cache_blob.get("sort_mode") or "roles"

    # Page-size only: pagination without rebuilding cells.
    if triggered == {"pf-page-size"}:
        return (
            (no_update,) * 5
            + (page_size_i, 0)
            + (no_update,) * 11
        )

    # Pure header-sort: reorder cached full rows (keeps _rank_raw etc.).
    if triggered_props == {"pf-table.sort_by"} and cached_rows:
        formation_slots = _formation_slots(formation_id)
        columns = _role_table_columns(
            settings, include_slot=bool(formation_slots)
        )
        col_ids = {col["id"] for col in columns}
        sort_in = list(sort_by) if sort_by else []
        sort_by = _coerce_sort_by(
            sort_in,
            cached_mode,
            col_ids,
            triggered_id=ctx.triggered_id,
            previous=sort_memory,
            reset_default=False,
        )
        ordered = _sort_profile_rows(cached_rows, sort_by, mode=cached_mode)
        ordered_tips = _reorder_tips_for_rows(cached_rows, cached_tips, ordered)
        display_rows, display_tips = _display_from_cached_rows(
            ordered,
            ordered_tips,
            settings=settings,
            minutes_required=depth_minutes_f,
        )
        return (
            no_update,
            display_rows,
            display_tips,
            no_update,
            no_update,
            no_update,
            0,
            [],
            [],
            sort_by,
            sort_by,
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
            _table_row_cache_blob(ordered, ordered_tips, cached_mode),
        )

    # Theme only: restyle + remint Role/Score colors from cache.
    if triggered == {"theme"} and cached_rows:
        style_data, style_header = _role_table_styles(theme, settings)
        reminted = _remint_theme_rows(
            cached_rows, settings=settings, theme=theme
        )
        display_rows, display_tips = _display_from_cached_rows(
            reminted,
            cached_tips,
            settings=settings,
            minutes_required=depth_minutes_f,
        )
        return (
            no_update,
            display_rows,
            display_tips,
            style_data,
            style_header,
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
            _table_row_cache_blob(reminted, cached_tips, cached_mode),
        )

    # Minutes threshold only: recolor Mins cells from cached _minutes_raw.
    if triggered == {"pf-depth-minutes-required"} and cached_rows:
        display_rows, display_tips = _display_from_cached_rows(
            cached_rows,
            cached_tips,
            settings=settings,
            minutes_required=depth_minutes_f,
        )
        return (
            no_update,
            display_rows,
            display_tips,
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
        )

    # Keep Ovr / category % in sync with adaptive metric ceilings — but only
    # when library or percentile-related settings actually changed.
    _ensure_profile_percentiles(settings)
    reset_sort = bool(triggered & FILTER_SORT_RESET_IDS)
    profile_cache = _PfProfileCache()

    include_slot = False
    columns = _role_table_columns(settings, include_slot=include_slot)
    all_rows, tips = _build_role_table_rows(
        settings, theme=theme, cache=profile_cache
    )
    filtered = _filter_role_rows(all_rows, focus_roles=focus_role)
    sort_mode = "roles"
    style_data, style_header = _role_table_styles(theme, settings)
    empty_msg = (
        "No role profiles yet. Mark players on Role scores and save — "
        "one row per evaluated role, including overall percentiles when available."
    )

    col_ids = {col["id"] for col in columns}
    sort_in = list(sort_by) if sort_by else []
    if reset_sort:
        sort_in = []
    sort_by = _coerce_sort_by(
        sort_in,
        sort_mode,
        col_ids,
        triggered_id=ctx.triggered_id,
        previous=sort_memory,
        reset_default=reset_sort,
    )
    # sort_by is both Input and Output. Echoing it on every pf-rev refresh
    # re-fires this callback into a loop.
    if reset_sort or ctx.triggered_id == "pf-table":
        sort_output = sort_by
    elif _sort_by_signature(sort_by) != _sort_by_signature(sort_in):
        sort_output = sort_by
    else:
        sort_output = no_update
    filtered = _sort_profile_rows(filtered, sort_by, mode=sort_mode)
    display_tips = _reorder_tips_for_rows(all_rows, tips, filtered)
    display_rows, display_tips = _display_from_cached_rows(
        filtered,
        display_tips,
        settings=settings,
        minutes_required=depth_minutes_f,
    )
    row_cache_out = _table_row_cache_blob(filtered, display_tips, sort_mode)

    total = len(all_rows)
    shown = len(display_rows)
    if total and shown != total:
        caption = f"{shown:,} of {total:,} profile row{'s' if total != 1 else ''}"
    else:
        caption = f"{shown:,} profile row{'s' if shown != 1 else ''}"

    no_matches = total > 0 and not display_rows
    if not total:
        return (
            columns,
            [],
            [],
            style_data,
            style_header,
            page_size_i,
            0,
            [],
            [],
            sort_output,
            sort_by,
            caption,
            html.Div(empty_msg, className="text-muted small"),
            False,
            True,
            True,
            True,
            _table_row_cache_blob([], [], sort_mode),
        )
    if no_matches:
        return (
            columns,
            [],
            [],
            style_data,
            style_header,
            page_size_i,
            0,
            [],
            [],
            sort_output,
            sort_by,
            caption,
            html.Div(
                "No profiles match the current filters.",
                className="text-muted small",
            ),
            False,
            True,
            True,
            True,
            row_cache_out,
        )
    return (
        columns,
        display_rows,
        display_tips,
        style_data,
        style_header,
        page_size_i,
        0,
        [],
        [],
        sort_output,
        sort_by,
        caption,
        None,
        True,
        False,
        False,
        True,
        row_cache_out,
    )


@callback(
    Output("pf-summary", "children"),
    Output("pf-depth-wrap", "hidden"),
    Input("pf-rev", "data"),
    Input("pf-formation-select", "value"),
    Input("ui-settings", "data"),
    Input("pf-hydrated", "data"),
    # Focus active-state is clientside; XI conflicts belong on the depth chart.
    State("pf-focus-role", "data"),
    State("pf-xi-view", "data"),
)
def refresh_profiles_squad_depth(
    _rev,
    formation_id,
    settings,
    hydrated,
    focus_role,
    xi_view,
):
    """Rebuild Squad depth cards (formation / library / settings only)."""
    if not hydrated:
        return no_update, no_update

    settings = us.normalize(settings)
    _ensure_profile_percentiles(settings)
    xi_view = _normalize_xi_view(xi_view)
    formation_slots = _formation_slots(formation_id)
    profile_cache = _PfProfileCache()
    entries = profile_cache.list_role_profiles()
    if formation_id and fm.exists(formation_id):
        depth_cards = _profile_depth_panel(
            entries,
            focus_role,
            formation_id=formation_id,
            formation_slots=formation_slots,
            settings=settings,
            xi_view=xi_view,
            cache=profile_cache,
        )
    elif fm.pack_options():
        depth_cards = [
            html.Div(
                "Select a formation to build Squad depth.",
                className="text-muted small",
            )
        ]
    else:
        depth_cards = [
            html.Div(
                "Save a formation on the Formations page to build Squad depth.",
                className="text-muted small",
            )
        ]
    return depth_cards, False


@callback(
    Output("pf-depth-chart-body", "children"),
    Output("pf-depth-chart-wrap", "hidden"),
    Input("pf-rev", "data"),
    Input("pf-focus-role", "data"),
    Input("pf-formation-select", "value"),
    Input("pf-depth-minutes-required", "value"),
    Input("ui-settings", "data"),
    Input("theme", "data"),
    Input("pf-hydrated", "data"),
    State("pf-xi-view", "data"),
)
def refresh_profiles_depth_chart(
    _rev,
    focus_role,
    formation_id,
    depth_minutes_required,
    settings,
    theme,
    hydrated,
    xi_view,
):
    """Rebuild the slot depth chart (focus / minutes / formation — not XI toggle)."""
    if not hydrated:
        return no_update, no_update

    settings = us.normalize(settings)
    _ensure_profile_percentiles(settings)
    xi_view = _normalize_xi_view(xi_view)
    depth_minutes_f = _resolve_minutes_required(depth_minutes_required, settings)
    formation_slots = _formation_slots(formation_id)
    focus = _focus_slot(focus_role)
    profile_cache = _PfProfileCache()
    # Stable mount id per rev — a fresh uuid every refresh remounts the
    # sortable depth list and can stack with sort_by echo into a React loop.
    chart = _mount_depth_chart(
        _build_depth_chart(
            focus_roles=focus_role,
            formation_id=formation_id,
            formation_slots=formation_slots,
            settings=settings,
            theme=theme,
            minutes_required=depth_minutes_f,
            xi_view=xi_view,
            cache=profile_cache,
        ),
        epoch=f"r{int(_rev or 0)}",
    )
    chart_hidden = not formation_slots and not focus
    return chart, chart_hidden


@callback(
    Output("pf-xi-chart-body", "children"),
    Input("pf-xi-view", "data"),
    Input("pf-rev", "data"),
    Input("pf-formation-select", "value"),
    Input("pf-depth-minutes-required", "value"),
    Input("ui-settings", "data"),
    Input("theme", "data"),
    Input("pf-hydrated", "data"),
)
def refresh_profiles_xi_chart(
    xi_view,
    _rev,
    formation_id,
    depth_minutes_required,
    settings,
    theme,
    hydrated,
):
    """Starting / Second XI lineup (decoupled from slot-focus depth chart)."""
    if not hydrated:
        return no_update

    settings = us.normalize(settings)
    _ensure_profile_percentiles(settings)
    xi_view = _normalize_xi_view(xi_view)
    depth_minutes_f = _resolve_minutes_required(depth_minutes_required, settings)
    formation_slots = _formation_slots(formation_id)
    if not formation_slots:
        return html.Div(
            "Select a formation to view Starting XI.",
            className="text-muted small",
        )
    profile_cache = _PfProfileCache()
    return _build_formation_xi_chart(
        formation_slots,
        formation_id=formation_id,
        settings=settings,
        theme=theme,
        minutes_required=depth_minutes_f,
        xi_view=xi_view,
        cache=profile_cache,
    )


@callback(
    Output("pf-setpiece-chart-body", "children"),
    Input("pf-setpiece-view", "data"),
    Input("pf-rev", "data"),
    Input("pf-formation-select", "value"),
    Input("ui-settings", "data"),
    Input("theme", "data"),
    Input("pf-hydrated", "data"),
)
def refresh_profiles_setpiece_chart(
    piece_view,
    _rev,
    formation_id,
    settings,
    theme,
    hydrated,
):
    """Top set-piece scores for unique players in the active library."""
    if not hydrated:
        return no_update

    settings = us.normalize(settings)
    _ensure_profile_percentiles(settings)
    piece_view = _normalize_setpiece_view(piece_view, settings)
    formation_slots = _formation_slots(formation_id)
    profile_cache = _PfProfileCache()
    return _build_setpiece_chart(
        piece_view,
        settings=settings,
        theme=theme,
        formation_id=formation_id,
        formation_slots=formation_slots,
        cache=profile_cache,
    )


clientside_callback(
    """
    function(focusRoles) {
        // Focus is {slot, role, label} (or a legacy role string). Match the
        // formation slot card; clear .active when nothing is selected.
        var focus = null;
        var list = Array.isArray(focusRoles)
            ? focusRoles
            : (focusRoles ? [focusRoles] : []);
        if (list.length) {
            var raw = list[0];
            if (raw && typeof raw === "object") {
                var role = String(raw.role || "").trim();
                if (role) {
                    focus = {
                        role: role,
                        slot: String(
                            raw.slot !== undefined && raw.slot !== null
                                ? raw.slot
                                : ""
                        ),
                    };
                }
            } else if (raw) {
                var legacy = String(raw || "").trim();
                if (legacy) {
                    focus = { role: legacy, slot: "" };
                }
            }
        }
        var cards = document.querySelectorAll("#pf-summary .rs-depth-card");
        cards.forEach(function(card) {
            var role = card.getAttribute("data-rs-role") || "";
            var slot = card.getAttribute("data-rs-slot") || "";
            var on = false;
            if (focus && focus.role) {
                if (focus.slot !== "") {
                    on = role === focus.role && slot === focus.slot;
                } else {
                    on = role === focus.role;
                }
            }
            card.classList.toggle("active", !!on);
        });
        return window.dash_clientside.no_update;
    }
    """,
    Output("pf-summary", "className"),
    Input("pf-focus-role", "data"),
    prevent_initial_call=True,
)


clientside_callback(
    """
    function(_n) {
        requestAnimationFrame(function() {
            window.dispatchEvent(new Event("resize"));
        });
        return "";
    }
    """,
    Output("pf-table-layout-nudge", "children"),
    Input("pf-table", "columns"),
    prevent_initial_call=True,
)


@callback(
    Output("pf-table", "selected_row_ids", allow_duplicate=True),
    Output("pf-table", "selected_rows", allow_duplicate=True),
    Output("pf-selected-order", "data", allow_duplicate=True),
    Input("pf-select-all", "n_clicks"),
    State("pf-table", "data"),
    State("pf-table", "selected_row_ids"),
    State("pf-table", "page_current"),
    State("pf-table", "page_size"),
    State("pf-selected-order", "data"),
    prevent_initial_call=True,
)
def select_all_profiles(n_clicks, rows, selected_ids, page_current, page_size, order):
    if not n_clicks or not rows:
        return no_update, no_update, no_update
    all_ids = [
        row_id
        for row in rows
        if (row_id := str(row.get("id") or row.get("_key") or "").strip())
    ]
    if not all_ids:
        return [], [], []
    current = {str(item) for item in (selected_ids or []) if item}
    # Toggle: clear if every visible row is already selected.
    if current and current.issuperset(all_ids):
        return [], [], []
    try:
        page = int(page_current or 0)
        size = int(page_size or len(rows) or 50)
    except (TypeError, ValueError):
        page, size = 0, len(rows) or 50
    start = max(0, page * size)
    end = start + size
    page_indices = list(range(min(size, max(0, len(rows) - start))))
    return all_ids, page_indices, append_ordered_keys(order, all_ids)


@callback(
    Output("pf-delete-selected", "disabled", allow_duplicate=True),
    Input("pf-table", "selected_row_ids"),
    prevent_initial_call=True,
)
def toggle_delete_btn(selected_ids):
    return not bool(selected_ids)


@callback(
    Output("pf-replace-btn", "disabled"),
    Input("pf-replace-file", "value"),
)
def toggle_replace_btn(file_id):
    return not bool(file_id)


@callback(
    Output("pf-replace-file", "data"),
    Input("pf-rev", "data"),
)
def refresh_replace_file_options(_rev):
    return lib.select_options(page="stats")


@callback(
    Output("pf-replace-status", "children"),
    Output("pf-rev", "data", allow_duplicate=True),
    Input("pf-replace-btn", "n_clicks"),
    State("pf-replace-file", "value"),
    State("ui-settings", "data"),
    State("pf-rev", "data"),
    prevent_initial_call=True,
)
def replace_profiles_from_file(n_clicks, file_id, settings, rev):
    if not n_clicks or not file_id:
        return no_update, no_update
    try:
        result = profiles.replace_profiles_from_saved_file(
            file_id,
            settings=settings,
        )
    except Exception as exc:
        return (
            html.Div(str(exc), className="text-danger small"),
            no_update,
        )
    updated = int(result.get("updated") or 0)
    missing = list(result.get("missing") or [])
    unresolved = list(result.get("unresolved_roles") or [])
    label = result.get("source_label") or "saved file"
    parts = [
        html.Span(
            f"Updated {updated} profile{'s' if updated != 1 else ''} from {label}.",
            className="text-success",
        )
    ]
    if missing:
        sample = ", ".join(missing[:5])
        extra = f" (+{len(missing) - 5} more)" if len(missing) > 5 else ""
        parts.append(
            html.Div(
                f"Not found in file ({len(missing)}): {sample}{extra}",
                className="text-muted small mt-1",
            )
        )
    if unresolved:
        parts.append(
            html.Div(
                f"Skipped unknown roles: {', '.join(unresolved[:5])}",
                className="text-muted small mt-1",
            )
        )
    try:
        next_rev = int(rev or 0) + 1
    except (TypeError, ValueError):
        next_rev = 1
    return html.Div(parts), next_rev


@callback(
    Output("pf-depth-undo", "data", allow_duplicate=True),
    Output("pf-rev", "data", allow_duplicate=True),
    Output("pf-selected-order", "data", allow_duplicate=True),
    Input("pf-delete-selected", "n_clicks"),
    State("pf-table", "selected_row_ids"),
    State("pf-rev", "data"),
    State("pf-depth-undo", "data"),
    State("pf-formation-select", "value"),
    State("ui-settings", "data"),
    State("pf-selected-order", "data"),
    prevent_initial_call=True,
)
def delete_selected(
    n_clicks, selected_ids, rev, undo_items, formation_id, settings, order
):
    if not n_clicks or not selected_ids:
        return no_update, no_update, no_update
    slots = _formation_slots(formation_id)
    limit = _depth_undo_limit(settings)
    next_undo = list(undo_items or [])
    deleted = 0
    seen: set[str] = set()
    removed_rows: set[str] = set()
    for row_id in selected_ids:
        removed_rows.add(str(row_id))
        profile_id = _resolve_profile_id(row_id)
        if not profile_id or profile_id in seen:
            continue
        seen.add(profile_id)
        payload = profiles.delete_profile_with_slot_cleanup(
            profile_id,
            formation_id=formation_id,
            formation_slots=slots,
        )
        if not payload:
            continue
        next_undo = _push_depth_undo(next_undo, payload, limit=limit)
        deleted += 1
    if not deleted:
        return no_update, no_update, no_update
    next_order = [
        key for key in as_list(order) if str(key) not in removed_rows
    ]
    return next_undo, int(rev or 0) + 1, next_order


@callback(
    Output("pf-selected-order", "data", allow_duplicate=True),
    Input("pf-table", "selected_row_ids"),
    State("pf-table", "data"),
    State("pf-selected-order", "data"),
    prevent_initial_call=True,
)
def sync_profile_selection_order(selected_ids, table_data, order):
    table_data = table_data or []
    keys_in_data = {
        key for row in table_data if (key := _profile_table_row_key(row))
    }
    order_list = [str(k) for k in as_list(order) if k]
    order_set = set(order_list)
    expected = {key for key in keys_in_data if key in order_set}
    selected = {str(key) for key in (selected_ids or []) if key}
    if selected == expected:
        return no_update
    if not selected:
        return no_update
    return merge_ordered_keys(
        order_list,
        keys_in_scope=keys_in_data,
        selected_ids=selected_ids,
    )


@callback(
    Output("pf-table", "data", allow_duplicate=True),
    Output("pf-table", "tooltip_data", allow_duplicate=True),
    Output("pf-summary", "children", allow_duplicate=True),
    Output("pf-table-row-cache", "data", allow_duplicate=True),
    Output("pf-depth-order", "data"),
    Output("pf-xi-chart-body", "children", allow_duplicate=True),
    Input("pf-depth-order", "data"),
    State("pf-formation-select", "value"),
    State("pf-focus-role", "data"),
    State("pf-xi-view", "data"),
    State("pf-table", "sort_by"),
    State("pf-depth-order-guard", "data"),
    State("pf-depth-minutes-required", "value"),
    State("ui-settings", "data"),
    State("theme", "data"),
    prevent_initial_call=True,
)
def apply_depth_chart_drag(
    order,
    formation_id,
    focus_role,
    xi_view,
    sort_by,
    order_guard,
    depth_minutes,
    settings,
    theme,
):
    """Persist drag order without remounting the depth chart.

    Bumping pf-rev rebuilds pf-depth-chart-body and fights the live DOM
    reorder (the main source of snap-back / inconsistent drag).
    """
    if not isinstance(order, dict):
        return (no_update,) * 6
    # Drop stale publishes that fired after Auto-rank remounted the list.
    try:
        guard = float(order_guard or 0)
        ts = float(order.get("ts") or 0)
    except (TypeError, ValueError):
        guard, ts = 0.0, 0.0
    if guard and ts and ts < guard:
        return (no_update,) * 6
    role = str(order.get("role") or "").strip()
    formation_id = str(order.get("formation") or formation_id or "").strip()
    ids = [
        str(pid).strip()
        for pid in (order.get("ids") or [])
        if str(pid or "").strip()
    ]
    if not role or not ids:
        return (no_update,) * 6
    slot_raw = order.get("slot")
    if formation_id and slot_raw is not None and str(slot_raw).strip() != "":
        try:
            slot_index = int(slot_raw)
        except (TypeError, ValueError):
            slot_index = slot_raw
        previous = profiles.get_slot_order_ids(
            formation_id, slot_index, role, seed=True
        )
        seen = set(ids)
        merged = list(ids) + [pid for pid in previous if pid not in seen]
        profiles.set_slot_order_ids(formation_id, slot_index, merged)
    else:
        profiles.set_depth_ranks(role, ids)

    settings = us.normalize(settings)
    xi_view = _normalize_xi_view(xi_view)
    depth_minutes_f = _resolve_minutes_required(depth_minutes, settings)
    formation_slots = _formation_slots(formation_id)
    profile_cache = _PfProfileCache()

    depth_cards = _profile_depth_panel(
        profile_cache.list_role_profiles(),
        focus_role,
        formation_id=formation_id,
        formation_slots=formation_slots,
        settings=settings,
        xi_view=xi_view,
        cache=profile_cache,
    )

    if formation_slots:
        xi_chart = _build_formation_xi_chart(
            formation_slots,
            formation_id=formation_id,
            settings=settings,
            theme=theme,
            minutes_required=depth_minutes_f,
            xi_view=xi_view,
            cache=profile_cache,
        )
        return (
            no_update,
            no_update,
            depth_cards,
            no_update,
            no_update,
            xi_chart,
        )

    rows, tips = _build_role_table_rows(
        settings=settings, theme=theme, cache=profile_cache
    )
    filtered = _filter_role_rows(rows, focus_roles=focus_role)
    filtered = _sort_profile_rows(filtered, sort_by, mode="roles")
    display_tips = _reorder_tips_for_rows(rows, tips, filtered)
    display_rows, display_tips = _display_from_cached_rows(
        filtered,
        display_tips,
        settings=settings,
        minutes_required=depth_minutes_f,
    )
    row_cache_out = _table_row_cache_blob(filtered, display_tips, "roles")
    return display_rows, display_tips, depth_cards, row_cache_out, no_update, no_update


@callback(
    Output("pf-rev", "data", allow_duplicate=True),
    Output("pf-depth-chart-body", "children", allow_duplicate=True),
    Output("pf-depth-order-guard", "data"),
    Input({"type": "pf-depth-auto-role", "role": ALL, "slot": ALL}, "n_clicks"),
    State("pf-rev", "data"),
    State("pf-formation-select", "value"),
    State("pf-focus-role", "data"),
    State("pf-xi-view", "data"),
    State("pf-depth-minutes-required", "value"),
    State("ui-settings", "data"),
    State("theme", "data"),
    prevent_initial_call=True,
)
def auto_rank_depth_role(
    n_clicks, rev, formation_id, focus_role, xi_view, depth_minutes, settings, theme
):
    if not _pattern_click_triggered() or not clicked(n_clicks):
        return no_update, no_update, no_update
    role = str(ctx.triggered_id.get("role") or "").strip()
    slot_raw = ctx.triggered_id.get("slot")
    if not role:
        return no_update, no_update, no_update
    try:
        slot_index = int(slot_raw)
    except (TypeError, ValueError):
        slot_index = slot_raw
    if formation_id:
        profiles.auto_rank_slot_by_score(formation_id, slot_index, role)
    else:
        profiles.auto_rank_role_by_score(role)
    formation_slots = _formation_slots(formation_id)
    next_rev = int(rev or 0) + 1
    profile_cache = _PfProfileCache()
    chart = _mount_depth_chart(
        _build_depth_chart(
            focus_roles=focus_role,
            formation_id=formation_id,
            formation_slots=formation_slots,
            settings=settings,
            theme=theme,
            minutes_required=depth_minutes,
            xi_view=xi_view,
            cache=profile_cache,
        ),
        epoch=f"auto-{next_rev}-{uuid.uuid4().hex[:10]}",
    )
    # Invalidate in-flight drag publishes (ts is Date.now() from the browser).
    return next_rev, chart, int(time.time() * 1000)


_PF_SQUAD_DEPTH_REFRESH_CLASS = (
    "pf-squad-depth-refresh pf-depth-role-btn pf-depth-role-btn-rank"
)


@callback(
    Output("pf-export-staging-notice", "children"),
    Output("pf-squad-depth-refresh", "className"),
    Input("pf-library-select", "value"),
    Input("pf-rev", "data"),
    Input("pf-staging-poll", "n_intervals"),
    Input("pf-squad-depth-refresh", "n_clicks"),
)
def refresh_export_staging_notice(
    library_id, _rev, _poll, _refresh_clicks
):
    count = profiles.pending_staged_export_count(library_id)
    notice = _export_staging_notice(count)
    button_class = _PF_SQUAD_DEPTH_REFRESH_CLASS
    if count > 0:
        button_class = f"{button_class} pf-squad-depth-refresh--pending"
    return notice, button_class


@callback(
    Output("pf-rev", "data", allow_duplicate=True),
    Output("pf-depth-chart-body", "children", allow_duplicate=True),
    Output("pf-depth-order-guard", "data", allow_duplicate=True),
    Input("pf-squad-depth-refresh", "n_clicks"),
    State("pf-rev", "data"),
    State("pf-formation-select", "value"),
    State("pf-focus-role", "data"),
    State("pf-xi-view", "data"),
    State("pf-depth-minutes-required", "value"),
    State("ui-settings", "data"),
    State("theme", "data"),
    prevent_initial_call=True,
)
def refresh_depth_from_role_exports(
    n_clicks, rev, formation_id, focus_role, xi_view, depth_minutes, settings, theme
):
    """Load staged Role-score exports into formation slots, then rebuild charts."""
    if not n_clicks:
        return no_update, no_update, no_update
    slots = _formation_slots(formation_id)
    if slots:
        profiles.sync_formation_depth_from_exports(formation_id, slots)
    next_rev = int(rev or 0) + 1
    chart = _mount_depth_chart(
        _build_depth_chart(
            focus_roles=focus_role,
            formation_id=formation_id,
            formation_slots=slots,
            settings=settings,
            theme=theme,
            minutes_required=depth_minutes,
            xi_view=xi_view,
            cache=_PfProfileCache(),
        ),
        epoch=f"sync-{next_rev}-{uuid.uuid4().hex[:10]}",
    )
    return next_rev, chart, int(time.time() * 1000)


@callback(
    Output("pf-rev", "data", allow_duplicate=True),
    Output("pf-depth-chart-body", "children", allow_duplicate=True),
    Output("pf-depth-order-guard", "data", allow_duplicate=True),
    Input("pf-depth-auto-all", "n_clicks"),
    State("pf-rev", "data"),
    State("pf-formation-select", "value"),
    State("pf-focus-role", "data"),
    State("pf-xi-view", "data"),
    State("pf-depth-minutes-required", "value"),
    State("ui-settings", "data"),
    State("theme", "data"),
    prevent_initial_call=True,
)
def auto_rank_depth_all(
    n_clicks, rev, formation_id, focus_role, xi_view, depth_minutes, settings, theme
):
    if not n_clicks:
        return no_update, no_update, no_update
    slots = _formation_slots(formation_id)
    if slots:
        for slot in slots:
            profiles.auto_rank_slot_by_score(
                formation_id, slot["index"], slot["column"]
            )
    else:
        profiles.auto_rank_all_roles_by_score()
    next_rev = int(rev or 0) + 1
    chart = _mount_depth_chart(
        _build_depth_chart(
            focus_roles=focus_role,
            formation_id=formation_id,
            formation_slots=slots,
            settings=settings,
            theme=theme,
            minutes_required=depth_minutes,
            xi_view=xi_view,
            cache=_PfProfileCache(),
        ),
        epoch=f"auto-all-{next_rev}-{uuid.uuid4().hex[:10]}",
    )
    return next_rev, chart, int(time.time() * 1000)


def _slot_role_and_label(formation_id, slot_index, focus_role=None) -> tuple[str, str]:
    role = ""
    slot_label = ""
    try:
        slot_i = int(slot_index)
    except (TypeError, ValueError):
        return "", ""
    for slot in _formation_slots(formation_id):
        if int(slot["index"]) == slot_i:
            role = slot["column"]
            slot_label = slot.get("display_label") or slot.get("label") or ""
            break
    if not role:
        focus = _focus_slot(focus_role)
        if focus and int(focus.get("slot", -1)) == slot_i:
            role = focus["role"]
            slot_label = focus.get("label") or ""
    return role, slot_label


def _remove_ids_from_slot(
    formation_id,
    slot_index,
    role: str,
    profile_ids: list[str],
    undo_items,
    *,
    settings=None,
    slot_label: str = "",
) -> tuple[list[dict], int]:
    """Remove one or more players from a slot depth; returns (undo, removed_count)."""
    pack = str(formation_id or "").strip()
    role = str(role or "").strip()
    if not pack or not role:
        return list(undo_items or []), 0
    # Seed sibling slots that share this role first so they keep their own copy.
    try:
        slot_i = int(slot_index)
    except (TypeError, ValueError):
        slot_i = slot_index
    for slot in _formation_slots(pack):
        if slot["column"] == role and int(slot["index"]) != int(slot_i):
            profiles.get_slot_order_ids(pack, slot["index"], role, seed=True)
    limit = _depth_undo_limit(settings)
    next_undo = list(undo_items or [])
    removed_n = 0
    seen: set[str] = set()
    for profile_id in profile_ids:
        pid = str(profile_id or "").strip()
        if not pid or pid in seen:
            continue
        seen.add(pid)
        removed = profiles.remove_from_slot_depth(pack, slot_i, pid, role)
        if not removed:
            continue
        if slot_label:
            removed["slot_label"] = slot_label
        next_undo = _push_depth_undo(next_undo, removed, limit=limit)
        removed_n += 1
    return next_undo, removed_n


@callback(
    Output("pf-depth-undo", "data"),
    Output("pf-rev", "data", allow_duplicate=True),
    Input({"type": "pf-depth-remove", "id": ALL, "slot": ALL, "src": ALL}, "n_clicks"),
    State("pf-depth-undo", "data"),
    State("pf-rev", "data"),
    State("pf-formation-select", "value"),
    State("pf-focus-role", "data"),
    State("ui-settings", "data"),
    prevent_initial_call=True,
)
def remove_from_depth_chart(
    n_clicks, undo_items, rev, formation_id, focus_role, settings
):
    if not _pattern_click_triggered() or not clicked(n_clicks):
        return no_update, no_update
    profile_id = str(ctx.triggered_id.get("id") or "").strip()
    slot_raw = ctx.triggered_id.get("slot")
    if not profile_id or slot_raw is None:
        return no_update, no_update
    try:
        slot_index = int(slot_raw)
    except (TypeError, ValueError):
        return no_update, no_update
    role, slot_label = _slot_role_and_label(formation_id, slot_index, focus_role)
    if not role or not formation_id:
        return no_update, no_update
    next_undo, removed_n = _remove_ids_from_slot(
        formation_id,
        slot_index,
        role,
        [profile_id],
        undo_items,
        settings=settings,
        slot_label=slot_label,
    )
    if not removed_n:
        return no_update, no_update
    return next_undo, int(rev or 0) + 1


@callback(
    Output({"type": "pf-depth-check", "id": ALL, "slot": ALL}, "checked"),
    Input({"type": "pf-depth-select-all", "slot": ALL}, "checked"),
    State({"type": "pf-depth-check", "id": ALL, "slot": ALL}, "id"),
    prevent_initial_call=True,
)
def toggle_depth_select_all(select_all_checked, check_ids):
    if not check_ids:
        return []
    triggered = ctx.triggered_id
    if not isinstance(triggered, dict):
        return no_update
    slot = str(triggered.get("slot") or "")
    checked = False
    inputs = ctx.inputs_list[0] if ctx.inputs_list else []
    if isinstance(select_all_checked, list) and isinstance(inputs, list):
        for idx, spec in enumerate(inputs):
            sid = spec.get("id") if isinstance(spec, dict) else None
            if isinstance(sid, dict) and str(sid.get("slot") or "") == slot:
                checked = bool(select_all_checked[idx])
                break
        else:
            checked = bool(select_all_checked[0]) if select_all_checked else False
    else:
        checked = bool(select_all_checked)
    out = []
    for spec in check_ids:
        if not isinstance(spec, dict):
            out.append(False)
            continue
        if str(spec.get("slot") or "") != slot:
            out.append(no_update)
        else:
            out.append(checked)
    return out


@callback(
    Output({"type": "pf-depth-remove-selected", "slot": ALL, "role": ALL}, "disabled"),
    Input({"type": "pf-depth-check", "id": ALL, "slot": ALL}, "checked"),
    State({"type": "pf-depth-check", "id": ALL, "slot": ALL}, "id"),
    State({"type": "pf-depth-remove-selected", "slot": ALL, "role": ALL}, "id"),
)
def toggle_depth_remove_selected_disabled(checked_vals, check_ids, button_ids):
    if not button_ids:
        return []
    selected_by_slot: dict[str, int] = {}
    for checked, spec in zip(checked_vals or [], check_ids or []):
        if not checked or not isinstance(spec, dict):
            continue
        slot = str(spec.get("slot") or "")
        selected_by_slot[slot] = selected_by_slot.get(slot, 0) + 1
    return [
        selected_by_slot.get(str((spec or {}).get("slot") or ""), 0) <= 0
        for spec in button_ids
    ]


@callback(
    Output("pf-depth-undo", "data", allow_duplicate=True),
    Output("pf-rev", "data", allow_duplicate=True),
    Input({"type": "pf-depth-remove-selected", "slot": ALL, "role": ALL}, "n_clicks"),
    State({"type": "pf-depth-check", "id": ALL, "slot": ALL}, "checked"),
    State({"type": "pf-depth-check", "id": ALL, "slot": ALL}, "id"),
    State("pf-depth-undo", "data"),
    State("pf-rev", "data"),
    State("pf-formation-select", "value"),
    State("pf-focus-role", "data"),
    State("ui-settings", "data"),
    prevent_initial_call=True,
)
def remove_selected_from_depth_chart(
    n_clicks,
    checked_vals,
    check_ids,
    undo_items,
    rev,
    formation_id,
    focus_role,
    settings,
):
    if not _pattern_click_triggered() or not clicked(n_clicks):
        return no_update, no_update
    slot_raw = ctx.triggered_id.get("slot")
    role = str(ctx.triggered_id.get("role") or "").strip()
    try:
        slot_index = int(slot_raw)
    except (TypeError, ValueError):
        return no_update, no_update
    if not role or not formation_id:
        return no_update, no_update
    selected = []
    for checked, spec in zip(checked_vals or [], check_ids or []):
        if not checked or not isinstance(spec, dict):
            continue
        if str(spec.get("slot") or "") != str(slot_index):
            continue
        pid = str(spec.get("id") or "").strip()
        if pid:
            selected.append(pid)
    if not selected:
        return no_update, no_update
    _role, slot_label = _slot_role_and_label(formation_id, slot_index, focus_role)
    next_undo, removed_n = _remove_ids_from_slot(
        formation_id,
        slot_index,
        role,
        selected,
        undo_items,
        settings=settings,
        slot_label=slot_label,
    )
    if not removed_n:
        return no_update, no_update
    return next_undo, int(rev or 0) + 1


@callback(
    Output("pf-depth-undo-wrap", "children"),
    Output("pf-depth-undo-wrap", "hidden"),
    Input("pf-depth-undo", "data"),
    Input("ui-settings", "data"),
)
def render_depth_undo(undo_items, settings):
    limit = _depth_undo_limit(settings)
    valid = _depth_undo_items(undo_items, limit=limit)
    return _depth_undo_panel(valid, limit=limit), not bool(valid)


@callback(
    Output("pf-depth-undo", "data", allow_duplicate=True),
    Output("pf-rev", "data", allow_duplicate=True),
    Input({"type": "pf-depth-undo-restore", "id": ALL}, "n_clicks"),
    State("pf-depth-undo", "data"),
    State("pf-rev", "data"),
    prevent_initial_call=True,
)
def restore_depth_undo(n_clicks, undo_items, rev):
    if not ctx.triggered_id or not clicked(n_clicks):
        return no_update, no_update
    undo_id = str(ctx.triggered_id.get("id") or "").strip()
    if not undo_id:
        return no_update, no_update
    items = list(undo_items or [])
    match = None
    remaining = []
    for item in items:
        if isinstance(item, dict) and str(item.get("undo_id") or "") == undo_id:
            match = item
            continue
        remaining.append(item)
    if not match:
        return no_update, no_update
    restored = profiles.restore_to_slot_depth(match)
    if not restored:
        return remaining, no_update
    return remaining, int(rev or 0) + 1


@callback(
    Output("pf-player-modal", "is_open", allow_duplicate=True),
    Output("pf-player-modal-title", "children", allow_duplicate=True),
    Output("pf-player-modal-body", "children", allow_duplicate=True),
    Output("pf-player-key", "data", allow_duplicate=True),
    Input({"type": "pf-depth-name", "id": ALL, "src": ALL, "slot": ALL}, "n_clicks"),
    State("ui-settings", "data"),
    State("theme", "data"),
    prevent_initial_call=True,
)
def open_profile_modal_from_depth(n_clicks, settings, theme):
    if not _pattern_click_triggered() or not clicked(n_clicks):
        return no_update, no_update, no_update, no_update
    profile_id = str(ctx.triggered_id.get("id") or "").strip()
    profile = profiles.get_profile(profile_id) if profile_id else None
    if not profile:
        return True, "Player", html.Div("Profile not found."), None
    player = profile.get("player")
    name = (player or {}).get("name") or profiles.profile_identity(profile)[0] or "Player"
    role = profile.get("role_column") or (profile.get("row") or {}).get("Role") or ""
    title = f"{name} · {role}" if role else name
    if not isinstance(player, dict) or not player:
        return (
            True,
            title,
            html.Div(
                "Full player details were not stored with this profile. "
                "Re-save from Role scores to open the scout modal.",
                className="rs-player-missing",
            ),
            profile_id,
        )
    settings = us.normalize(settings)
    body = _build_profile_modal_body(
        profile, player, settings=settings, theme=theme, mode="roles"
    )
    return True, title, body, profile_id


def _resolve_stats_player_for_profile(
    profile: dict, player: dict
) -> tuple[dict | None, list[dict] | None]:
    """Return (stats player, cohort) for the Profiles modal if available."""
    from scoring.stats_scorer import player_key as stats_player_key

    file_id = str(profile.get("file_id") or "").strip()
    stat_players = profiles.load_stats_players_for_file(file_id) if file_id else None

    name = (player.get("name") or "").strip()
    club = (player.get("club") or "").strip()
    target_key = stats_player_key({"name": name, "club": club}) if name else ""

    if stat_players and target_key:
        for sp in stat_players:
            if stats_player_key(sp) == target_key:
                return sp, stat_players

    embedded = profile.get("stats_player")
    if isinstance(embedded, dict) and embedded.get("stats"):
        return embedded, stat_players

    return None, stat_players


def _build_profile_modal_body(
    profile: dict,
    player: dict,
    *,
    settings: dict,
    theme: str | None,
    mode: str = "roles",
) -> html.Div:
    """Shared body builder for open and switch callbacks."""
    stats_player, stats_cohort = _resolve_stats_player_for_profile(profile, player)
    if isinstance(stats_player, dict):
        from scoring.stats_scorer import resolve_player_pos_group

        stats_player = dict(stats_player)
        # Prefer identity from the role export when classifying phase.
        if not stats_player.get("best_pos") and player.get("best_pos"):
            stats_player["best_pos"] = player.get("best_pos")
        if not stats_player.get("position") and player.get("position"):
            stats_player["position"] = player.get("position")
        stats_player["pos_group"] = resolve_player_pos_group(stats_player)
    display_player = dict(player)
    if isinstance(stats_player, dict):
        for key in (
            "minutes",
            "age",
            "club",
            "division",
            "nation",
            "position",
            "best_pos",
            "height",
            "left_foot",
            "right_foot",
            "rec",
            "injury",
            "pos_group",
        ):
            if display_player.get(key) in (None, "", [], {}):
                display_player[key] = stats_player.get(key)

    field_status = minutes_status(
        display_player.get("minutes"), us.default_minutes_required(settings)
    )
    field_styles = {
        "minutes": {"color": minutes_color(field_status)},
        "injury": {"color": "#fbbf24", "fontWeight": "600"},
    }
    segmented = dmc.SegmentedControl(
        id="pf-modal-bottom-mode",
        size="sm",
        value=mode,
        data=[
            {"label": "Role scores", "value": "roles"},
            {"label": "Player stats", "value": "stats"},
        ],
    )

    if (mode or "roles") == "roles":
        role_blocks = []
        role_fit = player_role_fit_section(display_player, settings)
        if role_fit:
            role_blocks.append(role_fit)
        role_blocks.append(player_attributes(display_player, settings["bands"]))
        bottom = html.Div(role_blocks)
    else:
        if stats_player:
            stats_content = stats_charts_bottom_pane(
                stats_player,
                theme=theme,
                view="bars",
                threshold_overrides=settings.get("stats_thresholds"),
                cohort_players=stats_cohort,
            )
        else:
            stats_content = html.P(
                "Player stats not available. This profile was saved from an "
                "attribute-only export. To see charts, re-save from a combined "
                "export that includes Moneyball stats, or compute the library "
                "cache on the Uploads page.",
                className="text-muted small",
            )
        bottom = html.Div(
            [html.Div("Player stats", className="rs-player-id-section-title"), stats_content]
        )

    return player_detail_body(
        display_player,
        id_prefix="pf",
        modal_fields=us.modal_identity_fields_for("player_stats", settings),
        extra_identity_fields=[("Minutes", "minutes")],
        field_styles=field_styles,
        after_identity=segmented,
        bottom=bottom,
        settings=settings,
    )


@callback(
    Output("pf-player-modal", "is_open"),
    Output("pf-player-modal-title", "children"),
    Output("pf-player-modal-body", "children"),
    Output("pf-player-key", "data"),
    Output("pf-table", "active_cell"),
    Input("pf-table", "active_cell"),
    Input("pf-player-modal", "is_open"),
    Input("pf-player-modal-close", "n_clicks"),
    State("pf-table", "derived_viewport_data"),
    State("pf-player-modal", "is_open"),
    State("ui-settings", "data"),
    State("theme", "data"),
    prevent_initial_call=True,
)
def open_profile_modal(
    active_cell,
    _modal_toggle,
    _close_clicks,
    viewport,
    is_open,
    settings,
    theme,
):
    triggered = ctx.triggered_id
    if triggered == "pf-player-modal":
        # Backdrop / Escape / header X — keep Dash in sync when the modal closes itself.
        if not is_open:
            return False, no_update, no_update, None, None
        return no_update, no_update, no_update, no_update, no_update
    if triggered == "pf-player-modal-close":
        return False, no_update, no_update, None, None
    if not active_cell or active_cell.get("column_id") != "Name":
        return no_update, no_update, no_update, no_update, no_update
    row_idx = active_cell.get("row")
    if not isinstance(viewport, list) or row_idx is None:
        return no_update, no_update, no_update, no_update, no_update
    try:
        row_idx = int(row_idx)
    except (TypeError, ValueError):
        return no_update, no_update, no_update, no_update, no_update
    if row_idx < 0 or row_idx >= len(viewport):
        return no_update, no_update, no_update, no_update, no_update
    row = viewport[row_idx] or {}
    profile_id = str(
        row.get("_profile_id") or _resolve_profile_id(row.get("id") or row.get("_key"))
    ).strip()
    profile = profiles.get_profile(profile_id) if profile_id else None
    if not profile:
        return (
            True,
            str(row.get("Name") or "Player"),
            html.Div("Profile not found.", className="rs-player-missing"),
            None,
            None,
        )
    player = profile.get("player")
    name = (player or {}).get("name") or profiles.profile_identity(profile)[0] or "Player"
    role = profile.get("role_column") or (profile.get("row") or {}).get("Role") or ""
    title = f"{name} · {role}" if role else name
    if not isinstance(player, dict) or not player:
        return (
            True,
            title,
            html.Div(
                "Full player details were not stored with this profile. "
                "Re-save from Role scores to open the scout modal.",
                className="rs-player-missing",
            ),
            profile_id,
            None,
        )
    settings = us.normalize(settings)
    body = _build_profile_modal_body(
        profile, player, settings=settings, theme=theme, mode="roles"
    )
    return (True, title, body, profile_id, None)


@callback(
    Output("pf-player-modal-body", "children", allow_duplicate=True),
    Input("pf-modal-bottom-mode", "value"),
    State("pf-player-key", "data"),
    State("ui-settings", "data"),
    State("theme", "data"),
    prevent_initial_call=True,
)
def switch_profile_modal_bottom(mode, profile_id, settings, theme):
    if not profile_id:
        return no_update
    profile = profiles.get_profile(str(profile_id))
    if not profile:
        return no_update
    player = profile.get("player")
    if not isinstance(player, dict) or not player:
        return no_update

    settings = us.normalize(settings)
    return _build_profile_modal_body(
        profile, player, settings=settings, theme=theme, mode=mode or "roles"
    )


def _enrich_stats_player(stats_player: dict | None, player: dict) -> dict | None:
    if not isinstance(stats_player, dict):
        if not isinstance(player, dict) or not player:
            return None
        stats_player = dict(player)
    else:
        stats_player = dict(stats_player)
    for key in ("best_pos", "position", "position_role", "name", "club", "positions"):
        if not stats_player.get(key) and player.get(key):
            stats_player[key] = player.get(key)
    if not stats_player.get("best_pos") and player.get("best_pos"):
        stats_player["best_pos"] = player.get("best_pos")
    if not stats_player.get("position") and player.get("position"):
        stats_player["position"] = player.get("position")
    stats_player["pos_group"] = resolve_player_pos_group(stats_player)
    return stats_player


def _profile_table_row_key(row) -> str:
    if not isinstance(row, dict):
        return ""
    return str(row.get("id") or row.get("_key") or "").strip()


def _depth_checked_profile_ids(
    checked_vals, check_ids
) -> set[str]:
    active: set[str] = set()
    for checked, spec in zip(checked_vals or [], check_ids or []):
        if not checked or not isinstance(spec, dict):
            continue
        pid = str(spec.get("id") or "").strip()
        if pid:
            active.add(pid)
    return active


def _sync_depth_compare_order(
    checked_vals,
    check_ids,
    order,
) -> list[str]:
    active = _depth_checked_profile_ids(checked_vals, check_ids)
    if not active:
        return []
    order_list = [str(k) for k in as_list(order) if str(k) in active]
    seen = set(order_list)
    for checked, spec in zip(checked_vals or [], check_ids or []):
        if not checked or not isinstance(spec, dict):
            continue
        pid = str(spec.get("id") or "").strip()
        if pid and pid in active and pid not in seen:
            order_list.append(pid)
            seen.add(pid)
    return order_list


def _profiles_for_compare(
    ordered_ids, *, selected_ids: list | None = None
) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    selected_set = {str(k) for k in (selected_ids or []) if k}
    for row_id in ordered_ids or []:
        rid = str(row_id)
        if selected_set and rid not in selected_set:
            continue
        profile_id = _resolve_profile_id(row_id)
        if not profile_id or profile_id in seen:
            continue
        profile = profiles.get_profile(profile_id)
        if not profile:
            continue
        seen.add(profile_id)
        out.append(profile)
        if len(out) >= 2:
            break
    return out


def _profile_compare_player_dicts(
    profile_a: dict, profile_b: dict
) -> tuple[dict, dict]:
    players: list[dict] = []
    for profile in (profile_a, profile_b):
        player = profile.get("player") if isinstance(profile.get("player"), dict) else {}
        stats, _ = _resolve_stats_player_for_profile(profile, player or {})
        players.append(_enrich_stats_player(stats, player or {}) or dict(player or {}))
    return players[0], players[1]


def _build_profile_stats_compare_body(
    profile_a: dict,
    profile_b: dict,
    *,
    view: str,
    eval_group: str,
    theme: str | None,
    settings: dict,
) -> html.Div:
    settings = us.normalize(settings)
    player_a = profile_a.get("player") if isinstance(profile_a.get("player"), dict) else {}
    player_b = profile_b.get("player") if isinstance(profile_b.get("player"), dict) else {}
    stats_a, cohort_a = _resolve_stats_player_for_profile(profile_a, player_a)
    stats_b, cohort_b = _resolve_stats_player_for_profile(profile_b, player_b)
    stats_a = _enrich_stats_player(stats_a, player_a) or dict(player_a)
    stats_b = _enrich_stats_player(stats_b, player_b) or dict(player_b)
    label_a = str(stats_a.get("name") or player_a.get("name") or "Player A")
    label_b = str(stats_b.get("name") or player_b.get("name") or "Player B")
    file_a = str(profile_a.get("file_id") or "").strip()
    file_b = str(profile_b.get("file_id") or "").strip()
    same_file = bool(file_a and file_a == file_b)
    thresh = settings.get("stats_thresholds")
    cohort_note = None
    if same_file and cohort_a:
        metric_p0, metric_p100 = adaptive_metric_bound_maps(cohort_a, thresh)
        metric_p0_a = metric_p0_b = metric_p0
        metric_p100_a = metric_p100_b = metric_p100
    else:
        if file_a != file_b:
            cohort_note = (
                "Percentiles are relative to each player's source export; raw values "
                "are directly comparable."
            )
        metric_p0_a, metric_p100_a = (
            adaptive_metric_bound_maps(cohort_a, thresh) if cohort_a else ({}, {})
        )
        metric_p0_b, metric_p100_b = (
            adaptive_metric_bound_maps(cohort_b, thresh) if cohort_b else ({}, {})
        )
    eval_group = normalize_compare_eval_group(eval_group, stats_a, stats_b)

    return stats_compare_body(
        stats_a,
        stats_b,
        label_a=label_a,
        label_b=label_b,
        view=normalize_compare_view(view),
        eval_group=eval_group,
        theme=theme,
        threshold_overrides=thresh,
        metric_p100_a=metric_p100_a,
        metric_p0_a=metric_p0_a,
        metric_p100_b=metric_p100_b,
        metric_p0_b=metric_p0_b,
        cohort_note=cohort_note,
        prefix="pf",
    )


@callback(
    Output("pf-depth-compare-order", "data", allow_duplicate=True),
    Input("pf-rev", "data"),
    prevent_initial_call=True,
)
def clear_depth_compare_order_on_rev(_rev):
    return []


@callback(
    Output("pf-depth-compare-order", "data", allow_duplicate=True),
    Input({"type": "pf-depth-check", "id": ALL, "slot": ALL}, "checked"),
    State({"type": "pf-depth-check", "id": ALL, "slot": ALL}, "id"),
    State("pf-depth-compare-order", "data"),
    prevent_initial_call=True,
)
def sync_depth_compare_order(checked_vals, check_ids, order):
    next_order = _sync_depth_compare_order(checked_vals, check_ids, order)
    prior = [str(k) for k in as_list(order) if k]
    if next_order == prior:
        return no_update
    return next_order


@callback(
    Output("pf-compare-modal", "is_open"),
    Output("pf-compare-modal-title", "children"),
    Output("pf-compare-modal-body", "children"),
    Output("pf-compare-keys", "data"),
    Output("pf-compare-group", "data", allow_duplicate=True),
    Input("pf-compare-btn", "n_clicks"),
    Input("pf-compare-modal", "is_open"),
    Input("pf-compare-modal-close", "n_clicks"),
    State("pf-depth-compare-order", "data"),
    State("pf-compare-view", "data"),
    State("pf-compare-group", "data"),
    State("theme", "data"),
    State("ui-settings", "data"),
    prevent_initial_call=True,
)
def open_profile_compare(
    compare_clicks,
    is_open,
    _close,
    depth_compare_order,
    view,
    eval_group,
    theme,
    settings,
):
    triggered = ctx.triggered_id
    if triggered == "pf-compare-modal":
        if not is_open:
            return False, no_update, no_update, None, no_update
        return no_update, no_update, no_update, no_update, no_update
    if triggered == "pf-compare-modal-close":
        return False, no_update, no_update, None, no_update
    order = [str(k) for k in as_list(depth_compare_order) if k]
    pair = _profiles_for_compare(order, selected_ids=order)
    if len(pair) != 2:
        return no_update, no_update, no_update, no_update, no_update
    profile_a, profile_b = pair
    player_a, player_b = _profile_compare_player_dicts(profile_a, profile_b)
    blocked, _message = compare_control_state(
        2, player_a=player_a, player_b=player_b
    )
    if blocked:
        return (no_update,) * 5
    keys = [str(profile_a.get("id") or ""), str(profile_b.get("id") or "")]
    label_a = str(player_a.get("name") or profiles.profile_identity(profile_a)[0] or "Player A")
    label_b = str(player_b.get("name") or profiles.profile_identity(profile_b)[0] or "Player B")
    settings = us.normalize(settings)
    eval_group_out = default_compare_eval_group(player_a, player_b)
    body = _build_profile_stats_compare_body(
        profile_a,
        profile_b,
        view=view or "bars",
        eval_group=eval_group_out,
        theme=theme,
        settings=settings,
    )
    return (
        True,
        compare_title(label_a, label_b),
        body,
        keys,
        eval_group_out,
    )


def _lookup_profile_compare_pair(compare_keys):
    keys = [str(k) for k in (compare_keys or []) if k]
    if len(keys) != 2:
        return None, None
    profile_a = profiles.get_profile(keys[0])
    profile_b = profiles.get_profile(keys[1])
    if not profile_a or not profile_b:
        return None, None
    return profile_a, profile_b


@callback(
    Output("pf-compare-view", "data", allow_duplicate=True),
    Output("pf-compare-modal-body", "children", allow_duplicate=True),
    Input({"type": "pf-compare-view", "view": ALL}, "n_clicks"),
    State("pf-compare-view", "data"),
    State("pf-compare-group", "data"),
    State("pf-compare-keys", "data"),
    State("theme", "data"),
    State("ui-settings", "data"),
    prevent_initial_call=True,
)
def switch_profile_compare_view(
    n_clicks,
    current,
    eval_group,
    compare_keys,
    theme,
    settings,
):
    if not ctx.triggered_id or not _pattern_click_triggered():
        return no_update, no_update
    view = ctx.triggered_id.get("view")
    if view == "_" or view not in ("values", "bars"):
        return no_update, no_update
    if view == current:
        return no_update, no_update
    profile_a, profile_b = _lookup_profile_compare_pair(compare_keys)
    if not profile_a or not profile_b:
        return normalize_compare_view(view), html.Div("Profiles not found.")
    settings = us.normalize(settings)
    return (
        normalize_compare_view(view),
        _build_profile_stats_compare_body(
            profile_a,
            profile_b,
            view=view,
            eval_group=eval_group,
            theme=theme,
            settings=settings,
        ),
    )


@callback(
    Output("pf-compare-group", "data", allow_duplicate=True),
    Output("pf-compare-modal-body", "children", allow_duplicate=True),
    Input({"type": "pf-compare-group", "group": ALL}, "n_clicks"),
    State("pf-compare-group", "data"),
    State("pf-compare-view", "data"),
    State("pf-compare-keys", "data"),
    State("theme", "data"),
    State("ui-settings", "data"),
    prevent_initial_call=True,
)
def switch_profile_compare_group(
    n_clicks,
    current,
    view,
    compare_keys,
    theme,
    settings,
):
    if not ctx.triggered_id or not _pattern_click_triggered():
        return no_update, no_update
    group = ctx.triggered_id.get("group")
    if group == "_":
        return no_update, no_update
    profile_a, profile_b = _lookup_profile_compare_pair(compare_keys)
    if not profile_a or not profile_b:
        return no_update, no_update
    stats_a, _ = _resolve_stats_player_for_profile(
        profile_a, profile_a.get("player") or {}
    )
    stats_b, _ = _resolve_stats_player_for_profile(
        profile_b, profile_b.get("player") or {}
    )
    if not isinstance(stats_a, dict) or not isinstance(stats_b, dict):
        return no_update, no_update
    from components.stats_compare import compare_eval_groups

    allowed = {key for key, _ in compare_eval_groups(stats_a, stats_b)}
    if group not in allowed:
        return no_update, no_update
    if group == current:
        return no_update, no_update
    settings = us.normalize(settings)
    return (
        group,
        _build_profile_stats_compare_body(
            profile_a,
            profile_b,
            view=normalize_compare_view(view or "bars"),
            eval_group=group,
            theme=theme,
            settings=settings,
        ),
    )


@callback(
    Output("pf-compare-btn", "disabled"),
    Output("pf-compare-status", "children"),
    Input("pf-depth-compare-order", "data"),
)
def update_profiles_compare_controls(depth_compare_order):
    order = [str(k) for k in as_list(depth_compare_order) if k]
    count = len(order)
    if count != 2:
        disabled, message = compare_control_state(count)
        return disabled, compare_status_children(message)
    pair = _profiles_for_compare(order, selected_ids=order)
    if len(pair) != 2:
        return True, compare_status_children(
            "Could not resolve both selected profiles."
        )
    player_a, player_b = _profile_compare_player_dicts(pair[0], pair[1])
    disabled, message = compare_control_state(
        2, player_a=player_a, player_b=player_b
    )
    return disabled, compare_status_children(message)
