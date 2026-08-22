"""Parse FM player exports and score selected FM26 roles.

A role belongs to one or more position groups (`gk`, `cb`, `wm`, `w`, …).
`wm` is wide midfielders; `w` is wingers (formerly labelled wide attackers).
Eligibility is OR across a role’s groups. See docs/ARCHITECTURE.md.
"""
from __future__ import annotations

import csv
import io
from enum import IntEnum
from typing import Any

import config.fm26_role_weight_config as pc
import role_config
from phases import phase_is_gk, phase_label, phase_matches, phase_tone, pretty_role_name
from utils import calculate_score

role_config.ensure_loaded()

SET_PIECE_PROFILES = (
    {
        "id": "corners",
        "label": "Corners",
        "abbr": "COR",
        "detail": "taker",
        "raw": "Cor",
        "score": "Corners",
        "key": ("Cor",),
        "preferred": ("Cro", "Tec"),
        "useful": (),
    },
    {
        "id": "dfk",
        "label": "DFK",
        "abbr": "DFK",
        "detail": "direct — shooting chance",
        "raw": "Fre",
        "score": "DFK",
        "key": ("Fre",),
        "preferred": ("Tec", "Lon"),
        "useful": (),
    },
    {
        "id": "ifk",
        "label": "IFK",
        "abbr": "IFK",
        "detail": "indirect — crossing chance",
        "raw": "Fre",
        "score": "IFK",
        "key": ("Fre",),
        "preferred": ("Cro", "Tec"),
        "useful": ("Pas",),
    },
    {
        "id": "throws",
        "label": "Long throws",
        "abbr": "LTH",
        "detail": "taker",
        "raw": "LTh",
        "score": "Throws",
        "key": ("LTh",),
        "preferred": (),
        "useful": (),
    },
    {
        "id": "pens",
        "label": "Penalties",
        "abbr": "PEN",
        "detail": "spot kicks",
        "raw": "Pen",
        "score": "Pens",
        "key": ("Pen",),
        "preferred": ("Fin", "Cmp"),
        "useful": (),
    },
    {
        "id": "aerial",
        "label": "Aerial threat",
        "abbr": "AER",
        "detail": "in the box",
        "raw": None,
        "score": "Aerial",
        "key": ("Jum", "Hea"),
        "preferred": ("Str",),
        "useful": (),
    },
)


def _resolve_tier_weights(tier_weights: dict[str, float] | None = None) -> dict[str, float]:
    if tier_weights:
        return {
            "key": float(tier_weights.get("key", pc.KEY_WEIGHT)),
            "preferred": float(tier_weights.get("preferred", pc.PREFERRED_WEIGHT)),
            "useful": float(tier_weights.get("useful", pc.USEFUL_WEIGHT)),
        }
    return {
        "key": float(pc.KEY_WEIGHT),
        "preferred": float(pc.PREFERRED_WEIGHT),
        "useful": float(pc.USEFUL_WEIGHT),
    }


def _resolve_set_piece_profiles(profiles: list[dict] | None = None) -> list[dict]:
    if profiles:
        return list(profiles)
    return list(SET_PIECE_PROFILES)


def set_piece_divisor(
    profile: dict, tier_weights: dict[str, float] | None = None
) -> float:
    weights = _resolve_tier_weights(tier_weights)
    return (
        weights["key"] * len(profile.get("key") or ())
        + weights["preferred"] * len(profile.get("preferred") or ())
        + weights["useful"] * len(profile.get("useful") or ())
    )


def set_piece_formula(
    profile: dict, tier_weights: dict[str, float] | None = None
) -> str:
    weights = _resolve_tier_weights(tier_weights)
    terms = []
    for attr in profile.get("key") or ():
        terms.append(f"{weights['key']:g}×{attr}")
    for attr in profile.get("preferred") or ():
        terms.append(f"{weights['preferred']:g}×{attr}")
    for attr in profile.get("useful") or ():
        if weights["useful"] == 1:
            terms.append(attr)
        else:
            terms.append(f"{weights['useful']:g}×{attr}")
    if not terms or not profile.get("score"):
        raw = profile.get("raw") or "?"
        return f"{profile['label']} = {raw} (raw only)"
    return (
        f"{profile['label']} = ({' + '.join(terms)}) "
        f"÷ {set_piece_divisor(profile, weights):g}"
    )


def set_piece_hint(tier_weights: dict[str, float] | None = None) -> str:
    weights = _resolve_tier_weights(tier_weights)
    return (
        "Combined scores use the same "
        f"{weights['key']:g}× key / {weights['preferred']:g}× preferred / "
        f"{weights['useful']:g}× useful weights as roles. "
        "DFK is a shot from the dead ball; IFK is a delivery into the box. "
        "Checked types add their computed score column only."
    )


def set_piece_sort_column(
    piece_id: str, profiles: list[dict] | None = None
) -> str | None:
    for profile in _resolve_set_piece_profiles(profiles):
        if profile["id"] == piece_id:
            return profile.get("score") or profile.get("raw")
    return None


def set_piece_filter_columns(
    piece_id: str, profiles: list[dict] | None = None
) -> str:
    """Column used for min-score filtering on a checked set-piece type."""
    return set_piece_sort_column(piece_id, profiles) or ""


def set_piece_columns(selected, profiles: list[dict] | None = None) -> list[str]:
    """Computed score columns only for checked set-piece types."""
    chosen = set(selected or [])
    cols = []
    seen: set[str] = set()
    for profile in _resolve_set_piece_profiles(profiles):
        if profile["id"] not in chosen:
            continue
        score = profile.get("score")
        if score and score not in seen:
            cols.append(score)
            seen.add(score)
    return cols


def set_piece_header(score_col: str, profiles: list[dict] | None = None) -> str:
    """Short table header for a set-piece score column (e.g. Corners → COR)."""
    for profile in _resolve_set_piece_profiles(profiles):
        if profile.get("score") == score_col:
            return profile.get("abbr") or profile.get("label") or score_col
    return score_col


def apply_set_piece_scores(
    row: dict[str, Any],
    attrs: dict[str, int],
    *,
    tier_weights: dict[str, float] | None = None,
    profiles: list[dict] | None = None,
) -> None:
    weights = _resolve_tier_weights(tier_weights)
    written_raw: set[str] = set()
    for profile in _resolve_set_piece_profiles(profiles):
        raw = profile.get("raw")
        if raw and raw not in written_raw:
            value = attrs.get(raw)
            row[raw] = value if value not in (None, "") else "-"
            written_raw.add(raw)
        score = profile.get("score")
        if not score:
            continue
        key_attrs = list(profile.get("key") or ())
        preferred_attrs = list(profile.get("preferred") or ())
        useful_attrs = list(profile.get("useful") or ())
        divisor = set_piece_divisor(profile, weights)
        row[score] = calculate_score(
            attrs,
            key_attrs,
            preferred_attrs,
            useful_attrs,
            weights["key"],
            weights["preferred"],
            weights["useful"],
            divisor,
        )


ATTR_MAP = {
    "Aerial Reach": "Aer",
    "Command Of Area": "Cmd",
    "Command of Area": "Cmd",
    "Communication": "Com",
    "Eccentricity": "Ecc",
    "Handling": "Han",
    "Kicking": "Kic",
    "One On Ones": "1v1",
    "One on Ones": "1v1",
    "Punching": "Pun",
    "Reflexes": "Ref",
    "Rushing Out (Tendency)": "TRO",
    "Rushing Out": "TRO",
    "Throwing": "Thr",
    "Aggression": "Agg",
    "Anticipation": "Ant",
    "Bravery": "Bra",
    "Concentration": "Cnt",
    "Composure": "Cmp",
    "Decisions": "Dec",
    "Determination": "Det",
    "Flair": "Fla",
    "Leadership": "Ldr",
    "Off The Ball": "OtB",
    "Off the Ball": "OtB",
    "Positioning": "Pos",
    "Team Work": "Tea",
    "Teamwork": "Tea",
    "Vision": "Vis",
    "Work Rate": "Wor",
    "Acceleration": "Acc",
    "Agility": "Agi",
    "Balance": "Bal",
    "Jumping Reach": "Jum",
    "Natural Fitness": "Nat",
    "Pace": "Pac",
    "Stamina": "Sta",
    "Strength": "Str",
    "Corners": "Cor",
    "Crossing": "Cro",
    "Dribbling": "Dri",
    "Finishing": "Fin",
    "First Touch": "Fir",
    "Free Kick Taking": "Fre",
    "Heading": "Hea",
    "Long Shots": "Lon",
    "Long Throws": "LTh",
    "Marking": "Mar",
    "Passing": "Pas",
    "Penalty Taking": "Pen",
    "Tackling": "Tck",
    "Technique": "Tec",
}

ABBRS = set(ATTR_MAP.values()) | set(ATTR_MAP.keys())

IDENTITY = {
    "Name": ["Player", "Name"],
    "Age": ["Age"],
    "Club": ["Club"],
    "Division": ["Division", "Div"],
    "Nation": ["Based In", "Nat", "Nationality"],
    "Position": ["Position"],
    "SecPosition": ["Sec. Position", "Secondary Position", "Sec Position"],
    "BestPos": ["Best Pos", "Best Position"],
    "BestRole": ["Best Role"],
    "Style": ["Style"],
    "Personality": ["Personality"],
    "MediaHandling": ["Media Handling"],
    "WorldReputation": ["World Reputation"],
    "Ability": ["Ability", "CA"],
    "Potential": ["Potential", "PA"],
    "Height": ["Height"],
    "LeftFoot": ["Left Foot", "LFoot", "L"],
    "RightFoot": ["Right Foot", "RFoot", "R"],
    "Rec": ["Rec.", "Rec"],
    "Inf": ["Inf"],
    "Injury": ["Injury"],
    "Squad": ["Squad"],
    "NationalTeam": ["National Team"],
    "IntAppsSeason": ["International Appearances (Season)"],
    "IntAssists": ["International Assists"],
    "AvgRatingInt": ["Average Rating International"],
    "Last5Int": ["Last 5 Games International"],
    "FormInt": ["Form International"],
    "IntGoalsConceded": ["International Goals Conceded"],
    "IntGls": ["Int Gls", "International Goals"],
    "IntApps": ["Int Apps", "International Appearances"],
    "YthApps": ["Yth Apps", "Youth Apps"],
    "YthGls": ["Yth Gls", "Youth Goals"],
}

DEFAULT_ROLE_CODES = []
DEFAULT_ROLES = [pc.role_code_to_id[code] for code in DEFAULT_ROLE_CODES]

GROUP_DEFS = [
    ("gk", "Goalkeepers", pc.gk_positions),
    ("cb", "Centre-backs", pc.cb_positions),
    ("fb", "Full-backs", pc.fb_positions),
    ("wb", "Wing-backs", pc.wb_positions),
    ("dm", "Defensive midfielders", pc.dm_positions),
    ("cm", "Central midfielders", pc.cm_positions),
    ("am", "Attacking midfielders", pc.am_positions),
    ("wm", "Wide midfielders", pc.wm_positions),
    ("w", "Wingers", pc.w_positions),
    ("st", "Strikers", pc.st_positions),
]

_ROLE_GROUP = {}
for _group, _label, _roles in GROUP_DEFS:
    for _role in _roles:
        _ROLE_GROUP[_role] = _group


def role_groups(role_id: str) -> list[str]:
    cfg = pc.all_positions.get(role_id) or {}
    groups = [g for g in (cfg.get("groups") or []) if g]
    if groups:
        return groups
    home = _ROLE_GROUP.get(role_id)
    return [home] if home else []


PHASE_SORT_ORDER = {"IP": 0, "OOP": 1, "GK": 2}


def role_sort_key(role_id: str) -> tuple[int, str, str]:
    """Phase first (IP → OOP → GK), then role name A–Z."""
    cfg = pc.all_positions.get(role_id) or {}
    phase_rank = PHASE_SORT_ORDER.get(phase_label(cfg.get("phase")), 99)
    return (phase_rank, pretty_role_name(role_id).casefold(), role_id)


def iter_roles(group: str | None = None) -> list[str]:
    """Role ids, optionally filtered to one position group via `groups`."""
    roles = sorted(pc.all_positions, key=role_sort_key)
    if not group or group in ("", "all"):
        return roles
    return [role_id for role_id in roles if group in role_groups(role_id)]


def group_labels(role_id: str) -> str:
    wanted = set(role_groups(role_id))
    return " / ".join(label for gid, label, _roles in GROUP_DEFS if gid in wanted)


def group_abbr(role_id: str) -> str:
    """Short group ids, e.g. WM/W."""
    return "/".join(group.upper() for group in role_groups(role_id))


def compact_role_label(role_id: str, *, with_phase: bool = True) -> str:
    """Compact UI name, e.g. 'WM/W Inside Winger IP'."""
    abbr = group_abbr(role_id)
    name = pretty_role_name(role_id)
    parts = [part for part in (abbr, name) if part]
    if with_phase:
        phase = phase_label((pc.all_positions.get(role_id) or {}).get("phase", ""))
        if phase and phase != "—":
            parts.append(phase)
    return " ".join(parts)

# Player-position filter cards on Role scores. The “Winger” card is AML/AMR
# players, not the `w` role group and not the Winger (`W`) role.
POS_CARDS = [
    ("all", "All", "", "all"),
    ("GK", "Goalkeeper", "GK", "gk"),
    ("DEF", "Defender", "DC / CB", "def"),
    ("FB", "Full Back", "FB / WB", "fb"),
    ("MID", "Midfielder", "DM / CM", "mid"),
    ("W", "Winger", "AML / AMR", "w"),
    ("ST", "Striker", "ST / CF", "st"),
]

POS_CARD_GROUPS = {
    "GK": ("gk",),
    "DEF": ("cb",),
    "FB": ("fb", "wb"),
    "MID": ("dm", "cm", "am"),
    "W": ("wm", "w"),
    "ST": ("st",),
}

GROUP_ABBR_TONE = {
    "GK": "gk",
    "CB": "def",
    "FB": "fb",
    "WB": "fb",
    "DM": "mid",
    "CM": "mid",
    "AM": "mid",
    "WM": "w",
    "W": "w",
    "ST": "st",
}


def group_abbr_tone(token: str) -> str:
    return GROUP_ABBR_TONE.get((token or "").upper(), "")

PHASE_SUFFIXES = ("_IP_GK", "_OOP_GK", "_IP", "_OOP", "_GK")


def unique_headers(raw: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    out = []
    for header in raw:
        n = seen.get(header, 0)
        out.append(header if n == 0 else f"{header}.{n}")
        seen[header] = n + 1
    return out


def sniff_delimiter(text: str) -> str:
    first = text.splitlines()[0] if text else ""
    return ";" if first.count(";") >= first.count(",") else ","


def pick(row: dict[str, str], aliases: list[str]) -> str:
    for alias in aliases:
        if alias in row and row[alias] not in (None, ""):
            return str(row[alias]).strip()
        for key in row:
            if key.split(".")[0] == alias and row[key] not in (None, ""):
                return str(row[key]).strip()
    return ""


def pick_all(row: dict[str, str], aliases: list[str]) -> list[str]:
    """All non-empty values for aliases, including ``Best Role.1`` duplicates."""
    out: list[str] = []
    seen: set[str] = set()
    for alias in aliases:
        for key, value in row.items():
            if key != alias and key.split(".")[0] != alias:
                continue
            text = "" if value in (None, "") else str(value).strip()
            if not text or text in seen:
                continue
            seen.add(text)
            out.append(text)
    return out


def pick_best_role(row: dict[str, str]) -> str:
    """Prefer the full Best Role label when the export also has a short code."""
    values = [
        value
        for value in pick_all(row, IDENTITY["BestRole"])
        if value.casefold() != "unknown"
    ]
    if not values:
        return ""
    if len(values) == 1:
        return values[0]
    # e.g. "WB" + "Wing back" → "Wing back (WB)"
    by_len = sorted(values, key=len)
    short, long = by_len[0], by_len[-1]
    if short.casefold() in long.casefold():
        return long
    return f"{long} ({short})"


def to_int(value: Any) -> int:
    if value in (None, "", "-"):
        return 0
    text = str(value).strip().replace(",", ".")
    if "-" in text and not text.startswith("-"):
        text = text.split("-")[0]
    try:
        return int(float(text))
    except ValueError:
        return 0


def parse_positions(position_str: str) -> list[dict[str, str]]:
    if not position_str or position_str == "-":
        return []
    parsed = []
    for group in [g.strip() for g in position_str.split(",")]:
        parts = group.split("(")
        positions = [p.strip() for p in parts[0].split("/") if p.strip()]
        area = parts[1].strip(")") if len(parts) > 1 else ""
        for pos in positions:
            parsed.append({"position": pos, "area": "C" if pos == "DM" else area})
    return parsed


def is_eligible(positions: list[dict[str, str]], group: str) -> bool:
    for item in positions:
        pos, area = item["position"], item["area"]
        if group == "gk" and pos == "GK":
            return True
        if group == "cb" and pos == "D" and "C" in area:
            return True
        if group in ("fb", "wb"):
            if pos == "WB":
                return True
            if pos == "D" and ("L" in area or "R" in area):
                return True
        if group in ("dm", "cm") and (pos == "DM" or (pos == "M" and "C" in area)):
            return True
        if group == "am" and (
            (pos == "AM" and "C" in area) or (pos == "M" and "C" in area)
        ):
            return True
        if group == "wm" and pos in ("M", "AM") and ("L" in area or "R" in area):
            return True
        if group == "w" and (
            (pos == "AM" and ("L" in area or "R" in area))
            or (pos == "M" and ("L" in area or "R" in area))
            or pos == "ST"
        ):
            return True
        if group == "st" and pos == "ST":
            return True
    return False


def player_pos_groups(positions: list[dict[str, str]]) -> list[str]:
    groups = []
    for card, role_groups in POS_CARD_GROUPS.items():
        if any(is_eligible(positions, group) for group in role_groups):
            groups.append(card)
    return groups


def _code_uses(code: str) -> int:
    return sum(1 for cfg in pc.all_positions.values() if cfg.get("role_code") == code)


def display_code(role_id: str, cfg: dict | None = None) -> str:
    """Short badge text for UI (e.g. CF). Phase is shown separately."""
    cfg = cfg or pc.all_positions.get(role_id, {})
    return cfg.get("role_code", role_id)


def column_label(role_id: str, cfg: dict | None = None) -> str:
    """Score / CSV column key; disambiguates duplicate codes (e.g. CF-IP)."""
    cfg = cfg or pc.all_positions.get(role_id, {})
    code = cfg.get("role_code", role_id)
    if _code_uses(code) > 1:
        tone = phase_tone(cfg.get("phase", "")).upper()
        if tone:
            return f"{code}-{tone}"
    return code


def role_meta(role_id: str) -> dict[str, str]:
    cfg = pc.all_positions.get(role_id, {})
    phase = cfg.get("phase", "")
    groups = role_groups(role_id)
    group = groups[0] if groups else _ROLE_GROUP.get(role_id, "")
    return {
        "id": role_id,
        "code": display_code(role_id, cfg),
        "column": column_label(role_id, cfg),
        "name": pretty_role_name(role_id),
        "phase": phase_label(phase),
        "tone": phase_tone(phase),
        "is_gk": "yes" if phase_is_gk(phase, role_id, group) or "gk" in groups else "",
        "group": group,
        "groups": ",".join(groups),
        "group_label": group_labels(role_id),
        "group_abbr": group_abbr(role_id),
        "compact": compact_role_label(role_id),
        "compact_name": compact_role_label(role_id, with_phase=False),
    }


def role_option_label(role_id: str) -> str:
    return compact_role_label(role_id)


COMBO_IP_WEIGHT = 2.0
COMBO_OOP_WEIGHT = 1.0


def combo_id(ip: str, oop: str) -> str:
    return f"combo:{ip}|{oop}"


def parse_combo_id(value: str) -> tuple[str, str] | None:
    text = str(value or "")
    if not text.startswith("combo:"):
        return None
    ip, sep, oop = text[6:].partition("|")
    if not sep or not ip or not oop:
        return None
    return ip, oop


def normalize_combos(raw) -> list[dict[str, str]]:
    out = []
    seen: set[tuple[str, str]] = set()
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        ip = item.get("ip") or ""
        oop = item.get("oop") or ""
        if ip not in pc.all_positions or oop not in pc.all_positions:
            continue
        if phase_tone(pc.all_positions[ip].get("phase")) != "ip":
            continue
        if phase_tone(pc.all_positions[oop].get("phase")) != "oop":
            continue
        key = (ip, oop)
        if key in seen:
            continue
        seen.add(key)
        out.append({"ip": ip, "oop": oop})
    return out


def combo_column(ip: str, oop: str) -> str:
    return f"{column_label(ip)}+{column_label(oop)}"


def combo_meta(ip: str, oop: str) -> dict[str, str]:
    ip_meta = role_meta(ip)
    oop_meta = role_meta(oop)
    groups = []
    for token in (ip_meta.get("group_abbr") or "").split("/") + (
        oop_meta.get("group_abbr") or ""
    ).split("/"):
        if token and token not in groups:
            groups.append(token)
    abbr = "/".join(groups)
    ip_col = ip_meta["column"]
    oop_col = oop_meta["column"]
    role_codes = f"{ip_col}+{oop_col}"
    same_name = ip_meta["name"] == oop_meta["name"]
    name = ip_meta["name"] if same_name else f"{ip_meta['name']} / {oop_meta['name']}"
    return {
        "id": combo_id(ip, oop),
        "ip": ip,
        "oop": oop,
        "column": combo_column(ip, oop),
        "ip_column": ip_col,
        "oop_column": oop_col,
        "code": role_codes,
        "name": name,
        "short_label": role_codes,
        "compact": f"{abbr} {role_codes}".strip(),
        "compact_name": f"{abbr} {role_codes}".strip(),
        "group_abbr": abbr,
        "phase": "IP+OOP",
        "tone": "combo",
    }


def apply_combos(
    rows: list[dict[str, Any]],
    combos: list[dict[str, str]] | None = None,
    ip_weight: float = COMBO_IP_WEIGHT,
    oop_weight: float = COMBO_OOP_WEIGHT,
) -> list[dict[str, Any]]:
    """Add combined IP+OOP columns. Eligible if either constituent is."""
    metas = [combo_meta(item["ip"], item["oop"]) for item in normalize_combos(combos)]
    if not metas:
        return rows
    total = ip_weight + oop_weight
    if total <= 0:
        total = 1.0
    for row in rows:
        for meta in metas:
            ip_score = float(row.get(meta["ip_column"]) or 0)
            oop_score = float(row.get(meta["oop_column"]) or 0)
            row[meta["column"]] = round(
                (ip_weight * ip_score + oop_weight * oop_score) / total, 1
            )
            row[f"{meta['column']} eligible"] = bool(
                row.get(f"{meta['ip_column']} eligible")
                or row.get(f"{meta['oop_column']} eligible")
            )
    return rows


def combo_score_labels(role_ids: list[str], combos: list[dict[str, str]] | None = None) -> list[str]:
    """Column order: each combo beside its IP and OOP parts, then leftover roles."""
    labels = []
    seen: set[str] = set()
    for item in normalize_combos(combos):
        meta = combo_meta(item["ip"], item["oop"])
        for column in (meta["column"], meta["ip_column"], meta["oop_column"]):
            if column not in seen:
                labels.append(column)
                seen.add(column)
    for role_id in role_ids:
        column = column_label(role_id)
        if column not in seen:
            labels.append(column)
            seen.add(column)
    return labels


def role_options(
    phase: str | None = None,
    group: str | None = None,
    keep: list[str] | None = None,
) -> list[dict]:
    """Flat `{label, value}` options. `phase` is All/IP/OOP."""
    keep = set(keep or [])
    phase = (phase or "all").upper()
    if phase == "GK":
        phase = "ALL"
    group = (group or "all").lower()
    options = []
    for role_id in iter_roles():
        cfg_phase = pc.all_positions[role_id].get("phase", "")
        groups = role_groups(role_id)
        home = groups[0] if groups else _ROLE_GROUP.get(role_id, "")
        if (
            phase not in ("", "ALL")
            and not phase_matches(cfg_phase, phase, role_id, "gk" if "gk" in groups else home)
            and role_id not in keep
        ):
            continue
        if group not in ("", "all") and group not in groups and role_id not in keep:
            continue
        options.append(
            {
                "label": compact_role_label(role_id),
                "value": role_id,
            }
        )
    return options


def extract_attrs(row: dict[str, str]) -> dict[str, int]:
    attrs: dict[str, int] = {}
    for key, value in row.items():
        base = key.split(".")[0]
        abbr = ATTR_MAP.get(base)
        if abbr:
            attrs[abbr] = to_int(value)
        elif base in ATTR_MAP.values():
            attrs[base] = to_int(value)
    return attrs


def _header_bases(header: list[str]) -> set[str]:
    return {h.split(".")[0] for h in header}


def _has_name_column(header: list[str]) -> bool:
    keys = set(header)
    bases = _header_bases(header)
    return any(alias in keys or alias in bases for alias in IDENTITY["Name"])


def _has_attribute_columns(header: list[str]) -> bool:
    bases = _header_bases(header)
    return any(full in bases or abbr in bases for full, abbr in ATTR_MAP.items())


def attr_count(row: dict[str, str]) -> int:
    n = 0
    for key in row:
        base = key.split(".")[0]
        if base in ATTR_MAP or base in ABBRS:
            if to_int(row[key]) > 0:
                n += 1
    return n


def parse_export(text: str) -> list[dict[str, Any]]:
    if not text or not text.strip():
        raise ValueError("The file is empty.")
    delim = sniff_delimiter(text)
    reader = csv.reader(io.StringIO(text), delimiter=delim)
    try:
        raw_header = next(reader)
    except StopIteration as exc:
        raise ValueError("The file has no header row.") from exc
    header = unique_headers(raw_header)
    if not _has_name_column(header):
        raise ValueError("CSV must include a Name or Player column.")
    if not _has_attribute_columns(header):
        raise ValueError(
            "CSV must include at least one player attribute column "
            "(e.g. Acceleration, Passing, Tackling)."
        )
    players = []
    for raw in reader:
        if not raw or all(not cell.strip() for cell in raw):
            continue
        if len(raw) < len(header):
            raw = list(raw) + [""] * (len(header) - len(raw))
        elif len(raw) > len(header):
            raw = raw[: len(header)]
        row = dict(zip(header, raw))
        name = pick(row, IDENTITY["Name"])
        if not name:
            continue
        attrs = extract_attrs(row)
        pos = pick(row, IDENTITY["Position"])
        sec = pick(row, IDENTITY["SecPosition"])
        positions = parse_positions(pos) + parse_positions(sec)
        players.append(
            {
                "name": name,
                "age": pick(row, IDENTITY["Age"]),
                "club": pick(row, IDENTITY["Club"]),
                "division": pick(row, IDENTITY["Division"]),
                "nation": pick(row, IDENTITY["Nation"]),
                "position": pos,
                "best_pos": pick(row, IDENTITY["BestPos"]),
                "best_role": pick_best_role(row),
                "style": pick(row, IDENTITY["Style"]),
                "personality": pick(row, IDENTITY["Personality"]),
                "media_handling": pick(row, IDENTITY["MediaHandling"]),
                "world_reputation": pick(row, IDENTITY["WorldReputation"]),
                "ability": pick(row, IDENTITY["Ability"]),
                "potential": pick(row, IDENTITY["Potential"]),
                "height": pick(row, IDENTITY["Height"]).strip('"'),
                "left_foot": pick(row, IDENTITY["LeftFoot"]),
                "right_foot": pick(row, IDENTITY["RightFoot"]),
                "rec": pick(row, IDENTITY["Rec"]),
                "inf": pick(row, IDENTITY["Inf"]),
                "injury": pick(row, IDENTITY["Injury"]),
                "squad": pick(row, IDENTITY["Squad"]),
                "national_team": pick(row, IDENTITY["NationalTeam"]),
                "int_apps_season": pick(row, IDENTITY["IntAppsSeason"]),
                "int_assists": pick(row, IDENTITY["IntAssists"]),
                "avg_rating_int": pick(row, IDENTITY["AvgRatingInt"]),
                "last_5_int": pick(row, IDENTITY["Last5Int"]),
                "form_int": pick(row, IDENTITY["FormInt"]),
                "int_goals_conceded": pick(row, IDENTITY["IntGoalsConceded"]),
                "int_gls": pick(row, IDENTITY["IntGls"]),
                "int_apps": pick(row, IDENTITY["IntApps"]),
                "yth_apps": pick(row, IDENTITY["YthApps"]),
                "yth_gls": pick(row, IDENTITY["YthGls"]),
                "attrs": attrs,
                "attr_hits": attr_count(row),
                "positions": positions,
                "pos_groups": player_pos_groups(positions),
            }
        )
    if not players:
        raise ValueError("No player rows found. Check that the file is an FM CSV export.")
    return players


class FootStrength(IntEnum):
    VERY_WEAK = 1
    WEAK = 2
    REASONABLE = 3
    FAIRLY_STRONG = 4
    STRONG = 5
    VERY_STRONG = 6


FOOT_STRENGTH_NAMES: dict[FootStrength, str] = {
    FootStrength.VERY_WEAK: "Very weak",
    FootStrength.WEAK: "Weak",
    FootStrength.REASONABLE: "Reasonable",
    FootStrength.FAIRLY_STRONG: "Fairly strong",
    FootStrength.STRONG: "Strong",
    FootStrength.VERY_STRONG: "Very strong",
}

_FOOT_STRENGTH_FROM_TEXT = {
    "very weak": FootStrength.VERY_WEAK,
    "weak": FootStrength.WEAK,
    "reasonable": FootStrength.REASONABLE,
    "fairly strong": FootStrength.FAIRLY_STRONG,
    "strong": FootStrength.STRONG,
    "very strong": FootStrength.VERY_STRONG,
}

DEFAULT_FOOT_THRESHOLD = FootStrength.FAIRLY_STRONG


def coerce_foot_strength(value, default: FootStrength = DEFAULT_FOOT_THRESHOLD) -> FootStrength:
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return default
    if number in FootStrength._value2member_map_:
        return FootStrength(number)
    return default


def foot_strength_options() -> list[dict[str, str]]:
    return [
        {"label": f"{int(level)} · {FOOT_STRENGTH_NAMES[level]}", "value": str(int(level))}
        for level in FootStrength
    ]


def foot_strength(value: str) -> FootStrength | None:
    text = str(value or "").strip().lower()
    if not text or text == "-":
        return None
    if text in _FOOT_STRENGTH_FROM_TEXT:
        return _FOOT_STRENGTH_FROM_TEXT[text]
    try:
        number = int(float(text.replace(",", ".")))
    except ValueError:
        return None
    if 1 <= number <= 6:
        return FootStrength(number)
    if 1 <= number <= 20:
        return FootStrength(min(6, max(1, ((number - 1) * 6) // 20 + 1)))
    return None


def resolve_foot_thresholds(
    thresholds: dict[str, Any] | int | FootStrength | None = None,
) -> dict[str, FootStrength]:
    """Accept settings dict, legacy single threshold, or None → left/both/right levels."""
    defaults = {
        "left": FootStrength.VERY_STRONG,
        "both": DEFAULT_FOOT_THRESHOLD,
        "right": FootStrength.VERY_STRONG,
    }
    if thresholds is None:
        return dict(defaults)
    if isinstance(thresholds, (int, FootStrength)) or (
        isinstance(thresholds, str) and str(thresholds).strip().isdigit()
    ):
        level = coerce_foot_strength(thresholds)
        return {"left": level, "both": level, "right": level}
    if not isinstance(thresholds, dict):
        return dict(defaults)
    # Support either flat thresholds or nested foot_thresholds from settings.
    src = thresholds.get("foot_thresholds") if "foot_thresholds" in thresholds else thresholds
    if not isinstance(src, dict):
        src = {}
    return {
        "left": coerce_foot_strength(src.get("left"), defaults["left"]),
        "both": coerce_foot_strength(src.get("both"), defaults["both"]),
        "right": coerce_foot_strength(src.get("right"), defaults["right"]),
    }


def foot_match(
    row: dict[str, Any],
    foot_filter: str,
    thresholds: dict[str, Any] | int | FootStrength | None = None,
) -> bool:
    levels = resolve_foot_thresholds(thresholds)
    left = foot_strength(row.get("Left Foot") or "")
    right = foot_strength(row.get("Right Foot") or "")
    if left is None or right is None:
        return False
    # Sided filters only require that foot; Both requires both ≥ threshold (overlap OK).
    if foot_filter == "foot-L":
        return left >= levels["left"]
    if foot_filter == "foot-R":
        return right >= levels["right"]
    if foot_filter == "foot-B":
        return left >= levels["both"] and right >= levels["both"]
    return True


def foot_filter_help(thresholds: dict[str, Any] | int | FootStrength | None = None) -> str:
    levels = resolve_foot_thresholds(thresholds)
    left = FOOT_STRENGTH_NAMES[levels["left"]].lower()
    both = FOOT_STRENGTH_NAMES[levels["both"]].lower()
    right = FOOT_STRENGTH_NAMES[levels["right"]].lower()
    return (
        f"Left: left foot at least {left}. "
        f"Right: right foot at least {right}. "
        f"Both: each foot at least {both}. "
        "Players can match more than one filter. "
        "Click the active filter again to clear it."
    )


def foot_filter_hints(thresholds: dict[str, Any] | int | FootStrength | None = None) -> dict[str, str]:
    levels = resolve_foot_thresholds(thresholds)
    left = FOOT_STRENGTH_NAMES[levels["left"]].lower()
    both = FOOT_STRENGTH_NAMES[levels["both"]].lower()
    right = FOOT_STRENGTH_NAMES[levels["right"]].lower()
    return {
        "foot-L": f"Left foot at least {left}.",
        "foot-B": f"Both feet at least {both}.",
        "foot-R": f"Right foot at least {right}.",
    }


def score_band(
    score: float,
    elite: float = 14,
    good: float = 12,
    ok: float = 10,
) -> str:
    if score >= elite:
        return "elite"
    if score >= good:
        return "good"
    if score >= ok:
        return "ok"
    return "poor"


def score_players(
    players: list[dict[str, Any]],
    role_ids: list[str],
    *,
    tier_weights: dict[str, float] | None = None,
    set_piece_profiles: list[dict] | None = None,
) -> list[dict[str, Any]]:
    weights = _resolve_tier_weights(tier_weights) if tier_weights else None
    configs = []
    for role_id in role_ids:
        if role_id not in pc.all_positions:
            continue
        cfg = pc.all_positions[role_id]
        configs.append(
            (
                role_id,
                column_label(role_id, cfg),
                cfg,
                role_groups(role_id),
            )
        )
    scored = []
    for player in players:
        row = {
            "Name": player["name"],
            "Age": to_int(player["age"]) if player.get("age") else "-",
            "Club": player["club"] or "-",
            "Division": player["division"] or "-",
            "Nation": player["nation"] or "-",
            "Position": player["position"] or "-",
            "Best Pos": player["best_pos"] or "-",
            "Style": player["style"] or "-",
            "Height": player["height"] or "-",
            "Left Foot": player["left_foot"] or "-",
            "Right Foot": player["right_foot"] or "-",
            "Rec": player["rec"] if player["rec"] not in ("", "-") else "-",
            "Inf": player["inf"] or "-",
            "Injury": player["injury"] if player["injury"] not in ("", "-") else "-",
            "Squad": player["squad"] or "-",
            "PosGroups": player.get("pos_groups") or [],
        }
        apply_set_piece_scores(
            row,
            player.get("attrs") or {},
            tier_weights=weights,
            profiles=set_piece_profiles,
        )
        best_label = ""
        best_score = -1.0
        for role_id, label, cfg, groups in configs:
            if weights:
                key_w = weights["key"]
                pref_w = weights["preferred"]
                useful_w = weights["useful"]
                divisor = (
                    key_w * len(cfg.get("key_attrs") or [])
                    + pref_w * len(cfg.get("preferred_attrs") or [])
                    + useful_w * len(cfg.get("useful_attrs") or [])
                )
            else:
                key_w = cfg["key_weight"]
                pref_w = cfg["preferred_weight"]
                useful_w = cfg["useful_weight"]
                divisor = cfg["divisor"]
            score = calculate_score(
                player["attrs"],
                cfg["key_attrs"],
                cfg["preferred_attrs"],
                cfg["useful_attrs"],
                key_w,
                pref_w,
                useful_w,
                divisor,
            )
            row[label] = score
            row[f"{label} eligible"] = any(
                is_eligible(player["positions"], group) for group in groups
            )
            if score > best_score:
                best_score = score
                best_label = label
        row["Best Role"] = best_label
        row["Best Role Score"] = best_score if best_score >= 0 else 0
        scored.append(row)
    return scored


def scored_csv(rows: list[dict[str, Any]], role_labels: list[str]) -> str:
    fieldnames = [
        "Name",
        "Age",
        "Club",
        "Division",
        "Nation",
        "Position",
        "Best Pos",
        "Style",
        "Height",
        "Left Foot",
        "Right Foot",
        "Rec",
        "Inf",
        "Injury",
        "Squad",
        *role_labels,
        *[f"{label} eligible" for label in role_labels],
        "Best Role Score",
        "Best Role",
    ]
    buf = io.StringIO()
    writer = csv.DictWriter(
        buf, fieldnames=fieldnames, delimiter=";", extrasaction="ignore", lineterminator="\n"
    )
    writer.writeheader()
    for row in rows:
        out = {key: row.get(key, "-") for key in fieldnames}
        for key, value in out.items():
            if value in (None, ""):
                out[key] = "-"
        writer.writerow(out)
    return buf.getvalue()


PLANNED_SQUAD_IDENTITY = [
    "Name",
    "Age",
    "Height",
    "Position",
    "Club",
    "Division",
    "Nation",
    "Rec",
    "Injury",
    "Left Foot",
    "Right Foot",
]


def player_row_key(row: dict[str, Any]) -> str:
    name = str(row.get("Name") or "").strip()
    club = str(row.get("Club") or "").strip()
    return f"{name}|{club}" if name else ""


def expand_view_role_columns(
    view_roles: list[str],
    combos: list[dict[str, str]] | None = None,
    *,
    include_parts: bool = True,
) -> list[str]:
    combo_by_col = {
        combo_meta(item["ip"], item["oop"])["column"]: combo_meta(item["ip"], item["oop"])
        for item in normalize_combos(combos)
    }
    expanded: list[str] = []
    for role in view_roles:
        if role not in expanded:
            expanded.append(role)
        if not include_parts:
            continue
        meta = combo_by_col.get(role)
        if meta:
            for column in (meta["ip_column"], meta["oop_column"]):
                if column not in expanded:
                    expanded.append(column)
    return expanded


def combo_column_labels(combos: list[dict[str, str]] | None = None) -> list[str]:
    return [
        combo_meta(item["ip"], item["oop"])["column"]
        for item in normalize_combos(combos)
    ]


def planned_squad_fieldnames(
    view_roles: list[str],
    combos: list[dict[str, str]] | None = None,
    set_pieces_selected: list[str] | None = None,
    *,
    include_parts: bool = True,
) -> list[str]:
    cols = list(PLANNED_SQUAD_IDENTITY)
    cols.append("View roles")
    for col in expand_view_role_columns(view_roles, combos, include_parts=include_parts):
        cols.append(col)
    for col in set_piece_columns(set_pieces_selected):
        if col not in cols:
            cols.append(col)
    return cols


def planned_squad_export_rows(
    rows: list[dict[str, Any]],
    marked_keys: list[str],
    view_roles: list[str],
    combos: list[dict[str, str]] | None = None,
    set_pieces_selected: list[str] | None = None,
    *,
    include_parts: bool = True,
) -> list[dict[str, Any]]:
    marked = set(marked_keys or [])
    if not marked or not view_roles:
        return []
    fieldnames = planned_squad_fieldnames(
        view_roles, combos, set_pieces_selected, include_parts=include_parts
    )
    view_label = ", ".join(view_roles)
    out: list[dict[str, Any]] = []
    for row in rows:
        if player_row_key(row) not in marked:
            continue
        item: dict[str, Any] = {"View roles": view_label}
        for key in fieldnames:
            if key == "View roles":
                continue
            val = row.get(key)
            item[key] = val if val not in (None, "") else "-"
        out.append(item)
    return out


def planned_squad_csv(
    rows: list[dict[str, Any]],
    marked_keys: list[str],
    view_roles: list[str],
    combos: list[dict[str, str]] | None = None,
    set_pieces_selected: list[str] | None = None,
    *,
    include_parts: bool = True,
) -> str:
    fieldnames = planned_squad_fieldnames(
        view_roles, combos, set_pieces_selected, include_parts=include_parts
    )
    export_rows = planned_squad_export_rows(
        rows,
        marked_keys,
        view_roles,
        combos,
        set_pieces_selected,
        include_parts=include_parts,
    )
    buf = io.StringIO()
    writer = csv.DictWriter(
        buf, fieldnames=fieldnames, delimiter=";", extrasaction="ignore", lineterminator="\n"
    )
    writer.writeheader()
    for row in export_rows:
        out = {key: row.get(key, "-") for key in fieldnames}
        for key, value in out.items():
            if value in (None, ""):
                out[key] = "-"
        writer.writerow(out)
    return buf.getvalue()
