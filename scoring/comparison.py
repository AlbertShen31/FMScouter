"""Current vs historical export comparison helpers."""
from __future__ import annotations

import math
import re
from typing import Any, Callable

from dash import html

_STRIP_TAG = re.compile(r"<[^>]+>")


def players_lookup(
    players: list[dict[str, Any]], key_fn: Callable[[dict[str, Any]], str]
) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for player in players or []:
        key = (key_fn(player) or "").strip()
        if key:
            out[key] = player
    return out


def strip_cell_text(value: Any) -> str:
    text = "" if value is None else str(value)
    if "<" in text:
        text = _STRIP_TAG.sub("", text)
    return text.strip()


def cell_number(value: Any) -> float | None:
    text = strip_cell_text(value).replace("%", "").replace(",", "").replace(" ", "")
    if not text or text in {"-", "—"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def delta_html(
    delta: float | None,
    *,
    decimals: int = 1,
    suffix: str = "",
    percent: bool = False,
    min_abs: float = 0.05,
    kind: str = "score",
    stacked: bool = True,
) -> str:
    """Delta with ↑/↓ and green/red styling (for markdown HTML cells).

    ``kind`` is ``score`` (up=green) or ``wage`` (up=red, for cost increases).
    When ``stacked`` is true, returns a block-level span for a second line.
    """
    if delta is None or math.isnan(float(delta)):
        return ""
    amount = float(delta)
    if abs(amount) < min_abs:
        return ""
    arrow = "↑" if amount > 0 else "↓"
    if kind == "wage":
        tone = "wage-up" if amount > 0 else "wage-down"
    else:
        tone = "up" if amount > 0 else "down"
    if percent:
        body = f"{amount:+.0f}%"
    elif decimals <= 0:
        body = f"{amount:+,.0f}{suffix}"
    else:
        body = f"{amount:+.{decimals}f}{suffix}"
    block = " cmp-delta-block" if stacked else ""
    return f'<span class="cmp-delta cmp-delta-{tone}{block}">{arrow}{body}</span>'


def wrap_cell_with_delta(value_html: str, delta: str) -> str:
    """Stack the main value and delta vertically inside narrow table cells."""
    if not delta:
        return value_html
    return (
        f'<span class="cmp-cell">'
        f'<span class="cmp-cell-val">{value_html}</span>{delta}</span>'
    )


def append_delta_html(
    display: str,
    current: Any,
    historical: Any,
    *,
    enabled: bool,
    decimals: int = 1,
    suffix: str = "",
    percent: bool = False,
) -> str:
    if not enabled:
        return display
    cur = cell_number(current) if not isinstance(current, (int, float)) else float(current)
    hist = (
        cell_number(historical)
        if historical is not None and not isinstance(historical, (int, float))
        else (float(historical) if historical is not None else None)
    )
    if cur is None or hist is None:
        return display
    return display + delta_html(cur - hist, decimals=decimals, suffix=suffix, percent=percent)


def score_display(
    value: Any,
    historical: Any = None,
    *,
    enabled: bool = False,
    color: str | None = None,
) -> str:
    if value is None or value in {"-", "—", ""}:
        return "-"
    try:
        current = float(value)
    except (TypeError, ValueError):
        return str(value)
    text = f"{current:.1f}"
    style = "font-weight:750;font-variant-numeric:tabular-nums;font-size:1.08em"
    if color:
        style = f"color:{color};{style}"
    val_html = f'<span class="rs-score-val" style="{style}">{text}</span>'
    if not enabled or historical is None:
        return f'<span class="rs-score-cell">{val_html}</span>'
    try:
        prior = float(historical)
    except (TypeError, ValueError):
        return f'<span class="rs-score-cell">{val_html}</span>'
    delta = delta_html(current - prior, decimals=1, kind="score")
    inner = wrap_cell_with_delta(val_html, delta)
    return f'<span class="rs-score-cell">{inner}</span>'


def money_delta_span(delta: float | None, *, enabled: bool) -> html.Span | None:
    if not enabled or delta is None or abs(float(delta)) < 0.5:
        return None
    amount = float(delta)
    arrow = "↑" if amount > 0 else "↓"
    from scoring.squad_finance import format_money

    body = format_money(abs(amount))
    sign = "+" if amount > 0 else "−"
    tone = "wage-up" if amount > 0 else "wage-down"
    return html.Span(
        f" ({arrow}{sign}{body})",
        className=f"cmp-delta cmp-delta-{tone}",
    )
