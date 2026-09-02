"""Persisted UI thresholds and colors for Role scores and Player stats.

Named JSON packs live in `config/settings/packs/`. Default uses built-in
values; edits are saved to `default-overrides.json`. Named packs save to
their own files. New creates a named copy.
"""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

from config.paths import (
    SETTINGS_ACTIVE_PATH,
    SETTINGS_DEFAULTS_PATH,
    SETTINGS_PACKS_DIR,
)

PACKS_DIR = SETTINGS_PACKS_DIR
ACTIVE_PATH = SETTINGS_ACTIVE_PATH
DEFAULT_OVERRIDES_PATH = SETTINGS_DEFAULTS_PATH

BUILTIN = "default"

BAND_KEYS = ("elite", "good", "ok", "poor")
COLOR_PARTS = ("bg", "fg", "bar")
PERSONALITY_TIER_COLOR_PARTS = ("bg", "fg")
PERSONALITY_TIER_KEYS = (
    "exemplary",
    "commendable",
    "acceptable",
    "unpredictable",
    "formative",
    "unsuitable",
)
TIER_KEYS = ("key", "preferred", "useful")
HYBRID_KEYS = ("ip", "oop")
TIER_BADGE_KEYS = ("key", "preferred", "useful")

ALLOWED_SHORTLIST_COLUMNS = (
    "Name",
    "Age",
    "Height",
    "Position",
    "Feet",
    "Club",
    "Rec",
    "Injury",
    "Division",
    "Nation",
    "Inf",
    "Best Pos",
)

ALLOWED_MODAL_EXTRA_FIELDS = (
    "world_reputation",
    "ability",
    "potential",
    "squad",
    "personality",
    "media_handling",
)

MODAL_EXTRA_FIELD_OPTIONS = (
    ("squad", "Squad"),
    ("personality", "Personality"),
    ("media_handling", "Media handling"),
)

FIELD_SCOPE_VALUES = frozenset({"both", "role_scores", "player_stats", "off"})

SHORTLIST_ASSIGNABLE = [col for col in ALLOWED_SHORTLIST_COLUMNS if col != "Name"]

DEFAULT_SHORTLIST_ORDER = [
    "Age",
    "Height",
    "Position",
    "Feet",
    "Club",
    "Division",
    "Rec",
    "Injury",
    "Nation",
    "Inf",
    "Best Pos",
]

DEFAULT_SHORTLIST_SCOPES = {
    "Age": "both",
    "Height": "both",
    "Position": "both",
    "Feet": "both",
    "Club": "both",
    "Rec": "both",
    "Injury": "both",
    "Division": "both",
    "Nation": "off",
    "Inf": "off",
    "Best Pos": "off",
}

DEFAULT_MODAL_IDENTITY_ORDER = [
    "age",
    "club",
    "division",
    "height",
    "left_foot",
    "right_foot",
    "rec",
    "inf",
    "injury",
    "last_5_club",
    "position",
    "best_pos",
    "best_role",
    "style",
    "nation",
    "second_nation",
    "national_team",
    "int_apps",
    "int_gls",
    "int_assists",
    "int_goals_conceded",
    "yth_apps",
    "yth_gls",
    "int_apps_season",
    "avg_rating_int",
    "last_5_int",
    "form_int",
    "personality",
    "media_handling",
]

DEFAULT_MODAL_IDENTITY_SCOPES = {
    "age": "both",
    "club": "both",
    "division": "both",
    "nation": "both",
    "second_nation": "both",
    "position": "both",
    "best_pos": "both",
    "best_role": "both",
    "style": "both",
    "height": "both",
    "left_foot": "both",
    "right_foot": "both",
    "rec": "both",
    "inf": "both",
    "injury": "both",
    "last_5_club": "both",
    "national_team": "both",
    "int_apps": "both",
    "int_gls": "both",
    "int_assists": "both",
    "int_goals_conceded": "both",
    "yth_apps": "both",
    "yth_gls": "both",
    "int_apps_season": "both",
    "avg_rating_int": "both",
    "last_5_int": "both",
    "form_int": "both",
    "squad": "off",
    "personality": "off",
    "media_handling": "off",
}

# Persisted keys shared by default-overrides and named packs (exclude id/name for overrides).
PACK_DATA_KEYS = (
    "age_tiers",
    "bands",
    "attribute_bands",
    "foot_thresholds",
    "hist_edges",
    "colors",
    "attribute_colors",
    "tier_weights",
    "hybrid_weights",
    "set_piece_profiles",
    "default_minutes_required",
    "exclude_limited_leagues_adaptive_bounds",
    "depth_undo_max",
    "page_size",
    "page_size_options",
    "preferred_theme",
    "tier_badge_colors",
    "personality_tier_colors",
)

DEFAULTS: dict[str, Any] = {
    "id": BUILTIN,
    "name": "Default",
    "age_tiers": [21, 25, 30],
    "bands": {"elite": 14.0, "good": 12.0, "ok": 10.0},
    # FM attributes are 1–20; default bands map to 16–20, 11–15, 6–10, 1–5.
    "attribute_bands": {"elite": 16, "good": 11, "ok": 6},
    # Left / Right default to Very Strong (6); Both to Fairly Strong (4).
    "foot_thresholds": {"left": 6, "both": 4, "right": 6},
    "hist_edges": [10.0, 11.0, 12.0, 13.0, 14.0],
    "colors": {
        "elite": {"bg": "#dcfce7", "fg": "#15803d", "bar": "#22c55e"},
        "good": {"bg": "#dbeafe", "fg": "#1d4ed8", "bar": "#3b82f6"},
        "ok": {"bg": "#fef3c7", "fg": "#b45309", "bar": "#f59e0b"},
        "poor": {"bg": "#fee2e2", "fg": "#b91c1c", "bar": "#ef4444"},
    },
    "attribute_colors": {
        "elite": {"bg": "#dcfce7", "fg": "#15803d", "bar": "#22c55e"},
        "good": {"bg": "#dbeafe", "fg": "#1d4ed8", "bar": "#3b82f6"},
        "ok": {"bg": "#fef3c7", "fg": "#b45309", "bar": "#f59e0b"},
        "poor": {"bg": "#fee2e2", "fg": "#b91c1c", "bar": "#ef4444"},
    },
    "tier_weights": {"key": 5.0, "preferred": 3.0, "useful": 1.0},
    "hybrid_weights": {"ip": 2.0, "oop": 1.0},
    "set_piece_profiles": None,
    "shortlist_columns": {
        "order": list(DEFAULT_SHORTLIST_ORDER),
        "scopes": dict(DEFAULT_SHORTLIST_SCOPES),
    },
    "default_minutes_required": 900,
    "exclude_limited_leagues_adaptive_bounds": True,
    "depth_undo_max": 10,
    "page_size": 50,
    "page_size_options": [25, 50, 100],
    "preferred_theme": "dark",
    "modal_identity_fields": {
        "order": list(DEFAULT_MODAL_IDENTITY_ORDER),
        "scopes": dict(DEFAULT_MODAL_IDENTITY_SCOPES),
    },
    "tier_badge_colors": {
        "key": "#3dff88",
        "preferred": "#c6e35b",
        "useful": "#5cadff",
    },
    # Personality table/modal highlights (guide tiers with formal names).
    "personality_tier_colors": {
        "exemplary": {"bg": "#dcfce7", "fg": "#15803d"},
        "commendable": {"bg": "#dbeafe", "fg": "#1d4ed8"},
        "acceptable": {"bg": "#e0e7ff", "fg": "#4338ca"},
        "unpredictable": {"bg": "#fef3c7", "fg": "#b45309"},
        "formative": {"bg": "#ffedd5", "fg": "#c2410c"},
        "unsuitable": {"bg": "#fee2e2", "fg": "#b91c1c"},
    },
}


def _as_float(value, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number != number:
        return default
    return number


def _clamp_score(value, default: float) -> float:
    return round(max(0.0, min(20.0, _as_float(value, default))) * 2) / 2


def format_cut(number: float) -> str:
    number = _clamp_score(number, 0.0)
    return str(int(number)) if number == int(number) else f"{number:.1f}"


def format_age(number) -> str:
    return str(int(number))


def format_list(values: list, *, kind: str = "score") -> str:
    if kind == "age":
        return ", ".join(format_age(value) for value in values)
    return ", ".join(format_cut(value) for value in values)


def parse_number_list(text, *, integer: bool = False) -> list[float]:
    values: list[float] = []
    seen: set[float] = set()
    if isinstance(text, (list, tuple)):
        parts = [str(item) for item in text]
    else:
        parts = str(text or "").replace(";", ",").split(",")
    for part in parts:
        token = part.strip()
        if not token:
            continue
        try:
            number = float(token)
        except ValueError:
            continue
        if number != number:
            continue
        number = int(round(number)) if integer else round(number * 2) / 2
        if number in seen:
            continue
        seen.add(number)
        values.append(float(number))
    values.sort()
    return values


def normalize_foot_threshold(value, default: int = 4) -> int:
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        number = default
    return max(1, min(6, number))


def normalize_foot_thresholds(raw=None) -> dict[str, int]:
    """Normalize left/both/right thresholds; migrate legacy `foot_threshold` → both."""
    raw = raw or {}
    defaults = DEFAULTS["foot_thresholds"]
    src = raw.get("foot_thresholds") if isinstance(raw.get("foot_thresholds"), dict) else {}
    legacy = raw.get("foot_threshold")
    both_fallback = legacy if legacy is not None else defaults["both"]
    return {
        "left": normalize_foot_threshold(src.get("left"), defaults["left"]),
        "both": normalize_foot_threshold(
            src.get("both", both_fallback), defaults["both"]
        ),
        "right": normalize_foot_threshold(src.get("right"), defaults["right"]),
    }


def parse_score_floor(value) -> float:
    if value in (None, "", "any", "Any"):
        return 0.0
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if number != number or number <= 0:
        return 0.0
    return number


def _hex_color(value, default: str) -> str:
    text = str(value or "").strip()
    if text.startswith("#") and len(text) == 7:
        body = text[1:]
        if all(ch in "0123456789abcdefABCDEF" for ch in body):
            return "#" + body.lower()
    if text.startswith("#") and len(text) == 4:
        body = text[1:]
        if all(ch in "0123456789abcdefABCDEF" for ch in body):
            return "#" + "".join(ch * 2 for ch in body.lower())
    return default


def default_stats_thresholds() -> dict[str, Any]:
    """Active MustermannFM / pack cut-points (compat helper)."""
    import services.stats_threshold_packs as stp

    return stp.builtin_thresholds()


def normalize_stats_thresholds(raw=None) -> dict[str, Any]:
    import services.stats_threshold_packs as stp

    return stp.normalize_thresholds(raw)


def stats_thresholds_differ(tree: dict[str, Any] | None) -> bool:
    import services.stats_threshold_packs as stp

    return stp.thresholds_differ(tree)


def _clamp_attr_threshold(value, default: int) -> int:
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        return default
    return max(1, min(20, number))


def normalize_attribute_bands(raw, edited: str | None = None) -> dict[str, int]:
    raw = raw or {}
    defaults = DEFAULTS["attribute_bands"]
    elite = _clamp_attr_threshold(raw.get("elite"), defaults["elite"])
    good = _clamp_attr_threshold(raw.get("good"), defaults["good"])
    ok = _clamp_attr_threshold(raw.get("ok"), defaults["ok"])
    if edited == "elite":
        if good >= elite:
            good = max(1, elite - 1)
        if ok >= good:
            ok = max(1, good - 1)
    elif edited == "ok":
        if ok >= good:
            good = min(19, ok + 1)
        if good >= elite:
            elite = min(20, good + 1)
    else:
        if good >= elite:
            elite = min(20, good + 1)
        if ok >= good:
            ok = max(1, good - 1)
    ok = min(ok, 19)
    good = min(max(good, ok + 1), 19)
    elite = min(max(elite, good + 1), 20)
    return {"elite": elite, "good": good, "ok": max(1, ok)}


def normalize_attribute_colors(
    raw=None,
    *,
    score_colors: dict[str, dict[str, str]] | None = None,
) -> dict[str, dict[str, str]]:
    src = raw if isinstance(raw, dict) else {}
    score_fallback = score_colors or DEFAULTS["colors"]
    out: dict[str, dict[str, str]] = {}
    for band in BAND_KEYS:
        entry = src.get(band) if isinstance(src.get(band), dict) else {}
        fallback = DEFAULTS["attribute_colors"][band]
        score_band_colors = score_fallback.get(band) or {}
        out[band] = {
            part: _hex_color(
                entry.get(part),
                _hex_color(score_band_colors.get(part), fallback[part]),
            )
            for part in COLOR_PARTS
        }
    return out


def normalize_bands(raw, edited: str | None = None) -> dict[str, float]:
    raw = raw or {}
    elite = _clamp_score(raw.get("elite"), DEFAULTS["bands"]["elite"])
    good = _clamp_score(raw.get("good"), DEFAULTS["bands"]["good"])
    ok = _clamp_score(raw.get("ok"), DEFAULTS["bands"]["ok"])
    if edited == "elite":
        if good >= elite:
            good = max(0.5, elite - 0.5)
        if ok >= good:
            ok = max(0.0, good - 0.5)
    elif edited == "ok":
        if ok >= good:
            good = min(19.5, ok + 0.5)
        if good >= elite:
            elite = min(20.0, good + 0.5)
    else:
        if good >= elite:
            elite = min(20.0, good + 0.5)
        if ok >= good:
            ok = max(0.0, good - 0.5)
    ok = min(ok, 19.0)
    good = min(max(good, ok + 0.5), 19.5)
    elite = min(max(elite, good + 0.5), 20.0)
    return {"elite": elite, "good": good, "ok": max(0.0, ok)}


def normalize_tier_weight(value, default) -> float:
    number = _as_float(value, float(default))
    if number <= 0:
        number = float(default)
    return round(number * 1000) / 1000


def normalize_tier_weights(raw=None) -> dict[str, float]:
    src = raw if isinstance(raw, dict) else {}
    defaults = DEFAULTS["tier_weights"]
    return {
        key: normalize_tier_weight(src.get(key), defaults[key]) for key in TIER_KEYS
    }


def normalize_hybrid_weights(raw=None) -> dict[str, float]:
    src = raw if isinstance(raw, dict) else {}
    defaults = DEFAULTS["hybrid_weights"]
    return {
        key: normalize_tier_weight(src.get(key), defaults[key]) for key in HYBRID_KEYS
    }


def _normalize_attr_list(raw) -> list[str]:
    if isinstance(raw, str):
        parts = [part.strip() for part in raw.replace(";", ",").split(",")]
        return [part for part in parts if part]
    if isinstance(raw, (list, tuple)):
        out: list[str] = []
        seen: set[str] = set()
        for item in raw:
            code = str(item or "").strip()
            if not code or code in seen:
                continue
            seen.add(code)
            out.append(code)
        return out
    return []


def normalize_set_piece_profiles(raw) -> list[dict[str, Any]] | None:
    """Merge user edits with builtin profiles by id.

    When unset/invalid, returns None (caller should treat as builtin).
    When set, returns a full list with builtin label/abbr/score/raw/detail
    and editable key/preferred/useful attr lists.
    """
    if raw is None:
        return None
    if not isinstance(raw, (list, tuple)) or not raw:
        return None
    import scoring.role_scorer as rs

    by_id = {
        str(item.get("id") or ""): item
        for item in raw
        if isinstance(item, dict) and item.get("id")
    }
    if not by_id:
        return None
    merged: list[dict[str, Any]] = []
    for builtin in rs.SET_PIECE_PROFILES:
        profile_id = builtin["id"]
        overlay = by_id.get(profile_id) or {}
        merged.append(
            {
                "id": profile_id,
                "label": builtin["label"],
                "abbr": builtin.get("abbr"),
                "detail": builtin.get("detail"),
                "raw": builtin.get("raw"),
                "score": builtin.get("score"),
                "key": _normalize_attr_list(
                    overlay["key"] if "key" in overlay else builtin["key"]
                ),
                "preferred": _normalize_attr_list(
                    overlay["preferred"]
                    if "preferred" in overlay
                    else builtin["preferred"]
                ),
                "useful": _normalize_attr_list(
                    overlay["useful"] if "useful" in overlay else builtin["useful"]
                ),
            }
        )
    return merged


def _normalize_column_list(raw, *, allowed: set[str]) -> list[str]:
    if isinstance(raw, str):
        raw = [part.strip() for part in raw.replace(";", ",").split(",")]
    if not isinstance(raw, (list, tuple)):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        col = str(item or "").strip()
        if col not in allowed or col in seen:
            continue
        seen.add(col)
        out.append(col)
    return out


def _normalize_scope(value) -> str:
    text = str(value or "off").strip()
    return text if text in FIELD_SCOPE_VALUES else "off"


def _shortlist_buckets_to_order_scopes(
    both: list[str], role_scores: list[str], player_stats: list[str]
) -> dict[str, Any]:
    order: list[str] = []
    scopes: dict[str, str] = dict(DEFAULT_SHORTLIST_SCOPES)
    for col in both:
        if col == "Name":
            continue
        if col not in order:
            order.append(col)
        scopes[col] = "both"
    for col in role_scores:
        if col == "Name" or col in scopes and scopes[col] == "both":
            continue
        if col not in order:
            order.append(col)
        scopes[col] = "role_scores"
    for col in player_stats:
        if col == "Name" or scopes.get(col) == "both":
            continue
        if col not in order:
            order.append(col)
        if scopes.get(col) != "role_scores":
            scopes[col] = "player_stats"
    for col in SHORTLIST_ASSIGNABLE:
        if col not in order:
            order.append(col)
    return {"order": order, "scopes": scopes}


def normalize_shortlist_columns(raw=None) -> dict[str, Any]:
    """Ordered shortlist config: {order: [...], scopes: {col: both|role_scores|player_stats|off}}."""
    defaults = copy.deepcopy(DEFAULTS["shortlist_columns"])

    if isinstance(raw, (list, tuple)):
        cols = _normalize_column_list(raw, allowed=set(ALLOWED_SHORTLIST_COLUMNS))
        both = [col for col in cols if col != "Name"]
        return _shortlist_buckets_to_order_scopes(both, [], [])

    if isinstance(raw, dict) and "order" in raw:
        order = _normalize_column_list(
            raw.get("order"), allowed=set(SHORTLIST_ASSIGNABLE)
        )
        scopes = dict(defaults["scopes"])
        for col, scope in (raw.get("scopes") or {}).items():
            if col in SHORTLIST_ASSIGNABLE:
                scopes[col] = _normalize_scope(scope)
        for col in SHORTLIST_ASSIGNABLE:
            if col not in order:
                order.append(col)
        return {"order": order, "scopes": scopes}

    if isinstance(raw, dict) and (
        "both" in raw or "role_scores" in raw or "player_stats" in raw
    ):
        return _shortlist_buckets_to_order_scopes(
            list(raw.get("both") or []),
            list(raw.get("role_scores") or []),
            list(raw.get("player_stats") or []),
        )

    return copy.deepcopy(defaults)


def shortlist_column_scope(col: str, cfg: dict[str, Any]) -> str:
    if col == "Name":
        return "both"
    return _normalize_scope((cfg.get("scopes") or {}).get(col))


def shortlist_scope_values(cfg: dict[str, Any]) -> list[str]:
    order = list(cfg.get("order") or DEFAULT_SHORTLIST_ORDER)
    scopes = cfg.get("scopes") or {}
    return [_normalize_scope(scopes.get(col)) for col in order]


def shortlist_columns_for(page: str, settings=None) -> list[str]:
    """Ordered identity columns for role_scores or player_stats shortlist tables."""
    cfg = normalize(settings)["shortlist_columns"]
    page_key = "role_scores" if page == "role_scores" else "player_stats"
    out = ["Name"]
    for col in cfg.get("order") or []:
        scope = shortlist_column_scope(col, cfg)
        if scope == "both" or scope == page_key:
            out.append(col)
    return out or ["Name"]


def _modal_field_catalog() -> list[tuple[str, str, str]]:
    from components.player_modal import iter_modal_field_defs

    return iter_modal_field_defs()


def _default_modal_identity_fields(extra_enabled=None) -> dict[str, Any]:
    del extra_enabled
    return {
        "order": list(DEFAULT_MODAL_IDENTITY_ORDER),
        "scopes": dict(DEFAULT_MODAL_IDENTITY_SCOPES),
    }


def normalize_modal_identity_fields(raw=None, *, legacy_extra=None) -> dict[str, Any]:
    defaults = _default_modal_identity_fields(extra_enabled=legacy_extra)
    allowed = {key for _label, key, _section in _modal_field_catalog()}

    if raw is None:
        return defaults

    if isinstance(raw, dict) and "order" in raw:
        from components.player_modal import STAR_ATTRIBUTES_BROKEN

        order: list[str] = []
        seen: set[str] = set()
        for key in raw.get("order") or []:
            text = str(key)
            if text in STAR_ATTRIBUTES_BROKEN:
                continue
            if text in allowed and text not in seen:
                order.append(text)
                seen.add(text)
        scopes = dict(defaults["scopes"])
        for key, scope in (raw.get("scopes") or {}).items():
            if str(key) in allowed and str(key) not in STAR_ATTRIBUTES_BROKEN:
                scopes[str(key)] = _normalize_scope(scope)
        for _label, key, _section in _modal_field_catalog():
            if key not in order:
                order.append(key)
        return {"order": order, "scopes": scopes}

    return defaults


def modal_identity_scope_values(cfg: dict[str, Any]) -> list[str]:
    order = list(cfg.get("order") or [])
    scopes = cfg.get("scopes") or {}
    return [_normalize_scope(scopes.get(key)) for key in order]


def modal_identity_fields_for(page: str, settings=None) -> list[tuple[str, str, str]]:
    """(label, key, section) rows for the player modal on one page."""
    from components.player_modal import STAR_ATTRIBUTES_BROKEN

    cfg = normalize(settings)["modal_identity_fields"]
    page_key = "role_scores" if page == "role_scores" else "player_stats"
    labels = {key: label for label, key, section in _modal_field_catalog()}
    sections = {key: section for label, key, section in _modal_field_catalog()}
    out: list[tuple[str, str, str]] = []
    for key in cfg.get("order") or []:
        if key in STAR_ATTRIBUTES_BROKEN:
            continue
        scope = _normalize_scope((cfg.get("scopes") or {}).get(key))
        if scope in ("off",):
            continue
        if scope != "both" and scope != page_key:
            continue
        out.append((labels.get(key, key), key, sections.get(key, "identity")))
    return out



def normalize_page_size_options(raw=None) -> list[int]:
    defaults = list(DEFAULTS["page_size_options"])
    values = parse_number_list(raw if raw is not None else defaults, integer=True)
    options = sorted({int(v) for v in values if 1 <= v <= 500})
    return options or defaults


def normalize_page_size(value, options: list[int] | None = None) -> int:
    opts = options or list(DEFAULTS["page_size_options"])
    default = int(DEFAULTS["page_size"])
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        number = default
    if number in opts:
        return number
    if opts:
        return min(opts, key=lambda opt: abs(opt - number))
    return default


def normalize_preferred_theme(value) -> str:
    text = str(value or "").strip().lower()
    return "light" if text == "light" else "dark"


def normalize_modal_extra_fields(raw=None) -> list[str]:
    allowed = set(ALLOWED_MODAL_EXTRA_FIELDS)
    if isinstance(raw, str):
        raw = [part.strip() for part in raw.replace(";", ",").split(",")]
    if not isinstance(raw, (list, tuple)):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        key = str(item or "").strip()
        if key not in allowed or key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def normalize_tier_badge_colors(raw=None) -> dict[str, str]:
    src = raw if isinstance(raw, dict) else {}
    defaults = DEFAULTS["tier_badge_colors"]
    return {
        key: _hex_color(src.get(key), defaults[key]) for key in TIER_BADGE_KEYS
    }


def normalize_personality_tier_colors(raw=None) -> dict[str, dict[str, str]]:
    src = raw if isinstance(raw, dict) else {}
    defaults = DEFAULTS["personality_tier_colors"]
    out: dict[str, dict[str, str]] = {}
    for tier in PERSONALITY_TIER_KEYS:
        entry = src.get(tier) if isinstance(src.get(tier), dict) else {}
        fallback = defaults[tier]
        out[tier] = {
            part: _hex_color(entry.get(part), fallback[part])
            for part in PERSONALITY_TIER_COLOR_PARTS
        }
    return out


def normalize_default_minutes_required(value) -> int:
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        number = int(DEFAULTS["default_minutes_required"])
    return max(0, min(20000, number))


def normalize_exclude_limited_leagues_adaptive_bounds(value) -> bool:
    if value is None:
        return bool(DEFAULTS["exclude_limited_leagues_adaptive_bounds"])
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in ("1", "true", "yes", "on"):
        return True
    if text in ("0", "false", "no", "off"):
        return False
    return bool(DEFAULTS["exclude_limited_leagues_adaptive_bounds"])


def normalize_depth_undo_max(value) -> int:
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        number = int(DEFAULTS["depth_undo_max"])
    return max(1, min(50, number))


def normalize(raw=None, *, pack_id: str | None = None, name: str | None = None) -> dict[str, Any]:
    raw = raw or {}
    ages = parse_number_list(raw.get("age_tiers", DEFAULTS["age_tiers"]), integer=True)
    ages = [int(age) for age in ages if 1 <= age <= 99]
    if not ages:
        ages = list(DEFAULTS["age_tiers"])

    edges = parse_number_list(raw.get("hist_edges", DEFAULTS["hist_edges"]))
    edges = [value for value in edges if 0 < value <= 20]
    if not edges:
        edges = list(DEFAULTS["hist_edges"])

    colors: dict[str, dict[str, str]] = {}
    raw_colors = raw.get("colors") or {}
    for band in BAND_KEYS:
        src = raw_colors.get(band) or {}
        fallback = DEFAULTS["colors"][band]
        colors[band] = {
            part: _hex_color(src.get(part), fallback[part]) for part in COLOR_PARTS
        }
    attribute_colors = normalize_attribute_colors(
        raw.get("attribute_colors"),
        score_colors=colors,
    )

    page_opts = normalize_page_size_options(raw.get("page_size_options"))
    pack_id = pack_id or raw.get("id") or BUILTIN
    label = name if name is not None else raw.get("name") or (
        "Default" if pack_id == BUILTIN else pack_id
    )
    import services.stats_threshold_packs as stp

    return {
        "id": pack_id,
        "name": label,
        "age_tiers": ages,
        "bands": normalize_bands(raw.get("bands") or raw),
        "attribute_bands": normalize_attribute_bands(raw.get("attribute_bands")),
        "foot_thresholds": normalize_foot_thresholds(raw),
        "hist_edges": edges,
        "colors": colors,
        "attribute_colors": attribute_colors,
        "tier_weights": normalize_tier_weights(raw.get("tier_weights")),
        "hybrid_weights": normalize_hybrid_weights(raw.get("hybrid_weights")),
        "set_piece_profiles": normalize_set_piece_profiles(raw.get("set_piece_profiles")),
        "shortlist_columns": normalize_shortlist_columns(),
        "default_minutes_required": normalize_default_minutes_required(
            raw.get("default_minutes_required")
        ),
        "exclude_limited_leagues_adaptive_bounds": normalize_exclude_limited_leagues_adaptive_bounds(
            raw.get("exclude_limited_leagues_adaptive_bounds")
        ),
        "depth_undo_max": normalize_depth_undo_max(raw.get("depth_undo_max")),
        "page_size": normalize_page_size(raw.get("page_size"), page_opts),
        "page_size_options": page_opts,
        "preferred_theme": normalize_preferred_theme(raw.get("preferred_theme")),
        "modal_identity_fields": normalize_modal_identity_fields(),
        "tier_badge_colors": normalize_tier_badge_colors(raw.get("tier_badge_colors")),
        "personality_tier_colors": normalize_personality_tier_colors(
            raw.get("personality_tier_colors")
        ),
        # Resolved from the separate stats-threshold pack domain (not stored here).
        "stats_thresholds": stp.load_tree(),
        "stats_threshold_pack_id": stp.active_id(),
    }


def _slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(name or "").strip().lower()).strip("-")
    return slug or "settings"


def _unique_id(name: str) -> str:
    base = _slug(name)
    candidate = base
    index = 2
    while candidate == BUILTIN or _pack_path(candidate).exists():
        candidate = f"{base}-{index}"
        index += 1
    return candidate


def _pack_path(pack_id: str) -> Path:
    return PACKS_DIR / f"{pack_id}.json"


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _active_id() -> str:
    pack_id = str(_read_json(ACTIVE_PATH).get("id") or BUILTIN)
    if pack_id != BUILTIN and not _pack_path(pack_id).exists():
        return BUILTIN
    return pack_id


def _set_active(pack_id: str) -> None:
    _write_json(ACTIVE_PATH, {"id": pack_id})


def _pack_payload(settings: dict[str, Any]) -> dict[str, Any]:
    payload = {key: settings[key] for key in PACK_DATA_KEYS}
    # Persist null explicitly so packs can reset to builtin formulas.
    if payload.get("set_piece_profiles") is None:
        payload["set_piece_profiles"] = None
    return payload


def _default_settings() -> dict[str, Any]:
    base = copy.deepcopy(DEFAULTS)
    overrides = _read_json(DEFAULT_OVERRIDES_PATH)
    if not overrides:
        return base
    merged = {**base, **overrides}
    if overrides.get("bands"):
        merged["bands"] = {**base["bands"], **overrides["bands"]}
    if overrides.get("foot_thresholds") or overrides.get("foot_threshold") is not None:
        merged["foot_thresholds"] = {
            **base["foot_thresholds"],
            **(overrides.get("foot_thresholds") or {}),
        }
        if overrides.get("foot_threshold") is not None and "both" not in (
            overrides.get("foot_thresholds") or {}
        ):
            merged["foot_thresholds"]["both"] = overrides["foot_threshold"]
    if overrides.get("colors"):
        merged["colors"] = {
            band: {**base["colors"].get(band, {}), **(overrides["colors"].get(band) or {})}
            for band in BAND_KEYS
        }
    if overrides.get("attribute_bands"):
        merged["attribute_bands"] = {
            **base["attribute_bands"],
            **(overrides.get("attribute_bands") or {}),
        }
    if overrides.get("attribute_colors"):
        merged["attribute_colors"] = {
            band: {
                **base["attribute_colors"].get(band, {}),
                **((overrides.get("attribute_colors") or {}).get(band) or {}),
            }
            for band in BAND_KEYS
        }
    if overrides.get("tier_weights"):
        merged["tier_weights"] = {
            **base["tier_weights"],
            **(overrides.get("tier_weights") or {}),
        }
    if overrides.get("hybrid_weights"):
        merged["hybrid_weights"] = {
            **base["hybrid_weights"],
            **(overrides.get("hybrid_weights") or {}),
        }
    if overrides.get("tier_badge_colors"):
        merged["tier_badge_colors"] = {
            **base["tier_badge_colors"],
            **(overrides.get("tier_badge_colors") or {}),
        }
    if overrides.get("personality_tier_colors"):
        merged["personality_tier_colors"] = {
            tier: {
                **base["personality_tier_colors"].get(tier, {}),
                **((overrides.get("personality_tier_colors") or {}).get(tier) or {}),
            }
            for tier in PERSONALITY_TIER_KEYS
        }
    if "set_piece_profiles" in overrides:
        merged["set_piece_profiles"] = overrides.get("set_piece_profiles")
    if overrides.get("page_size_options") is not None:
        merged["page_size_options"] = overrides.get("page_size_options")
    return normalize(merged, pack_id=BUILTIN, name="Default")


def has_default_overrides() -> bool:
    return DEFAULT_OVERRIDES_PATH.exists()


def clear_default_overrides() -> None:
    if DEFAULT_OVERRIDES_PATH.exists():
        DEFAULT_OVERRIDES_PATH.unlink()


def _pack_from_file(pack_id: str) -> dict[str, Any]:
    if pack_id == BUILTIN:
        return _default_settings()
    path = _pack_path(pack_id)
    if not path.exists():
        return copy.deepcopy(DEFAULTS)
    payload = _read_json(path)
    return normalize(payload, pack_id=pack_id, name=payload.get("name") or pack_id)


def read_pack(pack_id: str | None = None) -> dict[str, Any]:
    return _pack_from_file(pack_id or _active_id())


def pack_options() -> list[dict]:
    default_label = "Default (customized)" if has_default_overrides() else "Default"
    options = [{"label": default_label, "value": BUILTIN}]
    if not PACKS_DIR.exists():
        return options
    for path in sorted(PACKS_DIR.glob("*.json")):
        payload = _read_json(path)
        label = payload.get("name") or path.stem
        options.append({"label": label, "value": path.stem})
    return options


def active_id() -> str:
    return _active_id()


def load(pack_id: str | None = None) -> dict[str, Any]:
    chosen = pack_id or _active_id()
    settings = _pack_from_file(chosen)
    if pack_id:
        _set_active(settings["id"] if chosen != BUILTIN else BUILTIN)
    return settings


def save(raw, pack_id: str | None = None) -> dict[str, Any]:
    current = pack_id or raw.get("id") or _active_id()
    if current == BUILTIN:
        settings = normalize(raw, pack_id=BUILTIN, name="Default")
        settings["id"] = BUILTIN
        settings["name"] = "Default"
        _write_json(DEFAULT_OVERRIDES_PATH, _pack_payload(settings))
        _set_active(BUILTIN)
        return settings
    settings = normalize(raw, pack_id=current, name=raw.get("name"))
    settings["id"] = current
    to_write = {"id": settings["id"], "name": settings["name"], **_pack_payload(settings)}
    _write_json(_pack_path(current), to_write)
    _set_active(current)
    return settings


def create_pack(name: str, raw) -> dict[str, Any]:
    label = str(name or "").strip() or "Settings"
    pack_id = _unique_id(label)
    settings = normalize(raw, pack_id=pack_id, name=label)
    settings["id"] = pack_id
    settings["name"] = label
    to_write = {"id": settings["id"], "name": settings["name"], **_pack_payload(settings)}
    _write_json(_pack_path(pack_id), to_write)
    _set_active(pack_id)
    return settings


def is_builtin(pack_id: str | None) -> bool:
    return (pack_id or BUILTIN) == BUILTIN


def age_options(settings=None) -> list[dict]:
    settings = normalize(settings)
    options = [{"label": "Any", "value": "99"}]
    for age in settings["age_tiers"]:
        if age != 99:
            options.append({"label": str(age), "value": str(int(age))})
    return options


def clamp_choice(value, options: list[dict], fallback):
    allowed = {str(opt["value"]) for opt in options}
    if value is not None and str(value) in allowed:
        return str(value)
    try:
        number = str(int(float(value)))
    except (TypeError, ValueError):
        return str(fallback)
    if number in allowed:
        return number
    return str(fallback)


def hist_bins(settings=None) -> list[tuple[str, float, float]]:
    settings = normalize(settings)
    edges = settings["hist_edges"]
    bins = [(f"<{format_cut(edges[0])}", 0.0, float(edges[0]))]
    for lo, hi in zip(edges, edges[1:]):
        bins.append((f"{format_cut(lo)}–{format_cut(hi)}", float(lo), float(hi)))
    last = edges[-1]
    bins.append((f"{format_cut(last)}+", float(last), 99.0))
    return bins


def hist_preview(settings=None) -> str:
    return " · ".join(label for label, _lo, _hi in hist_bins(settings))


def score_colors(settings=None) -> dict[str, tuple[str, str]]:
    settings = normalize(settings)
    return {
        band: (settings["colors"][band]["bg"], settings["colors"][band]["fg"])
        for band in BAND_KEYS
    }


def band_text_color(band: str, settings=None, *, theme: str | None = None) -> str:
    """Saturated tier text color from UI settings (Score bands colors).

    Pass already-normalized settings when coloring many cells — ``normalize`` is
    expensive and must not run per cell in table builds.
    """
    if not isinstance(settings, dict) or "colors" not in settings:
        settings = normalize(settings)
    colors = settings["colors"][band]
    if theme == "light":
        return colors["fg"]
    return colors["bar"]


def band_text_colors(settings=None, *, theme: str | None = None) -> dict[str, str]:
    """Band → text color map for bulk shortlist/table rendering."""
    if not isinstance(settings, dict) or "colors" not in settings:
        settings = normalize(settings)
    key = "fg" if theme == "light" else "bar"
    return {band: settings["colors"][band][key] for band in BAND_KEYS}


def css_vars(settings=None) -> dict[str, str]:
    settings = normalize(settings)
    vars_: dict[str, str] = {}
    for band in BAND_KEYS:
        colors = settings["colors"][band]
        vars_[f"--band-{band}-bg"] = colors["bg"]
        vars_[f"--band-{band}-fg"] = colors["fg"]
        vars_[f"--band-{band}-bar"] = colors["bar"]
    for band in BAND_KEYS:
        colors = settings["attribute_colors"][band]
        vars_[f"--attr-band-{band}-bg"] = colors["bg"]
        vars_[f"--attr-band-{band}-fg"] = colors["fg"]
        vars_[f"--attr-band-{band}-bar"] = colors["bar"]
    badge = settings["tier_badge_colors"]
    vars_["--rc-key"] = badge["key"]
    vars_["--rc-green"] = badge["preferred"]
    vars_["--rc-blue"] = badge["useful"]
    for tier, colors in settings["personality_tier_colors"].items():
        vars_[f"--pers-tier-{tier}-bg"] = colors["bg"]
        vars_[f"--pers-tier-{tier}-fg"] = colors["fg"]
    return vars_


def personality_tier_colors(settings=None) -> dict[str, dict[str, str]]:
    return copy.deepcopy(normalize(settings)["personality_tier_colors"])


def tier_weights(settings=None) -> dict[str, float]:
    return copy.deepcopy(normalize(settings)["tier_weights"])


def hybrid_weights(settings=None) -> dict[str, float]:
    return copy.deepcopy(normalize(settings)["hybrid_weights"])


def set_piece_profiles(settings=None) -> list[dict[str, Any]]:
    """Resolved profiles (deep copy). Falls back to builtin when unset/invalid."""
    settings = normalize(settings)
    profiles = settings.get("set_piece_profiles")
    if profiles:
        return copy.deepcopy(profiles)
    import scoring.role_scorer as rs

    return copy.deepcopy(list(rs.SET_PIECE_PROFILES))


def shortlist_columns(settings=None) -> list[str]:
    """Role scores shortlist columns (backward-compatible alias)."""
    return shortlist_columns_for("role_scores", settings)


def page_size(settings=None) -> int:
    return int(normalize(settings)["page_size"])


def page_size_options(settings=None) -> list[str]:
    return [str(opt) for opt in normalize(settings)["page_size_options"]]


def default_minutes_required(settings=None) -> int:
    """Minutes threshold from UI settings (defaults to 900)."""
    return int(normalize(settings)["default_minutes_required"])


def exclude_limited_leagues_adaptive_bounds(settings=None) -> bool:
    """When True, adaptive p0/p100 dataset extremes ignore limited-tracking leagues."""
    return bool(normalize(settings)["exclude_limited_leagues_adaptive_bounds"])


def depth_undo_max(settings=None) -> int:
    """Max recently-removed depth/shortlist items kept for restore."""
    return int(normalize(settings)["depth_undo_max"])


def modal_identity_fields(settings=None) -> dict[str, Any]:
    return copy.deepcopy(normalize(settings)["modal_identity_fields"])


def modal_extra_fields(settings=None) -> list[str]:
    """Legacy helper: keys enabled on both pages."""
    cfg = normalize(settings)["modal_identity_fields"]
    return [
        key
        for key in cfg.get("order") or []
        if _normalize_scope((cfg.get("scopes") or {}).get(key)) == "both"
    ]


def tier_badge_colors(settings=None) -> dict[str, str]:
    return copy.deepcopy(normalize(settings)["tier_badge_colors"])


def preferred_theme(settings=None) -> str:
    return normalize(settings)["preferred_theme"]


def set_preferred_theme(theme: str, pack_id: str | None = None) -> dict[str, Any]:
    """Persist preferred theme on the active (or given) settings pack and return it."""
    current = load(pack_id)
    current["preferred_theme"] = normalize_preferred_theme(theme)
    return save(current, current.get("id"))


def format_page_size_options(settings=None) -> str:
    return ", ".join(page_size_options(settings))
