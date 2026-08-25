"""Saved player profiles from Role scores and Player stats."""
from __future__ import annotations

import re

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
import services.player_profiles as profiles
import services.ui_settings as us
from components.stats_player_pane import stats_charts_bottom_pane

register_page(__name__, path="/profiles", name="Profiles")

VIEW_MODES = (
    ("roles", "Role scores"),
    ("percentiles", "Overall percentiles"),
)

FILTER_SORT_RESET_IDS = frozenset(
    {
        "pf-view-mode",
        "pf-focus-role",
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


def _focus_roles(value) -> list[str]:
    """Focused Squad depth role columns (at most one)."""
    if value is None or value == "":
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    out: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text and text not in out:
            out.append(text)
        if out:
            break
    return out


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


def _profile_depth_card(stats: dict, focus_roles, bands: dict) -> html.Button:
    meta = stats["meta"]
    column = meta["column"]
    avg = stats["avg"]
    counts = stats["counts"]
    total = stats["total"]
    active = " active" if column in _focus_roles(focus_roles) else ""
    label = meta.get("short_label") or meta["name"]
    children = [
        html.Div(
            [
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
                html.Span(label, className="rs-depth-name"),
            ],
            className="rs-depth-title",
        ),
        html.Div(
            [
                html.Span("Avg", className="rs-depth-avg-label"),
                html.Span(
                    f"{avg:.1f}",
                    className=f"rs-depth-avg rs-band-{score_band(avg, **bands)}",
                ),
            ],
            className="rs-depth-avg-row",
        ),
        html.Div(
            [
                html.Div(
                    className=f"rs-depth-seg {band}",
                    style={"width": f"{counts[band] / total * 100:.1f}%"},
                )
                for band in ("elite", "good", "ok", "poor")
                if counts[band]
            ],
            className="rs-depth-bar",
        ),
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
    return html.Button(
        children,
        id={"type": "pf-depth", "role": _depth_role_key(meta)},
        n_clicks=0,
        className="rs-depth-card" + active,
        title=meta.get("compact") or meta["name"],
        **{"data-rs-role": column},
    )


def _profile_depth_panel(
    entries: list[dict],
    focus_roles,
    *,
    hybrids_only: bool = False,
    settings=None,
) -> list:
    if not entries:
        return []
    settings = us.normalize(settings)
    bands = settings["bands"]
    roles_seen: dict[str, dict] = {}
    for entry in entries:
        role = str(entry.get("role_column") or (entry.get("row") or {}).get("Role") or "").strip()
        if not role:
            continue
        if hybrids_only and "+" not in role:
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
    entry: dict,
    *,
    index: int,
    total: int,
    settings,
    theme=None,
) -> html.Div:
    del total  # kept for call-site compatibility
    settings = us.normalize(settings)
    row = entry.get("row") or {}
    profile_id = str(entry.get("id") or "").strip()
    name, club = profiles.profile_identity(entry)
    rank = _depth_rank_value(entry)
    display_rank = rank if rank is not None else index + 1
    position = _blank(row.get("Position"))
    if position == "—":
        position = _blank(row.get("Best Pos"))
    division = _blank(row.get("Division"))
    tier = classify_division(row.get("Division"), row.get("Nation"))
    div_class = "pf-depth-chart-div"
    if tier:
        div_class = f"{div_class} pf-div-{tier}"
    return html.Div(
        [
            html.Div(
                [
                    html.Span("⋮⋮", className="pf-depth-chart-grip", **{"aria-hidden": "true"}),
                    html.Span(str(display_rank), className="pf-depth-chart-rank"),
                ],
                className="pf-depth-chart-rank-cell",
            ),
            html.Button(
                name or "Player",
                id={"type": "pf-depth-name", "id": profile_id},
                n_clicks=0,
                className="pf-depth-chart-name",
                title="Open player details",
            ),
            html.Span(position, className="pf-depth-chart-pos", title=position),
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
        ],
        className="pf-depth-chart-row" + (" is-odd" if index % 2 else ""),
        draggable="true",
        **{"data-profile-id": profile_id},
    )


def _depth_chart_col_headers() -> html.Div:
    return html.Div(
        [
            html.Span("#", className="pf-depth-chart-rank"),
            html.Span("Name", className="pf-depth-chart-name-label"),
            html.Span("Pos", className="pf-depth-chart-pos"),
            html.Span("Club", className="pf-depth-chart-club"),
            html.Span("Division", className="pf-depth-chart-div"),
            html.Span("Ovr", className="pf-depth-chart-ovr"),
            html.Span("Score", className="pf-depth-chart-score"),
        ],
        className="pf-depth-chart-cols",
    )


def _build_depth_chart(
    *,
    focus_roles=None,
    hybrids_only: bool = False,
    settings=None,
    theme=None,
) -> html.Div:
    settings = us.normalize(settings)
    focused = _focus_roles(focus_roles)
    if not focused:
        return html.Div(
            "Select a role in Squad depth to edit its ranking.",
            className="text-muted small",
        )

    entries = profiles.list_role_profiles()
    roles_seen: dict[str, dict] = {}
    for entry in entries:
        role = str(
            entry.get("role_column") or (entry.get("row") or {}).get("Role") or ""
        ).strip()
        if not role:
            continue
        if role not in focused:
            continue
        if hybrids_only and "+" not in role:
            continue
        if role not in roles_seen:
            roles_seen[role] = _role_column_meta(role)
    if not roles_seen:
        return html.Div(
            "No saved profiles for the focused role.",
            className="text-muted small",
        )

    sections = []
    for column in focused:
        meta = roles_seen.get(column)
        if not meta:
            continue
        ordered = profiles.ordered_profiles_for_role(column)
        if hybrids_only and "+" not in column:
            continue
        if not ordered:
            continue
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
            )
            for idx, entry in enumerate(ordered)
        ]
        sections.append(
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
                                        label,
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
                                id={"type": "pf-depth-auto-role", "role": column},
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
                        **{"data-role": column},
                    ),
                ],
                className="pf-depth-chart-section",
            )
        )

    if not sections:
        return html.Div(
            "No saved profiles for the focused role.",
            className="text-muted small",
        )
    return html.Div(sections, className="pf-depth-chart-sections")


def _role_table_columns(settings) -> list[dict]:
    settings = us.normalize(settings)
    cols = []
    for col in _profile_identity_columns("role_scores", settings):
        spec = {"name": identity_header_name(col), "id": col}
        if col in ("Feet", "Injury"):
            spec["presentation"] = "markdown"
        cols.append(spec)
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

# Minimum widths sized so uppercase headers + sort padding and cell content fit.
# No maxWidth — fill_width lets columns grow with the table.
_PF_COL_MIN_WIDTHS: dict[str, str] = {
    "Name": "160px",
    "Position": "92px",
    "Club": "120px",
    "Division": "108px",
    "Age": "56px",
    "Height": "52px",
    "Feet": "84px",
    "Rec": "56px",
    "Injury": "52px",
    "Nation": "80px",
    "Inf": "52px",
    "Best Pos": "56px",
    "Role": "88px",
    "Rank": "64px",
    "Score": "72px",
    "Minutes": "64px",
    "overall": "56px",
    "defending": "56px",
    "final_third": "64px",
    "possession": "64px",
}


def _pf_col_box(column_id: str, *, header: bool = False) -> dict:
    """Shared min-width / wrap / align box for Profiles headers and cells."""
    align = "left" if column_id in _PF_LEFT_COLS else "center"
    box: dict = {
        "textAlign": align,
        "minWidth": _PF_COL_MIN_WIDTHS.get(column_id, "64px"),
        "whiteSpace": "pre-line" if header else "normal",
        "overflow": "visible",
        "lineHeight": "1.2",
    }
    # Clear shared identity maxWidth caps so columns can grow with the table.
    if column_id == "Name":
        box["maxWidth"] = "280px"
    elif column_id == "Club":
        box["maxWidth"] = "220px"
    elif column_id == "Position":
        box["maxWidth"] = "180px"
    else:
        box["maxWidth"] = "none"
    if header:
        # Symmetric padding on centered headers so titles line up with cell values
        # (sort chevron is absolutely positioned and must not shift the label).
        if column_id in _PF_LEFT_COLS:
            box["padding"] = "10px 22px 10px 10px"
        else:
            box["padding"] = "10px 10px"
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
            box["padding"] = "8px 10px"
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
        col_ids.extend(["Role", "Rank"])
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


def _build_role_table_rows(settings=None, theme=None) -> tuple[list[dict], list[dict]]:
    settings = us.normalize(settings)
    identity = _profile_identity_columns("role_scores", settings)
    rows = []
    tips = []
    for entry in profiles.list_role_profiles():
        raw = dict(entry.get("row") or {})
        if not raw.get("Role"):
            raw["Role"] = entry.get("role_column") or ""
        role_column = str(raw.get("Role") or entry.get("role_column") or "").strip()
        score_raw = raw.get("Score")
        try:
            score_f = (
                float(score_raw)
                if score_raw not in (None, "", "-", "—")
                else None
            )
        except (TypeError, ValueError):
            score_f = None
        overall_raw = _raw_float(raw.get("overall"))
        pct_raw = {pct: _raw_float(raw.get(pct)) for pct in PCT_COLS}
        rank_raw = _depth_rank_value(entry)
        item: dict = {
            "id": entry.get("id") or "",
            "_key": entry.get("id") or "",
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
        item["Role"] = _role_cell_markdown(role_column, theme=theme)
        item["Rank"] = str(rank_raw) if rank_raw is not None else "—"
        item["Score"] = _score_markdown(score_raw, settings, theme=theme)
        mins_raw = _profile_minutes_raw(entry, raw)
        item["_minutes_raw"] = mins_raw
        item["Minutes"] = _minutes_cell(mins_raw, settings)
        for pct in PCT_COLS:
            item[pct] = _pct_markdown(raw.get(pct), raw.get(f"{pct}_color"))
        rows.append(item)
        tips.append(injury_tooltip_entry(raw.get("Injury")))
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


def layout(**_kwargs):
    profiles.ensure_dirs()
    settings = us.load()
    mins_req = us.default_minutes_required(settings)
    return dbc.Container(
        [
            dcc.Store(id="pf-rev", data=0),
            dcc.Store(id="pf-depth-order", data=None),
            dcc.Store(id="pf-view-mode", data="roles"),
            dcc.Store(id="pf-focus-role", data=[]),
            dcc.Store(id="pf-sort-memory", data=None),
            dcc.Store(id="pf-player-key", data=None),
            player_modal(prefix="pf"),
            html.H1("Profiles", className="mt-2 mb-3"),
            html.P(
                "Saved shortlist rows from Role scores (one row per evaluated role, "
                "with overall percentiles when the source file has stats) and from "
                "Player stats. Select a role in Squad depth to rank players in the "
                "Depth chart; click a name for the player modal.",
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
                                                        "Click a card to focus one role "
                                                        "(table and depth chart). Click again to clear.",
                                                        className="rs-depth-heading-hint",
                                                    ),
                                                ],
                                                className="rs-depth-heading-copy",
                                            ),
                                            html.Div(
                                                _band_legend(settings),
                                                id="pf-band-legend",
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
                                            html.Div(
                                                [
                                                    html.Span(
                                                        "Depth chart",
                                                        className="rs-depth-heading-label",
                                                    ),
                                                    html.Span(
                                                        "Shows the role focused in Squad depth. "
                                                        "Drag rows to reorder. Auto-rank sets "
                                                        "order from saved Score (highest first).",
                                                        className="rs-depth-heading-hint",
                                                    ),
                                                ],
                                                className="rs-depth-heading-copy",
                                            ),
                                            dmc.Button(
                                                "Auto-rank all roles",
                                                id="pf-depth-auto-all",
                                                size="sm",
                                                variant="light",
                                                n_clicks=0,
                                            ),
                                        ],
                                        className="pf-depth-chart-toolbar",
                                    ),
                                    html.Div(id="pf-depth-chart-body"),
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
    Output("pf-focus-role", "data", allow_duplicate=True),
    Input({"type": "pf-depth", "role": ALL}, "n_clicks"),
    State("pf-focus-role", "data"),
    prevent_initial_call=True,
)
def focus_profile_role(n_clicks, current_focus):
    if not ctx.triggered_id or not clicked(n_clicks):
        return no_update
    role = ctx.triggered_id["role"]
    if role == "_":
        return no_update
    column = _depth_id_column(role)
    if not column:
        return no_update
    selected = _focus_roles(current_focus)
    # Single-select: click again to clear, otherwise replace.
    if column in selected:
        return []
    return [column]


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
        columns = _role_table_columns(settings)
        all_rows, tips = _build_role_table_rows(settings, theme=theme)
        filtered = _filter_role_rows(all_rows, focus_roles=focus_role)
        style_data, style_header = _role_table_styles(theme)
        empty_msg = (
            "No role profiles yet. Mark players on Role scores and save — "
            "one row per evaluated role, including overall percentiles when available."
        )
        entries = profiles.list_role_profiles()
        depth_cards = _profile_depth_panel(
            entries,
            focus_role,
            settings=settings,
        )
        depth_hidden = not depth_cards
        focused = _focus_roles(focus_role)[:1]
        chart = _build_depth_chart(
            focus_roles=focused,
            settings=settings,
            theme=theme,
        )
        chart_hidden = not focused
        sort_mode = "roles"

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
    for profile_id in selected_ids:
        if profile_id:
            profiles.delete_profile(str(profile_id))
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
    ids = [
        str(pid).strip()
        for pid in (order.get("ids") or [])
        if str(pid or "").strip()
    ]
    if not role or not ids:
        return no_update, None
    profiles.set_depth_ranks(role, ids)
    return int(rev or 0) + 1, None


@callback(
    Output("pf-rev", "data", allow_duplicate=True),
    Input({"type": "pf-depth-auto-role", "role": ALL}, "n_clicks"),
    State("pf-rev", "data"),
    prevent_initial_call=True,
)
def auto_rank_depth_role(n_clicks, rev):
    if not ctx.triggered_id or not clicked(n_clicks):
        return no_update
    role = str(ctx.triggered_id.get("role") or "").strip()
    if not role:
        return no_update
    profiles.auto_rank_role_by_score(role)
    return int(rev or 0) + 1


@callback(
    Output("pf-rev", "data", allow_duplicate=True),
    Input("pf-depth-auto-all", "n_clicks"),
    State("pf-rev", "data"),
    prevent_initial_call=True,
)
def auto_rank_depth_all(n_clicks, rev):
    if not n_clicks:
        return no_update
    profiles.auto_rank_all_roles_by_score()
    return int(rev or 0) + 1


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
    profile_id = str(row.get("id") or row.get("_key") or "").strip()
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
