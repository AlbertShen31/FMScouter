"""Shared multi-year status pills and modal year breakdown."""
from __future__ import annotations

from typing import Any

from dash import dcc, html
import plotly.graph_objects as go

from scoring.multi_year import YEAR_KEYS, status_label
from scoring.stats_scorer import metric_defs

_ROLE_GROWTH_CHART_CONFIG = {
    "displayModeBar": False,
    "displaylogo": False,
    "responsive": True,
    "scrollZoom": False,
    "doubleClick": False,
    "editable": False,
}


def status_pill(status: str | None) -> html.Span | str:
    if not status:
        return "—"
    label = status_label(status) or status
    return html.Span(label, className=f"my-status-pill {status}")


def status_markdown(status: str | None) -> str:
    """Markdown-friendly status for Dash DataTable cells."""
    if not status:
        return "—"
    label = status_label(status) or status
    return f'<span class="my-status-pill {status}">{label}</span>'


def _fmt_num(value: Any, *, digits: int = 2) -> str:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return "—"
    if abs(num - round(num)) < 1e-9:
        return str(int(round(num)))
    return f"{num:.{digits}f}"


def _safe_float(value: Any) -> float | None:
    if value is None or value == "" or value == "-":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _metric_label(metric_id: str) -> str:
    meta = metric_defs().get(metric_id) or {}
    return str(meta.get("abbr") or meta.get("label") or metric_id)


def _resolve_combo_meta(
    column: str | None,
    combo_meta: dict[str, str] | None = None,
) -> dict[str, str] | None:
    """Use caller meta, or resolve hybrid column names (formation / IP+OOP)."""
    if combo_meta:
        return combo_meta
    text = str(column or "").strip()
    if "+" not in text:
        return None
    try:
        from scoring.role_scorer import combo_meta_for_column

        return combo_meta_for_column(text)
    except Exception:
        return None


def _lookup_map_score(scores: dict[str, Any], *keys: Any) -> float | None:
    """First numeric hit among candidate keys (column ids, refs, short abbrs)."""
    seen: set[str] = set()
    for key in keys:
        text = str(key or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        val = _safe_float(scores.get(text))
        if val is not None:
            return val
    return None


def _role_part_lookup_keys(column: str | None, role_ref: str | None = None) -> list[str]:
    """Candidate map keys for one hybrid side (bucketed + plain + role-id forms)."""
    keys: list[str] = []
    col = str(column or "").strip()
    ref = str(role_ref or "").strip()
    if col:
        keys.append(col)
    if ref:
        keys.append(ref)
    try:
        from scoring.role_scorer import (
            column_display_abbr,
            decode_role_ref,
            parse_bucket_column,
            role_meta,
        )

        if col:
            _bucket, remainder = parse_bucket_column(col)
            if remainder and remainder != col:
                keys.append(remainder)
            abbr = column_display_abbr(col)
            # Prefer phase-bearing short ids (AM-IP) over bare codes (AM).
            if remainder:
                keys.append(remainder)
            if abbr:
                for suffix in ("-IP", "-OOP", "-GK"):
                    if col.endswith(suffix) or remainder.endswith(suffix):
                        keys.append(f"{abbr}{suffix}")
                        break
                keys.append(abbr)
        if ref:
            role_id, _group = decode_role_ref(ref)
            if role_id and role_id != ref:
                keys.append(role_id)
            try:
                plain_col = role_meta(role_id or ref)["column"]
            except Exception:
                plain_col = ""
            if plain_col:
                keys.append(plain_col)
                _b, rem = parse_bucket_column(plain_col)
                if rem and rem != plain_col:
                    keys.append(rem)
    except Exception:
        pass
    # Preserve order, drop empties / dupes.
    out: list[str] = []
    seen: set[str] = set()
    for key in keys:
        text = str(key or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def _score_from_map(
    scores: dict[str, Any] | None,
    column: str,
    *,
    combo_meta: dict[str, str] | None = None,
    ip_weight: float = 2.0,
    oop_weight: float = 1.0,
) -> float | None:
    """Pick a role/hybrid score from a year or combined score map."""
    scores = scores or {}
    meta = _resolve_combo_meta(column, combo_meta)
    if meta:
        ip_col = str(meta.get("ip_column") or "").strip()
        oop_col = str(meta.get("oop_column") or "").strip()
        # Year maps often store plain role columns (AM-IP) while formation
        # hybrids use bucket-prefixed ids (CM-AM-IP) — try both forms.
        ip = _lookup_map_score(scores, *_role_part_lookup_keys(ip_col, meta.get("ip")))
        oop = _lookup_map_score(scores, *_role_part_lookup_keys(oop_col, meta.get("oop")))
        if ip is None and oop is None:
            return None
        # Do not zero-fill a missing half — that collapses hybrids (e.g. OOP-only
        # → ~1/3 of the real score). Require both sides when either weight > 0.
        if ip is None or oop is None:
            return None
        total = float(ip_weight) + float(oop_weight)
        if total <= 0:
            total = 1.0
        return (float(ip_weight) * ip + float(oop_weight) * oop) / total
    val = _lookup_map_score(scores, *_role_part_lookup_keys(column))
    if val is not None:
        return val
    return None


def _year_score_bits(
    row: dict[str, Any] | None,
    column: str,
    *,
    by_year: dict[str, dict[str, float]] | None = None,
    combo_meta: dict[str, str] | None = None,
    ip_weight: float = 2.0,
    oop_weight: float = 1.0,
) -> list[tuple[str, float]]:
    """Collect (year, score) for years that have a value, oldest → newest."""
    row = row or {}
    by_year = by_year if by_year is not None else (row.get("role_scores_by_year") or {})
    meta = _resolve_combo_meta(column, combo_meta)
    bits: list[tuple[str, float]] = []
    if by_year:
        for year in ("1", "2", "3"):
            val = _score_from_map(
                by_year.get(year) or {},
                column,
                combo_meta=meta,
                ip_weight=ip_weight,
                oop_weight=oop_weight,
            )
            if val is None and not meta:
                val = _safe_float(row.get(f"{column} (Y{year})"))
            if val is not None:
                bits.append((year, val))
    else:
        for year in ("1", "2", "3"):
            val = _safe_float(row.get(f"{column} (Y{year})"))
            if val is not None:
                bits.append((year, val))
    return bits


def _role_display_label(column: str | None) -> str:
    """Short role label for modal growth headers (e.g. CF, CF+CM)."""
    text = str(column or "").strip()
    if not text:
        return ""
    try:
        from scoring.role_scorer import column_display_abbr

        if "+" in text:
            ip, _, oop = text.partition("+")
            return f"{column_display_abbr(ip)}+{column_display_abbr(oop)}"
        return column_display_abbr(text)
    except Exception:
        return text


def role_growth_row(
    role_scores_by_year: dict[str, dict[str, float]] | None,
    *,
    role_ref: str | None = None,
    column: str | None = None,
    combined: dict[str, float] | None = None,
    combo_meta: dict[str, str] | None = None,
    ip_weight: float = 2.0,
    oop_weight: float = 1.0,
) -> html.Div | None:
    """Per-year role scores with growth into the most recent year (Y3).

    Shows Y1 / Y2 / Y3 when present, plus Y2→Y3 and Y1→Y3 deltas (hybrid-aware).
    Year 3 is most recent; Year 1 is oldest.
    """
    by_year = role_scores_by_year or {}
    if not by_year:
        return None
    keys = [k for k in ("1", "2", "3") if k in by_year]
    if not keys:
        return None

    meta = _resolve_combo_meta(column, combo_meta)

    # Prefer a stable role key present across years.
    pick_key = role_ref or column
    if not pick_key and not meta:
        key_sets = [set((by_year.get(y) or {}).keys()) for y in keys]
        shared: set[str] = set.intersection(*key_sets) if key_sets else set()
        # Prefer short role-ref style keys over long column labels when both exist.
        if shared:
            pick_key = sorted(shared, key=len)[0]
        elif combined:
            pick_key = sorted(combined.keys(), key=len)[0]
        elif keys:
            first_scores = by_year.get(keys[0]) or {}
            if first_scores:
                pick_key = sorted(first_scores.keys(), key=len)[0]

    def _pick(scores: dict[str, float]) -> float | None:
        if meta or (pick_key and pick_key == column):
            return _score_from_map(
                scores,
                pick_key or column or "",
                combo_meta=meta,
                ip_weight=ip_weight,
                oop_weight=oop_weight,
            )
        if not scores:
            return None
        if pick_key and pick_key in scores:
            return _safe_float(scores[pick_key])
        for val in scores.values():
            num = _safe_float(val)
            if num is not None:
                return num
        return None

    score_by_year: dict[str, float] = {}
    for year in keys:
        score = _pick(by_year.get(year) or {})
        if score is not None:
            score_by_year[year] = score
    if len(score_by_year) < 2:
        return None

    # Oldest → newest score trail (include Y2 when present).
    ordered = [y for y in ("1", "2", "3") if y in score_by_year]
    score_parts: list = []
    for idx, year in enumerate(ordered):
        if idx:
            score_parts.append(html.Span(" · ", className="text-muted"))
        score_parts.append(
            html.Span(f"Y{year} {_fmt_num(score_by_year[year], digits=1)}")
        )

    def _delta_span(from_year: str, to_year: str) -> html.Span | None:
        if from_year not in score_by_year or to_year not in score_by_year:
            return None
        delta = score_by_year[to_year] - score_by_year[from_year]
        if abs(delta) < 0.05:
            return None
        cls = "my-role-delta-up" if delta >= 0 else "my-role-delta-down"
        sign = "+" if delta >= 0 else ""
        return html.Span(
            f"Y{from_year}→Y{to_year} {sign}{_fmt_num(delta, digits=1)}",
            className=cls,
        )

    # Growth into most recent year: Y2→Y3 and Y1→Y3 (labels match upload years).
    newest = ordered[-1]
    delta_parts: list = []
    for older in ("2", "1"):
        if older == newest:
            continue
        bit = _delta_span(older, newest)
        if bit is None:
            continue
        if delta_parts:
            delta_parts.append(html.Span(" · ", className="text-muted"))
        delta_parts.append(bit)

    children: list = [html.Div(score_parts, className="my-role-growth-scores")]
    if delta_parts:
        children.append(html.Div(delta_parts, className="my-role-growth-deltas"))
    return html.Div(children, className="my-role-growth")


def _year_scores_for_column(
    by_year: dict[str, dict[str, float]] | None,
    column: str,
    *,
    combo_meta: dict[str, str] | None = None,
    ip_weight: float = 2.0,
    oop_weight: float = 1.0,
) -> dict[str, float]:
    """Year → score for one role / hybrid column (skips missing years)."""
    by_year = by_year or {}
    meta = _resolve_combo_meta(column, combo_meta)
    out: dict[str, float] = {}
    for year in YEAR_KEYS:
        val = _score_from_map(
            by_year.get(year) or {},
            column,
            combo_meta=meta,
            ip_weight=ip_weight,
            oop_weight=oop_weight,
        )
        if val is not None:
            out[year] = val
    return out


def _growth_tone_colors(theme: str | None) -> dict[str, str]:
    dark = (theme or "dark") != "light"
    return {
        "ip": "#3dff88" if dark else "#15803d",
        "oop": "#f87171" if dark else "#b91c1c",
        "combo": "#c4b5fd" if dark else "#6d28d9",
        "role": "#38bdf8" if dark else "#0284c7",
        "font": "#e8eef6" if dark else "#0f172a",
        "muted": "#8b9bb0" if dark else "#64748b",
        "grid": "rgba(139, 155, 176, 0.22)" if dark else "rgba(100, 116, 139, 0.25)",
    }


def role_growth_figure(
    role_scores_by_year: dict[str, dict[str, float]] | None,
    *,
    column: str,
    combo_meta: dict[str, str] | None = None,
    ip_weight: float = 2.0,
    oop_weight: float = 1.0,
    theme: str | None = None,
) -> go.Figure | None:
    """Line chart of role score by year; hybrids add IP and OOP traces."""
    by_year = role_scores_by_year or {}
    if not by_year:
        return None
    col = str(column or "").strip()
    if not col:
        return None
    meta = _resolve_combo_meta(col, combo_meta)
    main = _year_scores_for_column(
        by_year,
        col,
        combo_meta=meta,
        ip_weight=ip_weight,
        oop_weight=oop_weight,
    )
    if len(main) < 2:
        return None

    colors = _growth_tone_colors(theme)
    dark = (theme or "dark") != "light"
    years = [y for y in YEAR_KEYS if y in main]
    labels = [f"Year {y}" for y in years]

    series: list[tuple[str, dict[str, float], str, dict]] = []
    main_label = _role_display_label(col) or "Role"
    main_color = colors["combo"] if meta else colors["role"]
    series.append(
        (
            main_label,
            main,
            main_color,
            dict(width=3),
        )
    )
    if meta:
        ip_col = str(meta.get("ip_column") or "").strip()
        oop_col = str(meta.get("oop_column") or "").strip()
        if ip_col:
            ip_scores = _year_scores_for_column(by_year, ip_col)
            if ip_scores:
                series.append(
                    (
                        f"{_role_display_label(ip_col) or 'IP'} (IP)",
                        ip_scores,
                        colors["ip"],
                        dict(width=2, dash="dot"),
                    )
                )
        if oop_col:
            oop_scores = _year_scores_for_column(by_year, oop_col)
            if oop_scores:
                series.append(
                    (
                        f"{_role_display_label(oop_col) or 'OOP'} (OOP)",
                        oop_scores,
                        colors["oop"],
                        dict(width=2, dash="dash"),
                    )
                )

    fig = go.Figure()
    all_vals: list[float] = []
    for name, scores, color, line in series:
        ys = [scores.get(y) for y in years]
        all_vals.extend(v for v in ys if v is not None)
        fig.add_trace(
            go.Scatter(
                x=labels,
                y=ys,
                name=name,
                mode="lines+markers",
                line=dict(color=color, **line),
                marker=dict(size=8, color=color),
                connectgaps=False,
                hovertemplate=f"{name}: %{{y:.1f}}<extra></extra>",
            )
        )

    y_min = min(all_vals) if all_vals else 0.0
    y_max = max(all_vals) if all_vals else 20.0
    pad = max(0.6, (y_max - y_min) * 0.15)
    fig.update_layout(
        template="plotly_dark" if dark else "plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=colors["font"], size=12),
        margin=dict(l=44, r=16, t=8, b=36),
        height=220,
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0,
            bgcolor="rgba(0,0,0,0)",
            font=dict(size=11, color=colors["muted"]),
        ),
        hovermode="x unified",
        dragmode=False,
        xaxis=dict(
            title=None,
            tickfont=dict(color=colors["muted"], size=11),
            gridcolor=colors["grid"],
            zeroline=False,
            fixedrange=True,
        ),
        yaxis=dict(
            title=None,
            range=[max(0.0, y_min - pad), y_max + pad],
            tickfont=dict(color=colors["muted"], size=11),
            gridcolor=colors["grid"],
            zeroline=False,
            fixedrange=True,
        ),
    )
    return fig


def role_growth_chart(
    role_scores_by_year: dict[str, dict[str, float]] | None,
    *,
    column: str,
    combo_meta: dict[str, str] | None = None,
    ip_weight: float = 2.0,
    oop_weight: float = 1.0,
    theme: str | None = None,
) -> dcc.Graph | None:
    """Dash graph wrapper for :func:`role_growth_figure`."""
    fig = role_growth_figure(
        role_scores_by_year,
        column=column,
        combo_meta=combo_meta,
        ip_weight=ip_weight,
        oop_weight=oop_weight,
        theme=theme,
    )
    if fig is None:
        return None
    return dcc.Graph(
        figure=fig,
        config=_ROLE_GROWTH_CHART_CONFIG,
        className="my-role-growth-chart",
    )


def role_growth_section(
    player: dict[str, Any],
    *,
    column: str | None = None,
    ip_weight: float = 2.0,
    oop_weight: float = 1.0,
    theme: str | None = None,
) -> html.Div | None:
    """Standalone modal section for role-score year growth (not inside By year)."""
    if not player.get("multi_year") and not player.get("role_scores_by_year"):
        return None
    col = str(column or "").strip()
    if not col:
        return None
    meta = _resolve_combo_meta(col)
    by_year = player.get("role_scores_by_year")
    growth = role_growth_row(
        by_year,
        column=col,
        combined=player.get("role_scores_combined"),
        combo_meta=meta,
        ip_weight=ip_weight,
        oop_weight=oop_weight,
    )
    chart = role_growth_chart(
        by_year,
        column=col,
        combo_meta=meta,
        ip_weight=ip_weight,
        oop_weight=oop_weight,
        theme=theme,
    )
    if growth is None and chart is None:
        return None
    label = _role_display_label(col)
    title_bits: list = [
        html.Span("Role score growth", className="rs-player-id-section-title"),
    ]
    if label:
        title_bits.append(html.Span(" · ", className="text-muted"))
        title_bits.append(html.Span(label, className="my-role-growth-role"))
    body: list = [
        html.Div(title_bits, className="d-flex align-items-center gap-1 mb-1"),
    ]
    if growth is not None:
        body.append(growth)
    if chart is not None:
        body.append(chart)
    return html.Div(body, className="my-role-growth-section rs-player-id-section")


def score_year_suffix_html(
    row: dict[str, Any],
    column: str,
    *,
    combo_meta: dict[str, str] | None = None,
    ip_weight: float = 2.0,
    oop_weight: float = 1.0,
) -> str:
    """Earliest→current role-score delta under a cell (historical-compare style)."""
    from scoring.comparison import delta_html

    meta = _resolve_combo_meta(column, combo_meta)
    year_bits = _year_score_bits(
        row,
        column,
        combo_meta=meta,
        ip_weight=ip_weight,
        oop_weight=oop_weight,
    )
    if len(year_bits) < 2:
        return ""

    earliest = year_bits[0][1]
    current = year_bits[-1][1]
    return delta_html(current - earliest, decimals=1, kind="score")


def score_year_delta_span(
    row: dict[str, Any],
    column: str,
    *,
    combo_meta: dict[str, str] | None = None,
    ip_weight: float = 2.0,
    oop_weight: float = 1.0,
) -> html.Span | None:
    """Dash span for earliest→current delta (Profiles depth chart / non-markdown)."""
    year_bits = _year_score_bits(
        row,
        column,
        combo_meta=_resolve_combo_meta(column, combo_meta),
        ip_weight=ip_weight,
        oop_weight=oop_weight,
    )
    if len(year_bits) < 2:
        return None
    delta = year_bits[-1][1] - year_bits[0][1]
    if abs(delta) < 0.05:
        return None
    tone = "up" if delta > 0 else "down"
    arrow = "↑" if delta > 0 else "↓"
    return html.Span(
        f"{arrow}{delta:+.1f}",
        className=f"cmp-delta cmp-delta-{tone} cmp-delta-block",
    )


_KEY_STAT_IDS = (
    "goals",
    "assists",
    "expected_goals",
    "expected_assists",
    "pass_completion",
    "passes_attempted",
    "tackles_attempted",
    "key_passes",
    "shots",
    "possession_won",
)


def by_year_section(player: dict[str, Any]) -> html.Div | None:
    """Modal section showing original per-year stats (no role-score growth)."""
    if not player.get("multi_year"):
        return None
    by_year = player.get("by_year") or {}
    if not isinstance(by_year, dict) or not by_year:
        return None

    status = player.get("multi_year_status")
    header_bits: list = [html.Span("By year", className="rs-player-id-section-title")]
    if status:
        header_bits.append(html.Span(" "))
        header_bits.append(status_pill(status))

    cards = []
    for year in YEAR_KEYS:
        snap = by_year.get(year)
        if not isinstance(snap, dict):
            continue
        stats = snap.get("stats") or {}
        meta_bits = []
        if snap.get("club"):
            meta_bits.append(str(snap["club"]))
        if snap.get("age") not in (None, "", "-"):
            meta_bits.append(f"Age {snap['age']}")
        mins = snap.get("minutes")
        if mins not in (None, "", "-"):
            meta_bits.append(f"{_fmt_num(mins, digits=0)} mins")
        stat_bits = []
        for mid in _KEY_STAT_IDS:
            if mid not in stats:
                continue
            stat_bits.append(f"{_metric_label(mid)} {_fmt_num(stats[mid])}")
        body = []
        if meta_bits:
            body.append(html.Div(" · ".join(meta_bits), className="my-year-meta"))
        if stat_bits:
            body.append(
                html.Div(
                    " · ".join(stat_bits[:8]),
                    className="my-year-meta",
                )
            )
        if not body:
            body.append(html.Div("No stats this year", className="my-year-meta"))
        cards.append(
            html.Div(
                [html.H4(f"Year {year}"), *body],
                className="my-year-card",
            )
        )

    children = [
        html.Div(header_bits, className="d-flex align-items-center gap-2 mb-2"),
        html.Div(cards, className="my-year-grid"),
    ]
    # Combined vs per-year note for stats
    if player.get("stats"):
        children.append(
            html.Div(
                "Tables use the recency-weighted combined rates; cards above are each season’s originals.",
                className="text-muted small mt-2",
            )
        )
    return html.Div(children, className="my-year-section rs-player-id-section")
