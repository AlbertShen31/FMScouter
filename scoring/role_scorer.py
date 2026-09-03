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
import services.role_config as role_config
from scoring.division_tiers import apply_division_tier
from scoring.personality_tiers import apply_personality_tier
from scoring.phases import phase_is_gk, phase_label, phase_matches, phase_tone, pretty_role_name
from scoring.utils import calculate_score

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
    "UniqueID": ["Unique ID", "UID"],
    "Age": ["Age"],
    "Club": ["Club"],
    "Division": ["Division", "Div"],
    # Nation = nationality code (ENG); Based In = country the club is in.
    "Nation": ["Nation", "Nat", "Nationality"],
    "BasedIn": ["Based In"],
    "SecondNation": ["2nd Nat", "Second Nationality", "Second Nation"],
    "Position": ["Position"],
    "SecPosition": ["Sec. Position", "Secondary Position", "Sec Position"],
    "BestPos": ["Best Pos", "Best Position"],
    "BestRole": ["Best Role"],
    "PositionRole": ["Position/Role", "Position / Role"],
    "Style": ["Style"],
    "Personality": ["Personality"],
    "MediaHandling": ["Media Handling"],
    "WorldReputation": ["World Reputation"],
    "WorldReputationGold": ["World Reputation Gold"],
    "WorldReputationSilver": ["World Reputation Silver"],
    "Ability": ["Ability", "CA"],
    "AbilityGold": ["Ability Gold"],
    "AbilitySilver": ["Ability Silver"],
    "Potential": ["Potential", "PA"],
    "PotentialGold": ["Potential Gold"],
    "PotentialSilver": ["Potential Silver"],
    "Height": ["Height"],
    "LeftFoot": ["Left Foot", "LFoot", "L"],
    "RightFoot": ["Right Foot", "RFoot", "R"],
    "Rec": ["Rec.", "Rec"],
    "Inf": ["Inf"],
    "Injury": ["Injury"],
    "InjuredOn": ["Injured On"],
    "TimeMissed": ["Time Missed"],
    "RecurringInjury": ["Recurring Injury"],
    "Squad": ["Squad"],
    "Picked": ["Picked"],
    "HomeGrownStatus": ["Home Grown Status"],
    "NationalTeam": ["National Team"],
    "IntAppsSeason": [
        "International Appearances (Season)",
        "Int Apps (Season)",
    ],
    "IntAssists": ["International Assists", "Int Assists"],
    "AvgRatingClub": [
        "Average Rating Club",
        "Rating",
    ],
    "AvgRatingInt": [
        "Average Rating International",
        "Avg Rating International",
    ],
    "Last5Club": [
        "Last 5 Games Club",
    ],
    "Last5Int": [
        "Last 5 Games International",
        "Last 5 Games Int",
    ],
    "FormClub": ["Form Club"],
    "FormInt": ["Form International", "Form Int"],
    "IntGoalsConceded": ["International Goals Conceded"],
    "IntGls": ["Int Gls", "International Goals"],
    "IntApps": ["Int Apps", "International Appearances"],
    "YthApps": ["Yth Apps", "Youth Apps"],
    "YthGls": ["Yth Gls", "Youth Goals"],
}

# Contract / transfer / wage columns from the Moneyball view (FM26).
FINANCE_CSV = {
    "min_release_clause": ["Minimum Fee Release Clause"],
    "active_non_promotion_release": ["Active Non Promotion Release Clause"],
    "active_relegation_release": ["Active Relegation Release Clause"],
    "min_release_clause_expires": ["Minimum Fee Release Clause - Expiry Date"],
    "min_release_clause_continental": [
        "Minimum Fee Release Clause (Clubs in a Continental Competition)"
    ],
    "min_release_clause_continental_expires": [
        "Minimum Fee Release Clause (Clubs in a Continental Competition) - Expiry Date"
    ],
    "min_release_clause_major_continental": [
        "Minimum Fee Release Clause (Clubs in a Major Continental Competition)"
    ],
    "min_release_clause_major_continental_expires": [
        "Minimum Fee Release Clause (Clubs in a Major Continental Competition) - Expiry Date"
    ],
    "min_release_clause_higher_division": [
        "Minimum Fee Release Clause (Domestic Clubs in Higher Division)"
    ],
    "min_release_clause_higher_division_expires": [
        "Minimum Fee Release Clause (Domestic Clubs in Higher Division) - Expiry Date"
    ],
    "min_release_clause_domestic": [
        "Minimum Fee Release Clause (Domestic Clubs)"
    ],
    "min_release_clause_domestic_expires": [
        "Minimum Fee Release Clause (Domestic Clubs) - Expiry Date"
    ],
    "min_release_clause_foreign": [
        "Minimum Fee Release Clause (Foreign Clubs)"
    ],
    "min_release_clause_foreign_expires": [
        "Minimum Fee Release Clause (Foreign Clubs) - Expiry Date"
    ],
    "non_promotion_release": ["Non Promotion Release Clause"],
    "relegation_release": ["Relegation Release Clause"],
    "promotion_salary_raise": ["Promotion Salary Raise"],
    "relegation_salary_drop": ["Relegation Salary Drop"],
    "top_division_promotion_salary_raise": [
        "Top Division Promotion Salary raise",
        "Top Division Promotion Salary Raise",
    ],
    "top_division_relegation_salary_drop": [
        "Top Division Relegation Salary Drop",
    ],
    "yearly_salary_raise": ["Yearly Salary Raise"],
    "ffp_contribution": ["FFP Contribution"],
    "contract_expires": ["Expires"],
    "work_permit_required": ["Work Permit Required"],
    "wp_needed": ["WP Needed"],
    "transfer_value": ["Transfer Value"],
    "transfer_status": ["Transfer Status"],
    "loan_status": ["Loan Status"],
    "salary": ["Salary"],
    "appearance_fee": ["Appearance Fee"],
    "unused_sub_fee": ["Unused Substitute Fee"],
    "goal_bonus": ["Goal Bonus"],
    "assist_bonus": ["Assist Bonus"],
    "shutout_bonus": ["Shutout Bonus"],
    "int_cap_bonus": ["Int Cap Bonus"],
}

# FM26 Moneyball export: star ratings (Ability / Potential / World Reputation) are unreliable.
CAREER_CSV = {
    "at_apps": ["AT Apps"],
    "at_gls": ["AT Gls"],
    "at_league_apps": ["AT League Apps"],
    "at_league_goals": ["AT League Goals"],
}

DISCIPLINE_CSV = {
    "appearances": ["Appearances"],
    "yellow_cards": ["Yellow Cards"],
    "red_cards": ["Red cards", "Red Cards"],
    "fouls_made": ["Fouls Made"],
    "fouls_against": ["Fouls Against"],
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

GROUP_LABELS = {gid: label for gid, label, _roles in GROUP_DEFS}

DEFAULT_PARTIAL_ELIGIBILITY_RULES = (
    {"primary": "fb", "secondary": "wb", "mutual": True},
    {"primary": "dm", "secondary": "cm", "mutual": True},
    {"primary": "cm", "secondary": "am", "mutual": True},
    {"primary": "wm", "secondary": "w", "mutual": True},
    {"primary": "st", "secondary": "w", "mutual": True},
)

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


ROLE_REF_SEP = "@"


def decode_role_ref(value: str) -> tuple[str, str | None]:
    """Split a stored role ref into ``(role_id, scoring_group | None)``."""
    text = str(value or "").strip()
    if ROLE_REF_SEP not in text:
        return text, None
    role_id, _, group = text.partition(ROLE_REF_SEP)
    role_id = role_id.strip()
    group = group.strip().lower() or None
    if role_id not in pc.all_positions:
        return text, None
    if group and group in role_groups(role_id):
        return role_id, group
    return role_id, None


def encode_role_ref(role_id: str, group: str | None) -> str:
    """Persist a bucket-specific pick for cross-bucket roles."""
    group = str(group or "").strip().lower()
    groups = role_groups(role_id)
    if not group or len(groups) <= 1 or group not in groups:
        return role_id
    return f"{role_id}{ROLE_REF_SEP}{group}"


def is_cross_bucket(role_id: str) -> bool:
    return len(role_groups(role_id)) > 1


def scoring_groups(role_id: str, group: str | None = None) -> list[str]:
    """Position groups used for eligibility; one bucket when explicitly chosen."""
    groups = role_groups(role_id)
    if group and group in groups:
        return [group]
    return groups


def canonical_role_ref(role_ref: str, *, position_group: str | None = None) -> str:
    """Normalize a role ref, inferring bucket from slot position when needed."""
    role_ref = str(role_ref or "").strip()
    if not role_ref:
        return ""
    role_id, group = decode_role_ref(role_ref)
    if role_id not in pc.all_positions:
        return role_ref
    if group:
        return encode_role_ref(role_id, group)
    pos_group = str(position_group or "").strip().lower()
    groups = role_groups(role_id)
    if len(groups) > 1 and pos_group in groups:
        return encode_role_ref(role_id, pos_group)
    return role_id


def _role_ref_kept(role_id: str, bucket: str | None, keep: set[str]) -> bool:
    if not keep:
        return False
    if role_id in keep:
        return True
    if bucket and encode_role_ref(role_id, bucket) in keep:
        return True
    for item in keep:
        kept_id, kept_bucket = decode_role_ref(item)
        if kept_id != role_id:
            continue
        if not kept_bucket or not bucket or kept_bucket == bucket:
            return True
    return False


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


def compact_role_label(
    role_id: str,
    *,
    with_phase: bool = True,
    group: str | None = None,
) -> str:
    """Compact UI name, e.g. 'WM/W Inside Winger IP' or 'FB Wing Back IP'."""
    if group:
        abbr = group.upper()
    else:
        abbr = group_abbr(role_id)
    name = pretty_role_name(role_id)
    parts = [part for part in (abbr, name) if part]
    if with_phase:
        phase = phase_label((pc.all_positions.get(role_id) or {}).get("phase", ""))
        if phase and phase != "—":
            parts.append(phase)
    return " ".join(parts)

# Player-position filter cards. Matching is exact FM positions (see
# matches_pos_card), aligned with role position groups.
POS_CARDS = [
    ("all", "All", "", "all"),
    ("GK", "Goalkeeper", "GK", "gk"),
    ("DEF", "Center Back", "CB", "def"),
    ("FB", "Full Back", "FB / WB", "fb"),
    ("DM", "Defensive Midfield", "DM", "dm"),
    ("CM", "Central Midfield", "M (C)", "cm"),
    ("AM", "Attacking Midfield", "AM (C)", "am"),
    ("WM", "Wide Midfielders", "ML / MR", "wm"),
    ("W", "Winger", "AML / AMR", "w"),
    ("ST", "Striker", "ST", "st"),
]

# Role groups aligned with each card (documentation / tooling). Position-bar
# filters use matches_pos_card, not this map.
POS_CARD_GROUPS = {
    "GK": ("gk",),
    "DEF": ("cb",),
    "FB": ("fb", "wb"),
    "DM": ("dm",),
    "CM": ("cm",),
    "AM": ("am",),
    "WM": ("wm",),
    "W": ("w",),
    "ST": ("st",),
}

GROUP_ABBR_TONE = {
    "GK": "gk",
    "CB": "def",
    "FB": "fb",
    "WB": "fb",
    "DM": "dm",
    "CM": "cm",
    "AM": "am",
    "WM": "wm",
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


def extract_record_fields(row: dict[str, str]) -> dict[str, str]:
    """Career totals and discipline columns from the stats export (when present)."""
    out: dict[str, str] = {}
    for key, aliases in {**CAREER_CSV, **DISCIPLINE_CSV}.items():
        value = pick(row, aliases)
        if value not in ("", "-"):
            out[key] = value
    return out


_UNSET_STATUS = frozenset({"not set", "no recurring injuries"})


def _present_csv_text(value: str, *, drop_unset: bool = False) -> str:
    text = str(value or "").strip()
    if text in ("", "-", "—"):
        return ""
    if drop_unset and text.casefold() in _UNSET_STATUS:
        return ""
    return text


def extract_injury_fields(row: dict[str, str]) -> dict[str, str]:
    """Injured On / Time Missed / Recurring Injury from the export."""
    return {
        "injured_on": _present_csv_text(pick(row, IDENTITY["InjuredOn"])),
        "time_missed": _present_csv_text(pick(row, IDENTITY["TimeMissed"])),
        "recurring_injury": _present_csv_text(
            pick(row, IDENTITY["RecurringInjury"]), drop_unset=True
        ),
    }


def extract_finance_fields(row: dict[str, str]) -> dict[str, str]:
    """Contract, transfer, wage, and release-clause columns when present."""
    out: dict[str, str] = {}
    status_keys = {"transfer_status", "loan_status"}
    for key, aliases in FINANCE_CSV.items():
        value = _present_csv_text(
            pick(row, aliases), drop_unset=key in status_keys
        )
        if value:
            out[key] = value
    return out


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
        if group == "fb" and pos == "D" and ("L" in area or "R" in area):
            return True
        if group == "wb" and pos == "WB":
            return True
        if group == "dm" and pos == "DM":
            return True
        if group == "cm" and pos == "M" and "C" in area:
            return True
        if group == "am" and pos == "AM" and "C" in area:
            return True
        # Wide midfielders: ML / MR only.
        if group == "wm" and pos == "M" and ("L" in area or "R" in area):
            return True
        # Wingers: AML / AMR only (ST is partial via st↔w).
        if group == "w" and pos == "AM" and ("L" in area or "R" in area):
            return True
        if group == "st" and pos == "ST":
            return True
    return False


# Built-in partial adjacency for yellow position match.
def build_partial_adjacency(rules: list[dict] | None) -> dict[str, frozenset[str]]:
    """Map each role group to groups that grant partial eligibility."""
    adj: dict[str, set[str]] = {}
    for rule in rules or []:
        if not isinstance(rule, dict):
            continue
        primary = str(rule.get("primary") or "").strip().lower()
        secondary = str(rule.get("secondary") or "").strip().lower()
        if primary not in pc.GROUP_IDS or secondary not in pc.GROUP_IDS:
            continue
        if primary == secondary:
            continue
        adj.setdefault(primary, set()).add(secondary)
        if rule.get("mutual", True):
            adj.setdefault(secondary, set()).add(primary)
    return {key: frozenset(values) for key, values in adj.items()}


def default_partial_eligibility_rules() -> list[dict]:
    return [dict(rule) for rule in DEFAULT_PARTIAL_ELIGIBILITY_RULES]


def default_partial_adjacency() -> dict[str, frozenset[str]]:
    return build_partial_adjacency(list(DEFAULT_PARTIAL_ELIGIBILITY_RULES))


def _default_partial_adjacency() -> dict[str, frozenset[str]]:
    return default_partial_adjacency()


def _resolve_partial_adjacency(
    partial_adjacency: dict[str, frozenset[str]] | None,
) -> dict[str, frozenset[str]]:
    if partial_adjacency is not None:
        return partial_adjacency
    return _default_partial_adjacency()

ELIGIBILITY_FULL = "full"
ELIGIBILITY_PARTIAL = "partial"
ELIGIBILITY_NONE = "none"


def normalize_eligibility(value) -> str:
    """Map stored eligible values (legacy bool or level string) to a level."""
    if value is True or value in (ELIGIBILITY_FULL, "yes"):
        return ELIGIBILITY_FULL
    if value == ELIGIBILITY_PARTIAL:
        return ELIGIBILITY_PARTIAL
    return ELIGIBILITY_NONE


def is_fully_eligible(value) -> bool:
    return normalize_eligibility(value) == ELIGIBILITY_FULL


def is_scoring_eligible(value) -> bool:
    """Full or partial — player is position-viable for the role."""
    return normalize_eligibility(value) != ELIGIBILITY_NONE


def player_matched_groups(positions: list[dict[str, str]]) -> set[str]:
    return {group for group in pc.GROUP_IDS if is_eligible(positions, group)}


def combine_eligibility_levels(*values) -> str:
    levels = [normalize_eligibility(value) for value in values]
    if all(level == ELIGIBILITY_FULL for level in levels):
        return ELIGIBILITY_FULL
    if all(level == ELIGIBILITY_NONE for level in levels):
        return ELIGIBILITY_NONE
    return ELIGIBILITY_PARTIAL


def role_eligibility_level(
    positions: list[dict[str, str]],
    groups: list[str],
    *,
    partial_adjacency: dict[str, frozenset[str]] | None = None,
) -> str:
    """Full = exact group match; partial = adjacent group only; else none."""
    if not groups:
        return ELIGIBILITY_NONE
    adjacency = _resolve_partial_adjacency(partial_adjacency)
    player_groups = player_matched_groups(positions)
    role_set = set(groups)
    if player_groups & role_set:
        return ELIGIBILITY_FULL
    neighbor_groups: set[str] = set()
    for group in role_set:
        neighbor_groups |= adjacency.get(group, frozenset())
    if player_groups & neighbor_groups:
        return ELIGIBILITY_PARTIAL
    return ELIGIBILITY_NONE


def matches_pos_card(positions: list[dict[str, str]], card: str) -> bool:
    """Exact FM position match for a player-position filter card."""
    for item in positions:
        pos, area = item["position"], item["area"]
        if card == "GK" and pos == "GK":
            return True
        if card == "DEF" and pos == "D" and "C" in area:
            return True
        if card == "FB" and (
            pos == "WB" or (pos == "D" and ("L" in area or "R" in area))
        ):
            return True
        if card == "DM" and pos == "DM":
            return True
        if card == "CM" and pos == "M" and "C" in area:
            return True
        if card == "AM" and pos == "AM" and "C" in area:
            return True
        if card == "WM" and pos == "M" and ("L" in area or "R" in area):
            return True
        if card == "W" and pos == "AM" and ("L" in area or "R" in area):
            return True
        if card == "ST" and pos == "ST":
            return True
    return False


def player_pos_groups(positions: list[dict[str, str]]) -> list[str]:
    return [card for card, *_ in POS_CARDS[1:] if matches_pos_card(positions, card)]


def best_pos_group(best_pos: str | None) -> str | None:
    """Map FM Best Pos text (e.g. ``AM (R)``, ``D (C)``) to a primary role group."""
    text = (best_pos or "").strip()
    if not text or text == "-":
        return None
    items = parse_positions(text)
    if not items:
        return None
    item = items[0]
    pos, area = item["position"], item["area"]
    if pos == "GK":
        return "gk"
    if pos == "D":
        if "L" in area or "R" in area:
            return "fb"
        if "C" in area:
            return "cb"
    if pos == "WB":
        return "wb"
    if pos == "DM":
        return "dm"
    if pos == "M":
        if "L" in area or "R" in area:
            return "wm"
        if "C" in area:
            return "cm"
    if pos == "AM":
        if "L" in area or "R" in area:
            return "w"
        if "C" in area:
            return "am"
    if pos == "ST":
        return "st"
    for group, _label, _roles in GROUP_DEFS:
        if is_eligible(items, group):
            return group
    return None


def group_label(group_id: str | None) -> str:
    if not group_id:
        return ""
    for gid, label, _roles in GROUP_DEFS:
        if gid == group_id:
            return label
    return (group_id or "").upper()


def score_player_role(
    player: dict[str, Any],
    role_id: str,
    *,
    tier_weights: dict[str, float] | None = None,
) -> float | None:
    """Score one player for one role using current pack weights."""
    cfg = pc.all_positions.get(role_id)
    if not cfg:
        return None
    weights = _resolve_tier_weights(tier_weights) if tier_weights else None
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
    return float(
        calculate_score(
            player.get("attrs") or {},
            cfg["key_attrs"],
            cfg["preferred_attrs"],
            cfg["useful_attrs"],
            key_w,
            pref_w,
            useful_w,
            divisor,
        )
    )


def _phase_bucket(role_id: str) -> str | None:
    """IP or OOP (keeper IP_GK / OOP_GK count as IP / OOP)."""
    cfg = pc.all_positions.get(role_id) or {}
    tone = phase_tone(cfg.get("phase", ""))
    if tone in ("ip", "oop"):
        return tone.upper()
    return None


def player_role_highlights(
    player: dict[str, Any],
    *,
    tier_weights: dict[str, float] | None = None,
    partial_adjacency: dict[str, frozenset[str]] | None = None,
) -> dict[str, Any]:
    """Best IP/OOP roles in Best Pos group, and best IP/OOP in other available groups.

    Returns::

        {
          "best_group": "cb",
          "best_group_label": "Centre-backs",
          "in_best": {"IP": {...}|None, "OOP": {...}|None},
          "other": {"IP": {...}|None, "OOP": {...}|None},
        }

    Each pick is ``{role_id, name, code, column, score, group_abbr, compact}``.
    """
    positions = player.get("positions") or []
    best_group = best_pos_group(player.get("best_pos"))
    empty = {"IP": None, "OOP": None}
    result = {
        "best_group": best_group,
        "best_group_label": group_label(best_group),
        "in_best": dict(empty),
        "other": dict(empty),
    }
    if not positions and not best_group:
        return result

    best_in = {"IP": None, "OOP": None}
    best_other = {"IP": None, "OOP": None}

    for role_id in iter_roles():
        groups = role_groups(role_id)
        if not groups:
            continue
        eligible_level = role_eligibility_level(
            positions, groups, partial_adjacency=partial_adjacency
        )
        eligible = eligible_level != ELIGIBILITY_NONE
        in_best = bool(best_group and best_group in groups)
        # Score roles for Best Pos even if the Position string omits that slot.
        if not eligible and not in_best:
            continue

        phase = _phase_bucket(role_id)
        if not phase:
            continue
        score = score_player_role(player, role_id, tier_weights=tier_weights)
        if score is None:
            continue
        meta = role_meta(role_id)
        pick = {
            "role_id": role_id,
            "name": meta["name"],
            "code": meta["code"],
            "column": meta["column"],
            "score": round(float(score), 2),
            "group_abbr": meta["group_abbr"],
            "compact": meta["compact"],
            "phase": phase,
        }
        if in_best:
            current = best_in[phase]
            if current is None or pick["score"] > current["score"]:
                best_in[phase] = pick
        if eligible and (not best_group or best_group not in groups):
            current = best_other[phase]
            if current is None or pick["score"] > current["score"]:
                best_other[phase] = pick

    result["in_best"] = best_in
    result["other"] = best_other
    return result


def _code_uses(code: str) -> int:
    return sum(1 for cfg in pc.all_positions.values() if cfg.get("role_code") == code)


def display_code(role_id: str, cfg: dict | None = None) -> str:
    """Short badge text for UI (e.g. CF). Phase is shown separately."""
    cfg = cfg or pc.all_positions.get(role_id, {})
    return cfg.get("role_code", role_id)


def has_bucket_role_refs(role_refs: list[str] | None) -> bool:
    """True when any selection uses an explicit position-bucket suffix."""
    for item in role_refs or []:
        if decode_role_ref(str(item))[1]:
            return True
    return False


def parse_bucket_column(column: str) -> tuple[str | None, str]:
    """Split a bucket-prefixed column id (``FB-WB-IP``) into group + remainder."""
    col = str(column or "")
    for gid in sorted(pc.GROUP_IDS, key=len, reverse=True):
        prefix = f"{gid.upper()}-"
        if col.startswith(prefix):
            remainder = col[len(prefix) :]
            # ``GK-OOP`` / ``FB-OOP`` are role+phase ids, not ``{bucket}-{role}``.
            if remainder in ("IP", "OOP", "GK"):
                continue
            return gid, remainder
    return None, col


def column_display_abbr(column: str) -> str:
    """Compact header text: strip bucket prefix and phase suffix."""
    _, base = parse_bucket_column(column)
    for suffix in ("-IP", "-OOP", "-GK"):
        if base.endswith(suffix):
            return base[: -len(suffix)]
    return base


_WB_HYBRID_CODES = frozenset({"AWB", "IWB", "PWB", "HWB"})


def hybrid_part_abbr(role_ref: str) -> str:
    """Short token for one side of a hybrid label (e.g. BGK, WB, FB)."""
    role_id, _ = decode_role_ref(role_ref)
    cfg = pc.all_positions.get(role_id, {})
    code = cfg.get("role_code", role_id)
    abbr = column_display_abbr(role_meta(role_ref)["column"])
    if code in _WB_HYBRID_CODES:
        return "WB"
    return abbr


def column_label(
    role_id: str,
    cfg: dict | None = None,
    *,
    scoring_group: str | None = None,
) -> str:
    """Score / CSV column key; disambiguates duplicate codes (e.g. CF-IP)."""
    cfg = cfg or pc.all_positions.get(role_id, {})
    code = cfg.get("role_code", role_id)
    if _code_uses(code) > 1:
        tone = phase_tone(cfg.get("phase", "")).upper()
        if tone:
            base = f"{code}-{tone}"
        else:
            base = code
    else:
        base = code
    if scoring_group and is_cross_bucket(role_id):
        return f"{scoring_group.upper()}-{base}"
    return base


def role_meta(role_ref: str) -> dict[str, str]:
    role_id, scoring_group = decode_role_ref(role_ref)
    cfg = pc.all_positions.get(role_id, {})
    phase = cfg.get("phase", "")
    groups = role_groups(role_id)
    group = scoring_group or (groups[0] if groups else _ROLE_GROUP.get(role_id, ""))
    group_abbr_text = group.upper() if scoring_group else group_abbr(role_id)
    return {
        "id": role_id,
        "ref": encode_role_ref(role_id, scoring_group) if scoring_group else role_id,
        "code": display_code(role_id, cfg),
        "column": column_label(role_id, cfg, scoring_group=scoring_group),
        "name": pretty_role_name(role_id),
        "phase": phase_label(phase),
        "tone": phase_tone(phase),
        "is_gk": "yes" if phase_is_gk(phase, role_id, group) or "gk" in groups else "",
        "group": group,
        "groups": ",".join(groups),
        "group_label": group_label(group) if scoring_group else group_labels(role_id),
        "group_abbr": group_abbr_text,
        "compact": compact_role_label(role_id, group=scoring_group),
        "compact_name": compact_role_label(role_id, with_phase=False, group=scoring_group),
        "short_label": column_display_abbr(
            column_label(role_id, cfg, scoring_group=scoring_group)
        ),
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
        ip_ref = str(item.get("ip") or "").strip()
        oop_ref = str(item.get("oop") or "").strip()
        ip_id, _ip_group = decode_role_ref(ip_ref)
        oop_id, _oop_group = decode_role_ref(oop_ref)
        if ip_id not in pc.all_positions or oop_id not in pc.all_positions:
            continue
        if phase_tone(pc.all_positions[ip_id].get("phase")) != "ip":
            continue
        if phase_tone(pc.all_positions[oop_id].get("phase")) != "oop":
            continue
        ip = canonical_role_ref(ip_ref)
        oop = canonical_role_ref(oop_ref)
        key = (ip, oop)
        if key in seen:
            continue
        seen.add(key)
        out.append({"ip": ip, "oop": oop})
    return out


def combo_column(ip: str, oop: str) -> str:
    return f"{role_meta(ip)['column']}+{role_meta(oop)['column']}"


def role_ref_variants(role_id: str) -> list[str]:
    """Plain role id plus bucket-specific refs for cross-bucket roles."""
    refs = [role_id]
    for group in role_groups(role_id):
        ref = encode_role_ref(role_id, group)
        if ref not in refs:
            refs.append(ref)
    return refs


def combo_meta_for_column(column: str) -> dict[str, str] | None:
    """Resolve hybrid meta for a combo column id (incl. cross-bucket refs)."""
    text = str(column or "").strip()
    if "+" not in text:
        return None
    ip_col, _, oop_col = text.partition("+")
    for ip_id in pc.all_positions:
        for ip_ref in role_ref_variants(ip_id):
            if role_meta(ip_ref)["column"] != ip_col:
                continue
            for oop_id in pc.all_positions:
                for oop_ref in role_ref_variants(oop_id):
                    if role_meta(oop_ref)["column"] != oop_col:
                        continue
                    return combo_meta(ip_ref, oop_ref)
    return None


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
    role_codes = f"{hybrid_part_abbr(ip)}+{hybrid_part_abbr(oop)}"
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
            row[f"{meta['column']} eligible"] = combine_eligibility_levels(
                row.get(f"{meta['ip_column']} eligible"),
                row.get(f"{meta['oop_column']} eligible"),
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
    for role_ref in role_ids:
        column = role_meta(role_ref)["column"]
        if column not in seen:
            labels.append(column)
            seen.add(column)
    return labels


def role_options(
    phase: str | None = None,
    group: str | None = None,
    keep: list[str] | None = None,
) -> list[dict]:
    """Flat `{label, value}` options. Cross-bucket roles get one entry per bucket."""
    keep_set = {str(item).strip() for item in (keep or []) if str(item).strip()}
    phase = (phase or "all").upper()
    if phase == "GK":
        phase = "ALL"
    group_filter = (group or "all").lower()
    options = []
    seen_values: set[str] = set()

    for role_id in iter_roles():
        cfg_phase = pc.all_positions[role_id].get("phase", "")
        groups = role_groups(role_id)
        home = groups[0] if groups else _ROLE_GROUP.get(role_id, "")
        phase_group = "gk" if "gk" in groups else home
        kept = _role_ref_kept(role_id, None, keep_set)

        if (
            phase not in ("", "ALL")
            and not phase_matches(cfg_phase, phase, role_id, phase_group)
            and not kept
            and not any(decode_role_ref(item)[0] == role_id for item in keep_set)
        ):
            continue

        if not is_cross_bucket(role_id):
            if (
                group_filter not in ("", "all")
                and group_filter not in groups
                and not _role_ref_kept(role_id, None, keep_set)
            ):
                continue
            value = role_id
            if value in seen_values:
                continue
            options.append(
                {
                    "label": compact_role_label(role_id),
                    "value": value,
                }
            )
            seen_values.add(value)
            continue

        buckets = list(groups)
        if group_filter not in ("", "all"):
            buckets = [bucket for bucket in buckets if bucket == group_filter]
        if not buckets and not kept:
            continue

        for bucket in buckets:
            value = encode_role_ref(role_id, bucket)
            if value in seen_values:
                continue
            if (
                phase not in ("", "ALL")
                and not phase_matches(cfg_phase, phase, role_id, phase_group)
                and not _role_ref_kept(role_id, bucket, keep_set)
            ):
                continue
            options.append(
                {
                    "label": compact_role_label(role_id, group=bucket),
                    "value": value,
                }
            )
            seen_values.add(value)

        if role_id in keep_set and role_id not in seen_values:
            options.append(
                {
                    "label": compact_role_label(role_id),
                    "value": role_id,
                }
            )
            seen_values.add(role_id)

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
                "unique_id": pick(row, IDENTITY["UniqueID"]),
                "age": pick(row, IDENTITY["Age"]),
                "club": pick(row, IDENTITY["Club"]),
                "division": pick(row, IDENTITY["Division"]),
                "nation": pick(row, IDENTITY["Nation"]),
                "based_in": pick(row, IDENTITY["BasedIn"]),
                "second_nation": pick(row, IDENTITY["SecondNation"]),
                "position": pos,
                "best_pos": pick(row, IDENTITY["BestPos"]),
                "best_role": pick_best_role(row),
                "position_role": pick(row, IDENTITY["PositionRole"]),
                "style": pick(row, IDENTITY["Style"]),
                "personality": pick(row, IDENTITY["Personality"]),
                "media_handling": pick(row, IDENTITY["MediaHandling"]),
                "world_reputation": pick(row, IDENTITY["WorldReputation"]),
                "world_reputation_gold": pick(row, IDENTITY["WorldReputationGold"]),
                "world_reputation_silver": pick(
                    row, IDENTITY["WorldReputationSilver"]
                ),
                "ability": pick(row, IDENTITY["Ability"]),
                "ability_gold": pick(row, IDENTITY["AbilityGold"]),
                "ability_silver": pick(row, IDENTITY["AbilitySilver"]),
                "potential": pick(row, IDENTITY["Potential"]),
                "potential_gold": pick(row, IDENTITY["PotentialGold"]),
                "potential_silver": pick(row, IDENTITY["PotentialSilver"]),
                "height": pick(row, IDENTITY["Height"]).strip('"'),
                "left_foot": pick(row, IDENTITY["LeftFoot"]),
                "right_foot": pick(row, IDENTITY["RightFoot"]),
                "rec": pick(row, IDENTITY["Rec"]),
                "inf": pick(row, IDENTITY["Inf"]),
                "injury": pick(row, IDENTITY["Injury"]),
                **extract_injury_fields(row),
                "squad": pick(row, IDENTITY["Squad"]),
                "picked": pick(row, IDENTITY["Picked"]),
                "home_grown_status": pick(row, IDENTITY["HomeGrownStatus"]),
                "national_team": pick(row, IDENTITY["NationalTeam"]),
                "int_apps_season": pick(row, IDENTITY["IntAppsSeason"]),
                "int_assists": pick(row, IDENTITY["IntAssists"]),
                "avg_rating_club": pick(row, IDENTITY["AvgRatingClub"]),
                "avg_rating_int": pick(row, IDENTITY["AvgRatingInt"]),
                "last_5_club": pick(row, IDENTITY["Last5Club"]),
                "last_5_int": pick(row, IDENTITY["Last5Int"]),
                "form_club": pick(row, IDENTITY["FormClub"]),
                "form_int": pick(row, IDENTITY["FormInt"]),
                "int_goals_conceded": pick(row, IDENTITY["IntGoalsConceded"]),
                "int_gls": pick(row, IDENTITY["IntGls"]),
                "int_apps": pick(row, IDENTITY["IntApps"]),
                "yth_apps": pick(row, IDENTITY["YthApps"]),
                "yth_gls": pick(row, IDENTITY["YthGls"]),
                **extract_record_fields(row),
                **extract_finance_fields(row),
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
    partial_adjacency: dict[str, frozenset[str]] | None = None,
) -> list[dict[str, Any]]:
    if partial_adjacency is None:
        partial_adjacency = default_partial_adjacency()
    weights = _resolve_tier_weights(tier_weights) if tier_weights else None
    configs = []
    for role_ref in role_ids:
        role_id, scoring_group = decode_role_ref(role_ref)
        if role_id not in pc.all_positions:
            continue
        cfg = pc.all_positions[role_id]
        configs.append(
            (
                role_ref,
                role_meta(role_ref)["column"],
                cfg,
                scoring_groups(role_id, scoring_group),
            )
        )
    scored = []
    for player in players:
        row = {
            "Name": player["name"],
            "Unique ID": str(player.get("unique_id") or "").strip(),
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
            "Injured On": player.get("injured_on") or "-",
            "Time Missed": player.get("time_missed") or "-",
            "Squad": player["squad"] or "-",
            "PosGroups": player.get("pos_groups") or [],
        }
        apply_division_tier(row)
        apply_personality_tier(row)
        apply_set_piece_scores(
            row,
            player.get("attrs") or {},
            tier_weights=weights,
            profiles=set_piece_profiles,
        )
        best_label = ""
        best_score = -1.0
        for role_ref, label, cfg, groups in configs:
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
            row[f"{label} eligible"] = role_eligibility_level(
                player["positions"], groups, partial_adjacency=partial_adjacency
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
        "Injured On",
        "Time Missed",
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
    """Stable player id: ``Name|Unique ID`` (club is display-only).

    Falls back to ``Name|Club`` when Unique ID is missing (older exports).
    Accepts scored rows (``Name`` / ``Unique ID``) and parsed players
    (``name`` / ``unique_id``) via the callers that normalize first.
    """
    name = str(row.get("Name") or row.get("name") or "").strip()
    if not name:
        return ""
    unique_id = str(row.get("Unique ID") or row.get("unique_id") or "").strip()
    if unique_id:
        return f"{name}|{unique_id}"
    club = str(row.get("Club") or row.get("club") or "").strip()
    if club in ("-", "—"):
        club = ""
    return f"{name}|{club}" if club else name


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
