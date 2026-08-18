"""IP / OOP / GK phase helpers.

Keeper roles can be tagged IP_GK or OOP_GK. Those still count as GK for
filters and attribute sheets, but take IP (green) or OOP (red) colors.
"""
from __future__ import annotations

PHASE_SUFFIXES = ("_IP_GK", "_OOP_GK", "_IP", "_OOP", "_GK")


def phase_tone(phase: str | None) -> str:
    """CSS token: ip (green), oop (red), or gk (gold)."""
    text = (phase or "").strip().upper()
    if text.startswith("OOP"):
        return "oop"
    if text.startswith("IP"):
        return "ip"
    if "GK" in text:
        return "gk"
    return ""


def phase_is_gk(phase: str | None = "", role_id: str = "", group: str = "") -> bool:
    if (group or "").lower() == "gk":
        return True
    text = (phase or "").upper()
    if "GK" in text:
        return True
    rid = role_id or ""
    return rid.endswith("_GK") or rid.endswith("_IP_GK") or rid.endswith("_OOP_GK")


def phase_matches(
    phase: str | None,
    wanted: str | None,
    role_id: str = "",
    group: str = "",
) -> bool:
    wanted = (wanted or "all").upper()
    if wanted in ("", "ALL"):
        return True
    text = (phase or "").upper()
    if wanted == "GK":
        return phase_is_gk(phase, role_id, group)
    if wanted == "IP":
        return text.startswith("IP")
    if wanted == "OOP":
        return text.startswith("OOP")
    return text == wanted


def pretty_role_name(role_id: str) -> str:
    name = role_id
    for suffix in PHASE_SUFFIXES:
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    return name.replace("_", " ")
