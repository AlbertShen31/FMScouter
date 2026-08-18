"""Parse FM player exports and score selected FM26 roles.

A role belongs to one or more position groups (`gk`, `cb`, `wm`, `w`, …).
`wm` is wide midfielders; `w` is wingers (formerly labelled wide attackers).
Eligibility is OR across a role’s groups. See docs/ARCHITECTURE.md.
"""
from __future__ import annotations

import csv
import io
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
        "detail": "raw attribute only",
        "raw": "LTh",
        "score": None,
        "key": (),
        "preferred": (),
        "useful": (),
    },
    {
        "id": "pens",
        "label": "Penalties",
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
        "detail": "in the box",
        "raw": None,
        "score": "Aerial",
        "key": ("Jum", "Hea"),
        "preferred": ("Str",),
        "useful": (),
    },
)


def set_piece_divisor(profile: dict) -> int:
    return (
        pc.KEY_WEIGHT * len(profile["key"])
        + pc.PREFERRED_WEIGHT * len(profile["preferred"])
        + pc.USEFUL_WEIGHT * len(profile["useful"])
    )


def set_piece_formula(profile: dict) -> str:
    if not profile.get("score"):
        return f"{profile['label']} = {profile['raw']} (raw only)"
    terms = []
    for attr in profile["key"]:
        terms.append(f"{pc.KEY_WEIGHT:g}×{attr}")
    for attr in profile["preferred"]:
        terms.append(f"{pc.PREFERRED_WEIGHT:g}×{attr}")
    for attr in profile["useful"]:
        if pc.USEFUL_WEIGHT == 1:
            terms.append(attr)
        else:
            terms.append(f"{pc.USEFUL_WEIGHT:g}×{attr}")
    return f"{profile['label']} = ({' + '.join(terms)}) ÷ {set_piece_divisor(profile):g}"


def set_piece_hint() -> str:
    return (
        "Combined scores use the same "
        f"{pc.KEY_WEIGHT:g}× key / {pc.PREFERRED_WEIGHT:g}× preferred / "
        f"{pc.USEFUL_WEIGHT:g}× useful weights as roles. "
        "DFK is a shot from the dead ball; IFK is a delivery into the box. "
        "Checking DFK or IFK also adds Fre once."
    )


def set_piece_sort_column(piece_id: str) -> str | None:
    for profile in SET_PIECE_PROFILES:
        if profile["id"] == piece_id:
            return profile.get("score") or profile.get("raw")
    return None


def set_piece_filter_columns(piece_id: str) -> str:
    """Column used for min-score filtering on a checked set-piece type."""
    return set_piece_sort_column(piece_id) or ""


def set_piece_columns(selected) -> list[str]:
    chosen = set(selected or [])
    cols = []
    seen: set[str] = set()
    for profile in SET_PIECE_PROFILES:
        if profile["id"] not in chosen:
            continue
        raw = profile.get("raw")
        score = profile.get("score")
        if raw and raw not in seen:
            cols.append(raw)
            seen.add(raw)
        if score and score not in seen:
            cols.append(score)
            seen.add(score)
    return cols


def apply_set_piece_scores(row: dict[str, Any], attrs: dict[str, int]) -> None:
    written_raw: set[str] = set()
    for profile in SET_PIECE_PROFILES:
        raw = profile.get("raw")
        if raw and raw not in written_raw:
            value = attrs.get(raw)
            row[raw] = value if value not in (None, "") else "-"
            written_raw.add(raw)
        score = profile.get("score")
        if not score:
            continue
        row[score] = calculate_score(
            attrs,
            list(profile["key"]),
            list(profile["preferred"]),
            list(profile["useful"]),
            pc.KEY_WEIGHT,
            pc.PREFERRED_WEIGHT,
            pc.USEFUL_WEIGHT,
            set_piece_divisor(profile),
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
    "Style": ["Style"],
    "Height": ["Height"],
    "LeftFoot": ["Left Foot", "LFoot", "L"],
    "RightFoot": ["Right Foot", "RFoot", "R"],
    "Rec": ["Rec.", "Rec"],
    "Inf": ["Inf"],
    "Injury": ["Injury"],
    "Squad": ["Squad"],
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
    same_name = ip_meta["name"] == oop_meta["name"]
    name = ip_meta["name"] if same_name else f"{ip_meta['name']} / {oop_meta['name']}"
    code = f"{ip_meta['code']}+{oop_meta['code']}"
    return {
        "id": combo_id(ip, oop),
        "ip": ip,
        "oop": oop,
        "column": combo_column(ip, oop),
        "ip_column": ip_meta["column"],
        "oop_column": oop_meta["column"],
        "code": code,
        "name": name,
        "compact": f"{abbr} {code} {name}".strip(),
        "compact_name": f"{abbr} {name}".strip(),
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
    for full, abbr in ATTR_MAP.items():
        if full in row:
            attrs[abbr] = to_int(row[full])
        elif abbr in row:
            attrs[abbr] = to_int(row[abbr])
    return attrs


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
    players = []
    for raw in reader:
        if not raw or all(not cell.strip() for cell in raw):
            continue
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
                "age": to_int(pick(row, IDENTITY["Age"])),
                "club": pick(row, IDENTITY["Club"]),
                "division": pick(row, IDENTITY["Division"]),
                "nation": pick(row, IDENTITY["Nation"]),
                "position": pos,
                "best_pos": pick(row, IDENTITY["BestPos"]),
                "style": pick(row, IDENTITY["Style"]),
                "height": pick(row, IDENTITY["Height"]).strip('"'),
                "left_foot": pick(row, IDENTITY["LeftFoot"]),
                "right_foot": pick(row, IDENTITY["RightFoot"]),
                "rec": pick(row, IDENTITY["Rec"]),
                "inf": pick(row, IDENTITY["Inf"]),
                "injury": pick(row, IDENTITY["Injury"]),
                "squad": pick(row, IDENTITY["Squad"]),
                "attrs": attrs,
                "attr_hits": attr_count(row),
                "positions": positions,
                "pos_groups": player_pos_groups(positions),
            }
        )
    if not players:
        raise ValueError("No player rows found. Check that the file is an FM CSV export.")
    avg_hits = sum(p["attr_hits"] for p in players) / len(players)
    if avg_hits < 8:
        raise ValueError(
            "This file does not include player attributes (Acceleration, Passing, "
            "Tackling, and so on). Export the attribute view from FM, not a stats-only view."
        )
    return players


def foot_strength(value: str) -> int:
    text = str(value or "").strip().lower()
    rating = {
        "very strong": 5,
        "strong": 4,
        "fairly strong": 3,
        "reasonable": 2,
        "weak": 1,
        "very weak": 0,
    }
    if text in rating:
        return rating[text]
    try:
        n = int(float(text.replace(",", ".")))
    except ValueError:
        return 0
    if 1 <= n <= 20:
        return round(n / 4)
    return 0


def foot_match(row: dict[str, Any], foot_filter: str) -> bool:
    lf = foot_strength(row.get("Left Foot") or "")
    rf = foot_strength(row.get("Right Foot") or "")
    if not lf and not rf:
        return False
    if foot_filter == "foot-L":
        return lf > rf and rf <= 2
    if foot_filter == "foot-R":
        return rf > lf and lf <= 2
    if foot_filter == "foot-B":
        return lf >= 3 and rf >= 3
    return True


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
    players: list[dict[str, Any]], role_ids: list[str]
) -> list[dict[str, Any]]:
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
            "Age": player["age"],
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
        apply_set_piece_scores(row, player.get("attrs") or {})
        best_label = ""
        best_score = -1.0
        for role_id, label, cfg, groups in configs:
            score = calculate_score(
                player["attrs"],
                cfg["key_attrs"],
                cfg["preferred_attrs"],
                cfg["useful_attrs"],
                cfg["key_weight"],
                cfg["preferred_weight"],
                cfg["useful_weight"],
                cfg["divisor"],
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
