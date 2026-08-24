"""Saved player profiles from Role scores and Player stats."""
from __future__ import annotations

from dash import ALL, Input, Output, State, callback, clientside_callback, ctx, dcc, html, no_update, register_page
import dash_bootstrap_components as dbc
import dash_mantine_components as dmc

from components.player_detail import role_player_detail_card
from components.player_modal import player_modal
from components.player_table import (
    default_page_size_value,
    feet_cell,
    identity_data_styles,
    identity_header_name,
    injury_cell,
    injury_tooltip_entry,
    player_data_table,
    style_cell,
    style_cell_conditional,
    style_header,
    style_header_conditional,
    table_caption_row,
    table_css,
)
from components.scouting_shell import clicked
from scoring.comparison import score_display
from scoring.role_scorer import (
    combo_column,
    combo_meta,
    group_abbr_tone,
    parse_combo_id,
    role_meta,
    score_band,
    to_int,
)
import services.player_profiles as profiles
import services.ui_settings as us

register_page(__name__, path="/profiles", name="Profiles")

VIEW_MODES = (
    ("roles", "Role scores"),
    ("percentiles", "Overall percentiles"),
)

PCT_COLS = ("overall", "defending", "final_third", "possession")
PCT_HEADERS = {
    "overall": "Ovr",
    "defending": "Def",
    "final_third": "Final third",
    "possession": "Possession",
}

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


def _focus_roles(value) -> list[str]:
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


def _role_table_columns(settings) -> list[dict]:
    settings = us.normalize(settings)
    cols = []
    for col in us.shortlist_columns_for("role_scores", settings):
        spec = {"name": identity_header_name(col), "id": col}
        if col in ("Feet", "Injury"):
            spec["presentation"] = "markdown"
        cols.append(spec)
    cols.append({"name": "Role", "id": "Role"})
    cols.append({"name": "Score", "id": "Score", "presentation": "markdown"})
    for pct in PCT_COLS:
        cols.append(
            {
                "name": PCT_HEADERS[pct],
                "id": pct,
                "presentation": "markdown",
            }
        )
    return cols


def _percentile_table_columns(settings) -> list[dict]:
    settings = us.normalize(settings)
    cols = []
    for col in us.shortlist_columns_for("player_stats", settings):
        spec = {"name": identity_header_name(col), "id": col}
        if col in ("Feet", "Injury"):
            spec["presentation"] = "markdown"
        cols.append(spec)
    cols.append({"name": "Mins", "id": "Minutes"})
    for pct in PCT_COLS:
        cols.append(
            {
                "name": PCT_HEADERS[pct],
                "id": pct,
                "presentation": "markdown",
            }
        )
    return cols


def _role_metric_styles() -> list[dict]:
    return [
        {
            "if": {"column_id": "Role"},
            "textAlign": "left",
            "fontWeight": "600",
            "minWidth": "72px",
            "maxWidth": "120px",
            "whiteSpace": "normal",
            "lineHeight": "1.2",
        },
        {
            "if": {"column_id": "Score"},
            "textAlign": "center",
            "minWidth": "64px",
            "width": "72px",
            "maxWidth": "80px",
            "fontVariantNumeric": "tabular-nums",
        },
        *[
            {
                "if": {"column_id": col},
                "textAlign": "center",
                "minWidth": "64px",
                "width": "72px",
                "maxWidth": "80px",
                "fontVariantNumeric": "tabular-nums",
            }
            for col in PCT_COLS
        ],
    ]


def _pct_metric_styles() -> list[dict]:
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
                "if": {"column_id": col},
                "textAlign": "center",
                "minWidth": "64px",
                "width": "72px",
                "maxWidth": "80px",
                "fontVariantNumeric": "tabular-nums",
            }
            for col in PCT_COLS
        ],
    ]


def _role_table_styles(theme) -> tuple[list, list]:
    data = identity_data_styles(theme, extra=_role_metric_styles())
    header = style_header_conditional(
        extra=[
            {"if": {"column_id": "Role"}, "textAlign": "left"},
            {"if": {"column_id": "Score"}, "textAlign": "center", "fontWeight": "700"},
            *[{"if": {"column_id": col}, "textAlign": "center"} for col in PCT_COLS],
        ]
    )
    return data, header


def _pct_table_styles(theme) -> tuple[list, list]:
    data = identity_data_styles(theme, extra=_pct_metric_styles())
    header = style_header_conditional(
        extra=[
            {"if": {"column_id": "Minutes"}, "textAlign": "center"},
            *[{"if": {"column_id": col}, "textAlign": "center"} for col in PCT_COLS],
        ]
    )
    return data, header


def _build_role_table_rows(settings=None, theme=None) -> tuple[list[dict], list[dict]]:
    settings = us.normalize(settings)
    identity = us.shortlist_columns_for("role_scores", settings)
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
        overall_raw = raw.get("overall")
        try:
            overall_f = (
                float(overall_raw)
                if overall_raw not in (None, "", "-", "—")
                else None
            )
        except (TypeError, ValueError):
            overall_f = None
        item: dict = {
            "id": entry.get("id") or "",
            "_key": entry.get("id") or "",
            "_role_column": role_column,
            "_score_raw": score_f,
            "_overall_raw": overall_f,
        }
        for col in identity:
            if col == "Feet":
                item[col] = feet_cell(raw)
            elif col == "Injury":
                item[col] = injury_cell(raw.get("Injury"))
            else:
                item[col] = _blank(raw.get(col))
        item["Role"] = _blank(raw.get("Role"))
        item["Score"] = _score_markdown(score_raw, settings, theme=theme)
        for pct in PCT_COLS:
            item[pct] = _pct_markdown(raw.get(pct), raw.get(f"{pct}_color"))
        rows.append(item)
        tips.append(injury_tooltip_entry(raw.get("Injury")))
    return rows, tips


def _sort_role_rows(rows: list[dict]) -> list[dict]:
    """Role ascending, then Score descending, then overall percentile descending."""

    def key(row: dict):
        role = str(row.get("_role_column") or row.get("Role") or "").casefold()
        score = row.get("_score_raw")
        overall = row.get("_overall_raw")
        score_sort = -float(score) if score is not None else float("inf")
        overall_sort = -float(overall) if overall is not None else float("inf")
        return (role, score_sort, overall_sort)

    return sorted(rows, key=key)


def _build_percentile_table_rows(settings=None) -> tuple[list[dict], list[dict]]:
    settings = us.normalize(settings)
    identity = us.shortlist_columns_for("player_stats", settings)
    rows = []
    tips = []
    for entry in profiles.list_percentile_profiles():
        raw = dict(entry.get("row") or {})
        item: dict = {"id": entry.get("id") or "", "_key": entry.get("id") or ""}
        for col in identity:
            if col == "Feet":
                item[col] = feet_cell(raw)
            elif col == "Injury":
                item[col] = injury_cell(raw.get("Injury"))
            else:
                item[col] = _blank(raw.get(col))
        mins = raw.get("Minutes")
        if mins in (None, ""):
            item["Minutes"] = "—"
        else:
            try:
                item["Minutes"] = f"{int(float(mins)):,}"
            except (TypeError, ValueError):
                item["Minutes"] = _blank(mins)
        for pct in PCT_COLS:
            item[pct] = _pct_markdown(raw.get(pct), raw.get(f"{pct}_color"))
        rows.append(item)
        tips.append(injury_tooltip_entry(raw.get("Injury")))
    return rows, tips


def _filter_role_rows(
    rows: list[dict],
    *,
    focus_roles,
    query: str,
    max_age,
    min_score: float,
    hybrids_only: bool,
) -> list[dict]:
    focused = _focus_roles(focus_roles)
    query = (query or "").strip().lower()
    try:
        max_age_i = 99 if max_age is None else int(max_age)
    except (TypeError, ValueError):
        max_age_i = 99
    out = []
    for row in rows:
        role_col = str(row.get("_role_column") or row.get("Role") or "").strip()
        if focused and role_col not in focused:
            continue
        if hybrids_only and "+" not in role_col:
            continue
        if max_age_i < 99 and to_int(row.get("Age")) > max_age_i:
            continue
        score_raw = row.get("_score_raw")
        if min_score > 0:
            try:
                score_f = float(score_raw) if score_raw is not None else 0.0
            except (TypeError, ValueError):
                score_f = 0.0
            if score_f < min_score:
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


def _filter_pct_rows(rows: list[dict], *, query: str, max_age) -> list[dict]:
    query = (query or "").strip().lower()
    try:
        max_age_i = 99 if max_age is None else int(max_age)
    except (TypeError, ValueError):
        max_age_i = 99
    out = []
    for row in rows:
        if max_age_i < 99 and to_int(row.get("Age")) > max_age_i:
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


def layout(**_kwargs):
    profiles.ensure_dirs()
    settings = us.load()
    return dbc.Container(
        [
            dcc.Store(id="pf-rev", data=0),
            dcc.Store(id="pf-view-mode", data="roles"),
            dcc.Store(id="pf-focus-role", data=[]),
            dcc.Store(id="pf-player-key", data=None),
            player_modal(prefix="pf"),
            html.H1("Profiles", className="mt-2 mb-3"),
            html.P(
                "Saved shortlist rows from Role scores (one row per evaluated role, "
                "with overall percentiles when the source file has stats) and from "
                "Player stats. Click a name for the Role scores player modal.",
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
                                                    html.Div(
                                                        [
                                                            html.Span(
                                                                "Squad depth",
                                                                className="rs-depth-heading-label",
                                                            ),
                                                            html.Span(
                                                                "Click cards to focus the table on one or more roles. "
                                                                "Click again to remove a role; clear all to show every role.",
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
                                                            html.Label(
                                                                "Search",
                                                                className="rs-field-label",
                                                            ),
                                                            dmc.TextInput(
                                                                id="pf-search",
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
                                                                id="pf-age",
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
                                                            html.Label(
                                                                "Min score",
                                                                className="rs-field-label",
                                                            ),
                                                            dmc.NumberInput(
                                                                id="pf-min-score",
                                                                placeholder="Any",
                                                                min=0,
                                                                max=20,
                                                                step=0.1,
                                                                decimalScale=1,
                                                                value=settings["bands"]["ok"],
                                                            ),
                                                        ],
                                                        className="rs-filter-score",
                                                    ),
                                                    dmc.Switch(
                                                        id="pf-hybrids-only",
                                                        label="Show only hybrid roles",
                                                        checked=False,
                                                        className="rs-filter-hybrids",
                                                    ),
                                                ],
                                                className="rs-shortlist-filters-row",
                                            ),
                                        ],
                                        className="rs-shortlist-filters mb-2",
                                    ),
                                ],
                                id="pf-role-filters",
                                hidden=False,
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
                                        style_cell_props=style_cell(text_align="right"),
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
                            table_caption_row(
                                prefix="pf",
                                clear_button_id="pf-delete-selected",
                                clear_label="Delete selected",
                                settings=settings,
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
    Output("pf-view-mode", "data"),
    Input("pf-view-toggle", "value"),
)
def set_view_mode(mode):
    return mode or "roles"


@callback(
    Output("pf-role-filters", "hidden"),
    Output("pf-pct-filters", "hidden"),
    Input("pf-view-mode", "data"),
)
def toggle_filter_panels(view_mode):
    roles = (view_mode or "roles") == "roles"
    return not roles, roles


@callback(
    Output("pf-age", "data"),
    Output("pf-age", "value", allow_duplicate=True),
    Output("pf-pct-age", "data"),
    Output("pf-pct-age", "value", allow_duplicate=True),
    Output("pf-band-legend", "children"),
    Input("ui-settings", "data"),
    State("pf-age", "value"),
    State("pf-pct-age", "value"),
    prevent_initial_call="initial_duplicate",
)
def sync_age_options(settings, age, pct_age):
    settings = us.normalize(settings)
    ages = us.age_options(settings)
    return (
        ages,
        us.clamp_choice(age, ages, "99"),
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
    if column in selected:
        return [item for item in selected if item != column]
    return selected + [column]


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
    Output("pf-table-caption", "children"),
    Output("pf-table-empty", "children"),
    Output("pf-table-empty", "hidden"),
    Output("pf-table-shell", "hidden"),
    Output("pf-delete-selected", "disabled"),
    Output("pf-summary", "children"),
    Output("pf-depth-wrap", "hidden"),
    Input("pf-view-mode", "data"),
    Input("pf-rev", "data"),
    Input("pf-focus-role", "data"),
    Input("pf-search", "value"),
    Input("pf-age", "value"),
    Input("pf-min-score", "value"),
    Input("pf-hybrids-only", "checked"),
    Input("pf-pct-search", "value"),
    Input("pf-pct-age", "value"),
    Input("pf-page-size", "value"),
    Input("ui-settings", "data"),
    Input("theme", "data"),
)
def refresh_profiles_table(
    view_mode,
    _rev,
    focus_role,
    search,
    age,
    min_score,
    hybrids_only,
    pct_search,
    pct_age,
    page_size,
    settings,
    theme,
):
    settings = us.normalize(settings)
    mode = view_mode or "roles"
    try:
        page_size_i = int(page_size or default_page_size_value(settings))
    except (TypeError, ValueError):
        page_size_i = us.page_size(settings)
    min_score_f = us.parse_score_floor(min_score)

    if mode == "percentiles":
        columns = _percentile_table_columns(settings)
        all_rows, tips = _build_percentile_table_rows(settings)
        filtered = _filter_pct_rows(all_rows, query=pct_search, max_age=pct_age)
        style_data, style_header = _pct_table_styles(theme)
        empty_msg = "No percentile profiles yet. Mark players on Player stats and save."
        depth_cards = []
        depth_hidden = True
    else:
        columns = _role_table_columns(settings)
        all_rows, tips = _build_role_table_rows(settings, theme=theme)
        filtered = _sort_role_rows(
            _filter_role_rows(
                all_rows,
                focus_roles=focus_role,
                query=search,
                max_age=age,
                min_score=min_score_f,
                hybrids_only=bool(hybrids_only),
            )
        )
        style_data, style_header = _role_table_styles(theme)
        empty_msg = (
            "No role profiles yet. Mark players on Role scores and save — "
            "one row per evaluated role, including overall percentiles when available."
        )
        entries = profiles.list_role_profiles()
        depth_cards = _profile_depth_panel(
            entries,
            focus_role,
            hybrids_only=bool(hybrids_only),
            settings=settings,
        )
        depth_hidden = not depth_cards

    display_rows = [_strip_internal(row) for row in filtered]
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
            caption,
            html.Div(empty_msg, className="text-muted small"),
            False,
            True,
            True,
            depth_cards,
            depth_hidden,
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
            caption,
            html.Div(
                "No profiles match the current filters.",
                className="text-muted small",
            ),
            False,
            True,
            True,
            depth_cards,
            depth_hidden,
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
        caption,
        None,
        True,
        False,
        True,
        depth_cards,
        depth_hidden,
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
    Output("pf-player-modal", "is_open"),
    Output("pf-player-modal-title", "children"),
    Output("pf-player-modal-body", "children"),
    Output("pf-player-key", "data"),
    Input("pf-table", "active_cell"),
    Input("pf-player-modal", "is_open"),
    Input("pf-player-modal-close", "n_clicks"),
    State("pf-table", "derived_viewport_data"),
    State("pf-player-modal", "is_open"),
    State("ui-settings", "data"),
    prevent_initial_call=True,
)
def open_profile_modal(
    active_cell,
    _modal_toggle,
    _close_clicks,
    viewport,
    is_open,
    settings,
):
    triggered = ctx.triggered_id
    if triggered == "pf-player-modal":
        if not is_open:
            return False, no_update, no_update, None
        return no_update, no_update, no_update, no_update
    if triggered == "pf-player-modal-close":
        return False, no_update, no_update, None
    if not active_cell or active_cell.get("column_id") != "Name":
        return no_update, no_update, no_update, no_update
    row_idx = active_cell.get("row")
    if not isinstance(viewport, list) or row_idx is None:
        return no_update, no_update, no_update, no_update
    try:
        row_idx = int(row_idx)
    except (TypeError, ValueError):
        return no_update, no_update, no_update, no_update
    if row_idx < 0 or row_idx >= len(viewport):
        return no_update, no_update, no_update, no_update
    row = viewport[row_idx] or {}
    profile_id = str(row.get("id") or row.get("_key") or "").strip()
    profile = profiles.get_profile(profile_id) if profile_id else None
    if not profile:
        return (
            True,
            str(row.get("Name") or "Player"),
            html.Div("Profile not found.", className="rs-player-missing"),
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
        )
    return (
        True,
        title,
        role_player_detail_card(player, settings),
        profile_id,
    )
