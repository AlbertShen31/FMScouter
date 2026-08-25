"""Saved player profiles: one shortlist-style row snapshot per saved entry."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from config.paths import PROFILES_DIR, PROFILES_INDEX_PATH
import services.export_library as lib
from scoring.role_scorer import player_row_key
from scoring.stats_scorer import player_key as stats_player_key

SAVED_FROM_LABELS = {
    "role_scores": "Role scores",
    "stats": "Player stats",
}

# Identity fields copied from a scored role shortlist row into the snapshot.
ROLE_IDENTITY_KEYS = (
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
)


def ensure_dirs() -> None:
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    if not PROFILES_INDEX_PATH.exists():
        PROFILES_INDEX_PATH.write_text("[]\n", encoding="utf-8")


def _read_index() -> list[dict[str, Any]]:
    ensure_dirs()
    if not PROFILES_INDEX_PATH.exists():
        return []
    try:
        data = json.loads(PROFILES_INDEX_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


def _write_index(entries: list[dict[str, Any]]) -> None:
    ensure_dirs()
    PROFILES_INDEX_PATH.write_text(
        json.dumps(entries, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def split_player_key(key: str) -> tuple[str, str]:
    text = str(key or "").strip()
    if "|" in text:
        name, club = text.split("|", 1)
        return name.strip(), club.strip()
    return text, ""


def profile_identity(profile: dict[str, Any]) -> tuple[str, str]:
    row = profile.get("row") or {}
    name = str(row.get("Name") or "").strip()
    club = str(row.get("Club") or "").strip()
    if name:
        return name, club
    return split_player_key(profile.get("player_key") or "")


def profile_upsert_key(entry: dict[str, Any]) -> tuple[str, str]:
    """Dedup by player + role (role blank for stats/percentile saves)."""
    return (
        entry.get("player_key") or "",
        entry.get("role_column") or "",
    )


def _clean_cell(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (int, float, bool)):
        return value
    text = str(value).strip()
    if text in ("", "-", "—"):
        return None
    return text


def _clean_snapshot_dict(row: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(row, dict):
        return {}
    return {key: _clean_cell(value) for key, value in row.items()}


def build_role_row_snapshot(
    scored_row: dict[str, Any],
    role_column: str,
    *,
    percentiles: dict[str, Any] | None = None,
    minutes: Any = None,
) -> dict[str, Any]:
    """Preserve the computed row and add normalized role snapshot fields."""
    out = _clean_snapshot_dict(scored_row)
    score = scored_row.get(role_column)
    try:
        score_f = float(score) if score not in (None, "", "-", "—") else None
    except (TypeError, ValueError):
        score_f = None
    out["Role"] = role_column
    out["Score"] = score_f
    out["Eligible"] = bool(scored_row.get(f"{role_column} eligible"))
    pct_keys = (
        "overall",
        "overall_color",
        "defending",
        "defending_color",
        "defending_label",
        "final_third",
        "final_third_color",
        "final_third_label",
        "possession",
        "possession_color",
        "possession_label",
        "Minutes",
    )
    if percentiles:
        for key in pct_keys:
            if key in percentiles:
                out[key] = percentiles.get(key)
    if minutes is not None and out.get("Minutes") in (None, ""):
        out["Minutes"] = minutes
    return out


def percentile_fields_from_stats_player(
    player: dict[str, Any] | None,
    *,
    settings=None,
) -> dict[str, Any]:
    """Subset of ``build_stats_row_snapshot`` used when enriching role saves."""
    if not player:
        return {}
    snap = build_stats_row_snapshot(player, settings=settings)
    keys = (
        "Minutes",
        "overall",
        "overall_color",
        "defending",
        "defending_color",
        "defending_label",
        "final_third",
        "final_third_color",
        "final_third_label",
        "possession",
        "possession_color",
        "possession_label",
    )
    return {k: snap[k] for k in keys if k in snap}


def build_stats_row_snapshot(
    player: dict[str, Any],
    *,
    settings=None,
) -> dict[str, Any]:
    """One shortlist-style row: identity + overall / category percentiles."""
    import services.ui_settings as us
    from scoring.stats_scorer import (
        category_average_band,
        labeled_view_categories,
        overall_average_band,
        scoring_stats,
    )

    settings = us.normalize(settings)
    identity_cols = us.shortlist_columns_for("player_stats", settings)
    out: dict[str, Any] = {
        "Name": _clean_cell(player.get("name")),
        "Age": player.get("age"),
        "Club": _clean_cell(player.get("club")),
        "Division": _clean_cell(player.get("division")),
        "Nation": _clean_cell(player.get("nation")),
        "Position": _clean_cell(player.get("position")),
        "Best Pos": _clean_cell(player.get("best_pos")),
        "Height": _clean_cell(player.get("height")),
        "Left Foot": _clean_cell(player.get("left_foot")),
        "Right Foot": _clean_cell(player.get("right_foot")),
        "Rec": _clean_cell(player.get("rec")),
        "Injury": _clean_cell(player.get("injury")),
        "Minutes": player.get("minutes"),
    }
    # Keep only configured identity columns + core fields.
    keep = set(identity_cols) | {
        "Name",
        "Club",
        "Minutes",
        "overall",
        "defending",
        "final_third",
        "possession",
    }
    out = {k: v for k, v in out.items() if k in keep or k in ("Name", "Club")}

    stats = scoring_stats(player)
    group = player.get("pos_group") or "mid"
    thresh = settings.get("stats_thresholds")
    overall = overall_average_band(group, stats, threshold_overrides=thresh)
    out["overall"] = overall.get("percentile")
    out["overall_color"] = overall.get("color")
    for section in labeled_view_categories(group=group, dual_final_third=False):
        cat_id = section["id"]
        band = category_average_band(
            group, cat_id, stats, threshold_overrides=thresh
        )
        out[cat_id] = band.get("percentile")
        out[f"{cat_id}_color"] = band.get("color")
        out[f"{cat_id}_label"] = section.get("abbr") or section.get("label") or cat_id
    return out


def expand_role_profile_rows(
    player_keys: list[str],
    payload: dict[str, Any] | None,
    *,
    focus_roles,
    hybrids_only: bool,
    eligible_only: bool = True,
    role_players: list[dict[str, Any]] | None = None,
    stats_players: list[dict[str, Any]] | None = None,
    file_id: str = "",
    settings=None,
) -> list[dict[str, Any]]:
    """Build one snapshot entry dict per (player, eligible role) for saving.

    Each item includes ``row`` (shortlist fields + percentiles) and ``player``
    (single parsed role player for the Role scores modal).
    """
    from scoring.role_scorer import (
        combo_column_labels,
        expand_view_role_columns,
        normalize_combos,
    )

    if not player_keys:
        return []
    labels = list((payload or {}).get("roles") or [])
    if not labels:
        return []

    focused: list[str] = []
    if focus_roles is None or focus_roles == "":
        focused = []
    elif isinstance(focus_roles, str):
        text = focus_roles.strip()
        focused = [text] if text else []
    else:
        for item in focus_roles:
            text = str(item or "").strip()
            if text and text not in focused:
                focused.append(text)
    view_roles = [role for role in focused if role in labels] or labels

    combos = normalize_combos((payload or {}).get("combos"))
    if hybrids_only:
        combo_cols = combo_column_labels(combos)
        if combo_cols:
            allowed = set(combo_cols)
            view_roles = [role for role in view_roles if role in allowed] or combo_cols

    role_columns = expand_view_role_columns(
        view_roles, combos, include_parts=not hybrids_only
    )
    rows_by_key = {
        player_row_key(row): row
        for row in ((payload or {}).get("rows") or [])
        if player_row_key(row)
    }
    role_by_key = {
        player_row_key({"Name": p.get("name"), "Club": p.get("club")}): p
        for p in (role_players or [])
        if player_row_key({"Name": p.get("name"), "Club": p.get("club")})
    }
    stats_by_key = {
        stats_player_key(p): p
        for p in (stats_players or [])
        if stats_player_key(p)
    }

    out: list[dict[str, Any]] = []
    for key in player_keys:
        scored = rows_by_key.get(key)
        if scored is None:
            continue
        player = role_by_key.get(key)
        stats_player = stats_by_key.get(key)
        pct = percentile_fields_from_stats_player(stats_player, settings=settings)
        minutes = stats_player.get("minutes") if stats_player else None
        for role_col in role_columns:
            if eligible_only and not scored.get(f"{role_col} eligible"):
                continue
            out.append(
                {
                    "player_key": key,
                    "role_column": role_col,
                    "row": build_role_row_snapshot(
                        scored,
                        role_col,
                        percentiles=pct or None,
                        minutes=minutes,
                    ),
                    "player": player,
                    "stats_player": stats_player,
                    "file_id": file_id or "",
                }
            )
    return out


def load_stats_players_for_file(file_id: str) -> list[dict[str, Any]]:
    """Best-effort stats players for enriching role-score saves with percentiles."""
    if not file_id:
        return []
    try:
        import services.upload_cache as upload_cache
        from scoring.stats_scorer import parse_stats_export

        hit = upload_cache.try_stats_players(file_id)
        if hit:
            return hit[0]
        entry = lib.get_file(file_id)
        if not entry:
            return []
        text, _ = lib.read_text(file_id)
        if not text:
            return []
        # Try parsing even when the library flag is stale — combined exports
        # often include Minutes + per-90 columns for role-score saves.
        try:
            return parse_stats_export(text)
        except ValueError:
            if not entry.get("stats"):
                return []
            raise
    except Exception:
        return []


def list_profiles() -> list[dict[str, Any]]:
    entries = _read_index()
    entries.sort(key=lambda item: item.get("saved_at") or "", reverse=True)
    return entries


def list_role_profiles() -> list[dict[str, Any]]:
    return [
        entry
        for entry in list_profiles()
        if entry.get("role_column") or (entry.get("row") or {}).get("Role")
    ]


def list_percentile_profiles() -> list[dict[str, Any]]:
    """Stats / percentile snapshots (no role_column)."""
    return [
        entry
        for entry in list_profiles()
        if not entry.get("role_column") and not (entry.get("row") or {}).get("Role")
    ]


def get_profile(profile_id: str) -> dict[str, Any] | None:
    for entry in list_profiles():
        if entry.get("id") == profile_id:
            return entry
    return None


def save_profile_rows(
    items: list[dict[str, Any]],
    *,
    saved_from: str,
    source_label: str = "",
    note: str | None = None,
) -> list[dict[str, Any]]:
    """Upsert profile entries that already include a ``row`` snapshot."""
    if saved_from not in SAVED_FROM_LABELS:
        raise ValueError(f"Invalid saved_from: {saved_from}")
    note_text = str(note or "").strip()
    if len(note_text) > 500:
        raise ValueError("Note is too long (max 500 characters).")
    if not items:
        raise ValueError("No profile rows to save.")

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    index = _read_index()
    by_key: dict[tuple[str, str], dict[str, Any]] = {
        profile_upsert_key(entry): entry for entry in index
    }
    saved: list[dict[str, Any]] = []
    for item in items:
        player_key_value = str(item.get("player_key") or "").strip()
        role_column = str(item.get("role_column") or "").strip()
        row = item.get("row")
        player = item.get("player")
        stats_player = item.get("stats_player")
        file_id = str(item.get("file_id") or "").strip()
        if not player_key_value or not isinstance(row, dict):
            continue
        pair = (player_key_value, role_column)
        existing = by_key.get(pair)
        if existing:
            existing["saved_at"] = now
            existing["saved_from"] = saved_from
            existing["row"] = row
            if isinstance(player, dict):
                existing["player"] = player
            if isinstance(stats_player, dict):
                existing["stats_player"] = stats_player
            elif "stats_player" in existing and stats_player is None:
                existing.pop("stats_player", None)
            existing["source_label"] = source_label or existing.get("source_label") or ""
            if note is not None:
                existing["note"] = note_text
            if file_id:
                existing["file_id"] = file_id
            saved.append(dict(existing))
            continue
        entry = {
            "id": uuid.uuid4().hex[:12],
            "player_key": player_key_value,
            "role_column": role_column,
            "row": row,
            "source_label": source_label or "",
            "saved_from": saved_from,
            "saved_at": now,
            "note": note_text,
        }
        if isinstance(player, dict):
            entry["player"] = player
        if isinstance(stats_player, dict):
            entry["stats_player"] = stats_player
        if file_id:
            entry["file_id"] = file_id
        index.append(entry)
        by_key[pair] = entry
        saved.append(dict(entry))
    _write_index(index)
    return saved


def save_profiles(
    file_id: str,
    player_keys: list[str],
    *,
    saved_from: str,
    note: str | None = None,
    role_entries: list[tuple[str, str]] | None = None,
    payload: dict[str, Any] | None = None,
    players: list[dict[str, Any]] | None = None,
    settings=None,
    source_label: str = "",
) -> list[dict[str, Any]]:
    """Build row snapshots then upsert. Prefer ``save_profile_rows`` for new callers."""
    label = source_label
    if not label and file_id:
        entry = lib.get_file(file_id)
        if entry:
            label = lib.display_label(entry)

    if saved_from == "role_scores":
        if role_entries is None:
            raise ValueError("Role saves require role_entries or expand_role_profile_rows.")
        # Legacy path: role_entries only had keys — build from payload.
        if payload is not None:
            items = expand_role_profile_rows(
                player_keys,
                payload,
                focus_roles=None,
                hybrids_only=False,
                eligible_only=False,
            )
            # Filter to requested pairs
            wanted = {(str(a), str(b)) for a, b in role_entries}
            items = [
                item
                for item in items
                if (item["player_key"], item["role_column"]) in wanted
            ]
        else:
            raise ValueError("Role saves need the scored payload to attach row data.")
        return save_profile_rows(
            items, saved_from=saved_from, source_label=label, note=note
        )

    # Stats: one row snapshot per player.
    players = players or []
    by_key = {stats_player_key(p): p for p in players if stats_player_key(p)}
    items = []
    for key in player_keys:
        player = by_key.get(key)
        if not player:
            continue
        items.append(
            {
                "player_key": key,
                "role_column": "",
                "row": build_stats_row_snapshot(player, settings=settings),
            }
        )
    return save_profile_rows(
        items, saved_from=saved_from, source_label=label, note=note
    )


def delete_profile(profile_id: str) -> bool:
    index = _read_index()
    removed_role = ""
    kept: list[dict[str, Any]] = []
    for entry in index:
        if entry.get("id") == profile_id:
            removed_role = _entry_role(entry)
            continue
        kept.append(entry)
    if len(kept) == len(index):
        return False
    _write_index(kept)
    if removed_role:
        compact_depth_ranks(removed_role)
    return True


def _entry_role(entry: dict[str, Any]) -> str:
    return str(
        entry.get("role_column") or (entry.get("row") or {}).get("Role") or ""
    ).strip()


def _parse_depth_rank(entry: dict[str, Any]) -> int | None:
    raw = entry.get("depth_rank")
    if raw in (None, "", "-", "—"):
        return None
    try:
        rank = int(raw)
    except (TypeError, ValueError):
        return None
    return rank if rank > 0 else None


def _score_name_sort_key(entry: dict[str, Any]) -> tuple:
    """Sort key: Score desc, then overall % desc, then name. Missing values last."""
    row = entry.get("row") or {}
    score = row.get("Score")
    try:
        score_f = float(score) if score not in (None, "", "-", "—") else None
    except (TypeError, ValueError):
        score_f = None
    overall = row.get("overall")
    try:
        overall_f = (
            float(overall) if overall not in (None, "", "-", "—") else None
        )
    except (TypeError, ValueError):
        overall_f = None
    name, _club = profile_identity(entry)
    return (
        0 if score_f is not None else 1,
        -(score_f or 0.0),
        0 if overall_f is not None else 1,
        -(overall_f or 0.0),
        name.casefold(),
    )


def ordered_profiles_for_role(role_column: str) -> list[dict[str, Any]]:
    """Ranked profiles first (by depth_rank), then unranked by Score desc."""
    role = str(role_column or "").strip()
    if not role:
        return []
    entries = [entry for entry in list_role_profiles() if _entry_role(entry) == role]
    ranked: list[tuple[int, dict[str, Any]]] = []
    unranked: list[dict[str, Any]] = []
    for entry in entries:
        rank = _parse_depth_rank(entry)
        if rank is None:
            unranked.append(entry)
        else:
            ranked.append((rank, entry))
    ranked.sort(key=lambda item: (item[0], *_score_name_sort_key(item[1])))
    unranked.sort(key=_score_name_sort_key)
    return [entry for _rank, entry in ranked] + unranked


def set_depth_ranks(role_column: str, ordered_profile_ids: list[str]) -> None:
    """Rewrite contiguous 1…n for ``role_column``; clear ranks for omitted ids."""
    role = str(role_column or "").strip()
    if not role:
        return
    ordered_ids = [str(pid).strip() for pid in ordered_profile_ids if str(pid or "").strip()]
    id_to_rank = {pid: index + 1 for index, pid in enumerate(ordered_ids)}
    index = _read_index()
    for entry in index:
        if _entry_role(entry) != role:
            continue
        eid = str(entry.get("id") or "").strip()
        if eid in id_to_rank:
            entry["depth_rank"] = id_to_rank[eid]
        else:
            entry.pop("depth_rank", None)
    _write_index(index)


def compact_depth_ranks(role_column: str) -> None:
    """Renumber existing ranked entries for a role to contiguous 1…n."""
    role = str(role_column or "").strip()
    if not role:
        return
    ranked = [
        entry
        for entry in list_role_profiles()
        if _entry_role(entry) == role and _parse_depth_rank(entry) is not None
    ]
    if not ranked:
        return
    ranked.sort(key=lambda entry: (_parse_depth_rank(entry) or 0, *_score_name_sort_key(entry)))
    set_depth_ranks(role, [str(entry.get("id") or "") for entry in ranked])


def auto_rank_role_by_score(role_column: str) -> int:
    """Set depth_rank 1…n by Score desc, then overall % desc, then name."""
    role = str(role_column or "").strip()
    if not role:
        return 0
    entries = [entry for entry in list_role_profiles() if _entry_role(entry) == role]
    if not entries:
        return 0
    ordered = sorted(entries, key=_score_name_sort_key)
    set_depth_ranks(role, [str(entry.get("id") or "") for entry in ordered])
    return len(ordered)


def auto_rank_all_roles_by_score() -> int:
    roles = sorted(
        {
            role
            for entry in list_role_profiles()
            if (role := _entry_role(entry))
        }
    )
    total = 0
    for role in roles:
        total += auto_rank_role_by_score(role)
    return total


def move_depth_rank(profile_id: str, direction: int) -> bool:
    """Swap with neighbor in display order, then assign contiguous ranks for the role."""
    pid = str(profile_id or "").strip()
    if not pid or direction not in (-1, 1):
        return False
    profile = get_profile(pid)
    if not profile:
        return False
    role = _entry_role(profile)
    if not role:
        return False
    ordered = ordered_profiles_for_role(role)
    ids = [str(entry.get("id") or "") for entry in ordered]
    try:
        index = ids.index(pid)
    except ValueError:
        return False
    neighbor = index + int(direction)
    if neighbor < 0 or neighbor >= len(ids):
        return False
    ids[index], ids[neighbor] = ids[neighbor], ids[index]
    set_depth_ranks(role, ids)
    return True


def place_depth_rank(profile_id: str, target_rank: int) -> bool:
    """Move profile to a 1-based rank within its role, then renumber 1…n."""
    pid = str(profile_id or "").strip()
    try:
        want = int(target_rank)
    except (TypeError, ValueError):
        return False
    if not pid or want < 1:
        return False
    profile = get_profile(pid)
    if not profile:
        return False
    role = _entry_role(profile)
    if not role:
        return False
    ordered = ordered_profiles_for_role(role)
    ids = [str(entry.get("id") or "").strip() for entry in ordered]
    ids = [eid for eid in ids if eid]
    if pid not in ids:
        return False
    current = ids.index(pid) + 1
    if current == want:
        return False
    ids.remove(pid)
    insert_at = min(max(want, 1), len(ids) + 1) - 1
    ids.insert(insert_at, pid)
    set_depth_ranks(role, ids)
    return True


def role_score_from_profile(profile: dict[str, Any]) -> dict[str, Any]:
    row = profile.get("row") or {}
    role = profile.get("role_column") or row.get("Role") or ""
    score = row.get("Score")
    try:
        score_f = float(score) if score not in (None, "", "-") else None
    except (TypeError, ValueError):
        score_f = None
    return {
        "role": role,
        "score": score_f,
        "eligible": bool(row.get("Eligible")),
    }


def percentile_from_profile(profile: dict[str, Any]) -> dict[str, Any] | None:
    row = profile.get("row") or {}
    if "overall" not in row and "defending" not in row:
        return None
    categories = {}
    for cat_id in ("defending", "final_third", "possession"):
        if cat_id not in row:
            continue
        categories[cat_id] = {
            "label": row.get(f"{cat_id}_label") or cat_id,
            "percentile": row.get(cat_id),
            "color": row.get(f"{cat_id}_color"),
        }
    return {
        "overall": row.get("overall"),
        "overall_color": row.get("overall_color"),
        "categories": categories,
    }
