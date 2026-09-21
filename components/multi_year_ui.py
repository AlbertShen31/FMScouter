"""Shared multi-year status pills and modal year breakdown."""
from __future__ import annotations

from typing import Any

from dash import html

from scoring.multi_year import YEAR_KEYS, status_label
from scoring.stats_scorer import metric_defs


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
        ip_abbr = oop_abbr = ""
        try:
            from scoring.role_scorer import column_display_abbr

            if ip_col:
                ip_abbr = column_display_abbr(ip_col)
            if oop_col:
                oop_abbr = column_display_abbr(oop_col)
        except Exception:
            pass
        # Year maps often store short codes (CHM) while combo columns use
        # position-prefixed ids (AM-CHM) — try both plus role-ref keys.
        ip = _lookup_map_score(scores, ip_col, meta.get("ip"), ip_abbr)
        oop = _lookup_map_score(scores, oop_col, meta.get("oop"), oop_abbr)
        if ip is None and oop is None:
            return None
        total = float(ip_weight) + float(oop_weight)
        if total <= 0:
            total = 1.0
        return (float(ip_weight) * (ip or 0.0) + float(oop_weight) * (oop or 0.0)) / total
    val = _lookup_map_score(scores, column)
    if val is not None:
        return val
    try:
        from scoring.role_scorer import column_display_abbr

        return _lookup_map_score(scores, column_display_abbr(column))
    except Exception:
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
    """Earliest → current year scores with one overall delta (hybrid-aware)."""
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

    year_bits: list[tuple[str, float]] = []
    for year in keys:
        score = _pick(by_year.get(year) or {})
        if score is not None:
            year_bits.append((year, score))
    if len(year_bits) < 2:
        return None

    earliest_year, earliest = year_bits[0]
    current_year, current = year_bits[-1]
    delta = current - earliest
    parts: list = [
        html.Span(f"Y{earliest_year} {_fmt_num(earliest, digits=1)}"),
        html.Span(" → ", className="text-muted"),
        html.Span(f"Y{current_year} {_fmt_num(current, digits=1)}"),
    ]
    if abs(delta) >= 0.05:
        cls = "my-role-delta-up" if delta >= 0 else "my-role-delta-down"
        sign = "+" if delta >= 0 else ""
        parts.append(html.Span(" "))
        parts.append(
            html.Span(f"({sign}{_fmt_num(delta, digits=1)})", className=cls)
        )
    return html.Div(parts, className="my-role-growth")


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
    """Modal section showing original per-year stats and role growth."""
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
        # Prefer full growth across years once (below cards).
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

    growth_all = role_growth_row(
        player.get("role_scores_by_year"),
        combined=player.get("role_scores_combined"),
    )
    children = [
        html.Div(header_bits, className="d-flex align-items-center gap-2 mb-2"),
        html.Div(cards, className="my-year-grid"),
    ]
    if growth_all:
        children.append(
            html.Div(
                [
                    html.Div("Role score growth", className="rs-player-id-section-title mt-2"),
                    growth_all,
                ]
            )
        )
    # Combined vs per-year note for stats
    if player.get("stats"):
        children.append(
            html.Div(
                "Tables use the recency-weighted combined rates; cards above are each season’s originals.",
                className="text-muted small mt-2",
            )
        )
    return html.Div(children, className="my-year-section rs-player-id-section")
