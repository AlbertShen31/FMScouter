"""Engine detail-level transforms for stats percentile benchmarks.

MustermannFM / FM Stag cut-points are stored in ``full_detail`` space
(``config/stats_detail_levels.json``). Per-division detail tiers:

- User-designated divisions → ``full_detail`` (no transform)
- Limited-tracking divisions → ``inactive``
- All other divisions → ``no_detail`` (default)
"""
from __future__ import annotations

import copy
import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Any

CONFIG_PATH = (
    Path(__file__).resolve().parents[1] / "config" / "stats_detail_levels.json"
)

BENCHMARK_REFERENCE = "full_detail"
DEFAULT_EXPORT = "no_detail"
VALID_LEVELS = frozenset({"no_detail", "inactive", "full_detail"})


@lru_cache(maxsize=1)
def _config() -> dict[str, Any]:
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def benchmark_reference_level() -> str:
    return str(_config().get("benchmark_reference") or BENCHMARK_REFERENCE)


def default_export_level() -> str:
    return str(_config().get("default_export") or DEFAULT_EXPORT)


def detail_level_options() -> list[dict[str, str]]:
    levels = _config().get("levels") or {}
    if isinstance(levels, dict) and levels:
        return [
            {"value": level_id, "label": str(meta.get("label") or level_id)}
            for level_id, meta in levels.items()
            if isinstance(meta, dict)
        ]
    return [
        {"value": "no_detail", "label": "No Detail"},
        {"value": "inactive", "label": "Inactive"},
        {"value": "full_detail", "label": "Full Detail"},
    ]


def normalize_detail_level(raw) -> str:
    text = str(raw or "").strip().lower().replace(" ", "_")
    if text in VALID_LEVELS:
        return text
    aliases = {
        "no": "no_detail",
        "none": "no_detail",
        "full": "full_detail",
    }
    return aliases.get(text, default_export_level())


def engine_detail_level_for_division(
    division: str | None,
    *,
    full_detail_divisions: set[str] | frozenset[str] | list[str] | None = None,
    limited_divisions: set[str] | frozenset[str] | list[str] | None = None,
) -> str:
    """Map a division to full_detail, inactive (limited tracking), or no_detail."""
    div = str(division or "").strip()
    if div in ("-", "—"):
        div = ""
    full_set = {str(x).strip() for x in (full_detail_divisions or []) if str(x).strip()}
    if div and div in full_set:
        return "full_detail"
    from scoring.stats_availability import division_has_limited_tracking

    if division_has_limited_tracking(div, limited_divisions):
        return "inactive"
    return default_export_level()


def engine_detail_level_for_player(
    player: dict[str, Any] | None,
    *,
    full_detail_divisions: set[str] | frozenset[str] | list[str] | None = None,
    limited_divisions: set[str] | frozenset[str] | list[str] | None = None,
) -> str:
    if not player:
        return default_export_level()
    return engine_detail_level_for_division(
        player.get("division"),
        full_detail_divisions=full_detail_divisions,
        limited_divisions=limited_divisions,
    )


def threshold_trees_by_level(
    raw_tree: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    """Precompute full_detail / no_detail / inactive threshold trees from pack cuts."""
    if not isinstance(raw_tree, dict) or not raw_tree:
        return {}
    return {
        "full_detail": copy.deepcopy(raw_tree),
        "no_detail": apply_detail_level_to_threshold_tree(
            copy.deepcopy(raw_tree), export_detail_level="no_detail"
        ),
        "inactive": apply_detail_level_to_threshold_tree(
            copy.deepcopy(raw_tree), export_detail_level="inactive"
        ),
    }


def _transform_spec(metric_id: str, pos_group: str, export_level: str) -> dict[str, Any] | None:
    export_level = normalize_detail_level(export_level)
    if export_level == benchmark_reference_level():
        return None
    metrics = _config().get("metrics") or {}
    group_cfg = (metrics.get(metric_id) or {}).get(pos_group)
    if not isinstance(group_cfg, dict):
        return None
    spec = group_cfg.get(export_level)
    return spec if isinstance(spec, dict) else None


def apply_transform(value: float, spec: dict[str, Any]) -> float:
    kind = spec.get("type")
    if kind == "power":
        return float(spec["a"]) * float(value) ** float(spec["b"])
    if kind == "linear":
        return float(spec["scale"]) * float(value) + float(spec["offset"])
    return float(value)


def inverse_transform(value: float, spec: dict[str, Any]) -> float:
    kind = spec.get("type")
    if kind == "power":
        a, b = float(spec["a"]), float(spec["b"])
        if a <= 0 or b <= 0:
            return float(value)
        return (float(value) / a) ** (1.0 / b)
    if kind == "linear":
        scale = float(spec["scale"])
        if scale == 0:
            return float(value)
        return (float(value) - float(spec["offset"])) / scale
    return float(value)


def transform_thresholds(
    thresholds: list[float],
    metric_id: str,
    pos_group: str,
    *,
    from_level: str,
    to_level: str,
) -> list[float]:
    """Transform four percentile cut-points between detail levels."""
    from_level = normalize_detail_level(from_level)
    to_level = normalize_detail_level(to_level)
    if from_level == to_level:
        return [float(x) for x in thresholds]
    ref = benchmark_reference_level()
    via_ref = [
        transform_value(t, metric_id, pos_group, from_level=from_level, to_level=ref)
        for t in thresholds
    ]
    return [
        transform_value(t, metric_id, pos_group, from_level=ref, to_level=to_level)
        for t in via_ref
    ]


def transform_value(
    value: float,
    metric_id: str,
    pos_group: str,
    *,
    from_level: str,
    to_level: str,
) -> float:
    from_level = normalize_detail_level(from_level)
    to_level = normalize_detail_level(to_level)
    if from_level == to_level:
        return float(value)
    ref = benchmark_reference_level()
    current = float(value)
    if from_level != ref:
        spec = _transform_spec(metric_id, pos_group, from_level)
        if spec:
            current = inverse_transform(current, spec)
    if to_level == ref:
        return current
    spec = _transform_spec(metric_id, pos_group, to_level)
    if not spec:
        return current
    return apply_transform(current, spec)


def apply_detail_level_to_threshold_tree(
    tree: dict[str, Any] | None,
    *,
    export_detail_level: str | None = None,
    benchmark_level: str | None = None,
) -> dict[str, Any]:
    """Map benchmark cut-points from reference detail level to export detail level."""
    if not isinstance(tree, dict) or not tree:
        return tree or {}
    export_level = normalize_detail_level(export_detail_level or default_export_level())
    bench_level = normalize_detail_level(benchmark_level or benchmark_reference_level())
    if export_level == bench_level:
        return tree
    out = copy.deepcopy(tree)
    for group, cats in out.items():
        if not isinstance(cats, dict):
            continue
        pos_group = str(group)
        for _cat, metrics in cats.items():
            if not isinstance(metrics, dict):
                continue
            for metric_id, row in list(metrics.items()):
                if not isinstance(row, (list, tuple)) or len(row) != 4:
                    continue
                spec = _transform_spec(metric_id, pos_group, export_level)
                if not spec:
                    continue
                try:
                    parsed = [float(x) for x in row]
                except (TypeError, ValueError):
                    continue
                metrics[metric_id] = [
                    round(x, 4) if math.isfinite(x) else x
                    for x in (apply_transform(t, spec) for t in parsed)
                ]
    return out
