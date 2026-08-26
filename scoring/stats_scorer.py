"""Parse FM stats exports and band values against MustermannFM benchmarks."""

from __future__ import annotations

import csv
import io
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from scoring.role_scorer import (
    IDENTITY,
    extract_attrs,
    extract_finance_fields,
    extract_record_fields,
    foot_strength,
    parse_positions,
    pick,
    player_pos_groups,
    player_row_key,
    sniff_delimiter,
    unique_headers,
)

DATA_PATH = Path(__file__).resolve().parents[1] / "config" / "stats_benchmarks.json"

# PDF / FM-style graduated colors (percentile 0 → 100).
_COLOR_RED = (255, 92, 92)
_COLOR_YELLOW = (255, 210, 64)
_COLOR_GREEN = (64, 220, 120)

POS_GROUPS = (
    ("all", "All", "all"),
    ("gk", "Goalkeepers", "gk"),
    ("def", "Defenders", "def"),
    ("mid", "Midfielders", "mid"),
    ("fwd", "Forwards", "fwd"),
)

# UI / store always uses outfield category ids. GK benchmark blocks map onto them.
_CATEGORY_ALIASES = {
    "goalkeeping": "final_third",
    "gk_def": "defending",
    "gk_possession": "possession",
}
_GK_STORAGE_CATEGORY = {
    "defending": "gk_def",
    "final_third": "goalkeeping",
    "possession": "gk_possession",
}


@lru_cache(maxsize=1)
def benchmarks() -> dict[str, Any]:
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def metric_defs() -> dict[str, dict[str, Any]]:
    return benchmarks()["metrics"]


def is_gk_group(group: str | None) -> bool:
    return (group or "") == "gk"


def canonical_category(category: str | None) -> str:
    """Normalize legacy GK category ids onto the shared outfield ids."""
    cat = (category or "").strip()
    if cat == "all":
        return "all"
    return _CATEGORY_ALIASES.get(cat, cat)


def storage_category(group: str | None, category: str | None) -> str | None:
    """Benchmark JSON category key for a position group + UI category."""
    cat = canonical_category(category)
    if cat in ("", "all"):
        return None
    if is_gk_group(group):
        return _GK_STORAGE_CATEGORY.get(cat)
    if cat in _GK_STORAGE_CATEGORY:
        return cat
    return None


def category_domain(category: str | None) -> str:
    """Return 'gk' only for legacy GK storage ids; shared UI ids are 'outfield'."""
    return "gk" if is_gk_category(category) else "outfield"


def is_gk_category(category: str | None) -> bool:
    """True only for legacy GK storage ids (goalkeeping / gk_*)."""
    return (category or "").strip() in _CATEGORY_ALIASES


def view_categories() -> list[dict[str, str]]:
    """Shared category tabs/columns for every position group."""
    return list(benchmarks()["categories"]["outfield"])


def category_label(
    category: str | None,
    *,
    group: str | None = None,
    dual_final_third: bool = False,
) -> str:
    """UI label for a shared category id.

    - Goalkeeper filter: ``final_third`` → Goalkeeping
    - All-category averages: ``final_third`` → Final third / Goalkeeping
    """
    cat = canonical_category(category)
    outfield = {c["id"]: c["label"] for c in view_categories()}
    if cat == "all":
        return "All"
    if cat == "final_third":
        gk_name = next(
            (c["label"] for c in benchmarks()["categories"]["gk"] if c["id"] == "goalkeeping"),
            "Goalkeeping",
        )
        if dual_final_third:
            return f"{outfield.get('final_third', 'Final third')} / {gk_name}"
        if is_gk_group(group):
            return gk_name
    return outfield.get(cat, cat or "")


def category_abbr(
    category: str | None,
    *,
    group: str | None = None,
    dual_final_third: bool = False,
) -> str:
    """Short table header for a shared category id."""
    cat = canonical_category(category)
    outfield = {c["id"]: (c.get("abbr") or c["label"]) for c in view_categories()}
    if cat == "all":
        return "All"
    if cat == "final_third":
        gk_abbr = next(
            (
                c.get("abbr") or c["label"]
                for c in benchmarks()["categories"]["gk"]
                if c["id"] == "goalkeeping"
            ),
            "GK",
        )
        if dual_final_third:
            return f"{outfield.get('final_third', 'F3')} / {gk_abbr}"
        if is_gk_group(group):
            return gk_abbr
    return outfield.get(cat, cat or "")


def labeled_view_categories(
    *,
    group: str | None = None,
    dual_final_third: bool = False,
) -> list[dict[str, str]]:
    """view_categories() with context-aware display labels and abbreviations."""
    return [
        {
            "id": cat["id"],
            "label": category_label(
                cat["id"], group=group, dual_final_third=dual_final_third
            ),
            "abbr": category_abbr(
                cat["id"], group=group, dual_final_third=dual_final_third
            ),
        }
        for cat in view_categories()
    ]


def categories_for_group(group: str) -> list[dict[str, str]]:
    """Same shared categories for GK and outfield (labels: Defending / Final third / Possession)."""
    return labeled_view_categories(group=group)


def default_category_for_group(group: str) -> str:
    return "all"


def metrics_for(
    group: str,
    category: str,
    threshold_overrides: dict[str, Any] | None = None,
) -> list[str]:
    """Metrics for one position group + shared category (GK uses mapped storage keys)."""
    stored = storage_category(group, category)
    if not stored:
        return []
    root = (
        threshold_overrides
        if isinstance(threshold_overrides, dict) and threshold_overrides
        else benchmarks()["benchmarks"]
    )
    block = (root.get(group) or {}).get(stored) or {}
    if not block and threshold_overrides:
        block = (benchmarks()["benchmarks"].get(group) or {}).get(stored) or {}
    return list(block.keys())


def default_minutes_required() -> int:
    return int(benchmarks().get("default_minutes_required") or 900)


def classify_best_pos(best_pos: str, position: str = "") -> str:
    """Map Best Pos / Position text to gk / def / mid / fwd."""
    text = f"{best_pos or ''} {position or ''}".upper()
    if re.search(r"\bGK\b", text):
        return "gk"
    if re.search(r"\b(ST|CF|SC)\b", text) or re.search(r"\bAM\s*\(\s*[LR]\s*\)", text):
        return "fwd"
    if re.search(r"\b(WB|FB)\b", text) or re.search(r"\bD\b", text):
        return "def"
    if re.search(r"\b(DM|MC|MR|ML|AMC|AM)\b", text) or re.search(
        r"\bM\s*\(|\bAM\s*\(\s*C\s*\)", text
    ):
        return "mid"
    # Fallbacks from looser tokens
    if "ST" in text or "FORWARD" in text:
        return "fwd"
    if "WING" in text and "BACK" not in text:
        return "fwd"
    if "MID" in text:
        return "mid"
    if "DEF" in text or "BACK" in text:
        return "def"
    return "mid"


def parse_number(value: Any) -> float | None:
    if value in (None, "", "-"):
        return None
    text = str(value).strip().replace("%", "").replace(" ", "")
    text = text.replace(",", ".")
    if not text or text == "-":
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _lerp_rgb(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    t = max(0.0, min(1.0, t))
    return tuple(int(round(x + (y - x) * t)) for x, y in zip(a, b))


def percentile_color(percentile: float | None) -> str | None:
    """CSS rgb for estimated percentile 0–100 (PDF/FM red→yellow→green)."""
    if percentile is None:
        return None
    p = max(0.0, min(100.0, float(percentile)))
    mid = 50.0
    if p <= mid:
        t = p / mid
        rgb = _lerp_rgb(_COLOR_RED, _COLOR_YELLOW, t)
    else:
        t = (p - mid) / (100.0 - mid)
        rgb = _lerp_rgb(_COLOR_YELLOW, _COLOR_GREEN, t)
    return f"rgb({rgb[0]}, {rgb[1]}, {rgb[2]})"


def estimate_percentile(
    value: float,
    thresholds: list[float],
    *,
    higher_is_better: bool,
    p100: float | None = None,
    p0: float | None = None,
) -> float:
    """Map a value onto ~0–100 using 20/40/60/80 boundaries.

    Optional ``p0`` / ``p100`` stretch the bottom (0→20) and top (80→100)
    spans. Adaptive callers pass max/min of the settings-implied floor/ceiling
    and the extreme in the phase cohort so tails do not collapse.
    """
    if len(thresholds) != 4:
        raise ValueError("Expected four percentile thresholds")
    t20, t40, t60, t80 = (float(x) for x in thresholds)
    points = [20.0, 40.0, 60.0, 80.0]
    bounds = [t20, t40, t60, t80]

    def lerp(v: float, lo: float, hi: float, plo: float, phi: float) -> float:
        if hi == lo:
            return phi
        return plo + (phi - plo) * ((v - lo) / (hi - lo))

    def end_span(bound: float, edge: float | None, *, toward_high: bool) -> float:
        if edge is not None:
            span = (edge - bound) if toward_high else (bound - edge)
            if span > 0:
                return span
        return abs(bound) if bound != 0 else 1.0

    if higher_is_better:
        if value <= bounds[0]:
            span = end_span(bounds[0], p0, toward_high=False)
            floor = (bounds[0] - span) if p0 is None else float(p0)
            if span <= 0:
                return 0.0 if value < bounds[0] else 20.0
            return max(0.0, min(20.0, 20.0 * (value - floor) / span))
        for i in range(3):
            if value <= bounds[i + 1]:
                return lerp(value, bounds[i], bounds[i + 1], points[i], points[i + 1])
        span = end_span(bounds[3], p100, toward_high=True)
        return min(100.0, 80.0 + 20.0 * min(1.0, (value - bounds[3]) / span))

    # Lower is better: thresholds decrease as quality improves
    if value >= bounds[0]:
        span = end_span(bounds[0], p0, toward_high=True)
        floor = (bounds[0] + span) if p0 is None else float(p0)
        if span <= 0:
            return 0.0 if value > bounds[0] else 20.0
        return max(0.0, min(20.0, 20.0 * (floor - value) / span))
    for i in range(3):
        if value >= bounds[i + 1]:
            return lerp(value, bounds[i], bounds[i + 1], points[i], points[i + 1])
    span = end_span(bounds[3], p100, toward_high=False)
    return min(100.0, 80.0 + 20.0 * min(1.0, (bounds[3] - value) / span))


def implied_percentile_ceiling(
    thresholds: list[float], *, higher_is_better: bool
) -> float:
    """Default 100th-percentile value implied by the 80th cut (settings)."""
    t80 = float(thresholds[3])
    span = abs(t80) if t80 != 0 else 1.0
    return t80 + span if higher_is_better else t80 - span


def implied_percentile_floor(
    thresholds: list[float], *, higher_is_better: bool
) -> float:
    """Default 0th-percentile value implied by the 20th cut (settings)."""
    t20 = float(thresholds[0])
    span = abs(t20) if t20 != 0 else 1.0
    return t20 - span if higher_is_better else t20 + span


def pos_group_label(group: str | None) -> str:
    """Human label for a stats phase group (Defenders, Midfielders, …)."""
    key = (group or "").strip().lower()
    for gid, label, _css in POS_GROUPS:
        if gid == key:
            return label
    return key or "—"


def resolve_player_pos_group(player: dict[str, Any] | None) -> str:
    """Canonical gk/def/mid/fwd for banding — prefer stored group, else classify."""
    if not player:
        return "mid"
    stored = str(player.get("pos_group") or "").strip().lower()
    if stored in {"gk", "def", "mid", "fwd"}:
        return stored
    return classify_best_pos(
        str(player.get("best_pos") or ""),
        str(player.get("position") or ""),
    )


def players_in_pos_group(
    players: list[dict[str, Any]] | None,
    group: str,
) -> list[dict[str, Any]]:
    """Players whose phase group matches ``group`` (gk/def/mid/fwd)."""
    want = str(group or "").strip().lower()
    if not want:
        return list(players or [])
    return [
        player
        for player in (players or [])
        if resolve_player_pos_group(player) == want
    ]


def metric_extreme_among_players(
    players: list[dict[str, Any]] | None,
    metric_id: str,
    *,
    higher_is_better: bool,
) -> float | None:
    """Best raw metric value among scorable players in the loaded set."""
    values: list[float] = []
    for player in players or []:
        raw = scoring_stats(player).get(metric_id)
        if raw is None:
            continue
        try:
            number = float(raw)
        except (TypeError, ValueError):
            continue
        if number != number:
            continue
        values.append(number)
    if not values:
        return None
    return max(values) if higher_is_better else min(values)


def metric_floor_among_players(
    players: list[dict[str, Any]] | None,
    metric_id: str,
    *,
    higher_is_better: bool,
) -> float | None:
    """Worst raw metric value among scorable players (adaptive 0th floor)."""
    values: list[float] = []
    for player in players or []:
        raw = scoring_stats(player).get(metric_id)
        if raw is None:
            continue
        try:
            number = float(raw)
        except (TypeError, ValueError):
            continue
        if number != number:
            continue
        values.append(number)
    if not values:
        return None
    return min(values) if higher_is_better else max(values)


def adaptive_metric_p100(
    players: list[dict[str, Any]] | None,
    metric_id: str,
    *,
    group: str,
    category: str,
    threshold_overrides: dict[str, Any] | None = None,
) -> float | None:
    """100th cut: max/min of settings ceiling and the extreme in the phase cohort."""
    thresholds = resolve_thresholds(
        group, category, metric_id, threshold_overrides=threshold_overrides
    )
    if not thresholds:
        return None
    hib = bool((metric_defs().get(metric_id) or {}).get("higher_is_better", True))
    setting = implied_percentile_ceiling(thresholds, higher_is_better=hib)
    cohort = players_in_pos_group(players, group) or list(players or [])
    observed = metric_extreme_among_players(
        cohort, metric_id, higher_is_better=hib
    )
    if observed is None:
        return setting
    return max(setting, observed) if hib else min(setting, observed)


def adaptive_metric_p0(
    players: list[dict[str, Any]] | None,
    metric_id: str,
    *,
    group: str,
    category: str,
    threshold_overrides: dict[str, Any] | None = None,
) -> float | None:
    """0th cut: min/max of settings floor and the worst value in the phase cohort."""
    thresholds = resolve_thresholds(
        group, category, metric_id, threshold_overrides=threshold_overrides
    )
    if not thresholds:
        return None
    hib = bool((metric_defs().get(metric_id) or {}).get("higher_is_better", True))
    setting = implied_percentile_floor(thresholds, higher_is_better=hib)
    cohort = players_in_pos_group(players, group) or list(players or [])
    observed = metric_floor_among_players(
        cohort, metric_id, higher_is_better=hib
    )
    if observed is None:
        return setting
    return min(setting, observed) if hib else max(setting, observed)


def xg_prevented_p100(
    players: list[dict[str, Any]] | None,
    threshold_overrides: dict[str, Any] | None = None,
) -> float | None:
    """Adaptive 100th ceiling for GK xGP/90 (settings vs loaded dataset)."""
    return adaptive_metric_p100(
        players,
        "xg_prevented",
        group="gk",
        category="final_third",
        threshold_overrides=threshold_overrides,
    )


def _metric_bound_lookup(
    bound_map: dict[str, float] | None,
    group: str,
    metric_id: str,
) -> float | None:
    """Prefer group-scoped bound, then bare metric id."""
    if not bound_map:
        return None
    for key in (f"{group}:{metric_id}", metric_id):
        if key not in bound_map:
            continue
        try:
            return float(bound_map[key])
        except (TypeError, ValueError):
            continue
    return None


def _store_group_metric_bound(
    out: dict[str, float],
    *,
    group: str,
    metric_id: str,
    value: float,
    higher_is_better: bool,
    prefer_max: bool,
) -> None:
    """Write ``group:metric`` and merge into bare ``metric`` across groups."""
    out[f"{group}:{metric_id}"] = value
    prior = out.get(metric_id)
    if prior is None:
        out[metric_id] = value
        return
    take_max = prefer_max if higher_is_better else (not prefer_max)
    out[metric_id] = max(prior, value) if take_max else min(prior, value)


def adaptive_metric_bound_maps(
    players: list[dict[str, Any]] | None,
    threshold_overrides: dict[str, Any] | None = None,
) -> tuple[dict[str, float], dict[str, float]]:
    """Phase-scoped adaptive 0th and 100th maps.

    Returns ``(p0_map, p100_map)``. Keys are ``group:metric_id`` (preferred by
    ``band_metric``) and bare ``metric_id``. Extremes use players in that phase
    group only (Defenders / Midfielders / Forwards / Goalkeepers).
    """
    p0_out: dict[str, float] = {}
    p100_out: dict[str, float] = {}
    groups = list(benchmarks().get("groups") or ["gk", "def", "mid", "fwd"])
    categories = [cat["id"] for cat in view_categories()]
    for group in groups:
        for category in categories:
            for metric_id in metrics_for(group, category, threshold_overrides):
                hib = bool(
                    (metric_defs().get(metric_id) or {}).get("higher_is_better", True)
                )
                p0 = adaptive_metric_p0(
                    players,
                    metric_id,
                    group=group,
                    category=category,
                    threshold_overrides=threshold_overrides,
                )
                p100 = adaptive_metric_p100(
                    players,
                    metric_id,
                    group=group,
                    category=category,
                    threshold_overrides=threshold_overrides,
                )
                if p0 is not None:
                    # Floor: keep the more extreme (worse) bound across groups.
                    _store_group_metric_bound(
                        p0_out,
                        group=group,
                        metric_id=metric_id,
                        value=float(p0),
                        higher_is_better=hib,
                        prefer_max=False,
                    )
                if p100 is not None:
                    _store_group_metric_bound(
                        p100_out,
                        group=group,
                        metric_id=metric_id,
                        value=float(p100),
                        higher_is_better=hib,
                        prefer_max=True,
                    )
    return p0_out, p100_out


def adaptive_metric_p100_map(
    players: list[dict[str, Any]] | None,
    threshold_overrides: dict[str, Any] | None = None,
) -> dict[str, float]:
    """Backward-compatible 100th-only map (see :func:`adaptive_metric_bound_maps`)."""
    _p0, p100 = adaptive_metric_bound_maps(players, threshold_overrides)
    return p100


def adaptive_metric_p0_map(
    players: list[dict[str, Any]] | None,
    threshold_overrides: dict[str, Any] | None = None,
) -> dict[str, float]:
    """Adaptive 0th floor map (see :func:`adaptive_metric_bound_maps`)."""
    p0, _p100 = adaptive_metric_bound_maps(players, threshold_overrides)
    return p0


def minutes_status(minutes: float | None, required: float) -> str:
    """meet / half / fail for the minutes requirement filter."""
    if required <= 0:
        return "meet"
    if minutes is None:
        return "fail"
    if minutes >= required:
        return "meet"
    if minutes >= required / 2:
        return "half"
    return "fail"


def minutes_color(status: str) -> str:
    return {
        "meet": "rgb(64, 220, 120)",
        "half": "rgb(255, 210, 64)",
        "fail": "rgb(255, 92, 92)",
    }.get(status, "rgb(255, 92, 92)")


def has_scorable_minutes(minutes: Any) -> bool:
    """True when the player has playing time that can support percentile scores."""
    if minutes is None:
        return False
    try:
        return float(minutes) > 0
    except (TypeError, ValueError):
        return False


def scoring_stats(player: dict[str, Any] | None) -> dict[str, Any]:
    """Stats used for banding; empty when minutes are missing or zero."""
    if not player or not has_scorable_minutes(player.get("minutes")):
        return {}
    return player.get("stats") or {}


def _pick_metric_raw(row: dict[str, str], metric_id: str) -> float | None:
    meta = metric_defs()[metric_id]
    aliases = list(meta.get("csv") or [])
    prefer_per90 = bool(meta.get("prefer_per90"))
    if prefer_per90:
        # Prefer first alias that looks like per90 when present and non-empty
        for alias in aliases:
            if "90" in alias or alias.endswith("/90"):
                val = parse_number(pick(row, [alias]))
                if val is not None:
                    return val
        for alias in aliases:
            val = parse_number(pick(row, [alias]))
            if val is not None:
                # raw total — convert if minutes available
                if meta.get("unit") == "per90":
                    minutes = parse_number(pick(row, ["Minutes"]))
                    if minutes and minutes > 0:
                        return val / (minutes / 90.0)
                return val
        return None

    if meta.get("derive") == "per90_from_total":
        total = None
        for alias in aliases:
            total = parse_number(pick(row, [alias]))
            if total is not None:
                break
        if total is None:
            return None
        minutes = parse_number(pick(row, ["Minutes"]))
        if not minutes or minutes <= 0:
            return None
        return total / (minutes / 90.0)

    for alias in aliases:
        val = parse_number(pick(row, [alias]))
        if val is not None and val != 0:
            return val
    for alias in aliases:
        val = parse_number(pick(row, [alias]))
        if val is not None:
            return val
    return None


def _has_stats_columns(header: list[str]) -> bool:
    bases = {h.split(".")[0] for h in header}
    markers = {
        "Minutes",
        "Possession Won per 90",
        "Goals per 90 minutes",
        "xG/90",
        "Passes Attempted per 90",
        "Goals Allowed",
    }
    return bool(bases & markers)


def parse_stats_export(text: str) -> list[dict[str, Any]]:
    """Parse a Moneyball stats CSV into player dicts."""
    players, _limited = parse_stats_export_with_meta(text)
    return players


def parse_stats_export_with_meta(
    text: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Like :func:`parse_stats_export`, plus limited-tracking division names."""
    if not text or not text.strip():
        raise ValueError("The file is empty.")
    delim = sniff_delimiter(text)
    reader = csv.reader(io.StringIO(text), delimiter=delim)
    try:
        raw_header = next(reader)
    except StopIteration as exc:
        raise ValueError("The file has no header row.") from exc
    header = unique_headers(raw_header)
    if not any(alias in header or alias in {h.split(".")[0] for h in header} for alias in IDENTITY["Name"]):
        raise ValueError("CSV must include a Name or Player column.")
    if not _has_stats_columns(header):
        raise ValueError(
            "CSV must include statistics columns (Minutes, per-90 rates, etc.). "
            "Use the Moneyball statistics export, not the attributes-only file."
        )

    from scoring.stats_availability import (
        analyze_division_availability,
        apply_limited_tracking,
        collect_limited_tracking_divisions,
    )

    raw_rows: list[dict[str, str]] = []
    for raw in reader:
        if not raw or all(not cell.strip() for cell in raw):
            continue
        if len(raw) < len(header):
            raw = list(raw) + [""] * (len(header) - len(raw))
        elif len(raw) > len(header):
            raw = raw[: len(header)]
        row = dict(zip(header, raw))
        if not pick(row, IDENTITY["Name"]):
            continue
        raw_rows.append(row)

    division_unavailable = analyze_division_availability(raw_rows)
    limited_divisions = collect_limited_tracking_divisions(division_unavailable)

    players: list[dict[str, Any]] = []
    for row in raw_rows:
        name = pick(row, IDENTITY["Name"])
        best_pos = pick(row, IDENTITY["BestPos"])
        position = pick(row, IDENTITY["Position"])
        minutes = parse_number(pick(row, ["Minutes"]))
        group = classify_best_pos(best_pos, position)
        stats: dict[str, float] = {}
        if has_scorable_minutes(minutes):
            for metric_id in metric_defs():
                value = _pick_metric_raw(row, metric_id)
                if value is not None:
                    stats[metric_id] = value
        player_payload: dict[str, Any] = {
            "minutes": minutes,
            "pos_group": group,
            "stats": stats,
        }
        apply_limited_tracking(
            player_payload, row, division_unavailable=division_unavailable
        )
        stats = player_payload["stats"]
        all_attrs = extract_attrs(row)
        attrs = {
            code: all_attrs[code]
            for code in ("Det", "Ldr")
            if code in all_attrs and all_attrs[code]
        }
        positions = parse_positions(position) + parse_positions(
            pick(row, IDENTITY["SecPosition"])
        )
        players.append(
            {
                "name": name,
                "age": pick(row, IDENTITY["Age"]),
                "club": pick(row, IDENTITY["Club"]),
                "division": pick(row, IDENTITY["Division"]),
                "nation": pick(row, IDENTITY["Nation"])
                or pick(row, IDENTITY["BasedIn"]),
                "based_in": pick(row, IDENTITY["BasedIn"]),
                "second_nation": pick(row, IDENTITY["SecondNation"]),
                "position": position,
                "best_pos": best_pos,
                "best_role": pick(row, IDENTITY.get("BestRole", ["Best Role"])),
                "position_role": pick(row, IDENTITY.get("PositionRole", ["Position/Role"])),
                "style": pick(row, IDENTITY["Style"]),
                "personality": pick(row, IDENTITY.get("Personality", ["Personality"])),
                "media_handling": pick(
                    row, IDENTITY.get("MediaHandling", ["Media Handling"])
                ),
                "height": pick(row, IDENTITY["Height"]).strip('"'),
                "left_foot": pick(row, IDENTITY["LeftFoot"]),
                "right_foot": pick(row, IDENTITY["RightFoot"]),
                "rec": pick(row, IDENTITY["Rec"]),
                "inf": pick(row, IDENTITY["Inf"]),
                "injury": pick(row, IDENTITY["Injury"]),
                "squad": pick(row, IDENTITY["Squad"]),
                "picked": pick(row, IDENTITY.get("Picked", ["Picked"])),
                "home_grown_status": pick(
                    row, IDENTITY.get("HomeGrownStatus", ["Home Grown Status"])
                ),
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
                **extract_record_fields(row),
                **extract_finance_fields(row),
                "minutes": minutes,
                "pos_group": group,
                "pos_cards": player_pos_groups(positions),
                "stats": stats,
                "stats_limited_tracking": player_payload.get(
                    "stats_limited_tracking", False
                ),
                "stats_unavailable": list(
                    player_payload.get("stats_unavailable") or []
                ),
                "attrs": attrs,
                "positions": positions,
                "left_foot_n": int(foot_strength(pick(row, IDENTITY["LeftFoot"])) or 0),
                "right_foot_n": int(foot_strength(pick(row, IDENTITY["RightFoot"])) or 0),
            }
        )
    if not players:
        raise ValueError("No player rows found. Check that the file is an FM stats CSV export.")
    return players, limited_divisions


def percentile_marks() -> list[int]:
    """Boundary percentiles used by the benchmark tables (e.g. 20/40/60/80)."""
    marks = benchmarks().get("percentiles") or [20, 40, 60, 80]
    return [int(x) for x in marks]


def resolve_thresholds(
    group: str,
    category: str,
    metric_id: str,
    threshold_overrides: dict[str, Any] | None = None,
) -> list[float] | None:
    """Four cut-points for a metric; prefer settings overrides when present."""
    stored = storage_category(group, category)
    if not stored:
        return None
    root = (
        threshold_overrides
        if isinstance(threshold_overrides, dict) and threshold_overrides
        else benchmarks()["benchmarks"]
    )
    values = ((root.get(group) or {}).get(stored) or {}).get(metric_id)
    if not values or len(values) != 4:
        # Fall back to built-in when an override tree is incomplete.
        values = (
            (benchmarks()["benchmarks"].get(group) or {}).get(stored) or {}
        ).get(metric_id)
    if not values or len(values) != 4:
        return None
    try:
        return [float(x) for x in values]
    except (TypeError, ValueError):
        return None


def band_metric(
    group: str,
    category: str,
    metric_id: str,
    value: float | None,
    *,
    threshold_overrides: dict[str, Any] | None = None,
    metric_p100: dict[str, float] | None = None,
    metric_p0: dict[str, float] | None = None,
) -> dict[str, Any]:
    meta = metric_defs().get(metric_id) or {}
    thresholds = resolve_thresholds(
        group, category, metric_id, threshold_overrides=threshold_overrides
    )
    if value is None or not thresholds:
        return {
            "value": value,
            "display": "—",
            "percentile": None,
            "color": None,
            "higher_is_better": bool(meta.get("higher_is_better", True)),
        }
    hib = bool(meta.get("higher_is_better", True))
    p100 = _metric_bound_lookup(metric_p100, group, metric_id)
    p0 = _metric_bound_lookup(metric_p0, group, metric_id)
    pct = estimate_percentile(
        float(value),
        list(thresholds),
        higher_is_better=hib,
        p100=p100,
        p0=p0,
    )
    unit = meta.get("unit")
    if unit == "percent":
        display = f"{value:.1f}%"
    elif abs(value) >= 10:
        display = f"{value:.2f}".rstrip("0").rstrip(".")
    else:
        display = f"{value:.2f}"
    return {
        "value": value,
        "display": display,
        "percentile": pct,
        "color": percentile_color(pct),
        "higher_is_better": hib,
        "thresholds": thresholds,
    }


def category_average_band(
    group: str,
    category: str,
    stats: dict[str, Any] | None,
    *,
    threshold_overrides: dict[str, Any] | None = None,
    metric_p100: dict[str, float] | None = None,
    metric_p0: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Mean estimated percentile across metrics in one category (missing skipped)."""
    pcts: list[float] = []
    for mid in metrics_for(group, category, threshold_overrides):
        band = band_metric(
            group,
            category,
            mid,
            (stats or {}).get(mid),
            threshold_overrides=threshold_overrides,
            metric_p100=metric_p100,
            metric_p0=metric_p0,
        )
        if band.get("percentile") is not None:
            pcts.append(float(band["percentile"]))
    if not pcts:
        return {
            "value": None,
            "display": "—",
            "percentile": None,
            "color": None,
        }
    avg = sum(pcts) / len(pcts)
    return {
        "value": avg,
        "display": f"{avg:.0f}",
        "percentile": avg,
        "color": percentile_color(avg),
    }


def overall_average_band(
    group: str,
    stats: dict[str, Any] | None,
    *,
    threshold_overrides: dict[str, Any] | None = None,
    metric_p100: dict[str, float] | None = None,
    metric_p0: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Mean of the three category average percentiles (missing categories skipped)."""
    pcts: list[float] = []
    for cat in view_categories():
        band = category_average_band(
            group,
            cat["id"],
            stats,
            threshold_overrides=threshold_overrides,
            metric_p100=metric_p100,
            metric_p0=metric_p0,
        )
        if band.get("percentile") is not None:
            pcts.append(float(band["percentile"]))
    if not pcts:
        return {
            "value": None,
            "display": "—",
            "percentile": None,
            "color": None,
        }
    avg = sum(pcts) / len(pcts)
    return {
        "value": avg,
        "display": f"{avg:.0f}",
        "percentile": avg,
        "color": percentile_color(avg),
    }


def player_key(player: dict) -> str:
    return player_row_key({"Name": player.get("name"), "Club": player.get("club")})


def passes_minutes_filter(status: str, wanted: str) -> bool:
    wanted = (wanted or "any").strip().lower()
    if wanted in ("", "any", "all"):
        return True
    if wanted == "meet":
        return status == "meet"
    if wanted == "half":
        return status in ("meet", "half")
    if wanted == "fail":
        return status == "fail"
    return True


def format_stat_export_rows(
    players: list[dict],
    *,
    group: str,
    category: str,
    minutes_required: float,
) -> tuple[list[str], list[dict]]:
    """Export rows for one position filter + shared category.

    Category ids are always outfield-shaped (``defending`` / ``final_third`` /
    ``possession`` / ``all``). Keepers use the mapped GK benchmark blocks.
    """
    category = canonical_category(category)
    metric_p0, metric_p100 = adaptive_metric_bound_maps(players)
    if category == "all":
        cats = labeled_view_categories(group=group, dual_final_third=True)
        fieldnames = [
            "Name",
            "Age",
            "Height",
            "Position",
            "Left Foot",
            "Right Foot",
            "Club",
            "Rec",
            "Injury",
            "Pos Group",
            "Minutes",
            "Minutes Status",
        ]
        for cat in cats:
            fieldnames.append(cat["label"])
        fieldnames.append("Overall average")
        rows = []
        for p in players:
            g = p.get("pos_group") or "mid"
            if group not in ("", "all") and g != group:
                continue
            status = minutes_status(p.get("minutes"), minutes_required)
            row = {
                "Name": p["name"],
                "Age": p.get("age"),
                "Height": p.get("height") or "-",
                "Position": p.get("position"),
                "Left Foot": p.get("left_foot") or "-",
                "Right Foot": p.get("right_foot") or "-",
                "Club": p.get("club"),
                "Rec": p.get("rec") or "-",
                "Injury": p.get("injury") or "-",
                "Pos Group": g,
                "Minutes": p.get("minutes"),
                "Minutes Status": status,
            }
            use_g = "gk" if is_gk_group(g) else g
            stats = scoring_stats(p)
            for cat in cats:
                band = category_average_band(
                    use_g, cat["id"], stats, metric_p100=metric_p100,
                    metric_p0=metric_p0
                )
                row[cat["label"]] = band["display"]
            row["Overall average"] = overall_average_band(
                use_g, stats, metric_p100=metric_p100,
                    metric_p0=metric_p0
            )["display"]
            rows.append(row)
        return fieldnames, rows

    if group == "all":
        # Column set follows outfield metrics; keepers fill overlapping ids only.
        metric_ids = metrics_for("def", category)
        fieldnames = [
            "Name",
            "Age",
            "Height",
            "Position",
            "Left Foot",
            "Right Foot",
            "Club",
            "Rec",
            "Injury",
            "Pos Group",
            "Minutes",
            "Minutes Status",
            "Category average",
        ]
        for mid in metric_ids:
            fieldnames.append(metric_defs()[mid]["abbr"])
        rows = []
        for p in players:
            g = p.get("pos_group") or "mid"
            status = minutes_status(p.get("minutes"), minutes_required)
            row = {
                "Name": p["name"],
                "Age": p.get("age"),
                "Height": p.get("height") or "-",
                "Position": p.get("position"),
                "Left Foot": p.get("left_foot") or "-",
                "Right Foot": p.get("right_foot") or "-",
                "Club": p.get("club"),
                "Rec": p.get("rec") or "-",
                "Injury": p.get("injury") or "-",
                "Pos Group": g,
                "Minutes": p.get("minutes"),
                "Minutes Status": status,
            }
            use_g = "gk" if is_gk_group(g) else g
            stats = scoring_stats(p)
            row["Category average"] = category_average_band(
                use_g, category, stats, metric_p100=metric_p100,
                    metric_p0=metric_p0
            )["display"]
            for mid in metric_ids:
                label = metric_defs()[mid]["abbr"]
                if mid not in metrics_for(use_g, category):
                    row[label] = "—"
                    continue
                band = band_metric(
                    use_g,
                    category,
                    mid,
                    stats.get(mid),
                    metric_p100=metric_p100,
                    metric_p0=metric_p0,
                )
                row[label] = band["display"]
            rows.append(row)
        return fieldnames, rows

    metric_ids = metrics_for(group, category)
    fieldnames = [
        "Name",
        "Age",
        "Height",
        "Position",
        "Left Foot",
        "Right Foot",
        "Club",
        "Rec",
        "Injury",
        "Minutes",
        "Minutes Status",
        "Category average",
    ]
    for mid in metric_ids:
        fieldnames.append(metric_defs()[mid]["abbr"])
    rows = []
    for p in players:
        status = minutes_status(p.get("minutes"), minutes_required)
        row = {
            "Name": p["name"],
            "Age": p.get("age"),
            "Height": p.get("height") or "-",
            "Position": p.get("position"),
            "Left Foot": p.get("left_foot") or "-",
            "Right Foot": p.get("right_foot") or "-",
            "Club": p.get("club"),
            "Rec": p.get("rec") or "-",
            "Injury": p.get("injury") or "-",
            "Minutes": p.get("minutes"),
            "Minutes Status": status,
        }
        stats = scoring_stats(p)
        row["Category average"] = category_average_band(
            group, category, stats, metric_p100=metric_p100,
                    metric_p0=metric_p0
        )["display"]
        for mid in metric_ids:
            band = band_metric(
                group,
                category,
                mid,
                stats.get(mid),
                metric_p100=metric_p100,
                    metric_p0=metric_p0,
            )
            row[metric_defs()[mid]["abbr"]] = band["display"]
        rows.append(row)
    return fieldnames, rows
