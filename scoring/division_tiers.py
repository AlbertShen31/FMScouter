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
    "Ligue 1": "top",
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
    "Premier League": "top",
    "EFL Championship": "pro",
    "EFL League One": "pro",
    "EFL League Two": "pro",
    "National League": "pro",
    "National League North": "pro",
    "National League South": "pro",
    "Liga Portugal": "top",
    "Scottish Premiership": "top",
    "Scottish Championship": "pro",
    "Scottish League 1": "pro",
    "Scottish League 2": "pro",
    "Parva Liga": "top",
    "Vtora Liga": "pro",
    "Allsvenskan": "top",
    "Ettan Södra": "amateur",
    "1. divisjon": "pro",
    "Eredivisie": "top",
    "Eerste Divisie": "pro",
    "Derde Divisie Zondag": "amateur",
    "Super liga Srbije": "top",
    "Prva liga Srbije": "top",
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
    # Brazil
    "Brasileirão": "top",
    "Brasileirão Série B": "pro",
    "Brasileirão Série C": "pro",
    "Brasileirão Série D": "pro",
    # Americas
    "Liga MX": "top",
    "Liga de Expansión MX": "pro",
    "Liga Profesional": "top",
    "Primera Nacional": "pro",
    "Primera A": "top",
    "Primera División": "top",
    "División Profesional": "top",
    "Liga FPD": "top",
    "Liga Nacional Honduras": "top",
    "Liga Nacional Guatemala": "top",
    "Primera Nicaragua": "top",
    "Liga FUTVE": "top",
    "Serie A de Ecuador": "top",
    "Segunda División": "pro",
    "CanPL": "top",
    # Asia / Oceania
    "J1 League": "top",
    "J2 League": "pro",
    "J3 League": "pro",
    "EPL": "top",
    "Indian Super League": "top",
    "Hong Kong Premier League": "top",
    "Hong Kong First Division League": "pro",
    "Liga Super": "top",
    "SPL": "top",
    "T1": "top",
    "Liga de Elite": "top",
    "Taiwan Premier League": "top",
    "DPRK Premier League": "top",
    # Africa / Middle East
    "PSL": "top",
    "NFD": "pro",
    "HNL": "top",
    "1. NL": "pro",
    "2. NL": "pro",
    "Superliga": "top",
    "Eliteserien": "top",
    "1. Division": "pro",
    "Persian Gulf League": "top",
    "Saudi 1st Division": "pro",
    "Botola D1": "top",
    "Botola D2": "pro",
    "Girabola": "top",
    "Moçambola": "top",
    "Premijer Liga BiH": "top",
    "Premyer Liqası": "top",
    "Vodacom Premier League": "top",
    "Castle Lager Premier League": "top",
    "Azam Rwanda Premier League": "top",
    "Bahraini Premier League": "top",
    "Botswana Premier League": "top",
    "Castel Ethiopia Premier League": "top",
    "Libyana Premier League": "top",
    "Dhivehi League": "top",
    "Ligue 1 Orange Mali": "top",
    "TNM Super League": "top",
    "Vitalor Ligue 1": "top",
    "GFA Premier Division": "top",
    "Premier Division": "top",
    "Division d'Honneur": "top",
    "Cymru Premier": "top",
    "NIFL Premiership": "top",
    "1. MFL": "top",
    "Primera Divisió": "top",
    "Virslīga": "top",
    "Liga Portugal 2": "pro",
    "Men's First Division": "pro",
    "Challenge League": "pro",
    "USL1": "pro",
    "2nd Division League": "pro",
    "Egyptian Second Division": "pro",
    "1. ČFL": "pro",
    "2. ČFL": "pro",
    "1st National - ACFF": "pro",
    "1st National - VV": "pro",
    "Segunda Division": "pro",
    "Clubes Sem Divisão Nacional/Fora da Série D": "amateur",
    # Remaining top flights (GK export audit)
    "Liga de Primera": "top",
    "A-League Men": "top",
    "Meistriliiga": "top",
    "GFL": "top",
    "Ýokary Liga": "top",
    "MTN/FAZ Super Division": "top",
    "Jogorku liga": "top",
    "LFA Primeira Divisao": "top",
    "Ligue de Bangui": "top",
    "Nitol Tata League": "top",
    "Omantel League": "top",
    "Iraqi Premier League": "top",
    "StarTimes Premier League": "top",
    "Jamaica Premier League": "top",
    "Bhutan Premier League": "top",
    "Vysheyshaya Liha": "top",
    "Jordan Pro League": "top",
    "WIV Provo Premier League": "top",
    "Digicel D1": "top",
    "Erovnuli Liga": "top",
    "THB Champions League": "top",
    "São Tomé Division 1": "top",
    "Linafoot A": "top",
    "Championnat de Saint-Martin": "top",
    "Première Division": "top",
    "3. NL Jug": "pro",
    "3. NL Centar": "pro",
    "Nation Link Telecom Championship": "pro",
    # Smaller nations / remaining audit gaps
    "PFL": "top",
    "Lebanese Premier League": "top",
    "SSFA Premier League": "top",
    "Econet Premier League": "top",
    "West Bank Premier League": "top",
    "Cingular Premier Division": "top",
    "NLA Premier League": "top",
    "I Divisão": "top",
    "Tochikiston Vyschaya Liga": "top",
    "I lyga": "pro",
    "Promotion League": "pro",
    "División Intermedia": "pro",
    "Samoa National League": "top",
    "Championship West": "pro",
    "Championship East": "pro",
    "Division One": "top",
    "Coimbra Second Division": "pro",
    "GB Division 2": "pro",
    "N'Djamena Premiere": "top",
    "Khürkhree Lig": "top",
    "Bonaire League": "top",
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
        "Second Division": "pro",
    },
    "Kuwait": {
        "First Division League": "pro",
    },
    "France": {
        "Ligue 1": "top",
        "Ligue 2": "pro",
        "National": "pro",
        "R1 - Hauts de France - B": "amateur",
        "Championnat Régional": "amateur",
    },
    "England": {
        "Premier League": "top",
        "EFL Championship": "pro",
        "EFL League One": "pro",
        "EFL League Two": "pro",
        "National League": "pro",
        "National League North": "pro",
        "National League South": "pro",
    },
    "Myanmar": {
        "National League": "top",
    },
    "Nepal": {
        "National League": "top",
    },
    "British Virgin Is.": {
        "National Football League": "top",
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
    (re.compile(r"^USL1\b", re.I), "pro"),
    (re.compile(r"^USL2\b", re.I), "amateur"),
    # France national tiers
    (re.compile(r"^National 2 Groupe\b", re.I), "pro"),
    (re.compile(r"^National 3\b", re.I), "amateur"),
    # Brazil
    (re.compile(r"^Brasileirão Série [BCD]\b", re.I), "pro"),
    # Serbia regional
    (re.compile(r"^Srpska liga\b", re.I), "amateur"),
    (re.compile(r"^Zonske lige\b", re.I), "amateur"),
    # Bulgaria regional
    (re.compile(r"^TAFL\b", re.I), "amateur"),
    # Portugal lower
    (re.compile(r"^Liga 3\b", re.I), "amateur"),
    (re.compile(r"^Campeonato de Portugal\b", re.I), "amateur"),
    (re.compile(r"^Ligas Regionais\b", re.I), "amateur"),
    # England non-league (Step 3–7)
    (re.compile(r"Northern Premier League", re.I), "amateur"),
    (re.compile(r"Southern League", re.I), "amateur"),
    (re.compile(r"Isthmian League", re.I), "amateur"),
    (re.compile(r"Combined Counties League", re.I), "amateur"),
    (re.compile(r"North West Counties League", re.I), "amateur"),
    (re.compile(r"Spartan South Midlands League", re.I), "amateur"),
    (re.compile(r"United Counties League", re.I), "amateur"),
    (re.compile(r"Northern League", re.I), "amateur"),
    (re.compile(r"Wessex League", re.I), "amateur"),
    (re.compile(r"Hellenic League", re.I), "amateur"),
    (re.compile(r"Eastern Counties League", re.I), "amateur"),
    (re.compile(r"Essex Senior League", re.I), "amateur"),
    (re.compile(r"Western League", re.I), "amateur"),
    (re.compile(r"Midland Football League", re.I), "amateur"),
    (re.compile(r"West Midlands \(Regional\) League", re.I), "amateur"),
    (re.compile(r"Northern Counties East League", re.I), "amateur"),
    (re.compile(r"Southern Counties East League", re.I), "amateur"),
    (re.compile(r"Southern Combination League", re.I), "amateur"),
    (re.compile(r"Anglian Combination League", re.I), "amateur"),
    (re.compile(r"Essex Olympian League", re.I), "amateur"),
    (re.compile(r"St\. Piran League", re.I), "amateur"),
    (re.compile(r"Wearside League", re.I), "amateur"),
    (re.compile(r"Manchester Football League", re.I), "amateur"),
    (re.compile(r"Humber Premier League", re.I), "amateur"),
    (re.compile(r"Thames Valley Premier League", re.I), "amateur"),
    (re.compile(r"Liverpool Premier League", re.I), "amateur"),
    (re.compile(r"York Football League", re.I), "amateur"),
    (re.compile(r"County League", re.I), "amateur"),
    (re.compile(r"County Senior League", re.I), "amateur"),
    (re.compile(r"County Football League", re.I), "amateur"),
    (re.compile(r"Football League Premier Division", re.I), "amateur"),
    (re.compile(r"Football League Division", re.I), "amateur"),
    (re.compile(r"Premier Football League", re.I), "amateur"),
    (re.compile(r"Senior League", re.I), "amateur"),
    (re.compile(r"Alliance League", re.I), "amateur"),
    (re.compile(r"Border League", re.I), "amateur"),
    (re.compile(r"Combination League", re.I), "amateur"),
    (re.compile(r"Mid Sussex Football League", re.I), "amateur"),
    (re.compile(r"South West Peninsula League", re.I), "amateur"),
    (re.compile(r"Central Midlands Alliance", re.I), "amateur"),
    (re.compile(r"Peterborough & District League", re.I), "amateur"),
    (re.compile(r"Middlesex County Football League", re.I), "amateur"),
    (re.compile(r"Bedfordshire County League", re.I), "amateur"),
    (re.compile(r"Cheshire Football League", re.I), "amateur"),
    (re.compile(r"Gloucestershire County League", re.I), "amateur"),
    (re.compile(r"Herefordshire Football League", re.I), "amateur"),
    (re.compile(r"Hertfordshire Senior County League", re.I), "amateur"),
    (re.compile(r"Kent County League", re.I), "amateur"),
    (re.compile(r"Leicestershire Senior League", re.I), "amateur"),
    (re.compile(r"Lincolnshire Football League", re.I), "amateur"),
    (re.compile(r"North Riding League", re.I), "amateur"),
    (re.compile(r"Nottinghamshire Senior League", re.I), "amateur"),
    (re.compile(r"Oxfordshire Senior League", re.I), "amateur"),
    (re.compile(r"Shropshire County League", re.I), "amateur"),
    (re.compile(r"Somerset County League", re.I), "amateur"),
    (re.compile(r"Staffordshire County Senior League", re.I), "amateur"),
    (re.compile(r"Surrey Premier County Football League", re.I), "amateur"),
    (re.compile(r"West Cheshire League", re.I), "amateur"),
    (re.compile(r"West Yorkshire League", re.I), "amateur"),
    (re.compile(r"Wiltshire Senior League", re.I), "amateur"),
    (re.compile(r"Yorkshire Amateur League", re.I), "amateur"),
    (re.compile(r"Devon Football League", re.I), "amateur"),
    (re.compile(r"Dorset Premier Football League", re.I), "amateur"),
    (re.compile(r"Cambridgeshire County League", re.I), "amateur"),
    (re.compile(r"Hampshire Premier League", re.I), "amateur"),
    (re.compile(r"Essex & Suffolk Border League", re.I), "amateur"),
    (re.compile(r"Essex Alliance League", re.I), "amateur"),
    (re.compile(r"Northern Football Alliance", re.I), "amateur"),
    (re.compile(r"Suffolk & Ipswich League", re.I), "amateur"),
    (re.compile(r"East Berkshire League", re.I), "amateur"),
    (re.compile(r"West Lancashire League", re.I), "amateur"),
    (re.compile(r"^Niže lige\b", re.I), "amateur"),
    (re.compile(r"^3\. NL\b", re.I), "pro"),
    (re.compile(r"Distrital Jun", re.I), "amateur"),
    (re.compile(r"AF Porto", re.I), "amateur"),
    (re.compile(r"Dzongkhag League", re.I), "amateur"),
    (re.compile(r"^Régionale\b", re.I), "amateur"),
    (re.compile(r"^Regional\b", re.I), "amateur"),
    (re.compile(r"^OFG\b", re.I), "amateur"),
    (re.compile(r"^A - OFG\b", re.I), "amateur"),
    (re.compile(r"^AF [A-Z]", re.I), "amateur"),
    (re.compile(r"^ŽNL\b", re.I), "amateur"),
    (re.compile(r"^MNL\b", re.I), "amateur"),
    (re.compile(r"^Bremen-Liga$", re.I), "amateur"),
    (re.compile(r"^Lower Division$", re.I), "amateur"),
    (re.compile(r"^Third Division$", re.I), "amateur"),
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
