"""Parse FM player exports and score selected roles."""
from __future__ import annotations

import csv
import io
from typing import Any

import config.role_weight_config as pc
from utils import calculate_score, format_position_name

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
    "Name": ["Name"],
    "Age": ["Age"],
    "Club": ["Club"],
    "Division": ["Division", "Div"],
    "Nation": ["Based In", "Nat", "Nationality"],
    "Position": ["Position"],
    "SecPosition": ["Sec. Position", "Secondary Position", "Sec Position"],
    "BestPos": ["Best Pos", "Best Position"],
    "Style": ["Style"],
    "Height": ["Height"],
    "LeftFoot": ["Left Foot", "L"],
    "RightFoot": ["Right Foot", "R"],
    "Rec": ["Rec.", "Rec"],
    "Inf": ["Inf"],
    "Injury": ["Injury"],
    "Squad": ["Squad"],
}

DEFAULT_ROLES = [
    "Sweeper_keeper_Support",
    "Ball_playing_defender_Defend",
    "Wing_Back_Support",
    "Central_midfielder_Support",
    "Mezzala_Support",
    "Inside_forward_Attack",
]

_ROLE_GROUP = {}
for _name, _group in [
    (pc.gk_positions, "gk"),
    (pc.cb_positions, "cb"),
    (pc.fb_positions, "fb"),
    (pc.wb_positions, "wb"),
    (pc.dm_positions, "dm"),
    (pc.cm_positions, "cm"),
    (pc.am_positions, "am"),
    (pc.w_positions, "w"),
    (pc.w_am_positions, "wam"),
    (pc.st_positions, "st"),
]:
    for _role in _name:
        _ROLE_GROUP[_role] = _group


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
        if group == "w" and pos in ("M", "AM") and ("L" in area or "R" in area):
            return True
        if group == "wam" and (
            (pos == "AM" and ("L" in area or "R" in area))
            or (pos == "M" and ("L" in area or "R" in area))
            or pos == "ST"
        ):
            return True
        if group == "st" and pos == "ST":
            return True
    return False


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
                "positions": parse_positions(pos) + parse_positions(sec),
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


def role_options() -> list[dict[str, str]]:
    options = []
    for role_id in pc.all_positions:
        options.append({"label": format_position_name(role_id), "value": role_id})
    return options


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
                format_position_name(role_id),
                cfg,
                _ROLE_GROUP.get(role_id, ""),
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
        }
        best_label = ""
        best_score = -1.0
        for role_id, label, cfg, group in configs:
            score = calculate_score(
                player["attrs"],
                cfg["key_attrs"],
                cfg["green_attrs"],
                cfg["blue_attrs"],
                cfg["key_weight"],
                cfg["green_weight"],
                cfg["blue_weight"],
                cfg["divisor"],
            )
            row[label] = score
            row[f"{label} eligible"] = is_eligible(player["positions"], group)
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
