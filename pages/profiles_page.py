"""Saved player profiles from Role scores and Player stats."""
from __future__ import annotations

import re
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
    rec_sort_key,
    style_cell,
    style_cell_conditional,
    style_header,
    style_header_conditional,
    table_css,
)
from components.scouting_shell import clicked
from scoring.comparison import score_display
from scoring.division_tiers import apply_division_tier, classify_division
from scoring.role_scorer import (
    combo_column,
    combo_meta,
    group_abbr_tone,
    parse_combo_id,
    role_meta,
    score_band,
    to_int,
)
from scoring.stats_scorer import (
    category_abbr,
    minutes_color,
    minutes_status,
    passes_minutes_filter,
    percentile_color,
)
import services.formations as fm
import services.player_profiles as profiles
import services.ui_settings as us
from components.stats_player_pane import stats_charts_bottom_pane

register_page(__name__, path="/profiles", name="Profiles")

VIEW_MODES = (
    ("roles", "Role scores"),
    ("percentiles", "Overall percentiles"),
)

DEPTH_UNDO_MAX = 5

FILTER_SORT_RESET_IDS = frozenset(
    {
        "pf-view-mode",
        "pf-focus-role",
        "pf-formation-select",
        "pf-pct-search",
        "pf-pct-age",
        "pf-minutes-match",
        "pf-minutes-required",
    }
)

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
    out.sort(
        key=lambda row: (
            1 if row.get("_overall_raw") is None else 0,
            -(float(row.get("_overall_raw") or 0)),
        )
    )
    return out


def _default_sort_by(mode: str) -> list[dict]:
    """Empty sort_by → mode default in _sort_profile_rows (roles: role/score/ovr)."""
    return []


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
    if reset_default or triggered_id == "pf-view-mode":
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


def _minutes_cell(mins_raw, settings) -> str:
    if mins_raw in (None, "", "-", "—", "undefined", "null", "None"):
        return "—"
    try:
        mins_f = float(mins_raw)
    except (TypeError, ValueError):
        return _blank(mins_raw)
    if mins_f != mins_f:  # NaN
        return "—"
    settings = us.normalize(settings)
    minutes_required = us.default_minutes_required(settings)
    status = minutes_status(mins_f, minutes_required)
    text = f"{int(mins_f):,}"
    color = minutes_color(status)
    if not color:
        return text
    return (
        f'<span style="color:{color};font-weight:650;font-variant-numeric:tabular-nums">'
        f"{text}</span>"
    )


def _profile_minutes_status(row: dict, minutes_required: float) -> str:
    raw = row.get("_minutes_raw")
    if raw in (None, "", "-", "—"):
        return minutes_status(None, minutes_required)
    try:
        return minutes_status(float(raw), minutes_required)
    except (TypeError, ValueError):
        return minutes_status(None, minutes_required)


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


def _formation_starter_slot_maps(
    formation_id: str | None,
    slots: list[dict],
) -> tuple[dict[int, str], set[str], set[int], set[int]]:
    """Starter player keys per slot, plus multi/unique starter slot indexes.

    Conflicts are based on each slot’s current #1 only, so they update when the
    Starting XI changes (remove, restore, reorder, auto-rank).
    """
    starters: dict[int, str] = {}
    key_slots: dict[str, set[int]] = {}
    for slot in slots:
        index = int(slot["index"])
        ordered = profiles.ordered_profiles_for_slot(
            formation_id, index, slot["column"]
        )
        key = _entry_player_key(ordered[0]) if ordered else ""
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
        "names": "No saved players",
    }


def _profile_depth_card_stats(meta: dict, entries: list[dict], bands: dict) -> dict | None:
    column = meta["column"]
    eligible = []
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
    if not eligible:
        return None
    scores = [float(row.get(column) or 0) for row in eligible]
    avg = sum(scores) / len(scores)
    counts = {"elite": 0, "good": 0, "ok": 0, "poor": 0}
    for score in scores:
        counts[score_band(score, **bands)] += 1
    total = len(scores) or 1
    top = sorted(eligible, key=lambda row: float(row.get(column) or 0), reverse=True)[:3]
    names = " · ".join(player.get("Name", "") for player in top)
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
    title_bits = [
        html.Div(
            [
                _colored_group_abbr(meta.get("group_abbr") or "", css="rs-depth-code"),
                html.Span(
                    meta.get("phase") or "",
                    className=f"rs-phase-tag {meta.get('tone') or 'gk'}",
                ),
            ],
            className="rs-depth-meta",
        ),
    ]
    if slot_label:
        title_bits.insert(
            0,
            html.Span(
                slot_label,
                className="rs-depth-slot"
                + _slot_status_class(
                    conflicted=slot_conflicted, unique=slot_unique
                ),
                title=(
                    "Same starter as another formation slot"
                    if slot_conflicted
                    else (
                        "Unique starter for this formation slot"
                        if slot_unique
                        else slot_label
                    )
                ),
            ),
        )
    title_bits.append(html.Span(role_label, className="rs-depth-name"))
    children = [
        html.Div(title_bits, className="rs-depth-title"),
        html.Div(
            [
                html.Span("Avg", className="rs-depth-avg-label"),
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
        html.Div(stats["names"], className="rs-depth-players"),
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
            _formation_starter_slot_maps(formation_id, formation_slots)
        )
        cards = []
        for slot in formation_slots:
            meta = _role_column_meta(slot["column"])
            payload = _profile_depth_card_stats(meta, entries, bands)
            if not payload:
                payload = _empty_depth_card_stats(meta)
            slot_index = int(slot["index"])
            cards.append(
                _profile_depth_card(
                    payload,
                    focus_roles,
                    bands,
                    slot=slot,
                    slot_conflicted=slot_index in conflicted_slots,
                    slot_unique=slot_index in unique_slots,
                )
            )
        return cards

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


def _apply_profile_division(item: dict, raw: dict) -> None:
    """Ensure Division text + DivisionTier for table highlighting."""
    if "Division" not in item:
        item["Division"] = _blank(raw.get("Division"))
    tier_row = {
        "Division": raw.get("Division") if raw.get("Division") not in (None, "", "-", "—")
        else item.get("Division"),
        "Nation": raw.get("Nation"),
    }
    apply_division_tier(tier_row)
    item["DivisionTier"] = tier_row.get("DivisionTier") or ""


def _depth_score_cell(score, settings, theme=None):
    """Colored score span matching the Profiles table bands."""
    if score is None or score in ("", "-", "—"):
        return html.Span("—", className="pf-depth-chart-metric")
    settings = us.normalize(settings)
    try:
        score_f = float(score)
        band = score_band(score_f, **settings["bands"])
    except (TypeError, ValueError):
        return html.Span(str(score), className="pf-depth-chart-metric")
    color = us.band_text_colors(settings, theme=theme).get(band)
    style = {"fontWeight": 750, "fontVariantNumeric": "tabular-nums"}
    if color:
        style["color"] = color
    return html.Span(f"{score_f:.1f}", className="pf-depth-chart-metric", style=style)


def _depth_ovr_cell(percentile, color=None):
    """Colored overall percentile span matching the Profiles table."""
    if percentile is None or percentile in ("", "-", "—"):
        return html.Span("—", className="pf-depth-chart-metric")
    try:
        pct_f = float(percentile)
    except (TypeError, ValueError):
        return html.Span(str(percentile), className="pf-depth-chart-metric")
    tint = color or percentile_color(pct_f)
    style = {"fontWeight": 750, "fontVariantNumeric": "tabular-nums"}
    if tint:
        style["color"] = tint
    return html.Span(f"{pct_f:.0f}%", className="pf-depth-chart-metric", style=style)


def _depth_chart_player_row(
    entry: dict | None,
    *,
    index: int,
    total: int,
    settings,
    theme=None,
    slot_label: str = "",
    slot_index: int | str | None = None,
    slot_conflicted: bool = False,
    slot_unique: bool = False,
    draggable: bool = True,
    removable: bool = True,
) -> html.Div:
    del total  # kept for call-site compatibility
    settings = us.normalize(settings)
    remove_cell = html.Span("", className="pf-depth-chart-remove")
    slot_class = "pf-depth-chart-slot" + _slot_status_class(
        conflicted=slot_conflicted, unique=slot_unique
    )
    slot_title = (
        "Same starter as another formation slot"
        if slot_conflicted
        else (
            "Unique starter for this formation slot"
            if slot_unique
            else slot_label
        )
    )
    if entry is None:
        return html.Div(
            [
                html.Div(
                    [
                        html.Span("", className="pf-depth-chart-grip", **{"aria-hidden": "true"}),
                        html.Span(str(index + 1), className="pf-depth-chart-rank"),
                    ],
                    className="pf-depth-chart-rank-cell",
                ),
                html.Span("—", className="pf-depth-chart-name is-empty"),
                html.Span(slot_label or "—", className=slot_class, title=slot_title),
                html.Span("—", className="pf-depth-chart-pos"),
                html.Span("—", className="pf-depth-chart-feet"),
                html.Span("—", className="pf-depth-chart-club"),
                html.Span("—", className="pf-depth-chart-div"),
                html.Div(
                    html.Span("—", className="pf-depth-chart-metric"),
                    className="pf-depth-chart-ovr",
                ),
                html.Div(
                    html.Span("—", className="pf-depth-chart-metric"),
                    className="pf-depth-chart-score",
                ),
                remove_cell,
            ],
            className="pf-depth-chart-row is-empty" + (" is-odd" if index % 2 else ""),
        )
    row = entry.get("row") or {}
    profile_id = str(entry.get("id") or "").strip()
    name, club = profiles.profile_identity(entry)
    display_rank = index + 1
    position = _blank(row.get("Position"))
    if position == "—":
        position = _blank(row.get("Best Pos"))
    division = _blank(row.get("Division"))
    tier = classify_division(row.get("Division"), row.get("Nation"))
    div_class = "pf-depth-chart-div"
    if tier:
        div_class = f"{div_class} pf-div-{tier}"
    if removable and profile_id and slot_index is not None:
        remove_cell = html.Button(
            "×",
            id={
                "type": "pf-depth-remove",
                "id": profile_id,
                "slot": str(slot_index),
            },
            n_clicks=0,
            className="pf-depth-chart-remove-btn",
            title=(
                f"Remove from {slot_label or 'this slot'} only "
                "(other slots keep this player)"
            ),
            **{
                "aria-label": (
                    f"Remove {name or 'player'} from "
                    f"{slot_label or 'this formation slot'}"
                )
            },
        )
    props = {
        "className": "pf-depth-chart-row" + (" is-odd" if index % 2 else ""),
        **({"data-profile-id": profile_id} if profile_id else {}),
    }
    if draggable and profile_id:
        props["draggable"] = "true"
    return html.Div(
        [
            html.Div(
                [
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
                    id={"type": "pf-depth-name", "id": profile_id},
                    n_clicks=0,
                    className="pf-depth-chart-name",
                    title="Open player details",
                )
                if profile_id
                else html.Span("—", className="pf-depth-chart-name is-empty")
            ),
            html.Span(slot_label or "—", className=slot_class, title=slot_title),
            html.Span(position, className="pf-depth-chart-pos", title=position),
            dcc.Markdown(
                feet_cell(row),
                dangerously_allow_html=True,
                className="pf-depth-chart-feet",
            ),
            html.Span(club or "—", className="pf-depth-chart-club", title=club or ""),
            html.Span(division, className=div_class, title=division),
            html.Div(
                _depth_ovr_cell(row.get("overall"), row.get("overall_color")),
                className="pf-depth-chart-ovr",
            ),
            html.Div(
                _depth_score_cell(row.get("Score"), settings, theme=theme),
                className="pf-depth-chart-score",
            ),
            remove_cell,
        ],
        **props,
    )


def _depth_chart_col_headers() -> html.Div:
    return html.Div(
        [
            html.Span("#", className="pf-depth-chart-rank"),
            html.Span("Name", className="pf-depth-chart-name-label"),
            html.Span("Slot", className="pf-depth-chart-slot"),
            html.Span("Pos", className="pf-depth-chart-pos"),
            html.Span("Feet", className="pf-depth-chart-feet"),
            html.Span("Club", className="pf-depth-chart-club"),
            html.Span("Division", className="pf-depth-chart-div"),
            html.Span("Ovr", className="pf-depth-chart-ovr"),
            html.Span("Score", className="pf-depth-chart-score"),
            html.Span("", className="pf-depth-chart-remove", **{"aria-hidden": "true"}),
        ],
        className="pf-depth-chart-cols",
    )


def _build_formation_xi_chart(
    slots: list[dict],
    *,
    formation_id: str | None = None,
    settings=None,
    theme=None,
) -> html.Div:
    """One starter per formation slot (slot-specific depth lists)."""
    settings = us.normalize(settings)
    if not slots:
        return html.Div(
            "This formation has no filled IP+OOP slots.",
            className="text-muted small",
        )
    _starters, multi_starters, conflicted_slots, unique_slots = (
        _formation_starter_slot_maps(formation_id, slots)
    )
    rows = []
    for index, slot in enumerate(slots):
        ordered = profiles.ordered_profiles_for_slot(
            formation_id, slot["index"], slot["column"]
        )
        entry = ordered[0] if ordered else None
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
                slot_conflicted=slot_index in conflicted_slots,
                slot_unique=slot_index in unique_slots,
                draggable=False,
            )
        )
    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Span(
                                "Starting XI",
                                className="pf-depth-chart-role-name",
                            ),
                            html.Span(
                                f"{len(slots)}",
                                className="pf-depth-chart-count",
                            ),
                        ],
                        className="pf-depth-chart-role-title",
                    ),
                    html.Span(
                        "Top player for each formation slot. "
                        "Slots that share a role start with the same exported players, "
                        "then can diverge. Click a Squad depth card to edit that slot.",
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


def _build_depth_chart(
    *,
    focus_roles=None,
    formation_id: str | None = None,
    formation_slots: list[dict] | None = None,
    hybrids_only: bool = False,
    settings=None,
    theme=None,
) -> html.Div:
    settings = us.normalize(settings)
    focus = _focus_slot(focus_roles)
    slots = list(formation_slots or [])

    if not focus:
        if slots:
            return _build_formation_xi_chart(
                slots, formation_id=formation_id, settings=settings, theme=theme
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
    ordered = profiles.ordered_profiles_for_slot(formation_id, slot_index, column)
    if slots:
        _starters, multi_starters, conflicted_slots, unique_slots = (
            _formation_starter_slot_maps(formation_id, slots)
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
        )
        for idx, entry in enumerate(ordered)
    ]
    title_label = f"{slot_label} · {label}" if slot_label else label
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
                            dmc.Button(
                                "Auto-rank by Score",
                                id={
                                    "type": "pf-depth-auto-role",
                                    "role": column,
                                    "slot": str(slot_index),
                                },
                                size="xs",
                                variant="light",
                                n_clicks=0,
                            ),
                        ],
                        className="pf-depth-chart-role-head",
                    ),
                    _depth_chart_col_headers(),
                    html.Div(
                        rows,
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


def _percentile_table_columns(settings) -> list[dict]:
    settings = us.normalize(settings)
    cols = []
    for col in _profile_identity_columns("player_stats", settings):
        spec = {"name": identity_header_name(col), "id": col}
        if col in ("Feet", "Injury"):
            spec["presentation"] = "markdown"
        cols.append(spec)
    cols.append({"name": "Mins", "id": "Minutes"})
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


def _role_table_styles(theme) -> tuple[list, list]:
    data = identity_data_styles(theme, extra=_role_metric_styles())
    # Override shared left-align for Division/Nation/Inf — Profiles centers those.
    header = style_header_conditional(
        extra=_table_header_styles(include_role=True, include_score=True)
    )
    return data, header


def _pct_table_styles(theme) -> tuple[list, list]:
    data = identity_data_styles(theme, extra=_pct_metric_styles())
    header = style_header_conditional(extra=_table_header_styles())
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
    item["Minutes"] = _minutes_cell(mins_raw, settings)
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
    for pct in PCT_COLS:
        item[pct] = "—"
    return item, {}


def _build_formation_xi_table_rows(
    slots: list[dict],
    *,
    formation_id: str | None = None,
    settings=None,
    theme=None,
) -> tuple[list[dict], list[dict]]:
    """One table row per formation slot using that slot’s depth list."""
    rows = []
    tips = []
    _starters, multi_starters, conflicted_slots, unique_slots = (
        _formation_starter_slot_maps(formation_id, slots)
    )
    for slot in slots:
        ordered = profiles.ordered_profiles_for_slot(
            formation_id, slot["index"], slot["column"]
        )
        label = slot.get("display_label") or slot.get("label") or "—"
        slot_index = int(slot["index"])
        conflicted = slot_index in conflicted_slots
        unique = slot_index in unique_slots
        if ordered:
            item, tip = _entry_to_role_table_row(
                ordered[0],
                settings=settings,
                theme=theme,
                slot_label=label,
                slot_conflicted=conflicted,
                slot_unique=unique,
                row_id=f"slot-{slot['index']}-{ordered[0].get('id') or 'player'}",
                depth_rank=1,
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


def _build_role_table_rows(settings=None, theme=None) -> tuple[list[dict], list[dict]]:
    settings = us.normalize(settings)
    rows = []
    tips = []
    # Prefer list position within each role so Rank stays filled even when
    # persisted depth_rank was never written (slot-depth is source of truth).
    by_role: dict[str, list[dict]] = {}
    for entry in profiles.list_role_profiles():
        role = str(entry.get("role_column") or "").strip()
        by_role.setdefault(role, []).append(entry)
    for role, role_entries in by_role.items():
        ordered = (
            profiles.ordered_profiles_for_role(role) if role else list(role_entries)
        )
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


def _build_percentile_table_rows(settings=None) -> tuple[list[dict], list[dict]]:
    settings = us.normalize(settings)
    identity = _profile_identity_columns("player_stats", settings)
    rows = []
    tips = []
    for entry in profiles.list_percentile_profiles():
        raw = dict(entry.get("row") or {})
        pct_raw = {pct: _raw_float(raw.get(pct)) for pct in PCT_COLS}
        item: dict = {
            "id": entry.get("id") or "",
            "_key": entry.get("id") or "",
            "_overall_raw": pct_raw["overall"],
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
        mins = raw.get("Minutes")
        mins_raw = _raw_float(mins)
        item["_minutes_raw"] = mins_raw
        if mins_raw is None:
            item["Minutes"] = "—"
        else:
            item["Minutes"] = f"{int(mins_raw):,}"
        for pct in PCT_COLS:
            item[pct] = _pct_markdown(raw.get(pct), raw.get(f"{pct}_color"))
        rows.append(item)
        tips.append(injury_tooltip_entry(raw.get("Injury")))
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


def _filter_pct_rows(
    rows: list[dict],
    *,
    query: str,
    max_age,
    minutes_match: str,
    minutes_required: float,
) -> list[dict]:
    query = (query or "").strip().lower()
    try:
        max_age_i = 99 if max_age is None else int(max_age)
    except (TypeError, ValueError):
        max_age_i = 99
    out = []
    for row in rows:
        if max_age_i < 99 and to_int(row.get("Age")) > max_age_i:
            continue
        if not passes_minutes_filter(
            _profile_minutes_status(row, minutes_required),
            minutes_match or "any",
        ):
            continue
        if query:
            blob = (
                f"{row.get('Name','')} {row.get('Club','')} "
                f"{row.get('Position','')} {row.get('Division','')}".lower()
            )
            if query not in blob:
                continue
        out.append(row)
    return out


def _strip_internal(row: dict) -> dict:
    return {k: v for k, v in row.items() if not k.startswith("_")}


def _minutes_filter_panel(mins_req: int) -> html.Div:
    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Label("Minutes", className="rs-field-label"),
                            *help_icon(
                                f"Default requirement {mins_req} min. "
                                "Green=meet, yellow=≥half, red=below half.",
                                "pf-help-minutes",
                            ),
                        ],
                        className="rs-field-label-row",
                    ),
                    html.Div(
                        [
                            dmc.NumberInput(
                                id="pf-minutes-required",
                                value=mins_req,
                                min=0,
                                max=20000,
                                step=90,
                            ),
                            dmc.Select(
                                id="pf-minutes-match",
                                data=[
                                    {"label": "Any", "value": "any"},
                                    {"label": "Half or more", "value": "half"},
                                    {"label": "Meets requirements", "value": "meet"},
                                ],
                                value="any",
                                clearable=False,
                                searchable=False,
                            ),
                        ],
                        className="st-minutes-fields",
                    ),
                ],
                className="rs-filter-pos-match st-filter-minutes",
            ),
        ],
        id="pf-minutes-filters",
        className="rs-shortlist-filters mb-2",
        hidden=True,
    )


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


def _depth_undo_panel(items) -> html.Div:
    rows = []
    for item in list(items or [])[:DEPTH_UNDO_MAX]:
        if not isinstance(item, dict):
            continue
        undo_id = str(item.get("undo_id") or "").strip()
        if not undo_id:
            continue
        slot_label = str(item.get("slot_label") or item.get("role") or "").strip()
        meta = f"Slot {slot_label}" if slot_label else "Formation slot"
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
                        variant="light",
                        n_clicks=0,
                    ),
                ],
                className="pf-depth-undo-row",
            )
        )
    if not rows:
        return html.Div(
            "No recently removed players.",
            className="text-muted small",
        )
    return html.Div(rows, className="pf-depth-undo-list")


def _push_depth_undo(undo_items, payload: dict) -> list[dict]:
    if not isinstance(payload, dict) or not payload.get("entries"):
        return list(undo_items or [])
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
        if len(next_items) >= DEPTH_UNDO_MAX:
            break
    return next_items[:DEPTH_UNDO_MAX]


def layout(**_kwargs):
    profiles.ensure_dirs()
    settings = us.load()
    mins_req = us.default_minutes_required(settings)
    return dbc.Container(
        [
            dcc.Store(id="pf-rev", data=0),
            dcc.Store(id="pf-depth-order", data=None),
            dcc.Store(id="pf-depth-undo", storage_type="local", data=[]),
            dcc.Store(id="pf-view-mode", data="roles"),
            dcc.Store(id="pf-focus-role", data=[]),
            dcc.Store(id="pf-formation", storage_type="local", data=None),
            dcc.Store(id="pf-sort-memory", data=None),
            dcc.Store(id="pf-player-key", data=None),
            player_modal(prefix="pf"),
            html.H1("Profiles", className="mt-2 mb-3"),
            html.P(
                "Saved shortlist rows from Role scores (one row per evaluated role, "
                "with overall percentiles when the source file has stats) and from "
                "Player stats. Pick a formation for Squad depth, focus a role to rank "
                "players in the Depth chart, and click a name for the player modal.",
                className="text-muted mb-3",
            ),
            dbc.Card(
                [
                    dbc.CardHeader(
                        html.Div(
                            [
                                html.Span("Saved players", className="me-3"),
                                dmc.SegmentedControl(
                                    id="pf-view-toggle",
                                    value="roles",
                                    data=[
                                        {"label": label, "value": value}
                                        for value, label in VIEW_MODES
                                    ],
                                    size="sm",
                                ),
                            ],
                            className="pf-view-header",
                        )
                    ),
                    dbc.CardBody(
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
                                                    html.Span(
                                                        "One card per formation position (up to 11). "
                                                        "Slots that share a role start with the same "
                                                        "exported players. Click a card to edit that "
                                                        "role’s depth; click again to return to the XI. "
                                                        "Auto-rank uses Score, then Ovr on ties.",
                                                        className="rs-depth-heading-hint",
                                                    ),
                                                ],
                                                className="rs-depth-heading-copy",
                                            ),
                                            html.Div(
                                                [
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
                                                    html.Div(
                                                        _band_legend(settings),
                                                        id="pf-band-legend",
                                                    ),
                                                    dmc.Button(
                                                        "Auto-rank all roles",
                                                        id="pf-depth-auto-all",
                                                        size="sm",
                                                        variant="light",
                                                        n_clicks=0,
                                                    ),
                                                ],
                                                className="pf-squad-depth-actions",
                                            ),
                                        ],
                                        className="rs-depth-heading",
                                    ),
                                    html.Div(id="pf-summary", className="rs-depth-grid"),
                                ],
                                id="pf-depth-wrap",
                                className="rs-depth-panel mb-2",
                                hidden=True,
                            ),
                            html.Div(
                                [
                                    html.Div(
                                        [
                                            html.Span(
                                                "Depth chart",
                                                className="rs-depth-heading-label",
                                            ),
                                            html.Span(
                                                "Starting XI shows one player per formation slot "
                                                "(Slot column). Focus a Squad depth card to rank "
                                                "that slot; drag to reorder; × removes the player "
                                                "from that slot only. Restore puts them back at "
                                                "the bottom of that same slot.",
                                                className="rs-depth-heading-hint",
                                            ),
                                        ],
                                        className="rs-depth-heading-copy pf-depth-chart-toolbar",
                                    ),
                                    html.Div(id="pf-depth-chart-body"),
                                    html.Div(
                                        [
                                            html.Div(
                                                [
                                                    html.Span(
                                                        "Recently removed",
                                                        className="rs-depth-heading-label",
                                                    ),
                                                    html.Span(
                                                        "Last 5 players removed from a formation slot. "
                                                        "Restore adds them back to the bottom of that "
                                                        "same slot’s depth (and the table if needed).",
                                                        className="rs-depth-heading-hint",
                                                    ),
                                                ],
                                                className="rs-depth-heading-copy",
                                            ),
                                            html.Div(
                                                id="pf-depth-undo-body",
                                                children=_depth_undo_panel([]),
                                            ),
                                        ],
                                        id="pf-depth-undo-wrap",
                                        className="pf-depth-undo-wrap",
                                    ),
                                ],
                                id="pf-depth-chart-wrap",
                                className="pf-depth-chart-wrap mb-3",
                                hidden=True,
                            ),
                            html.Div(
                                [
                                    html.Div(
                                        [
                                            html.Div(
                                                [
                                                    html.Label(
                                                        "Search",
                                                        className="rs-field-label",
                                                    ),
                                                    dmc.TextInput(
                                                        id="pf-pct-search",
                                                        placeholder="Name, club, position",
                                                    ),
                                                ],
                                                className="rs-filter-search",
                                            ),
                                            html.Div(
                                                [
                                                    html.Label(
                                                        "Max age",
                                                        className="rs-field-label",
                                                    ),
                                                    dmc.Select(
                                                        id="pf-pct-age",
                                                        data=us.age_options(settings),
                                                        value="99",
                                                        clearable=False,
                                                        searchable=False,
                                                    ),
                                                ],
                                                className="rs-filter-age",
                                            ),
                                        ],
                                        className="rs-shortlist-filters-row",
                                    ),
                                ],
                                id="pf-pct-filters",
                                className="rs-shortlist-filters mb-2",
                                hidden=True,
                            ),
                            _minutes_filter_panel(mins_req),
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
                                ],
                                id="pf-table-host",
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
    Output("pf-minutes-required", "value"),
    Input("ui-settings", "data"),
    State("pf-minutes-required", "value"),
)
def sync_pf_minutes_from_settings(settings, minutes_required):
    settings = us.normalize(settings)
    default_mins = us.default_minutes_required(settings)
    return minutes_required if minutes_required is not None else default_mins


@callback(
    Output("pf-view-mode", "data"),
    Input("pf-view-toggle", "value"),
)
def set_view_mode(mode):
    # Legacy "depth" tab maps back onto Role scores (chart sits under Squad depth).
    if mode == "depth":
        return "roles"
    return mode or "roles"


@callback(
    Output("pf-pct-filters", "hidden"),
    Output("pf-minutes-filters", "hidden"),
    Input("pf-view-mode", "data"),
)
def toggle_filter_panels(view_mode):
    # Role scores: no extra filters (Squad depth focus only). Percentiles keeps search/age/mins.
    roles = (view_mode or "roles") == "roles"
    return roles, roles


@callback(
    Output("pf-pct-age", "data"),
    Output("pf-pct-age", "value", allow_duplicate=True),
    Output("pf-band-legend", "children"),
    Input("ui-settings", "data"),
    State("pf-pct-age", "value"),
    prevent_initial_call="initial_duplicate",
)
def sync_age_options(settings, pct_age):
    settings = us.normalize(settings)
    ages = us.age_options(settings)
    return (
        ages,
        us.clamp_choice(pct_age, ages, "99"),
        _band_legend(settings),
    )


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
    if stored in ids:
        return options, stored, no_update
    active = fm.active_id()
    value = active if active in ids else (options[0]["value"] if options else None)
    return options, value, value


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
    Output("pf-summary", "children"),
    Output("pf-depth-wrap", "hidden"),
    Output("pf-depth-chart-body", "children"),
    Output("pf-depth-chart-wrap", "hidden"),
    Input("pf-view-mode", "data"),
    Input("pf-rev", "data"),
    Input("pf-focus-role", "data"),
    Input("pf-formation-select", "value"),
    Input("pf-pct-search", "value"),
    Input("pf-pct-age", "value"),
    Input("pf-minutes-match", "value"),
    Input("pf-minutes-required", "value"),
    Input("pf-page-size", "value"),
    Input("pf-table", "sort_by"),
    Input("ui-settings", "data"),
    Input("theme", "data"),
    State("pf-sort-memory", "data"),
)
def refresh_profiles_table(
    view_mode,
    _rev,
    focus_role,
    formation_id,
    pct_search,
    pct_age,
    minutes_match,
    minutes_required,
    page_size,
    sort_by,
    settings,
    theme,
    sort_memory,
):
    settings = us.normalize(settings)
    mode = view_mode or "roles"
    try:
        page_size_i = int(page_size or default_page_size_value(settings))
    except (TypeError, ValueError):
        page_size_i = us.page_size(settings)
    minutes_required_f = float(
        minutes_required
        if minutes_required is not None
        else us.default_minutes_required(settings)
    )
    triggered = {
        (item.get("prop_id") or "").split(".")[0]
        for item in (ctx.triggered or [])
        if item.get("prop_id")
    }
    reset_sort = bool(triggered & FILTER_SORT_RESET_IDS)

    if mode == "depth":
        mode = "roles"

    if mode == "percentiles":
        columns = _percentile_table_columns(settings)
        all_rows, tips = _build_percentile_table_rows(settings)
        filtered = _filter_pct_rows(
            all_rows,
            query=pct_search,
            max_age=pct_age,
            minutes_match=minutes_match or "any",
            minutes_required=minutes_required_f,
        )
        style_data, style_header = _pct_table_styles(theme)
        empty_msg = "No percentile profiles yet. Mark players on Player stats and save."
        depth_cards = []
        depth_hidden = True
        chart = None
        chart_hidden = True
        sort_mode = "percentiles"
    else:
        formation_slots = _formation_slots(formation_id)
        focus = _focus_slot(focus_role)
        include_slot = bool(formation_slots)
        columns = _role_table_columns(settings, include_slot=include_slot)
        if formation_slots and not focus:
            all_rows, tips = _build_formation_xi_table_rows(
                formation_slots,
                formation_id=formation_id,
                settings=settings,
                theme=theme,
            )
            filtered = list(all_rows)
            sort_mode = "formation"
        elif formation_slots and focus:
            slot_ordered = profiles.ordered_profiles_for_slot(
                formation_id, focus.get("slot", -1), focus["role"]
            )
            slot_label = focus.get("label") or "—"
            _starters, multi_starters, conflicted_slots, unique_slots = (
                _formation_starter_slot_maps(formation_id, formation_slots)
            )
            try:
                focused_slot_index = int(focus.get("slot", -1))
            except (TypeError, ValueError):
                focused_slot_index = -1
            slot_is_conflicted = focused_slot_index in conflicted_slots
            slot_is_unique = focused_slot_index in unique_slots
            all_rows = []
            tips = []
            for index, entry in enumerate(slot_ordered):
                player_key = _entry_player_key(entry)
                item, tip = _entry_to_role_table_row(
                    entry,
                    settings=settings,
                    theme=theme,
                    slot_label=slot_label,
                    slot_conflicted=(
                        slot_is_conflicted or player_key in multi_starters
                    ),
                    slot_unique=(
                        slot_is_unique and player_key not in multi_starters
                    ),
                    depth_rank=index + 1,
                )
                all_rows.append(item)
                tips.append(tip)
            filtered = list(all_rows)
            sort_mode = "roles"
        else:
            all_rows, tips = _build_role_table_rows(settings, theme=theme)
            filtered = _filter_role_rows(all_rows, focus_roles=focus_role)
            sort_mode = "roles"
        style_data, style_header = _role_table_styles(theme)
        empty_msg = (
            "No role profiles yet. Mark players on Role scores and save — "
            "one row per evaluated role, including overall percentiles when available."
        )
        entries = profiles.list_role_profiles()
        if formation_id and fm.exists(formation_id):
            depth_cards = _profile_depth_panel(
                entries,
                focus_role,
                formation_id=formation_id,
                formation_slots=formation_slots,
                settings=settings,
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
        depth_hidden = False
        chart = _build_depth_chart(
            focus_roles=focus_role,
            formation_id=formation_id,
            formation_slots=formation_slots,
            settings=settings,
            theme=theme,
        )
        chart_hidden = not formation_slots and not focus

    col_ids = {col["id"] for col in columns}
    if reset_sort:
        sort_by = []
    sort_by = _coerce_sort_by(
        sort_by,
        sort_mode,
        col_ids,
        triggered_id=ctx.triggered_id,
        previous=sort_memory,
        reset_default=reset_sort,
    )
    filtered = _sort_profile_rows(filtered, sort_by, mode=sort_mode)

    display_rows = []
    for row in filtered:
        clean = _strip_internal(row)
        minutes_value = clean.get("Minutes")
        if not isinstance(minutes_value, str) or not minutes_value.strip():
            clean["Minutes"] = _minutes_cell(row.get("_minutes_raw"), settings)
        display_rows.append(clean)
    display_tips = [
        tips[all_rows.index(row)] for row in filtered if row in all_rows
    ]
    if len(display_tips) != len(display_rows):
        tip_by_id = {
            str(row.get("id") or ""): tips[idx]
            for idx, row in enumerate(all_rows)
        }
        display_tips = [tip_by_id.get(str(row.get("id") or ""), {}) for row in filtered]

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
            sort_by,
            sort_by,
            caption,
            html.Div(empty_msg, className="text-muted small"),
            False,
            True,
            True,
            True,
            depth_cards,
            depth_hidden,
            chart,
            chart_hidden,
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
            sort_by,
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
            depth_cards,
            depth_hidden,
            chart,
            chart_hidden,
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
        sort_by,
        sort_by,
        caption,
        None,
        True,
        False,
        False,
        True,
        depth_cards,
        depth_hidden,
        chart,
        chart_hidden,
    )


clientside_callback(
    """
    function(focusRoles) {
        const focused = new Set(
            (Array.isArray(focusRoles) ? focusRoles : [])
                .map(function(r) { return String(r || ""); })
                .filter(Boolean)
        );
        const cards = document.querySelectorAll("#pf-summary .rs-depth-card");
        cards.forEach(function(card) {
            const role = card.getAttribute("data-rs-role") || "";
            const on = role && focused.has(role);
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
    Input("pf-select-all", "n_clicks"),
    State("pf-table", "data"),
    State("pf-table", "selected_row_ids"),
    State("pf-table", "page_current"),
    State("pf-table", "page_size"),
    prevent_initial_call=True,
)
def select_all_profiles(n_clicks, rows, selected_ids, page_current, page_size):
    if not n_clicks or not rows:
        return no_update, no_update
    all_ids = [
        row_id
        for row in rows
        if (row_id := str(row.get("id") or row.get("_key") or "").strip())
    ]
    if not all_ids:
        return [], []
    current = {str(item) for item in (selected_ids or []) if item}
    # Toggle: clear if every visible row is already selected.
    if current and current.issuperset(all_ids):
        return [], []
    try:
        page = int(page_current or 0)
        size = int(page_size or len(rows) or 50)
    except (TypeError, ValueError):
        page, size = 0, len(rows) or 50
    start = max(0, page * size)
    end = start + size
    page_indices = list(range(min(size, max(0, len(rows) - start))))
    return all_ids, page_indices


@callback(
    Output("pf-delete-selected", "disabled", allow_duplicate=True),
    Input("pf-table", "selected_row_ids"),
    prevent_initial_call=True,
)
def toggle_delete_btn(selected_ids):
    return not bool(selected_ids)


@callback(
    Output("pf-rev", "data", allow_duplicate=True),
    Input("pf-delete-selected", "n_clicks"),
    State("pf-table", "selected_row_ids"),
    State("pf-rev", "data"),
    prevent_initial_call=True,
)
def delete_selected(n_clicks, selected_ids, rev):
    if not n_clicks or not selected_ids:
        return no_update
    seen: set[str] = set()
    for row_id in selected_ids:
        profile_id = _resolve_profile_id(row_id)
        if profile_id and profile_id not in seen:
            seen.add(profile_id)
            profiles.delete_profile(profile_id)
    return int(rev or 0) + 1


@callback(
    Output("pf-rev", "data", allow_duplicate=True),
    Output("pf-depth-order", "data"),
    Input("pf-depth-order", "data"),
    State("pf-rev", "data"),
    prevent_initial_call=True,
)
def apply_depth_chart_drag(order, rev):
    if not isinstance(order, dict):
        return no_update, no_update
    role = str(order.get("role") or "").strip()
    formation_id = str(order.get("formation") or "").strip()
    ids = [
        str(pid).strip()
        for pid in (order.get("ids") or [])
        if str(pid or "").strip()
    ]
    if not role or not ids:
        return no_update, None
    slot_raw = order.get("slot")
    if formation_id and slot_raw is not None and str(slot_raw).strip() != "":
        try:
            slot_index = int(slot_raw)
        except (TypeError, ValueError):
            slot_index = slot_raw
        profiles.set_slot_order_ids(formation_id, slot_index, ids)
    else:
        profiles.set_depth_ranks(role, ids)
    return int(rev or 0) + 1, None


@callback(
    Output("pf-rev", "data", allow_duplicate=True),
    Input({"type": "pf-depth-auto-role", "role": ALL, "slot": ALL}, "n_clicks"),
    State("pf-rev", "data"),
    State("pf-formation-select", "value"),
    prevent_initial_call=True,
)
def auto_rank_depth_role(n_clicks, rev, formation_id):
    if not ctx.triggered_id or not clicked(n_clicks):
        return no_update
    role = str(ctx.triggered_id.get("role") or "").strip()
    slot_raw = ctx.triggered_id.get("slot")
    if not role:
        return no_update
    try:
        slot_index = int(slot_raw)
    except (TypeError, ValueError):
        slot_index = slot_raw
    if formation_id:
        profiles.auto_rank_slot_by_score(formation_id, slot_index, role)
    else:
        profiles.auto_rank_role_by_score(role)
    return int(rev or 0) + 1


@callback(
    Output("pf-rev", "data", allow_duplicate=True),
    Input("pf-depth-auto-all", "n_clicks"),
    State("pf-rev", "data"),
    State("pf-formation-select", "value"),
    prevent_initial_call=True,
)
def auto_rank_depth_all(n_clicks, rev, formation_id):
    if not n_clicks:
        return no_update
    slots = _formation_slots(formation_id)
    if slots:
        for slot in slots:
            profiles.auto_rank_slot_by_score(
                formation_id, slot["index"], slot["column"]
            )
    else:
        profiles.auto_rank_all_roles_by_score()
    return int(rev or 0) + 1


@callback(
    Output("pf-depth-undo", "data"),
    Output("pf-rev", "data", allow_duplicate=True),
    Input({"type": "pf-depth-remove", "id": ALL, "slot": ALL}, "n_clicks"),
    State("pf-depth-undo", "data"),
    State("pf-rev", "data"),
    State("pf-formation-select", "value"),
    State("pf-focus-role", "data"),
    prevent_initial_call=True,
)
def remove_from_depth_chart(n_clicks, undo_items, rev, formation_id, focus_role):
    if not ctx.triggered_id or not clicked(n_clicks):
        return no_update, no_update
    profile_id = str(ctx.triggered_id.get("id") or "").strip()
    slot_raw = ctx.triggered_id.get("slot")
    if not profile_id or slot_raw is None:
        return no_update, no_update
    try:
        slot_index = int(slot_raw)
    except (TypeError, ValueError):
        return no_update, no_update
    role = ""
    slot_label = ""
    for slot in _formation_slots(formation_id):
        if int(slot["index"]) == slot_index:
            role = slot["column"]
            slot_label = slot.get("display_label") or slot.get("label") or ""
            break
    if not role:
        focus = _focus_slot(focus_role)
        if focus and int(focus.get("slot", -1)) == slot_index:
            role = focus["role"]
            slot_label = focus.get("label") or ""
    if not role or not formation_id:
        return no_update, no_update
    # Seed sibling slots that share this role first so they keep their own copy.
    for slot in _formation_slots(formation_id):
        if slot["column"] == role and int(slot["index"]) != slot_index:
            profiles.get_slot_order_ids(
                formation_id, slot["index"], role, seed=True
            )
    removed = profiles.remove_from_slot_depth(
        formation_id, slot_index, profile_id, role
    )
    if not removed:
        return no_update, no_update
    removed["slot_label"] = slot_label
    return _push_depth_undo(undo_items, removed), int(rev or 0) + 1


@callback(
    Output("pf-depth-undo-body", "children"),
    Input("pf-depth-undo", "data"),
)
def render_depth_undo(undo_items):
    return _depth_undo_panel(undo_items)


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
    Input({"type": "pf-depth-name", "id": ALL}, "n_clicks"),
    State("ui-settings", "data"),
    State("theme", "data"),
    prevent_initial_call=True,
)
def open_profile_modal_from_depth(n_clicks, settings, theme):
    if not ctx.triggered_id or not clicked(n_clicks):
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


def _resolve_stats_player_for_profile(profile: dict, player: dict) -> dict | None:
    """Return a full stats player (minutes + stats) for the Profiles modal if available."""
    from scoring.stats_scorer import player_key as stats_player_key

    embedded = profile.get("stats_player")
    if isinstance(embedded, dict) and embedded.get("stats"):
        return embedded

    file_id = str(profile.get("file_id") or "").strip()
    if not file_id:
        return None
    stat_players = profiles.load_stats_players_for_file(file_id)
    if not stat_players:
        return None
    name = (player.get("name") or "").strip()
    club = (player.get("club") or "").strip()
    target_key = stats_player_key({"name": name, "club": club})
    if not target_key:
        return None
    for sp in stat_players:
        if stats_player_key(sp) == target_key:
            return sp
    return None


def _build_profile_modal_body(
    profile: dict,
    player: dict,
    *,
    settings: dict,
    theme: str | None,
    mode: str = "roles",
) -> html.Div:
    """Shared body builder for open and switch callbacks."""
    stats_player = _resolve_stats_player_for_profile(profile, player)
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
