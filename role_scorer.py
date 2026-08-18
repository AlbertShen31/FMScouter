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
        "name": pretty_role_name(role_id),
        "phase": phase_label(phase),
        "tone": phase_tone(phase),
        "is_gk": "yes" if phase_is_gk(phase, role_id, group) or "gk" in groups else "",
        "group": group,
        "groups": ",".join(groups),
        "group_label": group_labels(role_id),
    }


def role_option_label(role_id: str) -> str:
    meta = role_meta(role_id)
    return f"{meta['name']} ({meta['code']}) · {meta['phase']}"


def role_options(phase: str | None = None, keep: list[str] | None = None) -> list[dict]:
    """Flat `{label, value}` options. `phase` is All/IP/OOP/GK."""
    keep = set(keep or [])
    phase = (phase or "all").upper()
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
        prefix = group_labels(role_id) or next(
            (label for gid, label, _roles in GROUP_DEFS if gid == home),
            home,
        )
        options.append(
            {
                "label": f"{prefix} — {role_option_label(role_id)}",
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


def score_band(score: float) -> str:
    if score >= 14:
        return "elite"
    if score >= 11:
        return "good"
    if score >= 8:
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
                display_code(role_id, cfg),
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
