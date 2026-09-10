"""Division catalog for settings pickers: nations, tiers, and library exports."""
from __future__ import annotations

from collections import Counter, defaultdict

from scoring.division_tiers import (
    ROMANIA_NATION,
    TIER_LABELS,
    _fold,
    classify_division,
    collapse_picker_divisions,
    division_sort_key,
    is_romanian_division,
    picker_canonical_division,
    romanian_division_names,
)

# FM nationality codes and common aliases → canonical Based In labels.
_NATION_ALIASES: dict[str, str] = {
    "rou": ROMANIA_NATION,
    "rom": ROMANIA_NATION,
    "romania": ROMANIA_NATION,
    "eng": "England",
    "england": "England",
    "esp": "Spain",
    "spain": "Spain",
    "fra": "France",
    "france": "France",
    "ita": "Italy",
    "italy": "Italy",
    "ger": "Germany",
    "germany": "Germany",
    "por": "Portugal",
    "portugal": "Portugal",
    "mda": "Moldova",
    "moldova": "Moldova",
    "isr": "Israel",
    "israel": "Israel",
    "bel": "Belgium",
    "belgium": "Belgium",
    "srb": "Serbia",
    "serbia": "Serbia",
    "swe": "Sweden",
    "sweden": "Sweden",
    "aut": "Austria",
    "austria": "Austria",
    "irl": "Ireland",
    "ireland": "Ireland",
    "kos": "Kosovo",
    "kosovo": "Kosovo",
    "jor": "Jordan",
    "jordan": "Jordan",
    "usa": "U.S.A.",
    "u.s.a.": "U.S.A.",
    "united states": "U.S.A.",
    "uae": "U.A.E.",
    "u.a.e.": "U.A.E.",
    "kuwait": "Kuwait",
    "nep": "Nepal",
    "nepal": "Nepal",
    "nor": "Norway",
    "norway": "Norway",
    "sui": "Switzerland",
    "switzerland": "Switzerland",
    "gre": "Greece",
    "greece": "Greece",
    "bvi": "British Virgin Is.",
    "british virgin is.": "British Virgin Is.",
    "mya": "Myanmar",
    "myanmar": "Myanmar",
    "svn": "Slovenia",
    "slovenia": "Slovenia",
    "tur": "Türkiye",
    "turkiye": "Türkiye",
    "türkiye": "Türkiye",
    "pol": "Poland",
    "poland": "Poland",
    "chn": "China",
    "china": "China",
    "bul": "Bulgaria",
    "bulgaria": "Bulgaria",
    "hun": "Hungary",
    "hungary": "Hungary",
    "cro": "Croatia",
    "croatia": "Croatia",
    "sco": "Scotland",
    "scotland": "Scotland",
    "wal": "Wales",
    "wales": "Wales",
    "nir": "Northern Ireland",
    "northern ireland": "Northern Ireland",
    "alb": "Albania",
    "albania": "Albania",
    "arm": "Armenia",
    "armenia": "Armenia",
    "aze": "Azerbaijan",
    "azerbaijan": "Azerbaijan",
    "aus": "Australia",
    "australia": "Australia",
    "cyp": "Cyprus",
    "cyprus": "Cyprus",
    "kaz": "Kazakhstan",
    "kazakhstan": "Kazakhstan",
    "ltu": "Lithuania",
    "lithuania": "Lithuania",
    "qat": "Qatar",
    "qatar": "Qatar",
    "rus": "Russia",
    "russia": "Russia",
    "ksa": "Saudi Arabia",
    "sau": "Saudi Arabia",
    "saudi arabia": "Saudi Arabia",
    "svk": "Slovakia",
    "slovakia": "Slovakia",
    "ukr": "Ukraine",
    "ukraine": "Ukraine",
    "vie": "Vietnam",
    "vietnam": "Vietnam",
    "ned": "Netherlands",
    "netherlands": "Netherlands",
}

# Nation + division composite keys for grouped MultiSelect (shared FM division titles).
DIVISION_OPTION_SEP = "\x1f"
_library_cache: dict[str, str] | None = None
_library_busy = False


def encode_division_option_value(division: str, nation: str | None = None) -> str:
    """Unique MultiSelect value when the same division name appears in multiple nations."""
    name = str(division or "").strip()
    nat = normalize_nation_label(nation) if nation else ""
    if not name:
        return ""
    if not nat:
        return name
    return f"{nat}{DIVISION_OPTION_SEP}{name}"


def decode_division_option_value(raw: str | None) -> str:
    """Strip nation prefix from a composite MultiSelect value."""
    text = str(raw or "").strip()
    if DIVISION_OPTION_SEP not in text:
        return text
    return text.split(DIVISION_OPTION_SEP, 1)[1].strip()


def normalize_nation_label(raw: str | None) -> str:
    """Map FM nationality codes / aliases to canonical Based In country names."""
    text = str(raw or "").strip()
    if not text:
        return ""
    return _NATION_ALIASES.get(_fold(text), text)


# Prefer standard FM / FIFA-style codes when a nation has multiple aliases.
_PREFERRED_NATION_ABBR: dict[str, str] = {
    "romania": "ROU",
    "saudi arabia": "KSA",
    "u.s.a.": "USA",
    "u.a.e.": "UAE",
    "netherlands": "NED",
    "switzerland": "SUI",
    "türkiye": "TUR",
    "turkiye": "TUR",
}


def _nation_abbr_lookup() -> dict[str, str]:
    """Canonical nation label (folded) → uppercase abbreviation."""
    candidates: dict[str, set[str]] = defaultdict(set)
    for code, label in _NATION_ALIASES.items():
        code_text = str(code or "").strip()
        if not code_text.isalpha() or not (2 <= len(code_text) <= 3):
            continue
        candidates[_fold(label)].add(code_text.upper())
    out: dict[str, str] = {}
    for fold_lab, codes in candidates.items():
        preferred = _PREFERRED_NATION_ABBR.get(fold_lab)
        if preferred and preferred in codes:
            out[fold_lab] = preferred
            continue
        three = sorted(c for c in codes if len(c) == 3)
        out[fold_lab] = three[0] if three else sorted(codes)[0]
    return out


_NATION_ABBR_BY_LABEL = _nation_abbr_lookup()


def nation_abbreviation(raw: str | None) -> str:
    """FM-style nation abbreviation (e.g. ROU, ENG) from Based In / code."""
    text = str(raw or "").strip()
    if not text or text in ("-", "—", "Unknown"):
        return ""
    folded = _fold(text)
    if folded in _NATION_ALIASES and folded.isalpha() and 2 <= len(folded) <= 3:
        return folded.upper()
    label = normalize_nation_label(text)
    if not label:
        return ""
    return _NATION_ABBR_BY_LABEL.get(_fold(label), "")


def _nation_exact_pairs() -> list[tuple[str, str]]:
    """All (division, nation) pairs from nation-specific tier overrides."""
    from scoring.division_tiers import _NATION_EXACT

    return [
        (division, nation)
        for nation, divisions in _NATION_EXACT.items()
        for division in divisions
    ]


def _division_nation_catalog() -> dict[str, str]:
    """Best-effort division → primary nation map (one nation per division name)."""
    out: dict[str, str] = {}
    for division, nation in _nation_exact_pairs():
        out.setdefault(division, nation)
    for division in romanian_division_names():
        out.setdefault(division, ROMANIA_NATION)
    return out


def collect_division_nation_pairs(
    *,
    selected: list[str] | None = None,
    include_library: bool = True,
    library: dict[str, str] | None = None,
) -> list[tuple[str, str]]:
    """All (division, nation) associations for grouped settings pickers."""
    seen: set[tuple[str, str]] = set()
    out: list[tuple[str, str]] = []

    def add(division: str, nation: str) -> None:
        name = str(division or "").strip()
        if not name:
            return
        nat = normalize_nation_label(nation) if nation else ""
        key = (name, nat)
        if key in seen:
            return
        seen.add(key)
        out.append(key)

    for division, nation in _nation_exact_pairs():
        add(division, nation)
    for division in romanian_division_names():
        add(division, ROMANIA_NATION)
    if include_library:
        lib = library if library is not None else divisions_from_library()
        for division, nation in lib.items():
            if nation:
                add(division, nation)
            else:
                add(division, "")
    for division in selected or []:
        name = decode_division_option_value(division)
        if not name:
            continue
        matched = False
        for div, nat in _nation_exact_pairs():
            if div == name:
                add(name, nat)
                matched = True
        if not matched:
            if is_romanian_division(name):
                add(name, ROMANIA_NATION)
            else:
                add(name, "")
    return out


def divisions_from_library(*, use_cache: bool = True) -> dict[str, str]:
    """Division → nation from cached stats exports in the upload library."""
    global _library_cache, _library_busy
    if use_cache and _library_cache is not None:
        return dict(_library_cache)
    if _library_busy:
        return {}

    votes: dict[str, Counter[str]] = defaultdict(Counter)
    try:
        import services.export_library as lib
        from services.upload_cache import load_cache
    except ImportError:
        return {}

    _library_busy = True
    try:
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
                nation = normalize_nation_label(
                    player.get("based_in") or player.get("nation") or ""
                )
                if nation:
                    votes[division][nation] += 1
        result = {
            division: counter.most_common(1)[0][0]
            for division, counter in votes.items()
            if counter
        }
        if use_cache:
            _library_cache = result
        return result
    finally:
        _library_busy = False


def collect_division_nations(
    *,
    selected: list[str] | None = None,
    include_library: bool = True,
) -> dict[str, str]:
    """Merge catalog + library divisions; one primary nation per division name."""
    library = divisions_from_library() if include_library else {}
    nation_pairs = collect_division_nation_pairs(
        selected=selected,
        include_library=include_library,
        library=library,
    )
    out: dict[str, str] = {}
    for division, nation in nation_pairs:
        if division in library and library[division]:
            out[division] = normalize_nation_label(library[division])
        elif division not in out:
            out[division] = nation
        elif not out[division] and nation:
            out[division] = nation
    for division, nation in list(out.items()):
        if nation:
            out[division] = normalize_nation_label(nation)
        elif is_romanian_division(division):
            out[division] = ROMANIA_NATION
    return out


def is_full_detail_selectable(division: str | None, nation: str | None = None) -> bool:
    """Full Detail picker excludes youth and amateur leagues."""
    return classify_division(division, nation) != "amateur"


def filter_selectable_full_detail_divisions(
    names: list[str] | None,
    *,
    include_library: bool = True,
) -> list[str]:
    """Drop youth/amateur divisions while preserving order."""
    items = [str(name or "").strip() for name in (names or []) if str(name or "").strip()]
    if not items:
        return []
    pairs = collect_division_nations(selected=items, include_library=include_library)
    out: list[str] = []
    seen: set[str] = set()
    for name in items:
        if name in seen:
            continue
        nation = pairs.get(name, "")
        if is_full_detail_selectable(name, nation or None):
            seen.add(name)
            out.append(name)
    return collapse_picker_divisions(out)


def divisions_for_nation(
    nation: str,
    *,
    selected: list[str] | None = None,
    include_library: bool = True,
) -> list[str]:
    """All known divisions for one nation, highest tier first."""
    target = normalize_nation_label(nation)
    if not target:
        return []
    nation_pairs = collect_division_nation_pairs(
        selected=selected,
        include_library=include_library,
    )
    names = sorted(
        {
            div
            for div, nat in nation_pairs
            if normalize_nation_label(nat) == target
        },
        key=lambda div: division_sort_key(div, target),
    )
    return names


def full_detail_division_options(
    selected: list[str] | None = None,
    *,
    include_library: bool = True,
) -> list[dict[str, object]]:
    """Grouped MultiSelect options for dmc: [{group, items: [{value, label}]}]."""
    nation_pairs = collect_division_nation_pairs(
        selected=selected,
        include_library=include_library,
    )
    by_nation: dict[str, list[str]] = defaultdict(list)
    seen_in_group: dict[str, set[str]] = defaultdict(set)
    for division, nation in nation_pairs:
        nation_for_tier = nation or None
        canonical = picker_canonical_division(division, nation_for_tier)
        if not is_full_detail_selectable(canonical, nation_for_tier):
            continue
        nation_label = nation or "Other / unknown nation"
        if canonical in seen_in_group[nation_label]:
            continue
        seen_in_group[nation_label].add(canonical)
        by_nation[nation_label].append(canonical)

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
            nation_key = nation if nation != "Other / unknown nation" else ""
            items.append(
                {
                    "value": encode_division_option_value(division, nation_key),
                    "label": label,
                }
            )
        if items:
            options.append({"group": nation, "items": items})
    return options


def division_option_values_for_saved(
    saved: list[str] | None,
    options: list[dict] | None,
) -> list[str]:
    """Map stored division names to composite MultiSelect values (all nation groups)."""
    wanted = set(
        collapse_picker_divisions(
            [
                decode_division_option_value(name)
                for name in (saved or [])
                if decode_division_option_value(name)
            ]
        )
    )
    if not wanted:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for entry in options or []:
        if not isinstance(entry, dict):
            continue
        for item in entry.get("items") or []:
            if isinstance(item, str):
                value = item.strip()
            elif isinstance(item, dict):
                value = str(item.get("value") or "").strip()
            else:
                value = ""
            if not value or value in seen:
                continue
            if decode_division_option_value(value) in wanted:
                seen.add(value)
                out.append(value)
    return out


def division_values_from_options(options: list[dict] | None) -> list[str]:
    """Flatten grouped or flat MultiSelect data to division name strings."""
    values: list[str] = []
    seen: set[str] = set()
    for entry in options or []:
        if not isinstance(entry, dict):
            continue
        if "items" in entry:
            for item in entry.get("items") or []:
                if isinstance(item, str):
                    value = decode_division_option_value(item)
                elif isinstance(item, dict):
                    value = decode_division_option_value(item.get("value"))
                else:
                    value = ""
                if value and value not in seen:
                    seen.add(value)
                    values.append(value)
            continue
        value = decode_division_option_value(entry.get("value"))
        if value and value not in seen:
            seen.add(value)
            values.append(value)
    return values


def default_full_detail_divisions() -> list[str]:
    """Default Full Detail list: Romanian top- and second-tier leagues only."""
    return filter_selectable_full_detail_divisions(
        romanian_division_names(),
        include_library=False,
    )
