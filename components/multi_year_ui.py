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


def _metric_label(metric_id: str) -> str:
    meta = metric_defs().get(metric_id) or {}
    return str(meta.get("abbr") or meta.get("label") or metric_id)


def role_growth_row(
    role_scores_by_year: dict[str, dict[str, float]] | None,
    *,
    role_ref: str | None = None,
    column: str | None = None,
    combined: dict[str, float] | None = None,
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
    if not pick_key:
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
        if not scores:
            return None
        if pick_key and pick_key in scores:
            try:
                return float(scores[pick_key])
            except (TypeError, ValueError):
                return None
        for val in scores.values():
            try:
                return float(val)
            except (TypeError, ValueError):
                continue
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

    if combined:
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
) -> str:
    """Append Y1/Y2/Y3/Combined hints to a score cell (HTML string)."""
    by_year = row.get("role_scores_by_year") or {}
    combined = row.get("role_scores_combined") or {}
    if not by_year and not combined:
        # Fall back to stamped column keys from cache.
        bits = []
        for year in ("1", "2", "3"):
            val = row.get(f"{column} (Y{year})")
            if val is not None and val != "-":
                bits.append(f"Y{year} {val}")
        cval = row.get(f"{column} (Combined)")
        if cval is not None and cval != "-":
            bits.append(f"C {cval}")
        if not bits:
            return ""
        return (
            '<div class="my-role-growth text-muted" style="font-size:0.7rem">'
            + " · ".join(bits)
            + "</div>"
        )

    bits = []
    for year in ("1", "2", "3"):
        scores = by_year.get(year) or {}
        val = scores.get(column)
        if val is None:
            continue
        bits.append(f"Y{year} {_fmt_num(val, digits=1)}")
    # combined may be keyed by role_ref; try column too
    cval = combined.get(column)
    if cval is None:
        for val in combined.values():
            cval = val
            break
    if cval is not None:
        bits.append(f"C {_fmt_num(cval, digits=1)}")
    if not bits:
        return ""
    return (
        '<div class="my-role-growth text-muted" style="font-size:0.7rem">'
        + " · ".join(bits)
        + "</div>"
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
        growth = role_growth_row(
            {year: snap.get("role_scores") or {}}
            if snap.get("role_scores")
            else None,
        )
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
