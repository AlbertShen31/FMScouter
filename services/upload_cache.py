"""Precompute role scores + stats percentiles when a CSV is saved.

Caches live under ``data/uploads/cache/{file_id}.json.gz``. The settings
signature invalidates the cache when the role pack, tier weights, set-piece
profiles, stats thresholds, or benchmarks change. Hybrid IP/OOP weights are
applied at read time (cheap) and do not force a recompute.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.paths import ROOT_DIR, UPLOAD_CACHE_DIR
import services.export_library as lib
import services.role_config as rc
import scoring.role_scorer as rs
import services.stats_threshold_packs as stp

FORMULA_VERSION = "v16"
_BENCHMARKS_PATH = ROOT_DIR / "config" / "stats_benchmarks.json"


def ensure_cache_dir() -> None:
    UPLOAD_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _cache_path(file_id: str) -> Path:
    safe = "".join(ch for ch in str(file_id) if ch.isalnum() or ch in "-_")
    return UPLOAD_CACHE_DIR / f"{safe}.json.gz"


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _sha(value: Any) -> str:
    raw = (
        value
        if isinstance(value, (bytes, bytearray))
        else _canonical_json(value).encode("utf-8")
    )
    return hashlib.sha256(raw).hexdigest()[:24]


def current_signature() -> dict[str, Any]:
    """Fingerprint of settings that affect precomputed numbers."""
    import services.ui_settings as us

    settings = us.load()
    pack_id = rc.active_pack_id()
    rc.load_pack(pack_id, persist=False)
    role_snap = rc.snapshot()
    stats_id = stp.active_id()
    stats_tree = stp.load_tree(stats_id)
    bench_hash = (
        _sha(_BENCHMARKS_PATH.read_bytes()) if _BENCHMARKS_PATH.is_file() else ""
    )
    return {
        "formula_version": FORMULA_VERSION,
        "role_pack_id": pack_id,
        "role_pack_sha": _sha(role_snap),
        "tier_weights": us.tier_weights(settings),
        "set_piece_profiles": us.set_piece_profiles(settings),
        "partial_eligibility_rules": rs.default_partial_eligibility_rules(),
        "stats_pack_id": stats_id,
        "stats_tree_sha": _sha(stats_tree),
        "stats_benchmarks_sha": bench_hash,
        "default_minutes_required": us.default_minutes_required(settings),
        "exclude_limited_leagues_adaptive_bounds": us.exclude_limited_leagues_adaptive_bounds(
            settings
        ),
    }


def signature_key(sig: dict[str, Any] | None = None) -> str:
    return _sha(sig or current_signature())


def _write_cache(file_id: str, payload: dict[str, Any]) -> Path:
    ensure_cache_dir()
    path = _cache_path(file_id)
    blob = json.dumps(payload, separators=(",", ":"), default=str).encode("utf-8")
    path.write_bytes(gzip.compress(blob, compresslevel=6))
    return path


def load_cache(file_id: str) -> dict[str, Any] | None:
    path = _cache_path(file_id)
    if not path.is_file():
        return None
    try:
        data = json.loads(gzip.decompress(path.read_bytes()).decode("utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError, EOFError):
        return None
    return data if isinstance(data, dict) else None


def delete_cache(file_id: str) -> None:
    path = _cache_path(file_id)
    if path.is_file():
        path.unlink()


def is_fresh(cache: dict[str, Any] | None, sig: dict[str, Any] | None = None) -> bool:
    if not cache:
        return False
    current = signature_key(sig)
    stored = cache.get("signature_key") or signature_key(cache.get("signature") or {})
    return stored == current and bool(cache.get("role_scores") or cache.get("stats"))


def _patch_index_cache(
    file_id: str,
    cache_meta: dict[str, Any],
    *,
    limited_tracking_divisions: list[str] | None = None,
) -> None:
    index = lib._read_index()
    changed = False
    for entry in index:
        if entry.get("id") == file_id:
            entry["cache"] = cache_meta
            if limited_tracking_divisions is not None:
                entry["limited_tracking_divisions"] = list(limited_tracking_divisions)
            changed = True
            break
    if changed:
        lib._write_index(index)


def _page_needs_cache(entry: dict[str, Any], page: str | None) -> bool:
    if page == "role_scores":
        return bool(entry.get("role_scores"))
    if page == "stats":
        return bool(entry.get("stats"))
    if page is None:
        return bool(entry.get("role_scores") or entry.get("stats"))
    return False


def cache_status_light(
    entry: dict[str, Any],
    *,
    page: str | None = None,
    sig_key: str | None = None,
) -> dict[str, Any]:
    """UI status from index metadata + cache file presence (no gzip decompress).

    Prefer this for dropdown labels so opening the picker stays cheap.
    """
    if not _page_needs_cache(entry, page):
        return {
            "status": "n/a",
            "label": "—",
            "detail": "No precompute for this page",
            "role_scores": False,
            "stats": False,
        }
    meta = entry.get("cache") or {}
    file_id = str(entry.get("id") or "")
    has_blob = bool(file_id) and _cache_path(file_id).is_file()
    role_ok = bool(meta.get("role_scores"))
    stats_ok = bool(meta.get("stats"))
    if page == "role_scores":
        page_ready = role_ok
    elif page == "stats":
        page_ready = stats_ok
    else:
        page_ready = role_ok or stats_ok

    if meta.get("status") == "error" or meta.get("error"):
        if not has_blob:
            return {
                "status": "error",
                "label": "Error",
                "detail": str(meta.get("error") or "Compute failed"),
                "role_scores": role_ok,
                "stats": stats_ok,
            }

    if not has_blob or not page_ready:
        return {
            "status": "missing",
            "label": "Not computed",
            "detail": "Run Compute on Uploads",
            "role_scores": role_ok,
            "stats": stats_ok,
        }

    current = sig_key or signature_key()
    stored = meta.get("signature_key") or ""
    if stored and stored == current:
        bits = []
        if role_ok:
            bits.append("roles")
        if stats_ok:
            bits.append("stats")
        return {
            "status": "ready",
            "label": "Ready",
            "detail": "Precomputed: " + ", ".join(bits),
            "role_scores": role_ok,
            "stats": stats_ok,
            "computed_at": meta.get("computed_at"),
        }
    return {
        "status": "stale",
        "label": "Stale",
        "detail": "Settings changed — recompute on Uploads",
        "role_scores": role_ok,
        "stats": stats_ok,
        "computed_at": meta.get("computed_at"),
    }


def cache_status(file_id: str, entry: dict[str, Any] | None = None) -> dict[str, Any]:
    """UI-facing status for one library file."""
    entry = entry or lib.get_file(file_id) or {}
    needs_role = bool(entry.get("role_scores"))
    needs_stats = bool(entry.get("stats"))
    if not needs_role and not needs_stats:
        return {
            "status": "n/a",
            "label": "—",
            "detail": "No role/stats columns to precompute",
            "role_scores": False,
            "stats": False,
        }
    cache = load_cache(file_id)
    if not cache:
        meta = entry.get("cache") or {}
        if meta.get("error"):
            return {
                "status": "error",
                "label": "Error",
                "detail": str(meta.get("error")),
                "role_scores": False,
                "stats": False,
            }
        return {
            "status": "missing",
            "label": "Not computed",
            "detail": "Run Compute on Uploads",
            "role_scores": False,
            "stats": False,
        }
    if is_fresh(cache):
        bits = []
        if cache.get("role_scores"):
            bits.append("roles")
        if cache.get("stats"):
            bits.append("stats")
        return {
            "status": "ready",
            "label": "Ready",
            "detail": "Precomputed: " + ", ".join(bits),
            "role_scores": bool(cache.get("role_scores")),
            "stats": bool(cache.get("stats")),
            "computed_at": cache.get("computed_at"),
        }
    return {
        "status": "stale",
        "label": "Stale",
        "detail": "Settings changed — recompute on Uploads",
        "role_scores": bool(cache.get("role_scores")),
        "stats": bool(cache.get("stats")),
        "computed_at": cache.get("computed_at"),
    }


def _precompute_stats_percentiles(
    players: list[dict[str, Any]],
    threshold_tree: dict[str, Any] | None,
    *,
    min_minutes: float | None = None,
    limited_divisions: list[str] | None = None,
    exclude_limited_leagues: bool = True,
) -> dict[str, dict[str, dict[str, float]]]:
    """player_key → group → metric_id → percentile."""
    from scoring.stats_scorer import (
        adaptive_metric_bound_maps,
        band_metric,
        benchmarks,
        metrics_for,
        player_key,
        scoring_stats,
    )

    groups = list(benchmarks().get("groups") or ["gk", "def", "mid", "fwd"])
    categories = ["defending", "final_third", "possession", "all"]
    metric_p0, metric_p100 = adaptive_metric_bound_maps(
        players,
        threshold_tree,
        min_minutes=min_minutes,
        limited_divisions=limited_divisions,
        exclude_limited_leagues=exclude_limited_leagues,
    )
    out: dict[str, dict[str, dict[str, float]]] = {}
    for player in players:
        key = player_key(player)
        if not key:
            continue
        stats = scoring_stats(player)
        by_group: dict[str, dict[str, float]] = {}
        for group in groups:
            metric_ids: list[str] = []
            for cat in categories:
                for mid in metrics_for(group, cat, threshold_tree):
                    if mid not in metric_ids:
                        metric_ids.append(mid)
            band_map: dict[str, float] = {}
            for mid in metric_ids:
                chosen_cat = "all"
                for cat in categories:
                    if mid in metrics_for(group, cat, threshold_tree):
                        chosen_cat = cat
                        break
                band = band_metric(
                    group,
                    chosen_cat,
                    mid,
                    stats.get(mid),
                    threshold_overrides=threshold_tree,
                    metric_p100=metric_p100,
                    metric_p0=metric_p0,
                )
                pct = band.get("percentile")
                if pct is not None:
                    band_map[mid] = float(pct)
            if band_map:
                by_group[group] = band_map
        if by_group:
            out[key] = by_group
    return out


def compute_file(file_id: str) -> dict[str, Any]:
    """Parse + score eligible pages for one saved upload; write gzip cache."""
    import config.role_weights.fm26_role_weight_config as pc
    import services.ui_settings as us
    from scoring.stats_scorer import parse_stats_export_with_meta

    text, entry = lib.read_text(file_id)
    sig = current_signature()
    settings = us.load()
    payload: dict[str, Any] = {
        "file_id": file_id,
        "signature": sig,
        "signature_key": signature_key(sig),
        "computed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "role_scores": None,
        "stats": None,
    }
    errors: list[str] = []

    if entry.get("role_scores"):
        try:
            from scoring.role_scorer import parse_export, score_players

            rc.load_pack(sig["role_pack_id"], persist=False)
            players = parse_export(text)
            role_ids = list(pc.all_positions.keys())
            rows = score_players(
                players,
                role_ids,
                tier_weights=us.tier_weights(settings),
                set_piece_profiles=us.set_piece_profiles(settings),
                partial_adjacency=rs.default_partial_adjacency(),
            )
            payload["role_scores"] = {
                "players": players,
                "rows": rows,
                "role_ids": role_ids,
                "n_players": len(players),
                "n_roles": len(role_ids),
            }
        except Exception as exc:
            errors.append(f"role_scores: {exc}")
            traceback.print_exc()

    if entry.get("stats"):
        try:
            players, limited_divisions = parse_stats_export_with_meta(text)
            tree = stp.load_tree(sig.get("stats_pack_id"))
            percentiles = _precompute_stats_percentiles(
                players,
                tree,
                min_minutes=float(us.default_minutes_required(settings)),
                limited_divisions=limited_divisions,
                exclude_limited_leagues=us.exclude_limited_leagues_adaptive_bounds(
                    settings
                ),
            )
            payload["stats"] = {
                "players": players,
                "percentiles": percentiles,
                "n_players": len(players),
                "limited_tracking_divisions": limited_divisions,
            }
            payload["limited_tracking_divisions"] = limited_divisions
        except Exception as exc:
            errors.append(f"stats: {exc}")
            traceback.print_exc()

    limited_divisions = list(payload.get("limited_tracking_divisions") or [])

    if not payload["role_scores"] and not payload["stats"]:
        meta = {
            "status": "error",
            "signature_key": payload["signature_key"],
            "computed_at": payload["computed_at"],
            "error": "; ".join(errors) or "Nothing to compute",
            "role_scores": False,
            "stats": False,
            "limited_tracking_divisions": limited_divisions,
        }
        _patch_index_cache(
            file_id, meta, limited_tracking_divisions=limited_divisions
        )
        raise ValueError(meta["error"])

    _write_cache(file_id, payload)
    meta = {
        "status": "ready",
        "signature_key": payload["signature_key"],
        "computed_at": payload["computed_at"],
        "role_scores": bool(payload["role_scores"]),
        "stats": bool(payload["stats"]),
        "error": "; ".join(errors) if errors else "",
        "limited_tracking_divisions": limited_divisions,
    }
    _patch_index_cache(
        file_id, meta, limited_tracking_divisions=limited_divisions
    )
    return payload


def try_role_players(
    file_id: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]] | None:
    cache = load_cache(file_id)
    if not is_fresh(cache) or not (cache or {}).get("role_scores"):
        return None
    players = cache["role_scores"].get("players")
    if not isinstance(players, list):
        return None
    return players, cache


def try_stats_players(
    file_id: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]] | None:
    cache = load_cache(file_id)
    if not is_fresh(cache) or not (cache or {}).get("stats"):
        return None
    players = cache["stats"].get("players")
    if not isinstance(players, list):
        return None
    return players, cache


def cached_role_rows(file_id: str) -> list[dict[str, Any]] | None:
    cache = load_cache(file_id)
    if not is_fresh(cache) or not (cache or {}).get("role_scores"):
        return None
    rows = cache["role_scores"].get("rows")
    return rows if isinstance(rows, list) else None


def cached_stats_percentiles(file_id: str) -> dict[str, Any] | None:
    cache = load_cache(file_id)
    if not is_fresh(cache) or not (cache or {}).get("stats"):
        return None
    pct = cache["stats"].get("percentiles")
    return pct if isinstance(pct, dict) else None
