"""Player statistics page: Moneyball stats CSV vs MustermannFM benchmarks."""
from __future__ import annotations

import base64
import csv
import io
import json
import re
import zlib

from dash import (
    ALL,
    Input,
    Output,
    State,
    callback,
    ctx,
    dcc,
    html,
    no_update,
    register_page,
)
import dash_bootstrap_components as dbc
import dash_mantine_components as dmc
import plotly.graph_objects as go

from pack_picker import pack_picker_bar, section_card_header
from player_filters import player_filters, player_filters_host
from player_modal import player_detail_body, player_modal
from player_table import (
    IDENTITY_TEXT_COLS,
    feet_cell,
    feet_sort_key,
    identity_data_styles,
    identity_header_name,
    identity_header_tooltips,
    player_data_table,
    rec_sort_key,
    style_cell,
    style_cell_conditional,
    style_header,
    style_header_conditional,
    table_caption_row,
    table_css,
)
from role_scorer import (
    foot_match,
    player_row_key,
    to_int,
)
from stats_scorer import (
    POS_GROUPS,
    band_metric,
    benchmarks,
    canonical_category,
    categories_for_group,
    category_average_band,
    category_label,
    default_category_for_group,
    is_gk_group,
    labeled_view_categories,
    metric_defs,
    metrics_for,
    minutes_color,
    minutes_status,
    overall_average_band,
    parse_stats_export,
    passes_minutes_filter,
    percentile_color,
    player_key,
    scoring_stats,
    view_categories,
)
import ui_settings as us
import stats_threshold_packs as stp

register_page(__name__, path="/stats", name="Player stats")

AVG_PERCENTILE_COLS = (
    "overall",
    "category_avg",
    "defending",
    "final_third",
    "possession",
)
OVERALL_COL = {
    "id": "overall",
    "label": "Overall average",
    "abbr": "Ovr",
}
CATEGORY_AVG_COL = {
    "id": "category_avg",
    "abbr": "% AVG",
}

BLANK_FIG = go.Figure()
BLANK_FIG.update_layout(
    template="plotly_dark",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    margin=dict(l=40, r=20, t=20, b=40),
    height=240,
)


def _help_icon(tip: str, help_id: str) -> list:
    return [
        html.Span("ⓘ", id=help_id, className="rs-help", role="img", **{"aria-label": "Help"}),
        dbc.Tooltip(tip, target=help_id, placement="top", class_name="rs-help-tooltip"),
    ]


def _upload_status(count: int, filename: str) -> list:
    return [
        html.Span("✓", className="rs-upload-ok"),
        html.Span(f"{count:,} players loaded", className="rs-upload-count"),
        html.Span("·", className="rs-upload-sep"),
        html.Span(filename, className="rs-upload-name", title=filename),
        html.Span("·", className="rs-upload-sep"),
    ]


def _upload_error(message: str) -> html.Div:
    return html.Div(message, className="rs-upload-error")


def _decode_upload(contents: str) -> str:
    _ctype, _, payload = contents.partition(",")
    return base64.b64decode(payload).decode("utf-8-sig", errors="replace")


def _pack_parsed(players: list, filename: str) -> dict:
    """Compress parsed players for sessionStorage (large combined exports)."""
    raw = json.dumps(
        {"players": players, "filename": filename},
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    blob = base64.b64encode(zlib.compress(raw, 6)).decode("ascii")
    return {
        "v": 1,
        "encoding": "zlib+b64",
        "filename": filename,
        "n": len(players),
        "payload": blob,
    }


def _unpack_parsed(data) -> dict | None:
    """Return ``{players, filename}`` from a packed or legacy session store."""
    if not data:
        return None
    if isinstance(data.get("players"), list):
        return data
    blob = data.get("payload")
    if not blob:
        return None
    try:
        raw = zlib.decompress(base64.b64decode(blob))
        packed = json.loads(raw.decode("utf-8"))
    except (OSError, ValueError, json.JSONDecodeError, TypeError):
        return None
    if not isinstance(packed, dict) or not isinstance(packed.get("players"), list):
        return None
    packed.setdefault("filename", data.get("filename") or "export.csv")
    return packed


def _parsed_players(data) -> list:
    unpacked = _unpack_parsed(data)
    return list((unpacked or {}).get("players") or [])


def _colored_cell(text: str, color: str | None) -> str:
    if not color:
        return text
    return (
        f'<span style="color:{color};font-weight:650;font-variant-numeric:tabular-nums">'
        f"{text}</span>"
    )


def _percentile_cell(band: dict) -> str:
    """Table cell for an average-percentile column (All category view)."""
    pct = band.get("percentile")
    if pct is None:
        return '<span class="st-pct-cell is-missing">—</span>'
    text = f"{float(pct):.0f}%"
    color = band.get("color")
    style = "font-weight:750;font-variant-numeric:tabular-nums;font-size:1.08em"
    if color:
        style = f"color:{color};{style}"
    return f'<span class="st-pct-cell" style="{style}">{text}</span>'


def _strip_cell(value) -> str:
    text = "" if value is None else str(value)
    if "<" in text:
        text = re.sub(r"<[^>]+>", "", text)
    return text


TABLE_TEXT_COLS = IDENTITY_TEXT_COLS


def _cell_number(value) -> float:
    """Parse a display cell (plain or colored markdown) as a float."""
    text = _strip_cell(value).strip().replace("%", "").replace(",", "").replace(" ", "")
    if not text or text in ("-", "—"):
        return float("nan")
    try:
        return float(text)
    except ValueError:
        return float("nan")


def _column_sort_key(column_id: str, value, row: dict | None = None) -> tuple:
    if column_id == "Feet" and row is not None:
        return feet_sort_key(row)
    if column_id == "Rec":
        return rec_sort_key(value)
    if column_id in TABLE_TEXT_COLS:
        text = _strip_cell(value).strip()
        if not text or text in ("-", "—"):
            return (1, "\uffff")
        return (0, text.casefold())
    number = _cell_number(value)
    if number != number:  # NaN
        return (1, float("inf"))
    return (0, number)


def _is_percentile_sort_column(column_id: str) -> bool:
    """Avg percentile cols + metric cells (colored rates / %)."""
    if not column_id or column_id in TABLE_TEXT_COLS:
        return False
    if column_id in ("Feet", "Rec", "Minutes", "Age", "Height"):
        return False
    return True


def _sort_table_rows(rows: list[dict], sort_by) -> None:
    if not sort_by:
        return
    item = sort_by[0]
    column = item.get("column_id")
    reverse = item.get("direction") == "desc"
    if _is_percentile_sort_column(column):
        # Encode direction in the key so missing (—) values always sort last.
        def pct_key(row, *, _col=column, _desc=reverse):
            number = _cell_number(row.get(_col))
            if number != number:  # NaN / blank
                return (1, 0.0)
            return (0, -number if _desc else number)

        rows.sort(key=pct_key)
        return
    rows.sort(
        key=lambda row: _column_sort_key(column, row.get(column), row),
        reverse=reverse,
    )


def _default_sort_by(category: str) -> list[dict]:
    """All → overall desc; single category → that category's avg desc."""
    column = OVERALL_COL["id"] if category == "all" else CATEGORY_AVG_COL["id"]
    return [{"column_id": column, "direction": "desc"}]


def _effective_sort_by(sort_by, category: str, column_ids: set[str]) -> list[dict]:
    if sort_by:
        column = (sort_by[0] or {}).get("column_id")
        if column in column_ids:
            return list(sort_by)
    return _default_sort_by(category)


def _coerce_sort_by(
    sort_by,
    category: str,
    column_ids: set[str],
    *,
    triggered_id,
    previous,
) -> list[dict]:
    """Keep a sensible sort; map DataTable's desc→clear click to asc on that column."""
    default = _default_sort_by(category)
    if triggered_id == "st-category":
        return default
    if not sort_by:
        if triggered_id == "st-table":
            prev = (previous or [None])[0] or {}
            col = prev.get("column_id")
            if col in column_ids:
                return [{"column_id": col, "direction": "asc"}]
        return default
    return _effective_sort_by(sort_by, category, column_ids)


def _resolve_category(group: str, category: str) -> tuple[str, str]:
    """Pick a valid shared category for the active position filter.

    Categories are always Defending / Final third / Possession (plus All).
    Goalkeepers use the mapped GK benchmark blocks under those same ids.
    """
    g = "gk" if is_gk_group(group) else (group if group in ("def", "mid", "fwd") else "def")
    cat = canonical_category(category)
    if cat == "all":
        return g, "all"
    if any(c["id"] == cat for c in view_categories()):
        return g, cat
    return g, default_category_for_group(g)


def _band_group_cat(player: dict, view_group: str, view_cat: str) -> tuple[str | None, str | None]:
    """Benchmark group + shared category for one player under the current view."""
    pg = player.get("pos_group") or "mid"
    cat = canonical_category(view_cat)
    if view_group not in ("", "all") and pg != view_group:
        return None, None
    use_g = "gk" if is_gk_group(pg) else pg
    return use_g, cat


def _pos_groups_for_bar(players: list[dict], active: str) -> list[dict]:
    counts = {"all": len(players)}
    for key, _label, _css in POS_GROUPS[1:]:
        counts[key] = sum(1 for p in players if p.get("pos_group") == key)
    return [
        {
            "key": key,
            "label": label,
            "css": css,
            "count": counts.get(key, 0),
        }
        for key, label, css in POS_GROUPS
    ]


def _category_items(group: str, active: str) -> tuple[list[dict[str, str]], str]:
    _g, active = _resolve_category(group, active)
    cats = [
        {"id": "all", "label": "All"},
        *labeled_view_categories(group=group),
    ]
    return cats, active


def _filters_bar(
    players: list[dict],
    *,
    pos: str,
    category: str,
    foot: str,
    foot_thresholds,
):
    cats, category = _category_items(pos, category)
    return player_filters(
        prefix="st",
        pos_groups=_pos_groups_for_bar(players, pos),
        active_pos=pos or "all",
        active_foot=foot or "",
        foot_thresholds=foot_thresholds,
        categories=cats,
        active_category=category,
        pos_id_attr="key",
        foot_inline=False,
    )


def _clicked(n_clicks) -> bool:
    return bool(n_clicks) and any(n_clicks)


def _stats_metric_styles() -> list[dict]:
    """Minutes + All-category average column sizing (stats-only)."""
    return [
        {
            "if": {"column_id": "Minutes"},
            "textAlign": "center",
            "minWidth": "64px",
            "width": "68px",
            "maxWidth": "76px",
            "fontWeight": "650",
            "fontVariantNumeric": "tabular-nums",
        },
        *[
            {
                "if": {"column_id": col_id},
                "textAlign": "center",
                "minWidth": "72px" if col_id == "category_avg" else "64px",
                "width": "80px" if col_id == "category_avg" else "72px",
                "maxWidth": "88px" if col_id == "category_avg" else "80px",
                "fontVariantNumeric": "tabular-nums",
            }
            for col_id in AVG_PERCENTILE_COLS
        ],
    ]


def _table_css() -> list[dict]:
    return table_css(center_non_identity=True)


def _table_base_styles(theme: str | None = None) -> list[dict]:
    return identity_data_styles(
        theme, extra=_stats_metric_styles() + _KEY_COLUMN_HIDE
    )


def _avg_header_styles() -> list[dict]:
    return [
        {
            "if": {"column_id": col_id},
            "textAlign": "center",
            "minWidth": "72px" if col_id == "category_avg" else "64px",
            "width": "80px" if col_id == "category_avg" else "72px",
            "maxWidth": "88px" if col_id == "category_avg" else "80px",
            "whiteSpace": "pre-line",
            "overflow": "visible",
            "lineHeight": "1.2",
            "padding": "10px 8px",
        }
        for col_id in AVG_PERCENTILE_COLS
    ]


def _avg_category_columns(group: str) -> list[dict[str, str]]:
    """All-category average columns; Final third shows both outfield + GK names."""
    return labeled_view_categories(group=group, dual_final_third=True)


def _single_category_avg_section(group: str, category: str) -> dict[str, str] | None:
    """Labeled section for the selected category's average column (non-All)."""
    _g, cat = _resolve_category(group, category)
    if cat == "all":
        return None
    for section in labeled_view_categories(group=group, dual_final_third=True):
        if section["id"] == cat:
            return section
    return {
        "id": cat,
        "label": category_label(cat, group=group),
        "abbr": CATEGORY_AVG_COL["abbr"],
    }


def _avg_header_name(section: dict[str, str]) -> str:
    """Compact All-category headers; allow dual labels to wrap on a clean break."""
    text = section.get("abbr") or section.get("label") or section.get("id") or ""
    return text.replace(" / ", " /\n")


def _display_blank(value) -> str:
    text = str(value or "").strip()
    return text if text and text not in ("-", "—") else "-"


def _row_mark_key(row: dict) -> str:
    """Stable player id for row selection (matches stats ``player_key``)."""
    key = str(row.get("_key") or "").strip()
    if key:
        return key
    club = str(row.get("Club") or "").strip()
    if club in ("—", "-"):
        club = ""
    return player_row_key({"Name": row.get("Name"), "Club": club})


def _hidden_key_column() -> dict:
    return {"name": "", "id": "_key"}


_KEY_COLUMN_HIDE = [
    {
        "if": {"column_id": "_key"},
        "display": "none",
        "width": "0px",
        "minWidth": "0px",
        "maxWidth": "0px",
        "padding": "0",
        "border": "none",
    },
]


def _table_columns(
    group: str, category: str, threshold_overrides=None, settings=None
) -> list[dict]:
    g, cat = _resolve_category(group, category)
    settings = us.normalize(settings)
    cols = []
    for col in us.shortlist_columns_for("player_stats", settings):
        spec = {"name": identity_header_name(col), "id": col}
        if col == "Feet":
            spec["presentation"] = "markdown"
        cols.append(spec)
    cols.append({"name": "Mins", "id": "Minutes", "presentation": "markdown"})
    if cat == "all":
        cols.append(
            {
                "name": OVERALL_COL["abbr"],
                "id": OVERALL_COL["id"],
                "presentation": "markdown",
            }
        )
        for section in _avg_category_columns(group):
            cols.append(
                {
                    "name": _avg_header_name(section),
                    "id": section["id"],
                    "presentation": "markdown",
                }
            )
        cols.append(_hidden_key_column())
        return cols
    avg_section = _single_category_avg_section(group, cat)
    if avg_section:
        cols.append(
            {
                "name": CATEGORY_AVG_COL["abbr"],
                "id": CATEGORY_AVG_COL["id"],
                "presentation": "markdown",
            }
        )
    for mid in metrics_for(g, cat, threshold_overrides):
        abbr = metric_defs()[mid]["abbr"]
        cols.append({"name": abbr, "id": abbr, "presentation": "markdown"})
    cols.append(_hidden_key_column())
    return cols


def _identity_cells(player: dict, identity_cols: list[str]) -> dict:
    """Build shortlist identity cells for one stats player row."""
    left = player.get("left_foot") or ""
    right = player.get("right_foot") or ""
    foot_row = {"Left Foot": left, "Right Foot": right}
    getters = {
        "Name": lambda: player.get("name") or "",
        "Age": lambda: player.get("age") or "—",
        "Height": lambda: _display_blank(player.get("height")),
        "Position": lambda: player.get("position") or "—",
        "Club": lambda: player.get("club") or "—",
        "Rec": lambda: _display_blank(player.get("rec")),
        "Injury": lambda: _display_blank(player.get("injury")),
        "Division": lambda: _display_blank(player.get("division")),
        "Nation": lambda: _display_blank(player.get("nation")),
        "Inf": lambda: _display_blank(player.get("inf")),
        "Best Pos": lambda: _display_blank(player.get("best_pos")),
        "Feet": lambda: feet_cell(foot_row),
    }
    row: dict = {}
    for col in identity_cols:
        getter = getters.get(col)
        if getter is not None:
            row[col] = getter()
    if "Feet" in identity_cols:
        row["Left Foot"] = left
        row["Right Foot"] = right
    return row


def _header_tooltips(
    group: str,
    category: str,
    threshold_overrides=None,
    settings=None,
) -> dict[str, str]:
    """Full names for abbreviated Mins / Ht / percentile / metric headers."""
    g, cat = _resolve_category(group, category)
    identity_cols = us.shortlist_columns_for("player_stats", settings)
    tips = identity_header_tooltips(*identity_cols, "Minutes")
    if cat == "all":
        tips[OVERALL_COL["id"]] = OVERALL_COL["label"]
        for section in _avg_category_columns(group):
            tips[section["id"]] = section["label"]
        return tips
    avg_section = _single_category_avg_section(group, cat)
    if avg_section:
        tips[CATEGORY_AVG_COL["id"]] = f"{avg_section['label']} average"
    for mid in metrics_for(g, cat, threshold_overrides):
        meta = metric_defs()[mid]
        tips[meta["abbr"]] = meta["label"]
    return tips


def _build_rows(
    players,
    *,
    group,
    category,
    minutes_required,
    threshold_overrides=None,
    settings=None,
) -> list[dict]:
    settings = us.normalize(settings)
    identity_cols = us.shortlist_columns_for("player_stats", settings)
    g, cat = _resolve_category(group, category)
    metric_ids = (
        [] if cat == "all" else metrics_for(g, cat, threshold_overrides)
    )
    avg_cats = _avg_category_columns(group) if cat == "all" else []
    rows = []
    for p in players:
        if group not in ("", "all") and p.get("pos_group") != group:
            continue
        status = minutes_status(p.get("minutes"), minutes_required)
        mins = p.get("minutes")
        mins_text = "—" if mins is None else f"{mins:.0f}"
        row = _identity_cells(p, identity_cols)
        row["Minutes"] = _colored_cell(mins_text, minutes_color(status))
        row["_key"] = player_key(p)
        stats = scoring_stats(p)
        bg, bc = _band_group_cat(p, group, cat)
        if cat == "all":
            if bg is None or bc is None:
                row[OVERALL_COL["id"]] = _percentile_cell(
                    {"percentile": None, "color": None}
                )
            else:
                use_g = g if group not in ("", "all") else bg
                row[OVERALL_COL["id"]] = _percentile_cell(
                    overall_average_band(
                        use_g, stats, threshold_overrides=threshold_overrides
                    )
                )
            for section in avg_cats:
                col_id = section["id"]
                if bg is None or bc is None:
                    row[col_id] = _percentile_cell({"percentile": None, "color": None})
                    continue
                use_g = g if group not in ("", "all") else bg
                band = category_average_band(
                    use_g,
                    section["id"],
                    stats,
                    threshold_overrides=threshold_overrides,
                )
                row[col_id] = _percentile_cell(band)
            rows.append(row)
            continue
        # Single category: avg percentile, then individual metrics.
        if bg is None or bc is None:
            row[CATEGORY_AVG_COL["id"]] = _percentile_cell(
                {"percentile": None, "color": None}
            )
        else:
            use_g, use_c = (g, cat) if group not in ("", "all") else (bg, bc)
            row[CATEGORY_AVG_COL["id"]] = _percentile_cell(
                category_average_band(
                    use_g, use_c, stats, threshold_overrides=threshold_overrides
                )
            )
        for mid in metric_ids:
            abbr = metric_defs()[mid]["abbr"]
            if bg is None or bc is None:
                row[abbr] = "—"
                continue
            use_g, use_c = (g, cat) if group not in ("", "all") else (bg, bc)
            if mid not in metrics_for(use_g, use_c, threshold_overrides):
                row[abbr] = "—"
                continue
            band = band_metric(
                use_g,
                use_c,
                mid,
                stats.get(mid),
                threshold_overrides=threshold_overrides,
            )
            row[abbr] = _colored_cell(band["display"], band["color"])
        rows.append(row)
    return rows


EVAL_GROUPS = tuple((key, label) for key, label, _css in POS_GROUPS if key != "all")
EVAL_GROUPS_GK = tuple((key, label) for key, label in EVAL_GROUPS if key == "gk")
EVAL_GROUPS_OUTFIELD = tuple((key, label) for key, label in EVAL_GROUPS if key != "gk")


def _eval_groups_for_player(player: dict | None) -> tuple[tuple[str, str], ...]:
    pg = (player or {}).get("pos_group") or "mid"
    return EVAL_GROUPS_GK if is_gk_group(pg) else EVAL_GROUPS_OUTFIELD


def _normalize_eval_group(
    group: str | None,
    fallback: str | None = "mid",
    *,
    player: dict | None = None,
) -> str:
    options = _eval_groups_for_player(player) if player is not None else EVAL_GROUPS
    allowed = {key for key, _ in options}
    default = fallback or (options[0][0] if options else "mid")
    if default not in allowed:
        default = next(iter(allowed), "mid")
    g = group or default
    return g if g in allowed else default


def _player_metric_sections(
    player: dict,
    eval_group: str | None = None,
    *,
    threshold_overrides=None,
) -> list[dict]:
    g = _normalize_eval_group(
        eval_group, player.get("pos_group") or "mid", player=player
    )
    stats = scoring_stats(player)
    sections = []
    for cat in categories_for_group(g):
        metrics = []
        for mid in metrics_for(g, cat["id"], threshold_overrides):
            band = band_metric(
                g,
                cat["id"],
                mid,
                stats.get(mid),
                threshold_overrides=threshold_overrides,
            )
            meta = metric_defs()[mid]
            metrics.append(
                {
                    "id": mid,
                    "label": meta["label"],
                    "abbr": meta["abbr"],
                    "display": band["display"],
                    "percentile": band.get("percentile"),
                    "color": band.get("color"),
                    "missing": band.get("percentile") is None,
                }
            )
        pcts = [
            float(m["percentile"])
            for m in metrics
            if m.get("percentile") is not None
        ]
        avg = sum(pcts) / len(pcts) if pcts else None
        sections.append(
            {
                "id": cat["id"],
                "label": cat["label"],
                "metrics": metrics,
                "avg_percentile": avg,
                "avg_color": percentile_color(avg) if avg is not None else None,
            }
        )
    return sections


def _section_title(cat: dict) -> html.Div:
    """Category heading with average percentile badge when available."""
    avg = cat.get("avg_percentile")
    children: list = [html.Span(cat["label"], className="st-section-title-text")]
    if avg is None:
        children.append(
            html.Span("Avg —", className="st-section-avg is-missing")
        )
    else:
        children.append(
            html.Span(
                f"Avg ~{avg:.0f}th",
                className="st-section-avg",
                style={"color": cat.get("avg_color")} if cat.get("avg_color") else None,
                title=f"Average estimated percentile across metrics in {cat['label']}",
            )
        )
    return html.Div(children, className="rs-player-id-section-title st-section-title")


def _seg_switcher(
    *,
    options: list[tuple[str, str]],
    active: str,
    id_key: str,
    id_type: str,
) -> html.Div:
    buttons = []
    for value, label in options:
        buttons.append(
            html.Button(
                label,
                id={"type": id_type, id_key: value},
                n_clicks=0,
                className="st-player-seg-btn"
                + (" active" if active == value else ""),
            )
        )
    return html.Div(buttons, className="st-player-seg")


def _view_switcher(active: str) -> html.Div:
    return _seg_switcher(
        options=[("values", "Values"), ("bars", "Bars"), ("pizzas", "Pizzas")],
        active=active,
        id_key="view",
        id_type="st-player-view",
    )


def _group_switcher(active: str, player: dict | None = None) -> html.Div:
    return _seg_switcher(
        options=list(_eval_groups_for_player(player)),
        active=active,
        id_key="group",
        id_type="st-player-group",
    )

def _metrics_values(sections: list[dict]) -> list:
    blocks = []
    for cat in sections:
        items = []
        for metric in cat["metrics"]:
            if metric["missing"]:
                value = html.Div(
                    [
                        html.Span("No data", className="rs-player-id-value st-metric-nodata"),
                        html.Span("—", className="st-metric-pct is-missing"),
                    ],
                    className="st-metric-value-row",
                )
            else:
                pct = metric["percentile"]
                value = html.Div(
                    [
                        html.Span(
                            metric["display"],
                            className="rs-player-id-value",
                            style={"color": metric["color"]} if metric["color"] else None,
                        ),
                        html.Span(
                            f"~{pct:.0f}th",
                            className="st-metric-pct",
                            title=f"~{pct:.0f}th percentile",
                        ),
                    ],
                    className="st-metric-value-row",
                )
            items.append(
                html.Div(
                    [
                        html.Span(metric["label"], className="rs-player-id-label"),
                        value,
                    ],
                    className="rs-player-id-item",
                )
            )
        blocks.append(
            html.Div(
                [
                    _section_title(cat),
                    html.Div(items, className="rs-player-identity"),
                ],
                className="rs-player-id-section",
            )
        )
    return blocks


PLAYER_CHART_CONFIG = {
    "displayModeBar": False,
    "displaylogo": False,
    "responsive": True,
    "scrollZoom": False,
    "doubleClick": False,
    "showAxisDragHandles": False,
    "showAxisRangeEntryBoxes": False,
}


def _normalize_player_view(view: str | None) -> str:
    return view if view in ("values", "bars", "pizzas") else "bars"


def _chart_layout(theme: str | None, *, height: int, margin: dict | None = None) -> dict:
    dark = (theme or "dark") != "light"
    return dict(
        template="plotly_dark" if dark else "plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(
            color="#f8fafc" if dark else "#0f172a",
            size=14,
            family="IBM Plex Sans, Segoe UI, sans-serif",
        ),
        margin=margin or dict(l=130, r=72, t=12, b=36),
        height=height,
        showlegend=False,
        dragmode=False,
        hovermode="closest",
    )


def _bars_figure(metrics: list[dict], theme: str | None) -> go.Figure:
    dark = (theme or "dark") != "light"
    label_color = "#f8fafc" if dark else "#0f172a"
    muted = "#cbd5e1" if dark else "#475569"
    labels = [m["label"] for m in metrics][::-1]
    pcts = []
    colors = []
    texts = []
    for metric in metrics[::-1]:
        if metric["missing"]:
            pcts.append(0)
            colors.append("rgba(148, 163, 184, 0.35)")
            texts.append("No data")
        else:
            pcts.append(float(metric["percentile"]))
            colors.append(metric["color"] or "rgb(64, 220, 120)")
            texts.append(metric["display"])
    fig = go.Figure(
        go.Bar(
            x=pcts,
            y=labels,
            orientation="h",
            marker=dict(color=colors, line=dict(width=0)),
            text=texts,
            textposition="outside",
            textfont=dict(color=label_color, size=15),
            cliponaxis=False,
            hovertemplate="%{y}<br>%{x:.0f}th pct · %{text}<extra></extra>",
        )
    )
    fig.update_layout(
        **_chart_layout(
            theme,
            height=max(220, 42 * len(metrics) + 64),
            margin=dict(l=168, r=72, t=12, b=36),
        ),
        xaxis=dict(
            range=[0, 112],
            title=None,
            ticksuffix="",
            showgrid=True,
            gridcolor="rgba(148,163,184,0.22)",
            zeroline=False,
            fixedrange=True,
            tickfont=dict(color=muted, size=13),
            title_font=dict(color=muted, size=13),
            domain=[0.02, 1],
        ),
        yaxis=dict(
            automargin=True,
            fixedrange=True,
            tickfont=dict(color=label_color, size=14),
            ticksuffix="   ",
            ticklabelposition="outside",
            ticklabeloverflow="allow",
            ticklabelstandoff=18,
        ),
        bargap=0.18,
        bargroupgap=0.08,
    )
    fig.update_xaxes(title_text="Percentile")
    return fig


def _pizza_radius(percentile: float) -> float:
    """Map 0–100 percentile onto a visible polar radius (0th still a sliver).

    Tops out slightly under 100 so the outer 100% ring stays visible.
    """
    floor = 10.0
    ceiling = 96.0
    p = max(0.0, min(100.0, float(percentile)))
    return floor + (p / 100.0) * (ceiling - floor)


def _pizza_figure(metrics: list[dict], theme: str | None) -> go.Figure:
    dark = (theme or "dark") != "light"
    label_color = "#f8fafc" if dark else "#0f172a"
    muted = "#cbd5e1" if dark else "#475569"
    ring_color = "rgba(226, 232, 240, 0.85)" if dark else "rgba(71, 85, 105, 0.75)"
    missing_fill = "rgba(148, 163, 184, 0.18)" if dark else "rgba(148, 163, 184, 0.22)"
    if not metrics:
        fig = go.Figure()
        fig.update_layout(
            **_chart_layout(theme, height=320, margin=dict(l=40, r=40, t=20, b=20))
        )
        return fig

    n = len(metrics)
    # Full-width wedges so arcs meet with no gaps.
    width = 360.0 / n
    theta = []
    radius = []
    colors = []
    custom = []
    for i, metric in enumerate(metrics):
        theta.append(i * width)
        if metric["missing"]:
            radius.append(5.0)
            colors.append(missing_fill)
            custom.append(f"{metric['abbr']} · No data")
        else:
            pct = float(metric["percentile"])
            radius.append(_pizza_radius(pct))
            colors.append(metric["color"] or ("rgb(61, 255, 136)" if dark else "rgb(22, 163, 74)"))
            custom.append(f"{metric['abbr']} · {metric['display']}<br>{pct:.0f}th pct")

    tickvals = [i * width for i in range(n)]
    ticktext = [metric["abbr"] for metric in metrics]
    # Explicit closed ring at r=100 so the outer percentile bound is always visible.
    ring_theta = list(range(0, 361, 3))
    fig = go.Figure(
        data=[
            go.Barpolar(
                r=radius,
                theta=theta,
                width=[width] * n,
                base=0,
                marker=dict(
                    color=colors,
                    line=dict(
                        color="rgba(15, 23, 42, 0.45)" if dark else "rgba(255,255,255,0.75)",
                        width=1.25,
                    ),
                ),
                hovertemplate="%{customdata}<extra></extra>",
                customdata=custom,
                name="Percentile",
            ),
            go.Scatterpolar(
                r=[100] * len(ring_theta),
                theta=ring_theta,
                mode="lines",
                line=dict(color=ring_color, width=2),
                hoverinfo="skip",
                showlegend=False,
                cliponaxis=False,
            ),
        ]
    )
    fig.update_layout(
        **_chart_layout(theme, height=360, margin=dict(l=48, r=48, t=36, b=36)),
        polar=dict(
            bgcolor="rgba(0,0,0,0)",
            hole=0.08,
            radialaxis=dict(
                range=[0, 100],
                autorange=False,
                tickvals=[0, 25, 50, 75, 100],
                showticklabels=False,
                ticks="",
                gridcolor="rgba(148,163,184,0.32)",
                gridwidth=1,
                tickfont=dict(color=muted, size=11),
                showline=False,
            ),
            angularaxis=dict(
                rotation=90,
                direction="clockwise",
                period=360,
                tickmode="array",
                tickvals=tickvals,
                ticktext=ticktext,
                showticklabels=True,
                ticks="",
                gridcolor="rgba(148,163,184,0.18)",
                tickfont=dict(color=label_color, size=12),
                showline=False,
            ),
        ),
    )
    return fig


def _pizza_infobox(metrics: list[dict]) -> html.Div:
    rows = []
    for metric in metrics:
        swatch = metric["color"] or "rgba(148, 163, 184, 0.35)"
        if metric["missing"]:
            value = "No data"
            pct = "—"
        else:
            value = metric["display"]
            pct = f"~{metric['percentile']:.0f}th"
        rows.append(
            html.Div(
                [
                    html.Span(
                        className="st-pizza-swatch",
                        style={"background": swatch},
                    ),
                    html.Div(
                        [
                            html.Span(metric["abbr"], className="st-pizza-legend-abbr"),
                            html.Span(metric["label"], className="st-pizza-legend-name"),
                        ],
                        className="st-pizza-legend-text",
                    ),
                    html.Div(
                        [
                            html.Span(
                                value,
                                className="st-pizza-legend-val"
                                + (" is-missing" if metric["missing"] else ""),
                                style=(
                                    None
                                    if metric["missing"] or not metric["color"]
                                    else {"color": metric["color"]}
                                ),
                            ),
                            html.Span(pct, className="st-pizza-legend-pct"),
                        ],
                        className="st-pizza-legend-nums",
                    ),
                ],
                className="st-pizza-legend-row",
            )
        )
    return html.Div(
        [
            html.Div("Metrics", className="st-pizza-infobox-title"),
            html.Div(rows, className="st-pizza-legend"),
        ],
        className="st-pizza-infobox",
    )


def _metrics_bars(sections: list[dict], theme: str | None) -> list:
    blocks = []
    for cat in sections:
        if not cat["metrics"]:
            continue
        blocks.append(
            html.Div(
                [
                    _section_title(cat),
                    dcc.Graph(
                        figure=_bars_figure(cat["metrics"], theme),
                        config=PLAYER_CHART_CONFIG,
                        className="st-player-chart",
                    ),
                ],
                className="rs-player-id-section st-player-chart-section",
            )
        )
    return blocks


def _metrics_pizzas(sections: list[dict], theme: str | None) -> list:
    blocks = []
    for cat in sections:
        if not cat["metrics"]:
            continue
        blocks.append(
            html.Div(
                [
                    _section_title(cat),
                    html.Div(
                        [
                            dcc.Graph(
                                figure=_pizza_figure(cat["metrics"], theme),
                                config={
                                    **PLAYER_CHART_CONFIG,
                                    "staticPlot": True,
                                },
                                className="st-player-chart st-player-pizza",
                            ),
                            _pizza_infobox(cat["metrics"]),
                        ],
                        className="st-pizza-layout",
                    ),
                ],
                className="rs-player-id-section st-player-chart-section",
            )
        )
    return blocks


def _format_minutes_identity(value) -> str:
    if value in (None, "", "-"):
        return "—"
    try:
        num = float(value)
    except (TypeError, ValueError):
        return str(value)
    return str(int(num)) if num == int(num) else str(num)


def _overall_avg_banner(sections: list[dict]) -> html.Div:
    """Modal summary: mean of the three category average percentiles."""
    pcts = [
        float(cat["avg_percentile"])
        for cat in sections
        if cat.get("avg_percentile") is not None
    ]
    if not pcts:
        return html.Div(
            [
                html.Span("Overall", className="st-overall-label"),
                html.Span("Avg —", className="st-section-avg is-missing"),
            ],
            className="st-overall-avg",
        )
    avg = sum(pcts) / len(pcts)
    color = percentile_color(avg)
    return html.Div(
        [
            html.Span("Overall", className="st-overall-label"),
            html.Span(
                f"Avg ~{avg:.0f}th",
                className="st-section-avg",
                style={"color": color} if color else None,
                title=(
                    "Average of Defending, Final third / Goalkeeping, "
                    "and Possession category averages"
                ),
            ),
        ],
        className="st-overall-avg",
    )


def _player_modal_body(
    player: dict,
    minutes_required: float,
    *,
    view: str = "bars",
    eval_group: str | None = None,
    theme: str | None = "dark",
    threshold_overrides=None,
    settings=None,
) -> html.Div:
    settings = us.normalize(settings)
    view = _normalize_player_view(view)
    eval_group = _normalize_eval_group(
        eval_group, player.get("pos_group") or "mid", player=player
    )
    sections = _player_metric_sections(
        player, eval_group, threshold_overrides=threshold_overrides
    )
    if view == "bars":
        metrics = _metrics_bars(sections, theme)
    elif view == "pizzas":
        metrics = _metrics_pizzas(sections, theme)
    else:
        metrics = _metrics_values(sections)
    status = minutes_status(player.get("minutes"), minutes_required)
    return player_detail_body(
        player,
        id_prefix="st",
        extra_identity_fields=[("Minutes", "minutes")],
        modal_fields=us.modal_identity_fields_for("player_stats", settings) if settings else None,
        field_styles={
            "minutes": {"color": minutes_color(status)},
            "injury": {"color": "#fbbf24", "fontWeight": "600"},
        },
        field_formatters={"minutes": _format_minutes_identity},
        after_identity=[
            html.Div(
                [
                    html.Div("Evaluate as", className="st-player-switch-label"),
                    _group_switcher(eval_group, player),
                ],
                className="st-player-switch-block",
            ),
            html.Div(
                [
                    html.Div("Display", className="st-player-switch-label"),
                    _view_switcher(view),
                ],
                className="st-player-switch-block",
            ),
            _overall_avg_banner(sections),
        ],
        bottom=html.Div(metrics, className="st-player-metrics"),
    )


def _filter_players(
    players,
    *,
    pos,
    search,
    max_age,
    minutes_match,
    minutes_required,
    foot,
    foot_thresholds,
):
    q = (search or "").strip().casefold()
    max_age = 99 if max_age is None else int(max_age)
    out = []
    for p in players:
        if pos not in ("", "all") and p.get("pos_group") != pos:
            continue
        if q:
            blob = " ".join(
                str(p.get(k) or "")
                for k in ("name", "club", "position", "best_pos", "division")
            ).casefold()
            if q not in blob:
                continue
        if max_age < 99 and to_int(p.get("age")) > max_age:
            continue
        status = minutes_status(p.get("minutes"), minutes_required)
        if not passes_minutes_filter(status, minutes_match or "any"):
            continue
        row = {
            "Left Foot": p.get("left_foot") or "",
            "Right Foot": p.get("right_foot") or "",
        }
        if foot and not foot_match(row, foot, foot_thresholds):
            continue
        out.append(p)
    return out


def layout(**_kwargs):
    settings = us.load()
    mins_req = us.default_minutes_required(settings)
    foot_thresholds = settings["foot_thresholds"]
    return html.Div(
        [
            dcc.Interval(id="st-hydrate-tick", interval=50, max_intervals=1),
            dcc.Store(id="st-pos", data="all"),
            dcc.Store(id="st-category", data="all"),
            dcc.Store(id="st-foot", data=""),
            dcc.Store(id="st-marked", data=[]),
            dcc.Store(id="st-sort-memory", data=None),
            dcc.Store(id="st-player-key", data=None),
            dcc.Store(id="st-player-view", data="bars", storage_type="local"),
            dcc.Store(id="st-player-group", data="mid"),
            dcc.Download(id="st-download"),
            html.Div(
                [
                    html.Button(id={"type": "st-pos", "key": "_"}, n_clicks=0),
                    html.Button(id={"type": "st-cat", "key": "_"}, n_clicks=0),
                    html.Button(id={"type": "st-foot", "foot": "_"}, n_clicks=0),
                    html.Button(id={"type": "st-player-view", "view": "_"}, n_clicks=0),
                    html.Button(id={"type": "st-player-group", "group": "_"}, n_clicks=0),
                ],
                hidden=True,
            ),            dbc.Card(
                [
                    dbc.CardHeader("1. Upload statistics export"),
                    dbc.CardBody(
                        [
                            html.Div(
                                dcc.Upload(
                                    id="st-upload",
                                    children=html.Div(
                                        [
                                            "Drag and drop or ",
                                            html.A("select a Moneyball stats CSV"),
                                        ]
                                    ),
                                    className="rs-upload",
                                    multiple=False,
                                ),
                                id="st-upload-wrap",
                            ),
                            html.Div(
                                [
                                    html.Div(
                                        id="st-upload-status",
                                        className="rs-upload-status",
                                    ),
                                    html.Div(
                                        dcc.Upload(
                                            id="st-upload-replace",
                                            children=html.Span(
                                                "Replace",
                                                className="rs-upload-replace",
                                            ),
                                            className="rs-upload-replace-wrap",
                                            multiple=False,
                                        ),
                                        id="st-upload-replace-wrap",
                                        hidden=True,
                                    ),
                                ],
                                className="rs-upload-status-row",
                            ),
                            html.P(
                                f"Use the statistics Moneyball export. Benchmarks: {benchmarks()['name']}.",
                                className="text-muted small mb-0 mt-2",
                            ),
                        ]
                    ),
                ],
                className="mb-3 rs-section-card",
            ),
            html.Div(
                [
                    dbc.Card(
                        [
                            section_card_header(
                                "2. Shortlist",
                                trailing=pack_picker_bar(
                                    select_id="st-stats-thresh-pack",
                                    label="Percentiles",
                                    options=stp.pack_options(),
                                    value=(
                                        settings.get("stats_threshold_pack_id")
                                        or stp.active_id()
                                    ),
                                    edit_href="/settings?section=player-stats",
                                    edit_title=(
                                        "Open Settings → Player stats to edit percentile packs."
                                    ),
                                    select_title=(
                                        "Benchmark cut-points used for estimated percentiles."
                                    ),
                                ),
                            ),
                            dbc.CardBody(
                                [
                                    player_filters_host(prefix="st", stacked=True),
                                    html.Div(
                                        [
                                            html.Div(
                                                [
                                                    html.Label("Search", className="rs-field-label"),
                                                    dmc.TextInput(
                                                        id="st-search",
                                                        placeholder="Name, club, position",
                                                    ),
                                                ],
                                                className="rs-filter-search",
                                            ),
                                            html.Div(
                                                [
                                                    html.Label("Max age", className="rs-field-label"),
                                                    dmc.Select(
                                                        id="st-age",
                                                        data=us.age_options(settings),
                                                        value="99",
                                                        clearable=False,
                                                        searchable=False,
                                                    ),
                                                ],
                                                className="rs-filter-age",
                                            ),
                                            html.Div(
                                                [
                                                    html.Div(
                                                        [
                                                            html.Label(
                                                                "Minutes",
                                                                className="rs-field-label",
                                                            ),
                                                            *_help_icon(
                                                                f"Default requirement {mins_req} min. "
                                                                "Green=meet, yellow=≥half, red=below half.",
                                                                "st-help-minutes",
                                                            ),
                                                        ],
                                                        className="rs-field-label-row",
                                                    ),
                                                    html.Div(
                                                        [
                                                            dmc.NumberInput(
                                                                id="st-minutes-required",
                                                                value=mins_req,
                                                                min=0,
                                                                max=20000,
                                                                step=90,
                                                            ),
                                                            dmc.Select(
                                                                id="st-minutes-match",
                                                                data=[
                                                                    {
                                                                        "label": "Any",
                                                                        "value": "any",
                                                                    },
                                                                    {
                                                                        "label": "Half or more",
                                                                        "value": "half",
                                                                    },
                                                                    {
                                                                        "label": "Meets requirements",
                                                                        "value": "meet",
                                                                    },
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
                                        className="rs-shortlist-filters-row",
                                    ),
                                    player_data_table(
                                        prefix="st",
                                        columns=_table_columns("all", "all", settings=settings),
                                        page_size=us.page_size(settings),
                                        style_cell_props=style_cell(text_align="center"),
                                        style_cell_conditional_rules=style_cell_conditional()
                                        + _KEY_COLUMN_HIDE,
                                        style_header_props=style_header(),
                                        style_header_conditional_rules=style_header_conditional(
                                            extra=_avg_header_styles() + _KEY_COLUMN_HIDE
                                        ),
                                        style_data_conditional_rules=_table_base_styles("dark"),
                                        css=_table_css(),
                                        shell_class_name="rs-table-shell mt-2",
                                    ),
                                    table_caption_row(
                                        prefix="st",
                                        clear_button_id="st-clear-marks",
                                        settings=settings,
                                    ),
                                    html.Div(
                                        [
                                            dmc.Button(
                                                "Show score distribution",
                                                id="st-hist-toggle",
                                                n_clicks=0,
                                                variant="light",
                                                className="rs-hist-toggle",
                                            ),
                                            html.Div(
                                                dcc.Graph(
                                                    id="st-hist",
                                                    figure=BLANK_FIG,
                                                    config={"displayModeBar": False},
                                                    responsive=True,
                                                    style={"width": "100%", "height": "240px"},
                                                ),
                                                id="st-hist-wrap",
                                                className="rs-hist-wrap",
                                                hidden=True,
                                            ),
                                        ],
                                        className="rs-hist-block",
                                    ),
                                ]
                            ),
                        ],
                        className="mb-3 rs-section-card",
                    ),
                    dbc.Card(
                        [
                            dbc.CardHeader("3. Export"),
                            dbc.CardBody(
                                [
                                    dmc.Button(
                                        "Download stats CSV",
                                        id="st-csv-btn",
                                        className="me-2",
                                    ),
                                    dmc.Button(
                                        "Download marked CSV",
                                        id="st-marked-csv-btn",
                                        variant="light",
                                        disabled=True,
                                    ),
                                    html.Div(
                                        id="st-marked-preview",
                                        className="mt-2 text-muted",
                                    ),
                                ]
                            ),
                        ],
                        className="mb-3 rs-section-card",
                    ),
                ],
                id="st-main",
                hidden=True,
            ),
            player_modal(prefix="st"),
        ],
        className="rs-page st-page",
    )


@callback(
    Output("st-parsed", "data"),
    Output("st-upload-status", "children"),
    Output("st-upload-wrap", "hidden"),
    Output("st-upload-replace-wrap", "hidden"),
    Output("st-main", "hidden"),
    Input("st-upload", "contents"),
    Input("st-upload-replace", "contents"),
    State("st-upload", "filename"),
    State("st-upload-replace", "filename"),
    prevent_initial_call=True,
)
def on_upload(upload_contents, replace_contents, upload_name, replace_name):
    if ctx.triggered_id == "st-upload-replace":
        contents = replace_contents
        name = replace_name or "upload.csv"
    elif ctx.triggered_id == "st-upload":
        contents = upload_contents
        name = upload_name or "upload.csv"
    else:
        contents = replace_contents or upload_contents
        name = (replace_name or upload_name) or "upload.csv"
    if not contents:
        return no_update, no_update, no_update, no_update, no_update
    if not name.lower().endswith(".csv"):
        return (
            None,
            _upload_error("Upload a Moneyball statistics CSV export."),
            False,
            True,
            True,
        )
    try:
        players = parse_stats_export(_decode_upload(contents))
    except Exception as exc:
        return None, _upload_error(str(exc)), False, True, True
    return (
        _pack_parsed(players, name),
        _upload_status(len(players), name),
        True,
        False,
        False,
    )


@callback(
    Output("st-upload-status", "children", allow_duplicate=True),
    Output("st-upload-wrap", "hidden", allow_duplicate=True),
    Output("st-upload-replace-wrap", "hidden", allow_duplicate=True),
    Output("st-main", "hidden", allow_duplicate=True),
    Input("st-parsed", "data"),
    Input("st-hydrate-tick", "n_intervals"),
    prevent_initial_call="initial_duplicate",
)
def restore_upload_ui(parsed, _tick):
    """Re-show upload status when session-stored CSV survives page navigation."""
    unpacked = _unpack_parsed(parsed)
    if not unpacked or not unpacked.get("players"):
        return no_update, no_update, no_update, no_update
    filename = unpacked.get("filename") or "export.csv"
    return (
        _upload_status(len(unpacked["players"]), filename),
        True,
        False,
        False,
    )


@callback(
    Output("st-pos", "data"),
    Input({"type": "st-pos", "key": ALL}, "n_clicks"),
    State("st-pos", "data"),
    prevent_initial_call=True,
)
def set_pos(n_clicks, current):
    if not ctx.triggered_id or not _clicked(n_clicks):
        return no_update
    key = ctx.triggered_id.get("key")
    if key == "_":
        return no_update
    return key or current or "all"


@callback(
    Output("st-category", "data"),
    Input({"type": "st-cat", "key": ALL}, "n_clicks"),
    Input("st-pos", "data"),
    State("st-category", "data"),
    prevent_initial_call=True,
)
def set_category(n_clicks, pos, current):
    triggered = ctx.triggered_id
    if triggered == "st-pos" or (
        isinstance(triggered, dict) and triggered.get("type") == "st-pos"
    ):
        _g, cat = _resolve_category(pos or "all", current or "")
        return cat
    if not isinstance(triggered, dict) or not _clicked(n_clicks):
        return no_update
    key = triggered.get("key") or current or ""
    if key == "_":
        return no_update
    _g, cat = _resolve_category(pos or "all", key)
    return cat


@callback(
    Output("st-foot", "data"),
    Input({"type": "st-foot", "foot": ALL}, "n_clicks"),
    State("st-foot", "data"),
    prevent_initial_call=True,
)
def set_foot(n_clicks, current):
    if not ctx.triggered_id or not _clicked(n_clicks):
        return no_update
    chosen = ctx.triggered_id.get("foot")
    if chosen == "_":
        return no_update
    # Off by default; click the active foot again to clear.
    return "" if current == chosen else chosen


@callback(
    Output("st-age", "data"),
    Output("st-age", "value"),
    Output("st-stats-thresh-pack", "data"),
    Output("st-stats-thresh-pack", "value"),
    Input("ui-settings", "data"),
    State("st-age", "value"),
    State("st-stats-thresh-pack", "value"),
)
def apply_stats_settings(settings, age, thresh_pack_id):
    settings = us.normalize(settings)
    ages = us.age_options(settings)
    packs = stp.pack_options()
    allowed = {opt["value"] for opt in packs}
    active = (
        settings.get("stats_threshold_pack_id")
        or thresh_pack_id
        or stp.active_id()
    )
    if active not in allowed:
        active = stp.BUILTIN if stp.BUILTIN in allowed else next(iter(allowed), stp.BUILTIN)
    return ages, us.clamp_choice(age, ages, "99"), packs, active


@callback(
    Output("ui-settings", "data", allow_duplicate=True),
    Input("st-stats-thresh-pack", "value"),
    State("ui-settings", "data"),
    prevent_initial_call=True,
)
def switch_stats_thresh_pack(pack_id, settings):
    if not pack_id:
        return no_update
    settings = us.normalize(settings)
    if pack_id == settings.get("stats_threshold_pack_id"):
        return no_update
    pack = stp.load(pack_id)
    settings["stats_thresholds"] = pack["thresholds"]
    settings["stats_threshold_pack_id"] = pack["id"]
    return settings


@callback(
    Output("st-page-size", "data"),
    Output("st-page-size", "value"),
    Output("st-minutes-required", "value"),
    Input("ui-settings", "data"),
)
def sync_st_controls_from_settings(settings):
    from player_table import default_page_size_value, page_size_select_data

    settings = us.normalize(settings)
    return (
        page_size_select_data(settings),
        default_page_size_value(settings),
        us.default_minutes_required(settings),
    )


@callback(
    Output("st-filters", "children"),
    Output("st-table", "columns"),
    Output("st-table", "data"),
    Output("st-table", "tooltip_header"),
    Output("st-table", "style_data_conditional"),
    Output("st-table", "page_size"),
    Output("st-table", "selected_rows"),
    Output("st-table", "sort_by"),
    Output("st-sort-memory", "data"),
    Output("st-table-caption", "children"),
    Output("st-clear-marks", "disabled"),
    Output("st-marked-csv-btn", "disabled"),
    Output("st-marked-preview", "children"),
    Output("st-hist", "figure"),
    Input("st-parsed", "data"),
    Input("st-pos", "data"),
    Input("st-category", "data"),
    Input("st-search", "value"),
    Input("st-age", "value"),
    Input("st-minutes-match", "value"),
    Input("st-minutes-required", "value"),
    Input("st-foot", "data"),
    Input("st-page-size", "value"),
    Input("st-marked", "data"),
    Input("st-table", "sort_by"),
    Input("ui-settings", "data"),
    Input("theme", "data"),
    State("st-sort-memory", "data"),
)
def refresh_table(
    parsed,
    pos,
    category,
    search,
    max_age,
    minutes_match,
    minutes_required,
    foot,
    page_size,
    marked,
    sort_by,
    settings,
    theme,
    sort_memory,
):
    players = _parsed_players(parsed)
    pos = pos or "all"
    settings = us.normalize(settings)
    minutes_required = float(
        minutes_required
        if minutes_required is not None
        else us.default_minutes_required(settings)
    )
    g, category = _resolve_category(pos, category or "")
    thresh = settings.get("stats_thresholds")

    filtered = _filter_players(
        players,
        pos=pos,
        search=search,
        max_age=max_age,
        minutes_match=minutes_match,
        minutes_required=minutes_required,
        foot=foot or "",
        foot_thresholds=settings["foot_thresholds"],
    )
    rows = _build_rows(
        filtered,
        group=pos,
        category=category,
        minutes_required=minutes_required,
        threshold_overrides=thresh,
        settings=settings,
    )
    cols = _table_columns(pos, category, thresh, settings=settings)
    col_ids = {c["id"] for c in cols}
    sort_by = _coerce_sort_by(
        sort_by,
        category,
        col_ids,
        triggered_id=ctx.triggered_id,
        previous=sort_memory,
    )
    _sort_table_rows(rows, sort_by)
    header_tips = _header_tooltips(pos, category, thresh, settings=settings)
    col_ids = [c["id"] for c in cols]
    table_rows = [{col: row.get(col, "—") for col in col_ids} for row in rows]
    marked_set = set(marked or [])
    selected = [
        i
        for i, row in enumerate(table_rows)
        if _row_mark_key(row) in marked_set
    ]
    page_size_i = int(page_size or 50)
    style_data = _table_base_styles(theme)

    caption = f"{len(rows):,} players"
    if marked_set:
        caption += f" · {len(marked_set)} marked"

    fig = BLANK_FIG
    if category == "all" and filtered:
        avg_cats = _avg_category_columns(pos)
        first = avg_cats[0] if avg_cats else None
        values = []
        if first:
            for p in filtered:
                bg, bc = _band_group_cat(p, pos, category)
                if bg is None or bc is None:
                    continue
                use_g = g if pos not in ("", "all") else bg
                band = category_average_band(
                    use_g,
                    first["id"],
                    scoring_stats(p),
                    threshold_overrides=thresh,
                )
                if band.get("percentile") is not None:
                    values.append(float(band["percentile"]))
        if values and first:
            fig = go.Figure(
                data=[go.Histogram(x=values, nbinsx=20, marker_color="#3b82f6")]
            )
            fig.update_layout(
                template="plotly_dark" if (theme or "dark") != "light" else "plotly_white",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                margin=dict(l=40, r=20, t=30, b=40),
                height=240,
                title=dict(text=f"{first['label']} avg percentile", font=dict(size=12)),
                xaxis_title="Percentile",
                yaxis_title="Players",
            )
    else:
        mids = metrics_for(g, category, thresh)
        if mids and filtered:
            mid = mids[0]
            values = [
                float(v)
                for p in filtered
                if (v := scoring_stats(p).get(mid)) is not None
            ]
            if values:
                fig = go.Figure(
                    data=[go.Histogram(x=values, nbinsx=20, marker_color="#3b82f6")]
                )
                fig.update_layout(
                    template="plotly_dark" if (theme or "dark") != "light" else "plotly_white",
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    margin=dict(l=40, r=20, t=30, b=40),
                    height=240,
                    title=dict(text=metric_defs()[mid]["label"], font=dict(size=12)),
                    xaxis_title=metric_defs()[mid]["abbr"],
                    yaxis_title="Players",
                )

    preview = (
        f"{len(marked_set)} player(s) marked"
        if marked_set
        else "No players marked yet."
    )
    foot_filter = foot or ""
    return (
        _filters_bar(
            players,
            pos=pos,
            category=category,
            foot=foot_filter,
            foot_thresholds=settings["foot_thresholds"],
        ),
        cols,
        table_rows,
        header_tips,
        style_data,
        page_size_i,
        selected,
        sort_by,
        sort_by,
        caption,
        not bool(marked_set),
        not bool(marked_set),
        preview,
        fig,
    )


@callback(
    Output("st-hist-wrap", "hidden"),
    Output("st-hist-toggle", "children"),
    Input("st-hist-toggle", "n_clicks"),
    State("st-hist-wrap", "hidden"),
)
def toggle_hist(n, hidden):
    if not n:
        return True, "Show score distribution"
    opened = bool(hidden)
    return (not opened), (
        "Hide score distribution" if opened else "Show score distribution"
    )


@callback(
    Output("st-marked", "data", allow_duplicate=True),
    Input("st-clear-marks", "n_clicks"),
    prevent_initial_call=True,
)
def clear_marks(_n):
    return []


@callback(
    Output("st-marked", "data", allow_duplicate=True),
    Input("st-table", "selected_rows"),
    State("st-table", "data"),
    State("st-marked", "data"),
    prevent_initial_call=True,
)
def sync_marks(selected_rows, table_data, marked):
    table_data = table_data or []
    keys_on_page = [_row_mark_key(r) for r in table_data]
    marked_set = set(marked or [])
    expected = {i for i, key in enumerate(keys_on_page) if key in marked_set}
    selected = set(selected_rows or [])
    if selected == expected:
        return no_update
    marked_set -= {key for key in keys_on_page if key}
    for i in selected:
        if 0 <= i < len(keys_on_page) and keys_on_page[i]:
            marked_set.add(keys_on_page[i])
    return sorted(marked_set)


@callback(
    Output("st-player-modal", "is_open"),
    Output("st-player-modal-title", "children"),
    Output("st-player-modal-body", "children"),
    Output("st-player-key", "data"),
    Output("st-player-group", "data"),
    Input("st-table", "active_cell"),
    Input("st-player-modal-close", "n_clicks"),
    State("st-table", "derived_viewport_data"),
    State("st-parsed", "data"),
    State("st-minutes-required", "value"),
    State("theme", "data"),
    State("st-player-view", "data"),
    State("ui-settings", "data"),
    prevent_initial_call=True,
)
def open_player(
    active_cell, _close, viewport, parsed, minutes_required, theme, view, settings
):
    if ctx.triggered_id == "st-player-modal-close":
        return False, no_update, no_update, None, "mid"
    if not active_cell or active_cell.get("column_id") != "Name":
        return no_update, no_update, no_update, no_update, no_update
    rows = viewport or []
    idx = active_cell.get("row")
    if idx is None or idx >= len(rows):
        return no_update, no_update, no_update, no_update, no_update
    key = _row_mark_key(rows[idx])
    players = _parsed_players(parsed)
    player = next((p for p in players if player_key(p) == key), None)
    view = _normalize_player_view(view)
    if not player:
        return True, "Player", html.Div("Player not found."), None, "mid"
    settings = us.normalize(settings)
    minutes_required = float(
        minutes_required
        if minutes_required is not None
        else us.default_minutes_required(settings)
    )
    eval_group = _normalize_eval_group(player.get("pos_group"), "mid", player=player)
    thresh = settings.get("stats_thresholds")
    return (
        True,
        player.get("name"),
        _player_modal_body(
            player,
            minutes_required,
            view=view,
            eval_group=eval_group,
            theme=theme,
            threshold_overrides=thresh,
            settings=settings,
        ),
        key,
        eval_group,
    )


def _lookup_modal_player(parsed, player_key_value):
    players = _parsed_players(parsed)
    return next((p for p in players if player_key(p) == player_key_value), None)


@callback(
    Output("st-player-view", "data", allow_duplicate=True),
    Output("st-player-modal-body", "children", allow_duplicate=True),
    Input({"type": "st-player-view", "view": ALL}, "n_clicks"),
    State("st-player-view", "data"),
    State("st-player-group", "data"),
    State("st-player-key", "data"),
    State("st-parsed", "data"),
    State("st-minutes-required", "value"),
    State("theme", "data"),
    State("ui-settings", "data"),
    prevent_initial_call=True,
)
def switch_player_view(
    n_clicks,
    current,
    eval_group,
    player_key_value,
    parsed,
    minutes_required,
    theme,
    settings,
):
    if not ctx.triggered_id or not _clicked(n_clicks):
        return no_update, no_update
    view = ctx.triggered_id.get("view")
    if view == "_" or view not in ("values", "bars", "pizzas"):
        return no_update, no_update
    if view == current:
        return no_update, no_update
    player = _lookup_modal_player(parsed, player_key_value)
    if not player:
        return view, html.Div("Player not found.")
    settings = us.normalize(settings)
    thresh = settings.get("stats_thresholds")
    return (
        view,
        _player_modal_body(
            player,
            float(
                minutes_required
                if minutes_required is not None
                else us.default_minutes_required(settings)
            ),
            view=view,
            eval_group=eval_group,
            theme=theme,
            threshold_overrides=thresh,
            settings=settings,
        ),
    )


@callback(
    Output("st-player-group", "data", allow_duplicate=True),
    Output("st-player-modal-body", "children", allow_duplicate=True),
    Input({"type": "st-player-group", "group": ALL}, "n_clicks"),
    State("st-player-group", "data"),
    State("st-player-view", "data"),
    State("st-player-key", "data"),
    State("st-parsed", "data"),
    State("st-minutes-required", "value"),
    State("theme", "data"),
    State("ui-settings", "data"),
    prevent_initial_call=True,
)
def switch_player_group(
    n_clicks, current, view, player_key_value, parsed, minutes_required, theme, settings
):
    if not ctx.triggered_id or not _clicked(n_clicks):
        return no_update, no_update
    group = ctx.triggered_id.get("group")
    player = _lookup_modal_player(parsed, player_key_value)
    if not player:
        return no_update, no_update
    allowed = {key for key, _ in _eval_groups_for_player(player)}
    if group == "_" or group not in allowed:
        return no_update, no_update
    if group == current:
        return no_update, no_update
    settings = us.normalize(settings)
    thresh = settings.get("stats_thresholds")
    return (
        group,
        _player_modal_body(
            player,
            float(
                minutes_required
                if minutes_required is not None
                else us.default_minutes_required(settings)
            ),
            view=_normalize_player_view(view),
            eval_group=group,
            theme=theme,
            threshold_overrides=thresh,
            settings=settings,
        ),
    )


def _csv_payload(fieldnames, rows) -> dict:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return dict(content=buf.getvalue(), filename="fm_stats_export.csv")


@callback(
    Output("st-download", "data"),
    Input("st-csv-btn", "n_clicks"),
    Input("st-marked-csv-btn", "n_clicks"),
    State("st-parsed", "data"),
    State("st-pos", "data"),
    State("st-category", "data"),
    State("st-search", "value"),
    State("st-age", "value"),
    State("st-minutes-match", "value"),
    State("st-minutes-required", "value"),
    State("st-foot", "data"),
    State("st-marked", "data"),
    State("ui-settings", "data"),
    prevent_initial_call=True,
)
def download_csv(
    _all,
    _marked,
    parsed,
    pos,
    category,
    search,
    max_age,
    minutes_match,
    minutes_required,
    foot,
    marked,
    settings,
):
    players = _parsed_players(parsed)
    if not players:
        return no_update
    settings = us.normalize(settings)
    minutes_required = float(
        minutes_required
        if minutes_required is not None
        else us.default_minutes_required(settings)
    )
    pos = pos or "all"
    _g, category = _resolve_category(pos, category or "")
    filtered = _filter_players(
        players,
        pos=pos,
        search=search,
        max_age=max_age,
        minutes_match=minutes_match,
        minutes_required=minutes_required,
        foot=foot or "",
        foot_thresholds=settings["foot_thresholds"],
    )
    if ctx.triggered_id == "st-marked-csv-btn":
        marked_set = set(marked or [])
        filtered = [p for p in filtered if player_key(p) in marked_set]
    table_rows = _build_rows(
        filtered,
        group=pos,
        category=category,
        minutes_required=minutes_required,
        threshold_overrides=settings.get("stats_thresholds"),
        settings=settings,
    )
    fieldnames = [
        c["id"]
        for c in _table_columns(
            pos, category, settings.get("stats_thresholds"), settings=settings
        )
    ]
    export_rows = [{k: _strip_cell(r.get(k)) for k in fieldnames} for r in table_rows]
    return _csv_payload(fieldnames, export_rows)
