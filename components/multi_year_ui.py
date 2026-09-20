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
    if combo_meta:
        ip = _safe_float(scores.get(combo_meta.get("ip_column") or ""))
        if ip is None:
            ip = _safe_float(scores.get(combo_meta.get("ip") or ""))
        oop = _safe_float(scores.get(combo_meta.get("oop_column") or ""))
        if oop is None:
            oop = _safe_float(scores.get(combo_meta.get("oop") or ""))
        if ip is None and oop is None:
            return None
        total = float(ip_weight) + float(oop_weight)
        if total <= 0:
            total = 1.0
        return (float(ip_weight) * (ip or 0.0) + float(oop_weight) * (oop or 0.0)) / total
    val = _safe_float(scores.get(column))
    if val is not None:
        return val
    # Stamped cache columns as a last resort (single roles only).
    return None


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
    """Compact Y1 → Y2 → Y3 (+ Combined) for one role."""
    by_year = role_scores_by_year or {}
    if not by_year and not combined:
        return None
    keys = [k for k in ("1", "2", "3") if k in by_year]
    if not keys and not combined:
        return None

    # Prefer a stable role key present across years.
    pick_key = role_ref or column
    if not pick_key and not combo_meta:
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
        if combo_meta or (pick_key and pick_key == column):
            return _score_from_map(
                scores,
                pick_key or column or "",
                combo_meta=combo_meta,
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

    parts: list = []
    prev = None
    for year in keys:
        score = _pick(by_year.get(year) or {})
        if score is None:
            continue
        bit = f"Y{year} {_fmt_num(score, digits=1)}"
        if prev is not None:
            delta = score - prev
            cls = "my-role-delta-up" if delta >= 0 else "my-role-delta-down"
            sign = "+" if delta >= 0 else ""
            parts.append(
                html.Span(
                    [bit, " ", html.Span(f"({sign}{_fmt_num(delta, digits=1)})", className=cls)],
                )
            )
        else:
            parts.append(html.Span(bit))
        prev = score
        if year != keys[-1] and any(
            _pick(by_year.get(y) or {}) is not None for y in keys[keys.index(year) + 1 :]
        ):
            parts.append(html.Span(" → ", className="text-muted"))

    if combined is not None:
        cscore = _pick(combined) if not combo_meta else _score_from_map(
            combined,
            column or "",
            combo_meta=combo_meta,
            ip_weight=ip_weight,
            oop_weight=oop_weight,
        )
        if cscore is None and not combo_meta:
            cscore = _pick(combined)
        if cscore is not None:
            if parts:
                parts.append(html.Span(" · ", className="text-muted"))
            parts.append(html.Span(f"Combined {_fmt_num(cscore, digits=1)}"))

    if not parts:
        return None
    return html.Div(parts, className="my-role-growth")


def score_year_suffix_html(
    row: dict[str, Any],
    column: str,
    *,
    combo_meta: dict[str, str] | None = None,
    ip_weight: float = 2.0,
    oop_weight: float = 1.0,
) -> str:
    """Append Y1→Y2→Y3 growth (+ Combined) under a score cell (HTML string)."""
    by_year = row.get("role_scores_by_year") or {}
    combined = row.get("role_scores_combined") or {}

    year_bits: list[tuple[str, float]] = []
    if by_year:
        for year in ("1", "2", "3"):
            val = _score_from_map(
                by_year.get(year) or {},
                column,
                combo_meta=combo_meta,
                ip_weight=ip_weight,
                oop_weight=oop_weight,
            )
            if val is None and not combo_meta:
                stamped = row.get(f"{column} (Y{year})")
                val = _safe_float(stamped)
            if val is not None:
                year_bits.append((year, val))
    else:
        for year in ("1", "2", "3"):
            val = _safe_float(row.get(f"{column} (Y{year})"))
            if val is not None:
                year_bits.append((year, val))

    cval = _score_from_map(
        combined,
        column,
        combo_meta=combo_meta,
        ip_weight=ip_weight,
        oop_weight=oop_weight,
    )
    if cval is None and not combo_meta:
        cval = _safe_float(row.get(f"{column} (Combined)"))

    # Single-year presence with matching Combined is just noise under the cell.
    if len(year_bits) <= 1:
        if cval is None:
            return ""
        if year_bits and abs(year_bits[0][1] - cval) < 0.05:
            return ""

    if not year_bits and cval is None:
        return ""

    parts: list[str] = []
    prev: float | None = None
    for i, (year, score) in enumerate(year_bits):
        bit = f"Y{year} {_fmt_num(score, digits=1)}"
        if prev is not None:
            delta = score - prev
            if abs(delta) >= 0.05:
                cls = "my-role-delta-up" if delta >= 0 else "my-role-delta-down"
                sign = "+" if delta >= 0 else ""
                bit += (
                    f' <span class="{cls}">'
                    f"({sign}{_fmt_num(delta, digits=1)})</span>"
                )
        parts.append(bit)
        prev = score
        if i < len(year_bits) - 1:
            parts.append('<span class="text-muted"> → </span>')

    if cval is not None:
        # Skip Combined when it matches the newest year score.
        newest = year_bits[-1][1] if year_bits else None
        if newest is None or abs(newest - cval) >= 0.05:
            if parts:
                parts.append('<span class="text-muted"> · </span>')
            parts.append(f"C {_fmt_num(cval, digits=1)}")

    if not parts:
        return ""
    return (
        '<span class="my-role-growth text-muted">'
        + "".join(parts)
        + "</span>"
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
