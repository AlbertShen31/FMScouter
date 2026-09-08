#!/usr/bin/env python3
"""Fit engine detail-level transforms and write config/stats_detail_levels.json.

Source CSV: paired exports at No Detail / Inactive / Full Detail (900+ min).
Run after updating the calibration file path below.
"""
from __future__ import annotations

import csv
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scoring.stats_scorer import benchmarks, metric_defs  # noqa: E402

DEFAULT_SOURCE = ROOT / "data" / "calibration" / "engine_detail_metrics.csv"

PG_MAP = {
    "Goalkeepers": "gk",
    "Defenders": "def",
    "Midfielders": "mid",
    "Forwards": "fwd",
}

METRICS = {
    "xg_prevented": ("xGP", True),
    "goals_conceded": ("Goals Conceded", True),
    "possession_won": ("Poss Won/90", False),
    "possession_lost": ("Poss Lost", True),
    "progressive_passes": ("PsP", True),
    "passes_attempted": ("Pas A", True),
    "interceptions": ("Itc", True),
    "clearances": ("Clearances", True),
    "blocks": ("Blk", True),
    "tackles_attempted": ("Tck A", True),
    "key_passes": ("Key", True),
    "xa": ("xA", True),
    "shots": ("Shots", True),
    "shots_on_target": ("ShT", True),
    "xg": ("xG", True),
    "goals": ("Goals", True),
    "assists": ("Assists", True),
    "dribbles": ("Drb", True),
    "pressures": ("Pres A", True),
    "headers_attempted": ("Hdrs A", True),
}

QUARTILES = [20, 40, 60, 80]
LEVEL_KEYS = {"no_detail": "no", "inactive": "inactive"}


def norm_detail(save: str) -> str | None:
    if save.startswith("No Detail"):
        return "no_detail"
    if save.startswith("Inactive"):
        return "inactive"
    if save.startswith("Full Detail"):
        return "full_detail"
    return None


def pct(vals: list[float], p: int) -> float | None:
    if not vals:
        return None
    vals = sorted(vals)
    k = (len(vals) - 1) * p / 100
    f, c = math.floor(k), math.ceil(k)
    if f == c:
        return vals[int(k)]
    return vals[f] + (vals[c] - vals[f]) * (k - f)


def per90(total: float | None, mins: float) -> float | None:
    if total is None or mins <= 0:
        return None
    return total / (mins / 90.0)


def fit_power(xs: list[float], ys: list[float]) -> tuple[float, float] | None:
    pairs = [(x, y) for x, y in zip(xs, ys) if x > 0 and y > 0]
    if len(pairs) < 3:
        return None
    lx = [math.log(x) for x, _ in pairs]
    ly = [math.log(y) for _, y in pairs]
    mx, my = sum(lx) / len(lx), sum(ly) / len(ly)
    num = sum((lx[i] - mx) * (ly[i] - my) for i in range(len(lx)))
    den = sum((lx[i] - mx) ** 2 for i in range(len(lx)))
    if den == 0:
        return None
    b = num / den
    a = math.exp(my - b * mx)
    return round(a, 4), round(b, 4)


def fit_linear(xs: list[float], ys: list[float]) -> tuple[float, float] | None:
    pairs = [(x, y) for x, y in zip(xs, ys)]
    if len(pairs) < 3:
        return None
    xs = [p[0] for p in pairs]
    ys = [p[1] for p in pairs]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    num = sum((xs[i] - mx) * (ys[i] - my) for i in range(len(xs)))
    den = sum((xs[i] - mx) ** 2 for i in range(len(xs)))
    if den == 0:
        return None
    scale = num / den
    offset = my - scale * mx
    return round(scale, 4), round(offset, 4)


def band_val(level_dict: dict, q: int) -> float | None:
    return level_dict.get(q) if level_dict.get(q) is not None else level_dict.get(str(q))


def pick_transform(r: dict, level: str) -> dict | None:
    suffix = LEVEL_KEYS[level]
    pwr = r.get(f"power_full_to_{suffix}")
    lin = r.get(f"linear_full_to_{suffix}")
    fd = r.get("full_detail", {})
    tgt = r.get(level, {})
    if pwr and all((band_val(fd, q) or 0) > 0 and (band_val(tgt, q) or 0) > 0 for q in QUARTILES):
        return {"type": "power", "a": pwr[0], "b": pwr[1]}
    if lin is not None:
        return {"type": "linear", "scale": lin[0], "offset": lin[1]}
    return None


def analyze(source: Path) -> dict:
    bands: dict = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: {"vals": []})))
    with source.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            level = norm_detail(row["Save File"])
            if not level:
                continue
            pg = PG_MAP.get(row["Position Group"])
            if not pg:
                continue
            mins = float(row["Minutes"] or 0)
            if mins < 900:
                continue
            for mid, (col, is_total) in METRICS.items():
                raw = row.get(col)
                if raw in (None, ""):
                    continue
                val = float(raw)
                if is_total:
                    val = per90(val, mins)
                if val is None:
                    continue
                bands[pg][mid][level]["vals"].append(val)

    results: dict = {}
    for pg, metrics in bands.items():
        results[pg] = {}
        for mid, levels in metrics.items():
            if not all(k in levels for k in ("full_detail", "no_detail", "inactive")):
                continue
            fd = {q: pct(levels["full_detail"]["vals"], q) for q in QUARTILES}
            nd = {q: pct(levels["no_detail"]["vals"], q) for q in QUARTILES}
            ia = {q: pct(levels["inactive"]["vals"], q) for q in QUARTILES}
            xs = [fd[q] for q in QUARTILES]
            entry = {
                "full_detail": fd,
                "no_detail": nd,
                "inactive": ia,
            }
            for target, suffix in LEVEL_KEYS.items():
                ys = [entry[target][q] for q in QUARTILES]
                entry[f"power_full_to_{suffix}"] = fit_power(xs, ys)
                entry[f"linear_full_to_{suffix}"] = fit_linear(xs, ys)
            results[pg][mid] = entry
    return results


def build_config(analysis: dict) -> dict:
    used: set[str] = set()
    for group, cats in benchmarks()["benchmarks"].items():
        for _cat, metrics in cats.items():
            used.update(metrics.keys())

    config_metrics: dict = {}
    for mid in sorted(used):
        by_group: dict = {}
        for pg in ("gk", "def", "mid", "fwd"):
            r = (analysis.get(pg) or {}).get(mid)
            if not r:
                continue
            entry = {
                level: pick_transform(r, level)
                for level in ("no_detail", "inactive")
            }
            entry = {k: v for k, v in entry.items() if v}
            if entry:
                by_group[pg] = entry
        if by_group:
            config_metrics[mid] = by_group

    return {
        "id": "engine-detail-transforms-2026-03",
        "benchmark_reference": "full_detail",
        "default_export": "no_detail",
        "source": str(DEFAULT_SOURCE.name),
        "notes": (
            "MustermannFM / FM Stag cuts live in full_detail space. "
            "no_detail and inactive are separate tiers (inactive is lower)."
        ),
        "levels": {
            "no_detail": {"label": "No Detail"},
            "inactive": {"label": "Inactive"},
            "full_detail": {"label": "Full Detail"},
        },
        "metrics": config_metrics,
    }


def main() -> None:
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SOURCE
    if not source.is_file():
        raise SystemExit(f"Source CSV not found: {source}")
    analysis = analyze(source)
    config = build_config(analysis)
    out = ROOT / "config" / "stats_detail_levels.json"
    out.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {out} ({len(config['metrics'])} metrics)")


if __name__ == "__main__":
    main()
