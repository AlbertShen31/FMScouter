"""Squad vs scouting export merge helpers."""
from __future__ import annotations

import html as html_lib
from typing import Any, Callable

from dash import html

SOURCE_SQUAD = "squad"
SOURCE_SCOUTING = "scouting"

SOURCE_LABELS = {
    SOURCE_SQUAD: "Squad",
    SOURCE_SCOUTING: "Scouting",
}


def normalize_export_source(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if raw in {SOURCE_SCOUTING, "scout", "target", "targets", "transfer"}:
        return SOURCE_SCOUTING
    return SOURCE_SQUAD


def source_label(source: Any) -> str:
    return SOURCE_LABELS.get(normalize_export_source(source), SOURCE_LABELS[SOURCE_SQUAD])


def name_with_source_html(
    name: Any,
    source: Any = SOURCE_SQUAD,
    *,
    highlight: bool = False,
) -> str:
    """Player name cell; when ``highlight``, wrap with squad/scouting color class."""
    text = str(name or "").strip() or "—"
    if not highlight:
        return text
    kind = normalize_export_source(source)
    return f'<span class="src-name src-name-{kind}">{html_lib.escape(text)}</span>'


def export_source_legend(*, active: bool = True) -> html.Div | None:
    """Legend chips explaining Name-column colors. Empty when inactive."""
    if not active:
        return None
    chips = []
    for kind, note in (
        (SOURCE_SQUAD, "Club / international roster"),
        (SOURCE_SCOUTING, "Transfer targets"),
    ):
        chips.append(
            html.Span(
                [
                    html.Span(SOURCE_LABELS[kind], className="rs-legend-name"),
                    html.Span(note, className="rs-legend-op"),
                ],
                className=f"rs-legend-chip src-legend-chip {kind}",
            )
        )
    return html.Div(
        [
            html.Span("Name colors", className="rs-phase-legend-label"),
            html.Div(chips, className="rs-depth-legend"),
        ],
        className="rs-source-legend",
    )


def _tag_row(
    player: dict[str, Any],
    *,
    source: str,
    file_id: str = "",
) -> dict[str, Any]:
    row = dict(player)
    row["_export_source"] = source
    if file_id:
        row["_source_file_id"] = str(file_id).strip()
    elif "_source_file_id" not in row:
        row["_source_file_id"] = ""
    return row


def merge_squad_and_scouting(
    squad_players: list[dict[str, Any]] | None,
    scouting_players: list[dict[str, Any]] | None,
    *,
    key_fn: Callable[[dict[str, Any]], str] | None = None,
    squad_file_id: str = "",
    scouting_file_id: str = "",
) -> list[dict[str, Any]]:
    """Combine squad + scouting players; squad wins on identity-key duplicates.

    Each kept row is tagged with ``_export_source`` (``squad`` / ``scouting``)
    and ``_source_file_id`` when a file id is provided.
    """
    if key_fn is None:
        from scoring.role_scorer import player_row_key

        key_fn = player_row_key

    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for player in squad_players or []:
        if not isinstance(player, dict):
            continue
        tagged = _tag_row(player, source=SOURCE_SQUAD, file_id=squad_file_id)
        key = (key_fn(tagged) or "").strip()
        if key:
            if key in seen:
                continue
            seen.add(key)
        out.append(tagged)
    for player in scouting_players or []:
        if not isinstance(player, dict):
            continue
        tagged = _tag_row(player, source=SOURCE_SCOUTING, file_id=scouting_file_id)
        key = (key_fn(tagged) or "").strip()
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        out.append(tagged)
    return out


def has_scouting_rows(rows: list[dict[str, Any]] | None) -> bool:
    return any(
        normalize_export_source((r or {}).get("_export_source")) == SOURCE_SCOUTING
        for r in (rows or [])
    )
