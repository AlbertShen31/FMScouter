"""Precompute role scores + stats percentiles when a CSV is saved.

Caches live under ``data/uploads/cache/{file_id}.json.gz``. The settings
signature invalidates the cache when the role pack, tier weights, set-piece
profiles, stats thresholds, benchmarks, or archetype floors/defs change.
Hybrid IP/OOP weights are applied at read time (cheap) and do not force a
recompute. Stats caches also stamp each player with ``high_archetypes`` for
fast archetype filters.
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

FORMULA_VERSION = "v44"
_BENCHMARKS_PATH = ROOT_DIR / "config" / "stats_benchmarks.json"
_ARCHETYPES_PATH = ROOT_DIR / "config" / "player_archetypes.json"

# Process-level gunzip/JSON cache. Multiyear packs are ~10× single-year on disk;
# modal/rescore paths used to re-parse the same file repeatedly.
_CACHE_LRU_MAX = 4
_CACHE_LRU: dict[str, tuple[tuple[int, int], dict[str, Any]]] = {}

# Settings signature used by is_fresh / try_*_players. Rebuilding it reloads the
# role pack + stats tree (~0.5s); Profiles slot switches hit this every chart rebuild.
_SIG_MEMO: dict[str, Any] = {"fp": None, "sig": None, "key": None}


def ensure_cache_dir() -> None:
    UPLOAD_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _cache_path(file_id: str) -> Path:
    safe = "".join(ch for ch in str(file_id) if ch.isalnum() or ch in "-_")
    return UPLOAD_CACHE_DIR / f"{safe}.json.gz"


def _cache_fingerprint(path: Path) -> tuple[int, int] | None:
    try:
        st = path.stat()
    except OSError:
        return None
    return (int(st.st_mtime_ns), int(st.st_size))


def _invalidate_cache_lru(file_id: str | None = None) -> None:
    if file_id is None:
        _CACHE_LRU.clear()
        return
    _CACHE_LRU.pop(str(file_id), None)


def _remember_cache(file_id: str, fingerprint: tuple[int, int], data: dict[str, Any]) -> None:
    if len(_CACHE_LRU) >= _CACHE_LRU_MAX and file_id not in _CACHE_LRU:
        oldest = next(iter(_CACHE_LRU), None)
        if oldest is not None:
            _CACHE_LRU.pop(oldest, None)
    _CACHE_LRU[file_id] = (fingerprint, data)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _sha(value: Any) -> str:
    raw = (
        value
        if isinstance(value, (bytes, bytearray))
        else _canonical_json(value).encode("utf-8")
    )
    return hashlib.sha256(raw).hexdigest()[:24]


def _path_fp(path: Path) -> tuple[str, int, int]:
    try:
        st = path.stat()
        return (str(path), int(st.st_mtime_ns), int(st.st_size))
    except OSError:
        return (str(path), 0, 0)


def _signature_inputs_fp() -> tuple[Any, ...]:
    """Cheap mtime fingerprint so we can memoize ``current_signature``."""
    from config.paths import (
        ROLE_WEIGHTS_ACTIVE_PATH,
        ROLE_WEIGHTS_DEFAULTS_PATH,
        SETTINGS_ACTIVE_PATH,
        SETTINGS_DIR,
        STATS_THRESHOLDS_ACTIVE_PATH,
        STATS_THRESHOLDS_DEFAULTS_PATH,
    )

    paths = [
        SETTINGS_ACTIVE_PATH,
        SETTINGS_DIR / "default-overrides.json",
        ROLE_WEIGHTS_ACTIVE_PATH,
        ROLE_WEIGHTS_DEFAULTS_PATH,
        STATS_THRESHOLDS_ACTIVE_PATH,
        STATS_THRESHOLDS_DEFAULTS_PATH,
        _BENCHMARKS_PATH,
        _ARCHETYPES_PATH,
    ]
    # Active settings / role / stats pack payloads (when not builtin).
    for active_path, packs_dir in (
        (SETTINGS_ACTIVE_PATH, SETTINGS_DIR / "packs"),
        (ROLE_WEIGHTS_ACTIVE_PATH, ROLE_WEIGHTS_ACTIVE_PATH.parent / "packs"),
        (STATS_THRESHOLDS_ACTIVE_PATH, STATS_THRESHOLDS_ACTIVE_PATH.parent / "packs"),
    ):
        try:
            payload = json.loads(active_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            continue
        pack_id = str(
            payload.get("id") or payload.get("pack") or ""
        ).strip()
        if pack_id and pack_id not in ("builtin", "default"):
            paths.append(packs_dir / f"{pack_id}.json")
    return (FORMULA_VERSION, tuple(_path_fp(p) for p in paths))


def invalidate_signature_cache() -> None:
    """Drop memoized upload-cache settings signature (call after formula inputs change)."""
    _SIG_MEMO["fp"] = None
    _SIG_MEMO["sig"] = None
    _SIG_MEMO["key"] = None


def current_signature() -> dict[str, Any]:
    """Fingerprint of settings that affect precomputed numbers."""
    import services.ui_settings as us

    fp = _signature_inputs_fp()
    cached = _SIG_MEMO.get("sig")
    if cached is not None and _SIG_MEMO.get("fp") == fp:
        return cached

    settings = us.load()
    pack_id = rc.active_pack_id()
    rc.load_pack(pack_id, persist=False)
    role_snap = rc.snapshot()
    stats_id = stp.active_id()
    # load_tree(pack_id) would call _set_active and rewrite active.json every time.
    raw_tree = stp.load_tree()
    full_detail_divisions = us.normalize_stats_full_detail_divisions(
        settings.get("stats_full_detail_divisions")
    )
    sig = {
        "formula_version": FORMULA_VERSION,
        "role_pack_id": pack_id,
        "role_pack_sha": _sha(role_snap),
        "tier_weights": us.tier_weights(settings),
        "set_piece_profiles": us.set_piece_profiles(settings),
        "partial_eligibility_rules": rs.default_partial_eligibility_rules(),
        "stats_pack_id": stats_id,
        "stats_tree_sha": _sha(raw_tree),
        "stats_full_detail_divisions": full_detail_divisions,
        "stats_benchmarks_sha": (
            _sha(_BENCHMARKS_PATH.read_bytes()) if _BENCHMARKS_PATH.is_file() else ""
        ),
        "player_archetypes_sha": (
            _sha(_ARCHETYPES_PATH.read_bytes()) if _ARCHETYPES_PATH.is_file() else ""
        ),
        "archetype_tier_floors": us.normalize_archetype_tier_floors(
            settings.get("archetype_tier_floors")
        ),
        "default_minutes_required": us.default_minutes_required(settings),
        "exclude_limited_leagues_adaptive_bounds": us.exclude_limited_leagues_adaptive_bounds(
            settings
        ),
    }
    _SIG_MEMO["fp"] = fp
    _SIG_MEMO["sig"] = sig
    _SIG_MEMO["key"] = _sha(sig)
    return sig


def signature_key(sig: dict[str, Any] | None = None) -> str:
    if sig is None:
        current_signature()
        key = _SIG_MEMO.get("key")
        if isinstance(key, str) and key:
            return key
        return _sha(current_signature())
    return _sha(sig)


def _write_cache(file_id: str, payload: dict[str, Any]) -> Path:
    ensure_cache_dir()
    path = _cache_path(file_id)
    blob = json.dumps(payload, separators=(",", ":"), default=str).encode("utf-8")
    path.write_bytes(gzip.compress(blob, compresslevel=6))
    _invalidate_cache_lru(file_id)
    fingerprint = _cache_fingerprint(path)
    if fingerprint is not None:
        _remember_cache(file_id, fingerprint, payload)
    return path


def load_cache(file_id: str) -> dict[str, Any] | None:
    path = _cache_path(file_id)
    if not path.is_file():
        _invalidate_cache_lru(file_id)
        return None
    fingerprint = _cache_fingerprint(path)
    if fingerprint is None:
        return None
    hit = _CACHE_LRU.get(file_id)
    if hit and hit[0] == fingerprint:
        # Refresh insertion order for simple LRU.
        _CACHE_LRU.pop(file_id, None)
        _CACHE_LRU[file_id] = hit
        return hit[1]
    try:
        data = json.loads(gzip.decompress(path.read_bytes()).decode("utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError, EOFError):
        _invalidate_cache_lru(file_id)
        return None
    if not isinstance(data, dict):
        return None
    _remember_cache(file_id, fingerprint, data)
    return data


def delete_cache(file_id: str) -> None:
    _invalidate_cache_lru(file_id)
    path = _cache_path(file_id)
    if path.is_file():
        path.unlink()


def _players_from_cache(cache: dict[str, Any] | None, section: str) -> list[dict[str, Any]] | None:
    """Resolve player list for a cache section (shared multiyear payload supported)."""
    if not cache:
        return None
    block = cache.get(section)
    if isinstance(block, dict):
        players = block.get("players")
        if isinstance(players, list):
            return players
    shared = cache.get("players")
    if isinstance(shared, list):
        return shared
    # Older multiyear caches duplicated players under both sections.
    other = "stats" if section == "role_scores" else "role_scores"
    other_block = cache.get(other)
    if isinstance(other_block, dict):
        players = other_block.get("players")
        if isinstance(players, list):
            return players
    return None


def is_fresh(
    cache: dict[str, Any] | None,
    sig: dict[str, Any] | None = None,
    *,
    entry: dict[str, Any] | None = None,
) -> bool:
    if not cache:
        return False
    current = signature_key(sig)
    stored = cache.get("signature_key") or signature_key(cache.get("signature") or {})
    if stored != current or not bool(cache.get("role_scores") or cache.get("stats")):
        return False
    # Multi-year packs also stamp year ids/weights inside the cache signature blob.
    if entry and lib.is_multi_year(entry):
        from scoring.multi_year import pack_signature_bits

        bits = pack_signature_bits(entry)
        cached_bits = (cache.get("signature") or {}).get("multi_year_pack") or {}
        if cached_bits != bits:
            return False
    return True


def _patch_index_cache(
    file_id: str,
    cache_meta: dict[str, Any],
    *,
    limited_tracking_divisions: list[str] | None = None,
    limited_tracking_by_nation: list[dict[str, Any]] | None = None,
) -> None:
    index = lib._read_index()
    changed = False
    for entry in index:
        if entry.get("id") == file_id:
            entry["cache"] = cache_meta
            if limited_tracking_divisions is not None:
                entry["limited_tracking_divisions"] = list(limited_tracking_divisions)
            if limited_tracking_by_nation is not None:
                entry["limited_tracking_by_nation"] = list(limited_tracking_by_nation)
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
        if lib.is_multi_year(entry):
            from scoring.multi_year import pack_signature_bits

            cached_bits = meta.get("multi_year_pack") or {}
            if cached_bits != pack_signature_bits(entry):
                return {
                    "status": "stale",
                    "label": "Stale",
                    "detail": "Season files changed — recompute on Uploads",
                    "role_scores": role_ok,
                    "stats": stats_ok,
                    "computed_at": meta.get("computed_at"),
                }
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
    if is_fresh(cache, entry=entry):
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
    settings: dict[str, Any] | None = None,
) -> dict[str, dict[str, dict[str, float]]]:
    """player_key → group → metric_id → percentile."""
    import services.ui_settings as us
    from scoring.stats_scorer import (
        band_metric,
        benchmarks,
        metrics_for,
        player_key,
        scoring_stats,
    )

    settings = us.normalize(settings or {})
    if settings.get("stats_threshold_trees"):
        banding_ctx = us.build_stats_banding_context(
            settings,
            players,
            limited_divisions=limited_divisions,
            min_minutes=min_minutes,
            exclude_limited_leagues=exclude_limited_leagues,
        )
    else:
        from scoring.stats_scorer import adaptive_metric_bound_maps

        metric_p0, metric_p100 = adaptive_metric_bound_maps(
            players,
            threshold_tree,
            min_minutes=min_minutes,
            limited_divisions=limited_divisions,
            exclude_limited_leagues=exclude_limited_leagues,
        )
        banding_ctx = None

    groups = list(benchmarks().get("groups") or ["gk", "def", "mid", "fwd"])
    categories = ["defending", "final_third", "possession", "all"]
    out: dict[str, dict[str, dict[str, float]]] = {}
    for player in players:
        key = player_key(player)
        if not key:
            continue
        if banding_ctx:
            tree, metric_p0, metric_p100 = us.banding_for_player(banding_ctx, player)
        else:
            tree = threshold_tree
        stats = scoring_stats(player)
        by_group: dict[str, dict[str, float]] = {}
        for group in groups:
            metric_ids: list[str] = []
            for cat in categories:
                for mid in metrics_for(group, cat, tree, include_hidden=True):
                    if mid not in metric_ids:
                        metric_ids.append(mid)
            band_map: dict[str, float] = {}
            for mid in metric_ids:
                chosen_cat = "all"
                for cat in categories:
                    if mid in metrics_for(group, cat, tree, include_hidden=True):
                        chosen_cat = cat
                        break
                band = band_metric(
                    group,
                    chosen_cat,
                    mid,
                    stats.get(mid),
                    threshold_overrides=tree,
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


def _compute_single_file(
    file_id: str,
    text: str,
    entry: dict[str, Any],
    *,
    sig: dict[str, Any],
    settings: dict[str, Any],
) -> dict[str, Any]:
    import config.role_weights.fm26_role_weight_config as pc
    import services.ui_settings as us
    from scoring.stats_scorer import parse_stats_export_with_meta

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
            from scoring.stats_availability import nation_counts_for_limited_divisions

            players, limited_divisions = parse_stats_export_with_meta(text)
            percentiles = _precompute_stats_percentiles(
                players,
                stp.load_tree(sig.get("stats_pack_id")),
                min_minutes=float(us.default_minutes_required(settings)),
                limited_divisions=limited_divisions,
                exclude_limited_leagues=us.exclude_limited_leagues_adaptive_bounds(
                    settings
                ),
                settings=settings,
            )
            from scoring.player_archetypes import stamp_high_archetypes

            min_minutes = float(us.default_minutes_required(settings))
            exclude_limited = us.exclude_limited_leagues_adaptive_bounds(settings)
            banding_ctx = us.build_stats_banding_context(
                settings,
                players,
                limited_divisions=limited_divisions,
                min_minutes=min_minutes,
                exclude_limited_leagues=exclude_limited,
            )
            high_archetypes = stamp_high_archetypes(
                players,
                settings=settings,
                banding_ctx=banding_ctx,
                limited_divisions=limited_divisions,
            )
            payload["stats"] = {
                "players": players,
                "percentiles": percentiles,
                "high_archetypes": high_archetypes,
                "n_players": len(players),
                "limited_tracking_divisions": limited_divisions,
            }
            payload["limited_tracking_divisions"] = limited_divisions
            payload["limited_tracking_by_nation"] = [
                {"nation": nation, "count": count}
                for nation, count in nation_counts_for_limited_divisions(
                    limited_divisions, players
                )
            ]
        except Exception as exc:
            errors.append(f"stats: {exc}")
            traceback.print_exc()

    payload["_errors"] = errors
    return payload


def _compute_multi_year_pack(
    file_id: str,
    entry: dict[str, Any],
    *,
    sig: dict[str, Any],
    settings: dict[str, Any],
) -> dict[str, Any]:
    import config.role_weights.fm26_role_weight_config as pc
    import services.ui_settings as us
    from scoring.multi_year import (
        attach_role_scores_by_year,
        merge_year_maps,
        pack_signature_bits,
    )
    from scoring.role_scorer import parse_export, score_players
    from scoring.stats_availability import nation_counts_for_limited_divisions
    from scoring.stats_scorer import parse_stats_export_with_meta

    years = lib.configured_years(entry)
    weights = lib.year_weights(entry)
    configured = list(years.keys())
    if not configured:
        raise ValueError("Multi-year pack has no season files assigned.")

    pack_bits = pack_signature_bits(entry)
    full_sig = dict(sig)
    full_sig["multi_year_pack"] = pack_bits

    payload: dict[str, Any] = {
        "file_id": file_id,
        "signature": full_sig,
        "signature_key": signature_key(sig),
        "computed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "role_scores": None,
        "stats": None,
        "multi_year": True,
        "years": years,
        "weights": weights,
    }
    errors: list[str] = []

    role_by_year: dict[str, list[dict[str, Any]]] = {}
    stats_by_year: dict[str, list[dict[str, Any]]] = {}
    want_roles = bool(entry.get("role_scores"))
    want_stats = bool(entry.get("stats"))

    for year, src_id in years.items():
        src_entry = lib.get_file(src_id) or {}
        text: str | None = None

        def _season_text() -> str:
            nonlocal text, src_entry
            if text is None:
                text, src_entry = lib.read_text(src_id)
            return text

        if want_roles and src_entry.get("role_scores"):
            try:
                hit = try_role_players(src_id)
                if hit:
                    role_by_year[year] = hit[0]
                else:
                    role_by_year[year] = parse_export(_season_text())
            except Exception as exc:
                errors.append(f"role year {year}: {exc}")
                traceback.print_exc()
        if want_stats and src_entry.get("stats"):
            try:
                hit = try_stats_players(src_id)
                if hit:
                    stats_by_year[year] = hit[0]
                else:
                    players, _limited = parse_stats_export_with_meta(_season_text())
                    stats_by_year[year] = players
            except Exception as exc:
                errors.append(f"stats year {year}: {exc}")
                traceback.print_exc()

    if want_roles and not role_by_year:
        errors.append("role_scores: no seasons parsed")
    if want_stats and not stats_by_year:
        errors.append("stats: no seasons parsed")

    try:
        merged, limited_divisions = merge_year_maps(
            role_by_year=role_by_year if want_roles else None,
            stats_by_year=stats_by_year if want_stats else None,
            configured=configured,
            weights=weights,
        )
    except Exception as exc:
        payload["_errors"] = errors + [str(exc)]
        traceback.print_exc()
        return payload

    role_ids = list(pc.all_positions.keys())
    tier_w = us.tier_weights(settings)
    sp_profiles = us.set_piece_profiles(settings)

    # One shared players list — duplicated under role_scores + stats nearly
    # doubled multiyear cache size for identical blobs.
    payload["players"] = merged

    if want_roles and role_by_year:
        try:
            rc.load_pack(sig["role_pack_id"], persist=False)
            attach_role_scores_by_year(
                merged,
                role_players_by_year=role_by_year,
                role_ids=role_ids,
                weights=weights,
                tier_weights=tier_w,
                set_piece_profiles=sp_profiles,
            )
            rows = score_players(
                merged,
                role_ids,
                tier_weights=tier_w,
                set_piece_profiles=sp_profiles,
                partial_adjacency=rs.default_partial_adjacency(),
            )
            # Stamp growth maps onto scored rows for table display.
            # Per-year / Combined score columns are derived at read time from
            # role_scores_by_year (avoid ~200 denormalized columns per row).
            from scoring.role_scorer import player_row_key

            by_key = {player_row_key(p): p for p in merged if player_row_key(p)}
            for row in rows:
                key = player_row_key(row) if "name" in row else None
                # score_players rows use "Name" not "name"
                if not key:
                    key = player_row_key(
                        {
                            "name": row.get("Name"),
                            "unique_id": row.get("Unique ID"),
                            "club": row.get("Club"),
                        }
                    )
                src = by_key.get(key) if key else None
                if not src:
                    continue
                row["multi_year_status"] = src.get("multi_year_status")
                row["years_present"] = list(src.get("years_present") or [])
                row["role_scores_by_year"] = src.get("role_scores_by_year") or {}
                row["role_scores_combined"] = src.get("role_scores_combined") or {}
                if src.get("by_year"):
                    row["by_year"] = src.get("by_year")
                if src.get("multi_year"):
                    row["multi_year"] = True
            payload["role_scores"] = {
                "rows": rows,
                "role_ids": role_ids,
                "n_players": len(merged),
                "n_roles": len(role_ids),
                "multi_year": True,
            }
        except Exception as exc:
            errors.append(f"role_scores: {exc}")
            traceback.print_exc()

    if want_stats and stats_by_year:
        try:
            percentiles = _precompute_stats_percentiles(
                merged,
                stp.load_tree(sig.get("stats_pack_id")),
                min_minutes=float(us.default_minutes_required(settings)),
                limited_divisions=limited_divisions,
                exclude_limited_leagues=us.exclude_limited_leagues_adaptive_bounds(
                    settings
                ),
                settings=settings,
            )
            from scoring.player_archetypes import stamp_high_archetypes

            min_minutes = float(us.default_minutes_required(settings))
            exclude_limited = us.exclude_limited_leagues_adaptive_bounds(settings)
            banding_ctx = us.build_stats_banding_context(
                settings,
                merged,
                limited_divisions=limited_divisions,
                min_minutes=min_minutes,
                exclude_limited_leagues=exclude_limited,
                cache_key=f"compute:{file_id}",
            )
            high_archetypes = stamp_high_archetypes(
                merged,
                settings=settings,
                banding_ctx=banding_ctx,
                limited_divisions=limited_divisions,
            )
            payload["stats"] = {
                "percentiles": percentiles,
                "high_archetypes": high_archetypes,
                "n_players": len(merged),
                "limited_tracking_divisions": limited_divisions,
                "multi_year": True,
            }
            payload["limited_tracking_divisions"] = limited_divisions
            payload["limited_tracking_by_nation"] = [
                {"nation": nation, "count": count}
                for nation, count in nation_counts_for_limited_divisions(
                    limited_divisions, merged
                )
            ]
        except Exception as exc:
            errors.append(f"stats: {exc}")
            traceback.print_exc()

    payload["_errors"] = errors
    return payload


def compute_file(file_id: str) -> dict[str, Any]:
    """Parse + score eligible pages for one saved upload; write gzip cache."""
    import services.ui_settings as us

    entry = lib.get_file(file_id)
    if not entry:
        raise FileNotFoundError("Saved file not found.")
    sig = current_signature()
    settings = us.load()

    if lib.is_multi_year(entry):
        payload = _compute_multi_year_pack(
            file_id, entry, sig=sig, settings=settings
        )
    else:
        text, entry = lib.read_text(file_id)
        payload = _compute_single_file(
            file_id, text, entry, sig=sig, settings=settings
        )

    errors = list(payload.pop("_errors", []) or [])
    limited_divisions = list(payload.get("limited_tracking_divisions") or [])
    limited_by_nation = list(payload.get("limited_tracking_by_nation") or [])

    if not payload.get("role_scores") and not payload.get("stats"):
        meta = {
            "status": "error",
            "signature_key": payload["signature_key"],
            "computed_at": payload["computed_at"],
            "error": "; ".join(errors) or "Nothing to compute",
            "role_scores": False,
            "stats": False,
            "limited_tracking_divisions": limited_divisions,
            "limited_tracking_by_nation": limited_by_nation,
        }
        _patch_index_cache(
            file_id,
            meta,
            limited_tracking_divisions=limited_divisions,
            limited_tracking_by_nation=limited_by_nation,
        )
        raise ValueError(meta["error"])

    _write_cache(file_id, payload)
    meta = {
        "status": "ready",
        "signature_key": payload["signature_key"],
        "computed_at": payload["computed_at"],
        "role_scores": bool(payload.get("role_scores")),
        "stats": bool(payload.get("stats")),
        "error": "; ".join(errors) if errors else "",
        "limited_tracking_divisions": limited_divisions,
        "limited_tracking_by_nation": limited_by_nation,
        "multi_year": bool(lib.is_multi_year(entry)),
    }
    if lib.is_multi_year(entry):
        from scoring.multi_year import pack_signature_bits

        meta["multi_year_pack"] = pack_signature_bits(entry)
    _patch_index_cache(
        file_id,
        meta,
        limited_tracking_divisions=limited_divisions,
        limited_tracking_by_nation=limited_by_nation,
    )
    return payload


def try_role_players(
    file_id: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]] | None:
    entry = lib.get_file(file_id)
    cache = load_cache(file_id)
    if not is_fresh(cache, entry=entry) or not (cache or {}).get("role_scores"):
        return None
    players = _players_from_cache(cache, "role_scores")
    if not isinstance(players, list):
        return None
    return players, cache


def try_stats_players(
    file_id: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]] | None:
    entry = lib.get_file(file_id)
    cache = load_cache(file_id)
    if not is_fresh(cache, entry=entry) or not (cache or {}).get("stats"):
        return None
    players = _players_from_cache(cache, "stats")
    if not isinstance(players, list):
        return None
    return players, cache


def cached_role_rows(file_id: str) -> list[dict[str, Any]] | None:
    entry = lib.get_file(file_id)
    cache = load_cache(file_id)
    if not is_fresh(cache, entry=entry) or not (cache or {}).get("role_scores"):
        return None
    rows = cache["role_scores"].get("rows")
    return rows if isinstance(rows, list) else None


def cached_stats_percentiles(file_id: str) -> dict[str, Any] | None:
    entry = lib.get_file(file_id)
    cache = load_cache(file_id)
    if not is_fresh(cache, entry=entry) or not (cache or {}).get("stats"):
        return None
    pct = cache["stats"].get("percentiles")
    return pct if isinstance(pct, dict) else None


def cached_high_archetypes(file_id: str) -> dict[str, list[str]] | None:
    """player_key → high archetype ids from a fresh upload cache."""
    entry = lib.get_file(file_id)
    cache = load_cache(file_id)
    if not is_fresh(cache, entry=entry) or not (cache or {}).get("stats"):
        return None
    raw = cache["stats"].get("high_archetypes")
    if not isinstance(raw, dict):
        return None
    out: dict[str, list[str]] = {}
    for key, ids in raw.items():
        key_s = str(key or "").strip()
        if not key_s or not isinstance(ids, (list, tuple)):
            continue
        cleaned = [str(item).strip() for item in ids if str(item).strip()]
        if cleaned:
            out[key_s] = cleaned
    return out
