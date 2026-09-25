"""Squad vs scouting export merge helpers."""
from __future__ import annotations

from typing import Any, Callable

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


def source_markdown(source: Any) -> str:
    """Markdown-friendly Source pill for Dash DataTable cells."""
    kind = normalize_export_source(source)
    label = SOURCE_LABELS[kind]
    return f'<span class="src-pill src-pill-{kind}">{label}</span>'


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
