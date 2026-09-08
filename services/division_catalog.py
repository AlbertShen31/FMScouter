"""Division catalog for settings pickers: nations, tiers, and library exports."""
from __future__ import annotations

from collections import defaultdict

from scoring.division_tiers import (
    ROMANIA_NATION,
    TIER_LABELS,
    classify_division,
    division_sort_key,
    is_romanian_division,
    romanian_division_names,
)


def _division_nation_catalog() -> dict[str, str]:
    """Best-effort division → nation map from tier tables."""
    from scoring.division_tiers import _EXACT, _NATION_EXACT

    out: dict[str, str] = {}
    for nation, divisions in _NATION_EXACT.items():
        for division in divisions:
            out[division] = nation
    for division in _EXACT:
        if division in ("Liga I", "Liga II", "Liga V"):
            out.setdefault(division, ROMANIA_NATION)
    for division in romanian_division_names():
        out.setdefault(division, ROMANIA_NATION)
    return out


def divisions_from_library() -> dict[str, str]:
    """Division → nation from cached stats exports in the upload library."""
    out: dict[str, str] = {}
    try:
        import services.export_library as lib
        from services.upload_cache import load_cache
    except ImportError:
        return out

    for entry in lib.list_files():
        if not entry.get("stats"):
            continue
        file_id = str(entry.get("id") or "").strip()
        if not file_id:
            continue
        cache = load_cache(file_id)
        stats = (cache or {}).get("stats") if isinstance(cache, dict) else None
        players = (stats or {}).get("players") if isinstance(stats, dict) else None
        if not isinstance(players, list):
            continue
        for player in players:
            division = str(player.get("division") or "").strip()
            if not division or division in ("-", "—"):
                continue
            nation = str(player.get("nation") or "").strip()
            if nation:
                out[division] = nation
            else:
                out.setdefault(division, "")
    return out


def collect_division_nations(
    *,
    selected: list[str] | None = None,
    include_library: bool = True,
) -> dict[str, str]:
    """Merge catalog + library divisions; ensure saved selections stay visible."""
    pairs = _division_nation_catalog()
    if include_library:
        for division, nation in divisions_from_library().items():
            if nation:
                pairs[division] = nation
            else:
                pairs.setdefault(division, "")
    for division in selected or []:
        name = str(division or "").strip()
        if name:
            pairs.setdefault(name, "")
    for division, nation in list(pairs.items()):
        if not nation and is_romanian_division(division):
            pairs[division] = ROMANIA_NATION
    return pairs


def divisions_for_nation(
    nation: str,
    *,
    selected: list[str] | None = None,
    include_library: bool = True,
) -> list[str]:
    """All known divisions for one nation, highest tier first."""
    target = str(nation or "").strip()
    if not target:
        return []
    pairs = collect_division_nations(selected=selected, include_library=include_library)
    names = [div for div, nat in pairs.items() if nat == target]
    return sorted(names, key=lambda div: division_sort_key(div, target))


def full_detail_division_options(
    selected: list[str] | None = None,
    *,
    include_library: bool = True,
) -> list[dict[str, object]]:
    """Grouped MultiSelect options for dmc: [{group, items: [{value, label}]}]."""
    pairs = collect_division_nations(selected=selected, include_library=include_library)
    by_nation: dict[str, list[str]] = defaultdict(list)
    for division, nation in pairs.items():
        nation_label = nation or "Other / unknown nation"
        by_nation[nation_label].append(division)

    options: list[dict[str, object]] = []
    for nation in sorted(by_nation.keys(), key=str.casefold):
        divisions = sorted(
            by_nation[nation],
            key=lambda div: division_sort_key(
                div, nation if nation != "Other / unknown nation" else None
            ),
        )
        items: list[dict[str, str]] = []
        for division in divisions:
            tier = classify_division(
                division,
                nation if nation != "Other / unknown nation" else None,
            )
            tier_label = TIER_LABELS.get(tier, "")
            label = f"{division} — {tier_label}" if tier_label else division
            items.append({"value": division, "label": label})
        if items:
            options.append({"group": nation, "items": items})
    return options


def division_values_from_options(options: list[dict] | None) -> list[str]:
    """Flatten grouped or flat MultiSelect data to division value strings."""
    values: list[str] = []
    seen: set[str] = set()
    for entry in options or []:
        if not isinstance(entry, dict):
            continue
        if "items" in entry:
            for item in entry.get("items") or []:
                if isinstance(item, str):
                    value = item.strip()
                elif isinstance(item, dict):
                    value = str(item.get("value") or "").strip()
                else:
                    value = ""
                if value and value not in seen:
                    seen.add(value)
                    values.append(value)
            continue
        value = str(entry.get("value") or "").strip()
        if value and value not in seen:
            seen.add(value)
            values.append(value)
    return values


def default_full_detail_divisions() -> list[str]:
    """Default Full Detail list: all known Romanian leagues."""
    return romanian_division_names()
