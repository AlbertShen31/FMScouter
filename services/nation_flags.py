"""FM nationality / Based In labels → flag emoji (primary left of second)."""
from __future__ import annotations

import re
from typing import Any

from scoring.division_tiers import _fold
from services.division_catalog import normalize_nation_label

# ISO 3166-1 alpha-2 for regional-indicator pairs; UK home nations use tag flags.
_LABEL_ISO2: dict[str, str] = {
    "afghanistan": "AF",
    "albania": "AL",
    "algeria": "DZ",
    "american samoa": "AS",
    "andorra": "AD",
    "angola": "AO",
    "anguilla": "AI",
    "antigua & barbuda": "AG",
    "antigua and barbuda": "AG",
    "argentina": "AR",
    "armenia": "AM",
    "aruba": "AW",
    "australia": "AU",
    "austria": "AT",
    "azerbaijan": "AZ",
    "bahamas": "BS",
    "bahrain": "BH",
    "bangladesh": "BD",
    "barbados": "BB",
    "belarus": "BY",
    "belgium": "BE",
    "belize": "BZ",
    "benin": "BJ",
    "bermuda": "BM",
    "bhutan": "BT",
    "bolivia": "BO",
    "bosnia & herzegovina": "BA",
    "bosnia and herzegovina": "BA",
    "bosnia": "BA",
    "botswana": "BW",
    "brazil": "BR",
    "british virgin is.": "VG",
    "british virgin islands": "VG",
    "brunei": "BN",
    "bulgaria": "BG",
    "burkina faso": "BF",
    "burundi": "BI",
    "cambodia": "KH",
    "cameroon": "CM",
    "canada": "CA",
    "cape verde": "CV",
    "cayman islands": "KY",
    "central african republic": "CF",
    "chad": "TD",
    "chile": "CL",
    "china": "CN",
    "chinese taipei": "TW",
    "colombia": "CO",
    "comoros": "KM",
    "congo": "CG",
    "cook islands": "CK",
    "costa rica": "CR",
    "croatia": "HR",
    "cuba": "CU",
    "curaçao": "CW",
    "curacao": "CW",
    "cyprus": "CY",
    "czech republic": "CZ",
    "czechia": "CZ",
    "dr congo": "CD",
    "congo dr": "CD",
    "denmark": "DK",
    "djibouti": "DJ",
    "dominica": "DM",
    "dominican republic": "DO",
    "ecuador": "EC",
    "egypt": "EG",
    "el salvador": "SV",
    "england": "GB-ENG",
    "equatorial guinea": "GQ",
    "eritrea": "ER",
    "estonia": "EE",
    "eswatini": "SZ",
    "ethiopia": "ET",
    "faroe islands": "FO",
    "fiji": "FJ",
    "finland": "FI",
    "france": "FR",
    "gabon": "GA",
    "gambia": "GM",
    "georgia": "GE",
    "germany": "DE",
    "ghana": "GH",
    "gibraltar": "GI",
    "greece": "GR",
    "grenada": "GD",
    "guam": "GU",
    "guatemala": "GT",
    "guinea": "GN",
    "guinea-bissau": "GW",
    "guyana": "GY",
    "haiti": "HT",
    "honduras": "HN",
    "hong kong": "HK",
    "hungary": "HU",
    "iceland": "IS",
    "india": "IN",
    "indonesia": "ID",
    "iran": "IR",
    "iraq": "IQ",
    "ireland": "IE",
    "republic of ireland": "IE",
    "israel": "IL",
    "italy": "IT",
    "ivory coast": "CI",
    "côte d'ivoire": "CI",
    "cote d'ivoire": "CI",
    "jamaica": "JM",
    "japan": "JP",
    "jordan": "JO",
    "kazakhstan": "KZ",
    "kenya": "KE",
    "kosovo": "XK",
    "kuwait": "KW",
    "kyrgyzstan": "KG",
    "laos": "LA",
    "latvia": "LV",
    "lebanon": "LB",
    "lesotho": "LS",
    "liberia": "LR",
    "libya": "LY",
    "liechtenstein": "LI",
    "lithuania": "LT",
    "luxembourg": "LU",
    "macau": "MO",
    "madagascar": "MG",
    "malawi": "MW",
    "malaysia": "MY",
    "maldives": "MV",
    "mali": "ML",
    "malta": "MT",
    "mauritania": "MR",
    "mauritius": "MU",
    "mexico": "MX",
    "moldova": "MD",
    "mongolia": "MN",
    "montenegro": "ME",
    "montserrat": "MS",
    "morocco": "MA",
    "mozambique": "MZ",
    "myanmar": "MM",
    "namibia": "NA",
    "nepal": "NP",
    "netherlands": "NL",
    "new caledonia": "NC",
    "new zealand": "NZ",
    "nicaragua": "NI",
    "niger": "NE",
    "nigeria": "NG",
    "north macedonia": "MK",
    "macedonia": "MK",
    "northern ireland": "GB-NIR",
    "norway": "NO",
    "oman": "OM",
    "pakistan": "PK",
    "palestine": "PS",
    "panama": "PA",
    "papua new guinea": "PG",
    "paraguay": "PY",
    "peru": "PE",
    "philippines": "PH",
    "poland": "PL",
    "portugal": "PT",
    "puerto rico": "PR",
    "qatar": "QA",
    "romania": "RO",
    "russia": "RU",
    "rwanda": "RW",
    "samoa": "WS",
    "san marino": "SM",
    "saudi arabia": "SA",
    "scotland": "GB-SCT",
    "senegal": "SN",
    "serbia": "RS",
    "seychelles": "SC",
    "sierra leone": "SL",
    "singapore": "SG",
    "slovakia": "SK",
    "slovenia": "SI",
    "solomon islands": "SB",
    "somalia": "SO",
    "south africa": "ZA",
    "south korea": "KR",
    "korea republic": "KR",
    "spain": "ES",
    "sri lanka": "LK",
    "st kitts & nevis": "KN",
    "st lucia": "LC",
    "st vincent & grenadines": "VC",
    "sudan": "SD",
    "suriname": "SR",
    "sweden": "SE",
    "switzerland": "CH",
    "syria": "SY",
    "tahiti": "PF",
    "taiwan": "TW",
    "tajikistan": "TJ",
    "tanzania": "TZ",
    "thailand": "TH",
    "togo": "TG",
    "tonga": "TO",
    "trinidad & tobago": "TT",
    "trinidad and tobago": "TT",
    "tunisia": "TN",
    "turkey": "TR",
    "türkiye": "TR",
    "turkiye": "TR",
    "turkmenistan": "TM",
    "turks & caicos": "TC",
    "uganda": "UG",
    "ukraine": "UA",
    "u.a.e.": "AE",
    "uae": "AE",
    "united arab emirates": "AE",
    "u.s.a.": "US",
    "usa": "US",
    "united states": "US",
    "uruguay": "UY",
    "uzbekistan": "UZ",
    "vanuatu": "VU",
    "venezuela": "VE",
    "vietnam": "VN",
    "wales": "GB-WLS",
    "yemen": "YE",
    "zambia": "ZM",
    "zimbabwe": "ZW",
}

# Extra FM / FIFA three-letter codes not covered by division_catalog aliases.
_CODE_ISO2: dict[str, str] = {
    "afg": "AF",
    "alg": "DZ",
    "arg": "AR",
    "bih": "BA",
    "blr": "BY",
    "bol": "BO",
    "bot": "BW",
    "bra": "BR",
    "brb": "BB",
    "bdi": "BI",
    "can": "CA",
    "chi": "CL",
    "civ": "CI",
    "cmr": "CM",
    "cod": "CD",
    "col": "CO",
    "crc": "CR",
    "cta": "CF",
    "cub": "CU",
    "cze": "CZ",
    "den": "DK",
    "ecu": "EC",
    "egy": "EG",
    "eqg": "GQ",
    "est": "EE",
    "fij": "FJ",
    "fin": "FI",
    "gam": "GM",
    "gha": "GH",
    "grn": "GD",
    "gua": "GT",
    "gui": "GN",
    "guy": "GY",
    "hai": "HT",
    "hon": "HN",
    "idn": "ID",
    "ind": "IN",
    "irn": "IR",
    "irq": "IQ",
    "isl": "IS",
    "jam": "JM",
    "jpn": "JP",
    "ken": "KE",
    "kgz": "KG",
    "kor": "KR",
    "ksa": "SA",
    "lbn": "LB",
    "lbr": "LR",
    "lby": "LY",
    "lie": "LI",
    "lux": "LU",
    "mar": "MA",
    "mas": "MY",
    "mdv": "MV",
    "mex": "MX",
    "mkd": "MK",
    "mli": "ML",
    "mlt": "MT",
    "mne": "ME",
    "moz": "MZ",
    "mri": "MU",
    "mtn": "MR",
    "nam": "NA",
    "nga": "NG",
    "nzl": "NZ",
    "pan": "PA",
    "par": "PY",
    "per": "PE",
    "phi": "PH",
    "prk": "KP",
    "rsa": "ZA",
    "rwa": "RW",
    "sen": "SN",
    "sin": "SG",
    "sle": "SL",
    "slv": "SV",
    "som": "SO",
    "ssd": "SS",
    "stp": "ST",
    "sur": "SR",
    "svk": "SK",
    "svn": "SI",
    "syr": "SY",
    "tan": "TZ",
    "tga": "TO",
    "tha": "TH",
    "tjk": "TJ",
    "tkm": "TM",
    "tto": "TT",
    "tun": "TN",
    "uga": "UG",
    "uru": "UY",
    "uzb": "UZ",
    "ven": "VE",
    "zam": "ZM",
    "zim": "ZW",
    "eng": "GB-ENG",
    "sco": "GB-SCT",
    "wal": "GB-WLS",
    "nir": "GB-NIR",
}

_TAG = "\U000e0067\U000e0062{code}\U000e007f"
_SUBDIVISION = {
    "GB-ENG": "\U0001f3f4" + _TAG.format(code="\U000e0065\U000e006e\U000e0067"),
    "GB-SCT": "\U0001f3f4" + _TAG.format(code="\U000e0073\U000e0063\U000e0074"),
    "GB-WLS": "\U0001f3f4" + _TAG.format(code="\U000e0077\U000e006c\U000e0073"),
    "GB-NIR": "\U0001f3f4" + _TAG.format(code="\U000e006e\U000e0069\U000e0072"),
}

# Kosovo has no ISO regional pair on all platforms; XK is the common private-use code.
_XK_FLAG = "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in "XK")

_FLAG_RUN = re.compile(
    r"(?:"
    r"[\U0001F1E6-\U0001F1FF]{2}"
    r"|\U0001F3F4[\U000E0060-\U000E007E]+\U000E007F"
    r")"
    r"(?:\u00a0|\s)*"
)


def _iso_to_flag(code: str) -> str:
    text = str(code or "").strip().upper()
    if not text:
        return ""
    if text in _SUBDIVISION:
        return _SUBDIVISION[text]
    if text == "XK":
        return _XK_FLAG
    if len(text) == 2 and text.isalpha():
        return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in text)
    return ""


def _nation_iso2(raw: Any) -> str:
    text = str(raw or "").strip()
    if not text or text in ("-", "—", "Unknown", "N/A"):
        return ""
    folded = _fold(text)
    if folded in _CODE_ISO2:
        return _CODE_ISO2[folded]
    if folded in _LABEL_ISO2:
        return _LABEL_ISO2[folded]
    label = normalize_nation_label(text)
    fold_lab = _fold(label)
    if fold_lab in _LABEL_ISO2:
        return _LABEL_ISO2[fold_lab]
    if fold_lab in _CODE_ISO2:
        return _CODE_ISO2[fold_lab]
    return ""


def nation_flag_emoji(raw: Any) -> str:
    """Single nationality → one flag emoji, or empty when unknown."""
    return _iso_to_flag(_nation_iso2(raw))


def nation_flag_emojis(primary: Any = None, second: Any = None) -> str:
    """Primary then second nationality flags (no duplicates). Empty when none map."""
    flags: list[str] = []
    seen: set[str] = set()
    for raw in (primary, second):
        emoji = nation_flag_emoji(raw)
        if not emoji or emoji in seen:
            continue
        seen.add(emoji)
        flags.append(emoji)
    return "".join(flags)


def strip_nation_flags(text: Any) -> str:
    """Remove leading flag emoji runs (for Name sort keys)."""
    value = str(text or "")
    while True:
        updated = _FLAG_RUN.sub("", value, count=1)
        if updated == value:
            break
        value = updated.lstrip("\u00a0 ")
    return value
