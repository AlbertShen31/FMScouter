"""Import FM saves / Moneyball CSVs into career mid/end season snapshots."""
from __future__ import annotations

import csv
import io
import shutil
import uuid
import warnings
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Literal

import services.careers as careers
import services.fmsave_export as fms

SlotName = Literal["mid", "end"]
ScheduleKind = Literal["summer_spring", "winter_fall"]
SCHEDULES: tuple[ScheduleKind, ...] = ("summer_spring", "winter_fall")
DEFAULT_SCHEDULE: ScheduleKind = "summer_spring"

HIDDEN_ATTR_FIELD_TO_LABEL: dict[str, str] = {
    "consistency": "Consistency",
    "dirtiness": "Dirtiness",
    "important_matches": "Important Matches",
    "injury_proneness": "Injury Proneness",
    "versatility": "Versatility",
}

PERSONALITY_ATTR_FIELD_TO_LABEL: dict[str, str] = {
    "adaptability": "Adaptability",
    "ambition": "Ambition",
    "loyalty": "Loyalty",
    "pressure": "Pressure",
    "professionalism": "Professionalism",
    "sportsmanship": "Sportsmanship",
    "temperament": "Temperament",
    "controversy": "Controversy",
}

_FINANCE_CSV_KEYS = (
    "Salary",
    "Appearance Fee",
    "Unused Substitute Fee",
    "Transfer Value",
    "Expires",
    "Shutout Bonus",
    "Int Cap Bonus",
    "Minimum Fee Release Clause",
    "Relegation Release Clause",
    "Non Promotion Release Clause",
    "Minimum Fee Release Clause (Foreign Clubs)",
    "Minimum Fee Release Clause (Domestic Clubs)",
    "Minimum Fee Release Clause (Domestic Clubs in Higher Division)",
    "Top Division Relegation Salary Drop",
)

_STATS_CSV_KEYS = tuple(fms._season_columns(None).keys())  # noqa: SLF001
_VISIBLE_ATTR_LABELS = tuple(fms.ATTR_FIELD_TO_CSV.values())
_HIDDEN_ATTR_LABELS = tuple(HIDDEN_ATTR_FIELD_TO_LABEL.values())
_PERSONALITY_ATTR_LABELS = tuple(PERSONALITY_ATTR_FIELD_TO_LABEL.values())


def _utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _parse_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def normalize_schedule(value: Any) -> ScheduleKind:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "summer_spring": "summer_spring",
        "summer_to_spring": "summer_spring",
        "summer": "summer_spring",
        "winter_fall": "winter_fall",
        "winter_to_fall": "winter_fall",
        "winter": "winter_fall",
    }
    return aliases.get(text, DEFAULT_SCHEDULE)  # type: ignore[return-value]


def season_from_game_date(
    game_date: date | None,
    *,
    schedule: ScheduleKind | str | None = None,
) -> dict[str, Any]:
    """Auto season bounds/label from save date for the active schedule.

    summer_spring: Jul+ starts ``YYYY/(YY+1)`` (e.g. 2026/27).
    winter_fall: calendar year ``YYYY``.
    """
    kind = normalize_schedule(schedule)
    if game_date is None:
        game_date = date.today()
    if kind == "winter_fall":
        year = game_date.year
        return {
            "id": str(year),
            "label": str(year),
            "year_start": year,
            "year_end": year,
            "schedule": kind,
        }
    if game_date.month >= 7:
        year_start = game_date.year
        year_end = game_date.year + 1
    else:
        year_start = game_date.year - 1
        year_end = game_date.year
    label = f"{year_start}/{str(year_end)[-2:]}"
    season_id = f"{year_start}-{year_end}"
    return {
        "id": season_id,
        "label": label,
        "year_start": year_start,
        "year_end": year_end,
        "schedule": kind,
    }


def suggest_slot(
    game_date: date | None,
    *,
    schedule: ScheduleKind | str | None = None,
) -> SlotName:
    """Mid window depends on schedule; otherwise End.

    summer_spring mid: ~15 Dec–1 Jan (winter break).
    winter_fall mid: ~15 Jun–30 Jul (summer midpoint).
    """
    if game_date is None:
        return "end"
    kind = normalize_schedule(schedule)
    month, day = game_date.month, game_date.day
    if kind == "winter_fall":
        if month == 6 and day >= 15:
            return "mid"
        if month == 7 and day <= 30:
            return "mid"
        return "end"
    if month == 12 and day >= 15:
        return "mid"
    if month == 1 and day <= 1:
        return "mid"
    return "end"


def classify_import(
    game_date: date | None,
    *,
    schedule: ScheduleKind | str | None = None,
) -> dict[str, Any]:
    kind = normalize_schedule(schedule)
    season = season_from_game_date(game_date, schedule=kind)
    return {
        **season,
        "slot": suggest_slot(game_date, schedule=kind),
        "game_date": game_date.isoformat() if game_date else None,
    }


def _winter_season(year: int, *, slot: SlotName, game_date: date | None = None) -> dict[str, Any]:
    return {
        "id": str(year),
        "label": str(year),
        "year_start": year,
        "year_end": year,
        "slot": slot,
        "schedule": "winter_fall",
        "game_date": game_date.isoformat() if game_date else None,
    }


def _summer_season(
    year_start: int,
    year_end: int,
    *,
    slot: SlotName,
    game_date: date | None = None,
) -> dict[str, Any]:
    return {
        "id": f"{year_start}-{year_end}",
        "label": f"{year_start}/{str(year_end)[-2:]}",
        "year_start": year_start,
        "year_end": year_end,
        "slot": slot,
        "schedule": "summer_spring",
        "game_date": game_date.isoformat() if game_date else None,
    }


def _parse_year_bounds(
    year_start: int | None,
    year_end: int | None,
) -> tuple[int, int]:
    try:
        ys = int(year_start) if year_start not in (None, "") else 0
    except (TypeError, ValueError):
        ys = 0
    try:
        ye = int(year_end) if year_end not in (None, "") else 0
    except (TypeError, ValueError):
        ye = 0
    return ys, ye


def infer_schedule_from_bounds(
    year_start: int | None,
    year_end: int | None,
) -> ScheduleKind | None:
    """Split years ⇒ summer_spring; single calendar year ⇒ winter_fall."""
    ys, ye = _parse_year_bounds(year_start, year_end)
    if not ys and not ye:
        return None
    if ys and ye and ys != ye:
        return "summer_spring"
    return "winter_fall"


def season_matches_schedule(
    year_start: int | None,
    year_end: int | None,
    schedule: ScheduleKind | str | None,
) -> bool:
    """True when season bounds match the schedule's year type."""
    kind = normalize_schedule(schedule)
    ys, ye = _parse_year_bounds(year_start, year_end)
    if not ys and not ye:
        return False
    if kind == "winter_fall":
        return ys == ye
    return bool(ys and ye and ys != ye)


def remap_season_slot(
    *,
    year_start: int | None,
    year_end: int | None,
    slot: SlotName | str | None,
    from_schedule: ScheduleKind | str | None,
    to_schedule: ScheduleKind | str | None,
    game_date: date | None = None,
) -> dict[str, Any]:
    """Map a season mid/end slot across Summer→Spring ↔ Winter→Fall calendars.

    Summer ``YYYY/(YY+1)`` mid → Winter ``YYYY`` end;
    Summer ``YYYY/(YY+1)`` end → Winter ``YY+1`` mid.
    Inverse for Winter → Summer. Season year shape overrides ``from_schedule``
    so leftover opposite-type seasons convert correctly. Falls back to
    game-date classification when season bounds are missing.
    """
    to_kind = normalize_schedule(to_schedule)
    ys, ye = _parse_year_bounds(year_start, year_end)
    # Prefer bounds shape over the career's previous schedule so leftover
    # opposite-type seasons (full vs split) convert instead of lingering.
    inferred = infer_schedule_from_bounds(ys, ye)
    from_kind = inferred or normalize_schedule(from_schedule)
    slot_name: SlotName = "mid" if str(slot or "").strip().lower() == "mid" else "end"

    if not ys and not ye:
        return classify_import(game_date, schedule=to_kind)

    if from_kind == to_kind:
        if to_kind == "winter_fall":
            return _winter_season(ys or ye, slot=slot_name, game_date=game_date)
        return _summer_season(ys, ye, slot=slot_name, game_date=game_date)

    if from_kind == "summer_spring" and to_kind == "winter_fall":
        # 2025/26 mid → 2025 end; 2025/26 end → 2026 mid
        if slot_name == "mid":
            return _winter_season(ys, slot="end", game_date=game_date)
        return _winter_season(ye or (ys + 1), slot="mid", game_date=game_date)

    # winter_fall → summer_spring: mid Y → end (Y-1)/Y; end Y → mid Y/(Y+1)
    year = ys or ye
    if slot_name == "mid":
        return _summer_season(year - 1, year, slot="end", game_date=game_date)
    return _summer_season(year, year + 1, slot="mid", game_date=game_date)


def _coerce_number(value: Any) -> int | float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        if isinstance(value, float) and value.is_integer():
            return int(value)
        return value
    text = str(value).strip().replace(",", "")
    if not text or text in { "-", "—", "N/A", "n/a" }:
        return None
    if text.endswith("%"):
        text = text[:-1].strip()
    try:
        if "." in text:
            num = float(text)
            return int(num) if num.is_integer() else num
        return int(text)
    except ValueError:
        return None


def _player_from_moneyball_row(row: dict[str, str]) -> dict[str, Any]:
    unique_id = str(row.get("Unique ID") or "").strip()
    name = str(row.get("Player") or row.get("Name") or "").strip()
    attrs = {}
    for label in _VISIBLE_ATTR_LABELS:
        num = _coerce_number(row.get(label))
        if num is not None:
            attrs[label] = num
    hidden = {}
    for label in _HIDDEN_ATTR_LABELS:
        num = _coerce_number(row.get(label))
        if num is not None:
            hidden[label] = num
    personality_attrs = {}
    for label in _PERSONALITY_ATTR_LABELS:
        num = _coerce_number(row.get(label))
        if num is not None:
            personality_attrs[label] = num
    finance = {}
    for key in _FINANCE_CSV_KEYS:
        raw = row.get(key)
        if raw not in (None, ""):
            finance[key] = str(raw)
    stats = {}
    for key in _STATS_CSV_KEYS:
        num = _coerce_number(row.get(key))
        if num is not None:
            stats[key] = num
        elif row.get(key) not in (None, ""):
            stats[key] = str(row.get(key))
    player: dict[str, Any] = {
        "unique_id": unique_id or None,
        "name": name,
        "age": _coerce_number(row.get("Age")),
        "club": str(row.get("Club") or "").strip() or None,
        "division": str(row.get("Division") or "").strip() or None,
        "nation": str(row.get("Nation") or "").strip() or None,
        "based_in": str(row.get("Based In") or "").strip() or None,
        "second_nation": str(row.get("2nd Nat") or "").strip() or None,
        "best_pos": str(row.get("Best Pos") or "").strip() or None,
        "position": str(row.get("Position") or "").strip() or None,
        "sec_position": str(row.get("Sec. Position") or "").strip() or None,
        "height": str(row.get("Height") or "").strip() or None,
        "left_foot": str(row.get("Left Foot") or "").strip() or None,
        "right_foot": str(row.get("Right Foot") or "").strip() or None,
        "ability": _coerce_number(row.get("Ability")),
        "potential": _coerce_number(row.get("Potential")),
        "world_reputation": _coerce_number(row.get("World Reputation")),
        "personality": str(row.get("Personality") or "").strip() or None,
        "attrs": attrs,
        "hidden_attrs": hidden,
        "personality_attrs": personality_attrs,
        "finance": finance,
        "stats": stats,
    }
    return {k: v for k, v in player.items() if v not in (None, "", {}, [])}


def _player_from_fmsave(
    player: Any,
    season: Any | None,
    *,
    division: str = "",
) -> dict[str, Any]:
    row = fms._player_row(player, season, division=division)  # noqa: SLF001
    compact = _player_from_moneyball_row(row)
    compact["uid"] = getattr(player, "uid", None)
    club_uid = getattr(player, "club_uid", None)
    if club_uid is not None:
        compact["club_uid"] = int(club_uid)
    birth = getattr(player, "birth_date", None)
    if birth is not None:
        compact["birth_date"] = birth.isoformat() if hasattr(birth, "isoformat") else str(birth)

    attrs_obj = getattr(player, "attributes", None)
    hidden: dict[str, Any] = {}
    if attrs_obj is not None:
        for field, label in HIDDEN_ATTR_FIELD_TO_LABEL.items():
            value = getattr(attrs_obj, field, None)
            num = _coerce_number(value)
            if num is not None:
                hidden[label] = num
    if hidden:
        compact["hidden_attrs"] = hidden

    personality_obj = getattr(player, "personality", None)
    personality_attrs: dict[str, Any] = {}
    if personality_obj is not None:
        for field, label in PERSONALITY_ATTR_FIELD_TO_LABEL.items():
            value = getattr(personality_obj, field, None)
            num = _coerce_number(value)
            if num is not None:
                personality_attrs[label] = num
    if personality_attrs:
        compact["personality_attrs"] = personality_attrs
    return compact


def extract_players_from_fm(
    save_path: str | Path,
    *,
    scope: str = "all",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return compact player snapshots + import meta from a .fm save."""
    import fmsave
    from fmsave.models.season_stats import SeasonStatsKind

    import services.compute_progress as compute_progress

    path = Path(save_path).expanduser()
    if not path.is_file():
        raise FileNotFoundError(f"Save file not found: {path}")

    scope_key = fms._normalize_scope(scope)  # noqa: SLF001
    competition_names = fms.competition_name_map() or None
    game_date: date | None = None
    managed_club_uid = None
    managed_club_name = None
    game_label = ""
    game_build = ""

    compute_progress.update(phase="Opening save…", done=0, total=0)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with fmsave.open(path, competition_names=competition_names) as career_save:
            info = career_save.info
            game_date = info.game_date
            game_label = str(getattr(info, "game", "") or "")
            game_build = str(getattr(info, "build", "") or "")

            managed = career_save.managed_clubs()
            if managed:
                managed_club_uid = managed[0].club_uid
                managed_club_name = str(
                    getattr(managed[0], "club_name", None)
                    or getattr(managed[0], "name", None)
                    or ""
                ) or None

            compute_progress.update(phase="Loading players…")
            with fms._track_player_load_progress():  # noqa: SLF001
                if scope_key == "squad":
                    if managed_club_uid is None:
                        raise ValueError(
                            "No managed club in this save (between jobs?). "
                            "Use All players instead."
                        )
                    player_list = list(
                        career_save.players().where(club_uid=managed_club_uid)
                    )
                else:
                    player_list = list(career_save.players())

            uid_set = frozenset(p.uid for p in player_list)
            club_uid_set = {
                int(p.club_uid)
                for p in player_list
                if getattr(p, "club_uid", None) is not None
            }
            compute_progress.update(
                phase="Resolving divisions…",
                done=0,
                total=len(player_list),
            )
            club_divisions = fms._build_club_divisions(  # noqa: SLF001
                career_save,
                club_uid_set if club_uid_set else set(),
            )

            compute_progress.update(
                phase="Loading season stats…",
                done=0,
                total=len(player_list),
            )
            season_by_uid: dict[int, list[Any]] = {}
            try:
                for record in career_save.player_season_stats().where(
                    kind=SeasonStatsKind.OVERALL
                ):
                    if record.player_uid not in uid_set:
                        continue
                    season_by_uid.setdefault(record.player_uid, []).append(record)
            except (fmsave.ReaderCheckError, fmsave.UnsupportedGameError):
                season_by_uid = {}

            history_by_uid: dict[int, list[Any]] = {}
            need_history = {
                p.uid
                for p in player_list
                if not fms._season_has_minutes(  # noqa: SLF001
                    fms._pick_season_row(  # noqa: SLF001
                        season_by_uid.get(p.uid, []),
                        club_uid=p.club_uid,
                    )
                )
            }
            if need_history:
                compute_progress.update(
                    phase="Loading season history…",
                    done=0,
                    total=len(need_history),
                )
                try:
                    for record in career_save.player_season_history():
                        if record.player_uid not in need_history:
                            continue
                        history_by_uid.setdefault(record.player_uid, []).append(record)
                except (fmsave.ReaderCheckError, fmsave.UnsupportedGameError, AttributeError):
                    history_by_uid = {}

    players: list[dict[str, Any]] = []
    total = len(player_list)
    step = fms._progress_step(total)  # noqa: SLF001
    compute_progress.update(phase="Building snapshots…", done=0, total=total)
    for index, player in enumerate(player_list, start=1):
        season_row = fms._pick_season_row(  # noqa: SLF001
            season_by_uid.get(player.uid, []),
            club_uid=player.club_uid,
        )
        if not fms._season_has_minutes(season_row):  # noqa: SLF001
            season_row = fms._pick_history_row(  # noqa: SLF001
                history_by_uid.get(player.uid, []),
                club_uid=player.club_uid,
            )
        club_uid = getattr(player, "club_uid", None)
        division = ""
        if club_uid is not None:
            division = str(club_divisions.get(int(club_uid)) or "")
        players.append(_player_from_fmsave(player, season_row, division=division))
        if total > 0 and (index == 1 or index >= total or index % step == 0):
            compute_progress.tick(index, total, phase="Building snapshots…")

    meta = {
        "source": "fmsave",
        "source_name": path.name,
        "game_date": game_date.isoformat() if game_date else None,
        "game": game_label,
        "build": game_build,
        "managed_club_uid": managed_club_uid,
        "managed_club_name": managed_club_name,
        "player_count": len(players),
        "scope": scope_key,
        "classification": classify_import(game_date, schedule=DEFAULT_SCHEDULE),
    }
    return players, meta


def extract_players_from_csv(
    csv_text: str,
    *,
    source_name: str = "upload.csv",
    game_date: date | None = None,
    schedule: ScheduleKind | str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    import services.compute_progress as compute_progress

    compute_progress.update(phase="Reading CSV…", done=0, total=0)
    text = (csv_text or "").lstrip("\ufeff")
    if not text.strip():
        raise ValueError("CSV is empty")
    sample = text[:4096]
    delimiter = ";" if sample.count(";") >= sample.count(",") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    if not reader.fieldnames:
        raise ValueError("CSV has no header row")
    fieldnames = [str(h or "").strip() for h in reader.fieldnames]
    if "Unique ID" not in fieldnames and "Player" not in fieldnames and "Name" not in fieldnames:
        raise ValueError("CSV must include Unique ID and/or Player/Name columns")

    players: list[dict[str, Any]] = []
    for raw in reader:
        row = {str(k or "").strip(): ("" if v is None else str(v)) for k, v in raw.items()}
        if "Player" not in row and "Name" in row:
            row["Player"] = row.get("Name") or ""
        player = _player_from_moneyball_row(row)
        if not player.get("unique_id") and not player.get("name"):
            continue
        players.append(player)

    compute_progress.update(
        phase="CSV ready",
        done=len(players),
        total=len(players),
    )
    meta = {
        "source": "csv",
        "source_name": source_name,
        "game_date": game_date.isoformat() if game_date else None,
        "managed_club_uid": None,
        "managed_club_name": None,
        "player_count": len(players),
        "classification": classify_import(game_date, schedule=schedule),
    }
    return players, meta


def peek_classification(
    *,
    save_path: str | Path | None = None,
    csv_text: str | None = None,
    source_name: str = "",
    game_date_override: str | None = None,
    schedule: ScheduleKind | str | None = None,
) -> dict[str, Any]:
    """Return season/slot/date classification without extracting players.

    For .fm saves this only opens the save header (``info.game_date``).
    For CSV, classification uses ``game_date_override`` when provided (CSV has
    no save date); otherwise today's date is used.
    """
    kind = normalize_schedule(schedule)
    override = _parse_date(game_date_override)
    if override is not None:
        classification = classify_import(override, schedule=kind)
        source = "fmsave" if save_path else ("csv" if csv_text is not None else "override")
        return {
            "classification": classification,
            "meta": {
                "source": source,
                "source_name": (
                    Path(save_path).name
                    if save_path
                    else (source_name or ("upload.csv" if csv_text is not None else ""))
                ),
                "game_date": override.isoformat(),
            },
        }

    if save_path:
        import fmsave

        path = Path(save_path).expanduser()
        if not path.is_file():
            raise FileNotFoundError(f"Save file not found: {path}")
        competition_names = fms.competition_name_map() or None
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            with fmsave.open(path, competition_names=competition_names) as career_save:
                game_date = career_save.info.game_date
        classification = classify_import(game_date, schedule=kind)
        return {
            "classification": classification,
            "meta": {
                "source": "fmsave",
                "source_name": path.name,
                "game_date": game_date.isoformat() if game_date else None,
            },
        }

    if csv_text is not None:
        if not str(csv_text).strip():
            raise ValueError("CSV is empty")
        classification = classify_import(None, schedule=kind)
        return {
            "classification": classification,
            "meta": {
                "source": "csv",
                "source_name": source_name or "upload.csv",
                "game_date": classification.get("game_date"),
            },
        }

    raise ValueError("Choose a .fm save or drop a Moneyball CSV first.")


def preview_import(
    *,
    save_path: str | Path | None = None,
    csv_text: str | None = None,
    source_name: str = "",
    scope: str = "all",
    game_date_override: str | None = None,
    schedule: ScheduleKind | str | None = None,
) -> dict[str, Any]:
    """Extract players and return classification without writing (Import path)."""
    kind = normalize_schedule(schedule)
    override = _parse_date(game_date_override)
    if save_path:
        players, meta = extract_players_from_fm(save_path, scope=scope)
    elif csv_text is not None:
        players, meta = extract_players_from_csv(
            csv_text,
            source_name=source_name or "upload.csv",
            game_date=override,
            schedule=kind,
        )
    else:
        raise ValueError("Provide a save path or CSV text")

    game_date = override or _parse_date(meta.get("game_date"))
    classification = classify_import(game_date, schedule=kind)
    if override is not None:
        meta["game_date"] = override.isoformat()
    meta["classification"] = classification
    return {
        "players": players,
        "meta": meta,
        "classification": classification,
    }


def commit_import(
    career_id: str,
    *,
    players: list[dict[str, Any]],
    meta: dict[str, Any],
    season_label: str | None = None,
    season_id: str | None = None,
    year_start: int | None = None,
    year_end: int | None = None,
    slot: SlotName = "end",
    replace: bool = False,
    set_active_season: bool = True,
) -> dict[str, Any]:
    """Write snapshot into a career season slot."""
    if slot not in careers.SLOTS:
        raise ValueError(f"Invalid slot: {slot}")
    classification = meta.get("classification") or classify_import(
        _parse_date(meta.get("game_date"))
    )
    sid = season_id or classification.get("id")
    label = (season_label or classification.get("label") or sid or "").strip()
    y_start = int(year_start if year_start is not None else classification.get("year_start") or 0)
    y_end = int(year_end if year_end is not None else classification.get("year_end") or 0)
    if not sid:
        raise ValueError("Season id is required")
    if y_start <= 0 or y_end <= 0:
        raise ValueError("Season year bounds are required")

    occupied = careers.slot_occupied(career_id, sid, slot)
    if occupied and not replace:
        return {
            "ok": False,
            "needs_replace": True,
            "career_id": career_id,
            "season_id": sid,
            "slot": slot,
            "message": f"{slot} slot already has a snapshot for this season",
        }

    import services.compute_progress as compute_progress

    compute_progress.update(phase="Writing snapshot…", done=0, total=len(players))
    careers.upsert_season(
        career_id,
        season_id=sid,
        label=label,
        year_start=y_start,
        year_end=y_end,
    )

    snapshot = {
        "version": 1,
        "game_date": meta.get("game_date"),
        "source": meta.get("source"),
        "source_name": meta.get("source_name"),
        "managed_club_uid": meta.get("managed_club_uid"),
        "managed_club_name": meta.get("managed_club_name"),
        "player_count": len(players),
        "players": players,
    }
    snap_meta = {
        "imported_at": _utcnow(),
        "source": meta.get("source") or "unknown",
        "source_name": meta.get("source_name") or "",
        "game_date": meta.get("game_date"),
        "player_count": len(players),
        "managed_club_uid": meta.get("managed_club_uid"),
        "managed_club_name": meta.get("managed_club_name"),
    }
    written = careers.write_snapshot(
        career_id,
        sid,
        slot,
        snapshot,
        meta=snap_meta,
    )
    compute_progress.update(
        phase="Snapshot saved",
        done=len(players),
        total=len(players),
    )
    if set_active_season:
        careers.set_active(career_id=career_id, season_id=sid)
    return {
        "ok": True,
        "needs_replace": False,
        "career_id": career_id,
        "season_id": sid,
        "season_label": label,
        "slot": slot,
        "replaced": occupied,
        "snapshot_meta": written,
        "player_count": len(players),
    }


def import_save_to_career(
    career_id: str,
    save_path: str | Path,
    *,
    scope: str = "all",
    season_label: str | None = None,
    slot: SlotName | None = None,
    replace: bool = False,
    game_date_override: str | None = None,
    schedule: ScheduleKind | str | None = None,
) -> dict[str, Any]:
    kind = (
        normalize_schedule(schedule)
        if schedule is not None
        else careers.get_season_schedule(career_id)
    )
    preview = preview_import(
        save_path=save_path,
        scope=scope,
        game_date_override=game_date_override,
        schedule=kind,
    )
    classification = preview["classification"]
    return commit_import(
        career_id,
        players=preview["players"],
        meta=preview["meta"],
        season_label=season_label,
        season_id=classification["id"],
        year_start=classification["year_start"],
        year_end=classification["year_end"],
        slot=slot or classification["slot"],
        replace=replace,
    )


def import_csv_to_career(
    career_id: str,
    csv_text: str,
    *,
    source_name: str = "upload.csv",
    season_label: str | None = None,
    slot: SlotName | None = None,
    replace: bool = False,
    game_date: str | None = None,
    schedule: ScheduleKind | str | None = None,
) -> dict[str, Any]:
    kind = (
        normalize_schedule(schedule)
        if schedule is not None
        else careers.get_season_schedule(career_id)
    )
    preview = preview_import(
        csv_text=csv_text,
        source_name=source_name,
        game_date_override=game_date,
        schedule=kind,
    )
    classification = preview["classification"]
    return commit_import(
        career_id,
        players=preview["players"],
        meta=preview["meta"],
        season_label=season_label,
        season_id=classification["id"],
        year_start=classification["year_start"],
        year_end=classification["year_end"],
        slot=slot or classification["slot"],
        replace=replace,
    )


def stage_extracted(
    career_id: str,
    *,
    players: list[dict[str, Any]],
    meta: dict[str, Any],
    classification: dict[str, Any] | None = None,
    suggested_slot: SlotName | None = None,
) -> dict[str, Any]:
    """Store an extracted snapshot in career staging for later drag/assign."""
    classed = classification or meta.get("classification") or classify_import(
        _parse_date(meta.get("game_date"))
    )
    slot = suggested_slot or classed.get("slot") or "end"
    if slot not in careers.SLOTS:
        slot = "end"
    item = careers.add_staging_item(
        career_id,
        players=players,
        meta=meta,
        season_id=classed.get("id"),
        season_label=classed.get("label"),
        year_start=classed.get("year_start"),
        year_end=classed.get("year_end"),
        suggested_slot=slot,
    )
    return {"ok": True, "item": item}


def stage_import(
    career_id: str,
    *,
    save_path: str | Path | None = None,
    csv_text: str | None = None,
    source_name: str = "",
    scope: str = "all",
    game_date_override: str | None = None,
    schedule: ScheduleKind | str | None = None,
) -> dict[str, Any]:
    """Extract players and park them in staging (does not write a season slot)."""
    kind = (
        normalize_schedule(schedule)
        if schedule is not None
        else careers.get_season_schedule(career_id)
    )
    preview = preview_import(
        save_path=save_path,
        csv_text=csv_text,
        source_name=source_name,
        scope=scope,
        game_date_override=game_date_override,
        schedule=kind,
    )
    return stage_extracted(
        career_id,
        players=preview["players"],
        meta=preview["meta"],
        classification=preview["classification"],
    )


def auto_assign_staged(
    career_id: str,
    staging_id: str,
    *,
    replace: bool = False,
    set_active_season: bool = True,
) -> dict[str, Any]:
    """Commit a staged item into its suggested season mid/end slot."""
    item = careers.get_staging_item(career_id, staging_id)
    if item is None:
        raise ValueError(f"Unknown staging item: {staging_id}")
    season_id = str(item.get("season_id") or "").strip()
    slot = str(item.get("suggested_slot") or "end").strip().lower()
    if slot not in careers.SLOTS:
        slot = "end"
    if not season_id:
        raise ValueError(f"Staging item {staging_id} has no suggested season")
    return commit_staging_to_slot(
        career_id,
        staging_id,
        season_id=season_id,
        slot=slot,  # type: ignore[arg-type]
        season_label=item.get("season_label"),
        year_start=item.get("year_start"),
        year_end=item.get("year_end"),
        replace=replace,
        set_active_season=set_active_season,
    )


def _snapshot_sort_key(entry: dict[str, Any]) -> tuple:
    game_date = _parse_date(entry.get("game_date"))
    imported = str(entry.get("imported_at") or "")
    return (game_date or date.min, imported)


def reclassify_career_snapshots(
    career_id: str,
    *,
    schedule: ScheduleKind | str | None = None,
    from_schedule: ScheduleKind | str | None = None,
) -> dict[str, Any]:
    """Remap season mid/end slots when switching Summer↔Winter calendars.

    Moves existing gzip snapshot files and updates season/slot meta only —
    player payloads are never re-serialized. Uses season year bounds + slot
    (not raw game-date windows): e.g. Summer 2025/26 mid → Winter 2025 end,
    Summer 2025/26 end → Winter 2026 mid.

    When two snapshots map to the same season/slot, keep the later game date
    (then later imported_at) and move the other into staging.
    Staging suggestions are updated to match the new calendar.
    """
    kind = (
        normalize_schedule(schedule)
        if schedule is not None
        else careers.get_season_schedule(career_id)
    )
    prev_kind = (
        normalize_schedule(from_schedule)
        if from_schedule is not None
        else kind
    )
    collected: list[dict[str, Any]] = []
    old_seasons = careers.list_seasons(career_id)
    for season in old_seasons:
        for slot in careers.SLOTS:
            meta = (season.get("slots") or {}).get(slot)
            if not meta:
                continue
            src = careers.snapshot_file_path(career_id, season["id"], slot)
            if not src.is_file():
                continue
            game_date = _parse_date(meta.get("game_date"))
            classification = remap_season_slot(
                year_start=season.get("year_start"),
                year_end=season.get("year_end"),
                slot=slot,
                from_schedule=prev_kind,
                to_schedule=kind,
                game_date=game_date,
            )
            collected.append(
                {
                    "path": src,
                    "meta": meta,
                    "game_date": game_date.isoformat() if game_date else None,
                    "imported_at": meta.get("imported_at"),
                    "classification": classification,
                    "old_season_id": season["id"],
                    "old_slot": slot,
                }
            )

    winners: dict[tuple[str, str], dict[str, Any]] = {}
    staged_conflicts: list[dict[str, Any]] = []
    for entry in collected:
        classed = entry["classification"]
        key = (str(classed["id"]), str(classed["slot"]))
        existing = winners.get(key)
        if existing is None:
            winners[key] = entry
            continue
        if _snapshot_sort_key(entry) >= _snapshot_sort_key(existing):
            staged_conflicts.append(existing)
            winners[key] = entry
        else:
            staged_conflicts.append(entry)

    active = careers.get_active()
    prefer_active = (
        active.get("season_id") if active.get("career_id") == career_id else None
    )

    # Park every snapshot under a temp dir so season/slot renames cannot clash.
    temp_root = careers.career_root(career_id) / "_remap_tmp" / uuid.uuid4().hex
    temp_root.mkdir(parents=True, exist_ok=True)
    moved = 0
    conflict_staged = 0
    staging_updated = 0
    try:
        for index, entry in enumerate(collected):
            parked = temp_root / f"{index}.json.gz"
            careers.move_file(entry["path"], parked)
            entry["temp_path"] = parked

        careers.reset_season_slots(career_id)

        for entry in winners.values():
            classed = entry["classification"]
            if not season_matches_schedule(
                classed.get("year_start"), classed.get("year_end"), kind
            ):
                # Force target year type if remap somehow kept the opposite shape.
                classed = classify_import(
                    _parse_date(entry.get("game_date")), schedule=kind
                )
                entry["classification"] = classed
            meta = dict(entry["meta"] or {})
            game_date = classed.get("game_date") or entry.get("game_date")
            if game_date:
                meta["game_date"] = game_date
            careers.upsert_season(
                career_id,
                season_id=classed["id"],
                label=classed["label"],
                year_start=int(classed["year_start"]),
                year_end=int(classed["year_end"]),
            )
            careers.place_snapshot_file(
                career_id,
                classed["id"],
                classed["slot"],
                entry["temp_path"],
                meta=meta,
            )
            moved += 1

        # Drop any leftover seasons whose year type does not match the new schedule.
        for season in list(careers.list_seasons(career_id)):
            if not season_matches_schedule(
                season.get("year_start"), season.get("year_end"), kind
            ):
                careers.delete_season(career_id, season["id"])

        preexisting_staging_ids = {
            item["id"] for item in careers.list_staging(career_id)
        }

        for entry in staged_conflicts:
            classed = entry["classification"]
            meta = dict(entry["meta"] or {})
            game_date = classed.get("game_date") or entry.get("game_date")
            if game_date:
                meta["game_date"] = game_date
            careers.add_staging_from_file(
                career_id,
                entry["temp_path"],
                source=meta.get("source"),
                source_name=meta.get("source_name"),
                game_date=game_date,
                season_id=classed.get("id"),
                season_label=classed.get("label"),
                year_start=classed.get("year_start"),
                year_end=classed.get("year_end"),
                suggested_slot=classed.get("slot") or "end",
                player_count=int(meta.get("player_count") or 0),
                managed_club_uid=meta.get("managed_club_uid"),
                managed_club_name=meta.get("managed_club_name"),
            )
            conflict_staged += 1

        for item in careers.list_staging(career_id):
            # Conflict items already carry the new schedule — only remap prior staging.
            if item["id"] not in preexisting_staging_ids:
                continue
            game_date = _parse_date(item.get("game_date"))
            classed = remap_season_slot(
                year_start=item.get("year_start"),
                year_end=item.get("year_end"),
                slot=item.get("suggested_slot"),
                from_schedule=prev_kind,
                to_schedule=kind,
                game_date=game_date,
            )
            if not season_matches_schedule(
                classed.get("year_start"), classed.get("year_end"), kind
            ):
                classed = classify_import(game_date, schedule=kind)
            updated = careers.update_staging_classification(
                career_id,
                item["id"],
                season_id=classed.get("id"),
                season_label=classed.get("label"),
                year_start=classed.get("year_start"),
                year_end=classed.get("year_end"),
                suggested_slot=classed.get("slot") or "end",
            )
            if updated:
                staging_updated += 1
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)

    seasons = careers.list_seasons(career_id)
    next_season = None
    if prefer_active and any(s["id"] == prefer_active for s in seasons):
        next_season = prefer_active
    elif prefer_active:
        for entry in winners.values():
            if entry.get("old_season_id") == prefer_active:
                next_season = str(entry["classification"]["id"])
                break
    if next_season is None and seasons:
        next_season = seasons[-1]["id"]
    careers.set_active(career_id=career_id, season_id=next_season)

    return {
        "schedule": kind,
        "moved": moved,
        "conflict_staged": conflict_staged,
        "staging_updated": staging_updated,
        "season_count": len(seasons),
        "season_ids": [s["id"] for s in seasons],
    }


def apply_season_schedule(
    career_id: str,
    schedule: ScheduleKind | str | None,
) -> dict[str, Any]:
    """Persist schedule and remapping existing snapshots/staging when it changes."""
    kind = normalize_schedule(schedule)
    previous = careers.get_season_schedule(career_id)
    meta = careers.set_season_schedule(career_id, kind)
    if previous == kind:
        return {
            "changed": False,
            "meta": meta,
            "schedule": kind,
            "moved": 0,
            "conflict_staged": 0,
            "staging_updated": 0,
            "season_count": len(careers.list_seasons(career_id)),
            "season_ids": [s["id"] for s in careers.list_seasons(career_id)],
        }
    stats = reclassify_career_snapshots(
        career_id, schedule=kind, from_schedule=previous
    )
    return {"changed": True, "meta": meta, **stats}


def commit_staging_to_slot(
    career_id: str,
    staging_id: str,
    *,
    season_id: str,
    slot: SlotName,
    season_label: str | None = None,
    year_start: int | None = None,
    year_end: int | None = None,
    replace: bool = False,
    set_active_season: bool = True,
) -> dict[str, Any]:
    """Move a staged snapshot file into a season mid/end slot (no re-serialize)."""
    if slot not in careers.SLOTS:
        raise ValueError(f"Invalid slot: {slot}")
    item = careers.get_staging_item(career_id, staging_id)
    if item is None:
        raise ValueError(f"Unknown staging item: {staging_id}")
    src = careers.staging_snapshot_path(career_id, staging_id)
    if not src.is_file():
        raise ValueError(f"Staging snapshot missing: {staging_id}")

    sid = str(season_id or item.get("season_id") or "").strip()
    label = (
        season_label
        or item.get("season_label")
        or sid
        or ""
    ).strip()
    y_start = int(
        year_start if year_start is not None else item.get("year_start") or 0
    )
    y_end = int(year_end if year_end is not None else item.get("year_end") or 0)
    if not sid:
        raise ValueError("Season id is required")
    if y_start <= 0 or y_end <= 0:
        raise ValueError("Season year bounds are required")

    occupied = careers.slot_occupied(career_id, sid, slot)
    if occupied and not replace:
        return {
            "ok": False,
            "needs_replace": True,
            "career_id": career_id,
            "season_id": sid,
            "slot": slot,
            "message": f"{slot} slot already has a snapshot for this season",
        }

    careers.upsert_season(
        career_id,
        season_id=sid,
        label=label,
        year_start=y_start,
        year_end=y_end,
    )
    snap_meta = {
        "imported_at": item.get("staged_at") or _utcnow(),
        "source": item.get("source") or "unknown",
        "source_name": item.get("source_name") or "",
        "game_date": item.get("game_date"),
        "player_count": int(item.get("player_count") or 0),
        "managed_club_uid": item.get("managed_club_uid"),
        "managed_club_name": item.get("managed_club_name"),
    }
    written = careers.place_staging_into_slot(
        career_id,
        staging_id,
        season_id=sid,
        slot=slot,
        meta=snap_meta,
    )
    if set_active_season:
        careers.set_active(career_id=career_id, season_id=sid)
    return {
        "ok": True,
        "needs_replace": False,
        "career_id": career_id,
        "season_id": sid,
        "season_label": label,
        "slot": slot,
        "replaced": occupied,
        "snapshot_meta": written,
        "player_count": int(item.get("player_count") or 0),
        "staging_id": staging_id,
    }
