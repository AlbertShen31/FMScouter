"""Classify FM Division names into competition tiers for table highlighting.

Tiers (column `DivisionTier`):

- ``top`` — domestic top flight (green)
- ``pro`` — professional, not top flight (yellow)
- ``amateur`` — semi-pro / amateur / youth / regional (red)
- ``""`` — unknown / blank / free agent (no tint)

Nation is the FM **Based In** country (not Nationality). It only disambiguates
names that appear in more than one country (e.g. Super League). Distinctive
division titles are matched globally so expatriates still color correctly.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Literal

DivisionTier = Literal["top", "pro", "amateur", ""]

# Exact FM export titles → tier (checked after nation overrides).
_EXACT: dict[str, DivisionTier] = {
    # Romania
    "Liga I": "top",
    "Liga II": "pro",
    "Liga V": "amateur",
    # Italy
    "Serie A": "top",
    "Serie B": "pro",
    # Spain
    "LaLiga": "top",
    "LaLiga 2": "pro",
    "División Inferior": "amateur",
    # Germany
    "Bundesliga": "top",
    "2. Bundesliga": "pro",
    "3. Liga": "pro",
    "Amateurliga": "amateur",
    # Austria
    "Bundesliga": "top",  # also Germany; same tier
    "2. Liga": "pro",
    # Hungary
    "NB I": "top",
    "NB II": "pro",
    "Megyei bajnokság": "amateur",
    # Moldova
    "Super Liga": "top",
    # Israel
    "Ligat Ha'Al": "top",
    "Liga Leumit": "pro",
    # Türkiye
    "Süper Lig": "top",
    "1. Lig": "pro",
    # Greece / Switzerland (both top when named Super League)
    "Super League": "top",
    # Belgium
    "Profvoetbal 1A": "top",
    "Profvoetbal 1B": "pro",
    # Cyprus
    "A' Katigorías": "top",
    "B' Katigoría": "pro",
    "G΄ Katigorías": "amateur",
    # Poland
    "Ekstraklasa": "top",
    "1. Liga": "pro",
    # China
    "CSL": "top",
    "CFL1": "pro",
    # France
    "Ligue 2": "pro",
    "Championnat Régional": "amateur",
    # USA
    "MLS": "top",
    "MLSNP Western Conference": "pro",
    "USLC Western Conference": "pro",
    # UAE / Kuwait
    "UAE Pro League": "top",
    "First Division League": "pro",
    # England / Scotland / Portugal / others
    "EFL Championship": "pro",
    "Liga Portugal": "top",
    "Scottish Premiership": "top",
    "Scottish Championship": "pro",
    "Parva Liga": "top",
    "Vtora Liga": "pro",
    "Allsvenskan": "top",
    "Ettan Södra": "amateur",
    "1. divisjon": "pro",
    "Eredivisie": "top",
    "Derde Divisie Zondag": "amateur",
    "Super liga Srbije": "top",
    "V.League 1": "top",
    "V.League 2": "pro",
    "RPL": "top",
    "Toplyga": "top",
    "Nationaldivisioun": "top",
    "UPL": "top",
    "Saudi Pro League": "top",
    "I Liqa": "pro",
    "Kategoria Superiore": "top",
    "Men's Premier Division": "top",
    "Premiyer Liga": "top",
    "Qatar Stars League": "top",
    "C-League": "top",
    "Premer-liga": "top",
    "Malta Premier": "top",
    "I. liga": "top",
    "II. liga": "pro",
    # Australia
    "NPL VIC Men's": "amateur",
    "NPL WA Men's": "amateur",
    "VPL 1": "amateur",
    "Vic State League 1SE": "amateur",
}

# Nation (Based In) → exact division → tier. Wins over global exact/patterns.
_NATION_EXACT: dict[str, dict[str, DivisionTier]] = {
    "Switzerland": {
        "Super League": "top",
        "1. Liga Gruppe 3": "amateur",
    },
    "Greece": {
        "Super League": "top",
        "Super League 2 Voreios Om.": "pro",
        "Super League 2 Notios Om.": "pro",
    },
    "Moldova": {
        "Super Liga": "top",
        "Liga 1 Grupa A": "pro",
        "Liga 1 Grupa B": "pro",
        "Liga 2 Sud": "amateur",
    },
    "Austria": {
        "Bundesliga": "top",
        "2. Liga": "pro",
    },
    "Germany": {
        "Bundesliga": "top",
        "2. Bundesliga": "pro",
        "3. Liga": "pro",
    },
    "U.A.E.": {
        "First Division League": "pro",
    },
    "Kuwait": {
        "First Division League": "pro",
    },
    "France": {
        "Ligue 2": "pro",
        "R1 - Hauts de France - B": "amateur",
        "Championnat Régional": "amateur",
    },
    "Norway": {
        "1. divisjon": "pro",
        "2. divisjon avd. 2": "amateur",
    },
    "Slovenia": {
        "3. SNL Vzhod": "amateur",
    },
}

# (compiled regex, tier) — first match wins. Nation-agnostic distinctive titles.
_PATTERNS: list[tuple[re.Pattern[str], DivisionTier]] = [
    # Romania
    (re.compile(r"^Liga III(\s|$)", re.I), "amateur"),
    (re.compile(r"^Liga IV(\s|$)", re.I), "amateur"),
    (re.compile(r"^Liga V(\s|$)", re.I), "amateur"),
    (re.compile(r"^Na[țt]ional U\d+", re.I), "amateur"),
    (re.compile(r"^Liga de Tineret", re.I), "amateur"),
    # Italy
    (re.compile(r"^Serie C/", re.I), "pro"),
    (re.compile(r"^Serie D/", re.I), "amateur"),
    (re.compile(r"^Eccellenza\b", re.I), "amateur"),
    (re.compile(r"^Promozione\b", re.I), "amateur"),
    (re.compile(r"^Prima Categoria\b", re.I), "amateur"),
    # Spain
    (re.compile(r"^Primera Federación\b", re.I), "pro"),
    (re.compile(r"^Segunda Federación\b", re.I), "amateur"),
    (re.compile(r"^3ª Federación\b", re.I), "amateur"),
    (re.compile(r"^Preferente\b", re.I), "amateur"),
    (re.compile(r"^Regional Preferente\b", re.I), "amateur"),
    (re.compile(r"^Comunitat Valenciana\b", re.I), "amateur"),
    # Germany
    (re.compile(r"^RL\s", re.I), "amateur"),
    (re.compile(r"^Regionalliga\b", re.I), "amateur"),
    (re.compile(r"^Oberliga\b", re.I), "amateur"),
    # Austria
    (re.compile(r"^Regionalliga\b", re.I), "amateur"),
    (re.compile(r"^County League\b", re.I), "amateur"),
    (re.compile(r"^OÖ Liga$", re.I), "amateur"),
    (re.compile(r"^Vorarlberg-Liga$", re.I), "amateur"),
    (re.compile(r"Landesliga", re.I), "amateur"),
    (re.compile(r"^(1|2)\.\s*(Class|Klasse|Landesliga)", re.I), "amateur"),
    (re.compile(r"^Gebietsliga\b", re.I), "amateur"),
    (re.compile(r"^Bezirksliga\b", re.I), "amateur"),
    (re.compile(r"^Unterliga\b", re.I), "amateur"),
    (re.compile(r"Burgenländischer", re.I), "amateur"),
    (re.compile(r"^1\. NÖN Landesliga$", re.I), "amateur"),
    # Hungary
    (re.compile(r"^NB III\b", re.I), "amateur"),
    # Israel
    (re.compile(r"^Ligat A\b", re.I), "amateur"),
    # Greece regional
    (re.compile(r"^Super League 2\b", re.I), "pro"),
    (re.compile(r"^A1 EPS\b", re.I), "amateur"),
    # Belgium amateur
    (re.compile(r"Amateurklasse", re.I), "amateur"),
    (re.compile(r"\bD3 amateur\b", re.I), "amateur"),
    # Moldova
    (re.compile(r"^Liga 1\b", re.I), "pro"),
    (re.compile(r"^Liga 2\b", re.I), "amateur"),
    # Switzerland lower
    (re.compile(r"^1\. Liga Gruppe\b", re.I), "amateur"),
    # France regional
    (re.compile(r"^R1\b", re.I), "amateur"),
    # Norway
    (re.compile(r"^2\. divisjon\b", re.I), "amateur"),
    # Netherlands
    (re.compile(r"^Derde Divisie\b", re.I), "amateur"),
    # Sweden Ettan
    (re.compile(r"^Ettan\b", re.I), "amateur"),
    # Slovenia
    (re.compile(r"^\d\. SNL\b", re.I), "amateur"),
    # Australia NPL / state
    (re.compile(r"^NPL\b", re.I), "amateur"),
    (re.compile(r"^VPL\b", re.I), "amateur"),
    (re.compile(r"State League", re.I), "amateur"),
    # USA
    (re.compile(r"^MLSNP\b", re.I), "pro"),
    (re.compile(r"^USLC\b", re.I), "pro"),
]


def _fold(text: str) -> str:
    """Casefold and strip combining marks for fuzzy exact lookup."""
    norm = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in norm if not unicodedata.combining(c)).casefold().strip()


_EXACT_FOLD = {_fold(k): v for k, v in _EXACT.items()}
_NATION_EXACT_FOLD = {
    _fold(nation): {_fold(div): tier for div, tier in mapping.items()}
    for nation, mapping in _NATION_EXACT.items()
}


def classify_division(division: str | None, nation: str | None = None) -> DivisionTier:
    """Return ``top`` / ``pro`` / ``amateur`` / ``""`` for an FM Division cell."""
    raw = str(division or "").strip()
    if not raw or raw in ("-", "—"):
        return ""
    based_in = str(nation or "").strip()

    nation_map = _NATION_EXACT_FOLD.get(_fold(based_in))
    if nation_map:
        hit = nation_map.get(_fold(raw))
        if hit:
            return hit

    exact = _EXACT_FOLD.get(_fold(raw))
    if exact:
        return exact

    # Romania Liga I / II exact already handled; keep Seria variants on patterns.
    for pattern, tier in _PATTERNS:
        if pattern.search(raw):
            return tier

    return ""


def division_tier_colors(theme: str | None = None) -> dict[str, tuple[str, str]]:
    """Background / foreground pairs for each tier."""
    dark = (theme or "dark") != "light"
    if dark:
        return {
            "top": ("rgba(34, 197, 94, 0.18)", "#4ade80"),
            "pro": ("rgba(245, 158, 11, 0.20)", "#fbbf24"),
            "amateur": ("rgba(239, 68, 68, 0.20)", "#f87171"),
        }
    return {
        "top": ("#dcfce7", "#15803d"),
        "pro": ("#fef3c7", "#b45309"),
        "amateur": ("#fee2e2", "#b91c1c"),
    }


def apply_division_tier(row: dict) -> None:
    """Set ``DivisionTier`` on a table row from Division + Nation."""
    row["DivisionTier"] = classify_division(row.get("Division"), row.get("Nation"))
