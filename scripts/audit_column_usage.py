#!/usr/bin/env python3
"""Build column / metric usage reference from parsers and config.

Writes:
  - docs/column-usage.md   (human reference)
  - docs/column-usage.json (machine-readable; diff-friendly)

Run after changing parsers, stats benchmarks, or export format snapshots::

    python scripts/audit_column_usage.py

Unknown columns in ``config/export_formats/fm26_moneyball_combined_columns.json``
that are not mapped below are listed under *Undocumented columns* — resolve those
with the product owner and add mappings in this script.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PAGES = (
    "Uploads",
    "Role scores",
    "Player stats",
    "Profiles",
    "Squad finance",
)

# Internal keys hidden from player modal (still parsed).
STAR_HIDDEN = frozenset(
    {
        "ability",
        "ability_gold",
        "ability_silver",
        "potential",
        "potential_gold",
        "potential_silver",
        "world_reputation",
        "world_reputation_gold",
        "world_reputation_silver",
    }
)

# Finance keys used in squad wage / match-fee math (not just display).
FINANCE_CALC_KEYS = frozenset(
    {
        "salary",
        "appearance_fee",
        "unused_sub_fee",
        "yearly_salary_raise",
        "promotion_salary_raise",
        "top_division_promotion_salary_raise",
        "relegation_salary_drop",
        "top_division_relegation_salary_drop",
    }
)

# Columns present in the combined export snapshot but intentionally not parsed.
# Add new unknown columns here as ``unused`` once reviewed, or map them in parsers.
INTENTIONALLY_UNUSED: dict[str, str] = {
    "All/90": "Season overview aggregate",
    "Blk": "Block total; Blk/90 is the scored metric",
    "Chances Created per 90": "Not in stats benchmarks",
    "Clear Cut Chances Created": "Not in stats benchmarks",
    "Cln/90": "Clean sheets per 90 (GK); not scored",
    "Crosses Attempted": "Cross totals; only OP crosses completed /90 scored",
    "Crosses Attempted per 90": "Not in stats benchmarks",
    "Crosses Completed": "Cross totals; only OP crosses completed /90 scored",
    "Crosses Completed Ratio": "Not in stats benchmarks",
    "Dist/90": "Physical distance; not scored",
    "Distance": "Physical distance total; not scored",
    "Expected Save Percentage": "GK detail; xGP/90 used instead",
    "Form": "Generic form string; not parsed",
    "Free Kick Shots": "Shooting detail; not scored",
    "Game Win Ratio": "Results aggregate; not parsed",
    "Games Drawn": "Results aggregate; not parsed",
    "Games Lost": "Results aggregate; not parsed",
    "Games Missed In A Row": "Availability streak; not parsed",
    "Games Won": "Results aggregate; not parsed",
    "Goals From Outside The Box": "Shooting detail; not scored",
    "Headers Attempted": "Header total; per-90 / % variants scored",
    "Headers Lost per 90": "Not in stats benchmarks",
    "Key Headers per 90": "Not in stats benchmarks",
    "Key Tackles": "Tackle detail; not scored",
    "Key Tackles per 90": "Not in stats benchmarks",
    "Last Match Rating": "Single-match rating; not parsed",
    "Mins/Gl": "Minutes per goal; not parsed",
    "Mins/Gm": "Minutes per game; not parsed",
    "Minutes Since Last Conceded": "GK streak; not parsed",
    "Minutes Since Last Goal": "Scoring streak; not parsed",
    "Mistakes Leading to Goals": "GK error count; not scored",
    "NP-xG": "Non-penalty xG total; xG/90 scored",
    "NP-xG/90": "Not in stats benchmarks (xG/90 used)",
    "Off": "Unclear FM column; not parsed",
    "Open Play Cross Completion Percentage": "Cross %; not scored",
    "Open Play Crosses Attempted": "Cross totals; OP crosses completed /90 scored",
    "Open Play Crosses Attempted per 90": "Not in stats benchmarks",
    "Open Play Crosses Completed": "Cross total; per-90 variant scored",
    "Open Play Key Passes per 90": "Not in stats benchmarks",
    "Passes Completed": "Pass total; passes attempted /90 scored",
    "Passes Completed per 90": "Not in stats benchmarks",
    "Penalties Faced": "Penalty detail; not parsed",
    "Penalties Saved": "Penalty detail; not parsed",
    "Penalties Saved Ratio": "Penalty detail; not parsed",
    "Penalties Scored": "Penalty detail; not parsed",
    "Penalties Scored Ratio": "Penalty detail; not parsed",
    "Penalties Taken": "Penalty detail; not parsed",
    "Player of the Match": "Awards; not parsed",
    "Pres A": "Pressures attempted total; Pres C/90 scored",
    "Pres A/90": "Not in stats benchmarks",
    "Pres C": "Pressures completed total; Pres C/90 scored",
    "PsP": "Progressive passes total; per-90 variant scored",
    "Pts/Gm": "League points per game; not parsed",
    "Rating": "Average rating alias; parsed via Average Rating Club when present",
    "Save Percentage": "GK save %; not scored",
    "Saves Held": "GK save type; not parsed",
    "Saves Parried": "GK save type; not parsed",
    "Saves Tipped": "GK save type; not parsed",
    "Saves per 90": "GK saves rate; not in benchmarks",
    "Shots From Outside The Box Per 90 minutes": "Shooting detail; not scored",
    "Shots on Target Percentage": "SOT %; SOT per-90 scored",
    "Shts Blckd": "Block total; Blk/90 scored",
    "Shutouts": "GK shutouts; not scored",
    "Starts": "Lineup count; not parsed",
    "Tackled Completed": "Tackle total (FM typo); per-90 from attempts scored",
    "Tackles Completed per 90": "Not in stats benchmarks",
    "Tall": "Unknown FM flag; not parsed",
    "Tcon/90": "Team conceded per 90; not parsed",
    "Team Goals": "Team context; not parsed",
    "Tgls/90": "Team goals per 90; not parsed",
    "xG-OP": "Open-play xG delta; not scored",
    "xG/shot": "Shot quality average; not scored",
}

# Finance keys shown in player modal (components/player_modal.py).
FINANCE_MODAL_KEYS = frozenset(
    {
        "transfer_value",
        "transfer_status",
        "loan_status",
        "salary",
        "contract_expires",
        "ffp_contribution",
        "min_release_clause",
        "work_permit_required",
        "wp_needed",
        "appearance_fee",
        "unused_sub_fee",
        "goal_bonus",
        "assist_bonus",
        "shutout_bonus",
        "int_cap_bonus",
        "yearly_salary_raise",
        "promotion_salary_raise",
        "top_division_promotion_salary_raise",
        "relegation_salary_drop",
        "top_division_relegation_salary_drop",
    }
)


@dataclass
class ColumnEntry:
    csv_names: list[str]
    category: str
    internal_key: str = ""
    pages: set[str] = field(default_factory=set)
    usage: str = ""
    notes: str = ""

    def primary_name(self) -> str:
        return self.csv_names[0] if self.csv_names else self.internal_key


def _load_combined_columns() -> dict[str, str]:
    """Return {column_name: group_id} from the combined export snapshot."""
    path = ROOT / "config/export_formats/fm26_moneyball_combined_columns.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    for group, items in (data.get("groups") or {}).items():
        for item in items:
            name = str(item.get("name") or "").strip()
            if name:
                out[name] = group
    return out


def _build_entries() -> dict[str, ColumnEntry]:
    from scoring.role_scorer import (
        ATTR_MAP,
        CAREER_CSV,
        DISCIPLINE_CSV,
        FINANCE_CSV,
        IDENTITY,
        SET_PIECE_PROFILES,
    )
    from scoring.stats_scorer import metric_defs

    entries: dict[str, ColumnEntry] = {}

    def add(
        key: str,
        *,
        csv_names: list[str],
        category: str,
        internal_key: str = "",
        pages: set[str] | None = None,
        usage: str = "",
        notes: str = "",
    ) -> None:
        entries[key] = ColumnEntry(
            csv_names=csv_names,
            category=category,
            internal_key=internal_key or key,
            pages=pages or set(),
            usage=usage,
            notes=notes,
        )

    parse_pages = {"Uploads", "Role scores", "Player stats", "Profiles"}

    # --- Identity ---
    for ident_key, aliases in IDENTITY.items():
        ik = ident_key[0].lower() + "".join(
            c if c.islower() else f"_{c.lower()}" if i else c.lower()
            for i, c in enumerate(ident_key[1:])
        )
        # camelCase to snake_case for standard IDENTITY keys
        import re

        ik = re.sub(r"(?<!^)(?=[A-Z])", "_", ident_key).lower()
        pages = set(parse_pages)
        usage = "Parsed into player dict; shortlist / modal when configured"
        notes = ""
        if ik in STAR_HIDDEN:
            usage = "Parsed but hidden in UI (unreliable FM26 star ratings)"
            pages = set(parse_pages)
        elif ik in {
            "position",
            "sec_position",
            "best_pos",
            "best_role",
        }:
            usage = "Role eligibility, position groups, shortlist / modal"
        elif ik == "division":
            usage = "Division tier + limited-tracking stripe (Player stats / Profiles)"
        elif ik == "personality":
            usage = "Personality tier classification + modal"
        elif ik == "name":
            usage = "Player identity key across all pages"
        elif ik in {"club", "age"}:
            usage = "Page eligibility gate + identity"
        elif ik in {"injured_on", "time_missed"}:
            usage = "Injury tooltip (shortlist / depth chart)"
        elif ik == "recurring_injury":
            usage = "Player modal after Injury"
        add(
            f"identity:{ik}",
            csv_names=list(aliases),
            category="identity",
            internal_key=ik,
            pages=pages,
            usage=usage,
            notes=notes,
        )

    # --- Attributes (group all CSV aliases per abbreviation) ---
    attr_pages = {"Uploads", "Role scores", "Profiles", "Formulas"}
    set_piece_raw = {p.get("raw") for p in SET_PIECE_PROFILES}
    by_abbr: dict[str, list[str]] = defaultdict(list)
    for full_name, abbr in ATTR_MAP.items():
        if full_name == abbr:
            continue
        if full_name not in by_abbr[abbr]:
            by_abbr[abbr].append(full_name)
    for abbr, names in sorted(by_abbr.items()):
        pages = set(attr_pages)
        usage = "Role score weights (Role scores / Formulas); attribute grid in modals"
        if abbr in set_piece_raw:
            usage += "; set-piece raw column when checked on Role scores"
        if abbr in ("Det", "Ldr"):
            usage = "Personality hidden-range estimation (Player stats parser)"
            pages = {"Uploads", "Role scores", "Player stats", "Profiles"}
        add(
            f"attr:{abbr}",
            csv_names=names,
            category="attribute",
            internal_key=abbr,
            pages=pages,
            usage=usage,
        )

    # --- Career ---
    for key, aliases in CAREER_CSV.items():
        add(
            f"career:{key}",
            csv_names=list(aliases),
            category="career",
            internal_key=key,
            pages=set(parse_pages),
            usage="Player modal → Career totals",
        )

    # --- Discipline ---
    for key, aliases in DISCIPLINE_CSV.items():
        add(
            f"discipline:{key}",
            csv_names=list(aliases),
            category="discipline",
            internal_key=key,
            pages=set(parse_pages),
            usage="Player modal → Discipline",
        )

    # --- Finance ---
    for key, aliases in FINANCE_CSV.items():
        pages = set(parse_pages)
        usage = "Parsed into player dict"
        notes = ""
        if key in FINANCE_CALC_KEYS:
            pages.add("Squad finance")
            usage = "Squad finance wage / match-fee calculations"
        elif key == "ffp_contribution":
            pages.add("Squad finance")
            usage = "Displayed on Squad finance; excluded from totals"
        elif key in FINANCE_MODAL_KEYS:
            usage = "Player modal → Contract & finance"
        else:
            usage = "Parsed + stored; not shown in UI (granular release clause)"
            notes = "Consider surfacing or dropping if unused long-term"
        add(
            f"finance:{key}",
            csv_names=list(aliases),
            category="finance",
            internal_key=key,
            pages=pages,
            usage=usage,
            notes=notes,
        )

    # --- Stats benchmarks ---
    avail = json.loads(
        (ROOT / "config/stats_availability.json").read_text(encoding="utf-8")
    )
    probe_cols = set(avail.get("detection", {}).get("probe_csv_columns") or [])
    basic_cols = set(avail.get("detection", {}).get("basic_csv_columns") or [])

    stats_pages = {"Uploads", "Player stats", "Profiles"}
    seen_csv: set[str] = set()
    for metric_id, meta in metric_defs().items():
        label = str(meta.get("label") or metric_id)
        csv_cols = list(meta.get("csv") or [])
        for col in csv_cols:
            seen_csv.add(col)
            pages = set(stats_pages)
            usage = f"Stats percentile metric «{label}» ({metric_id})"
            notes = ""
            if col in probe_cols:
                pages.add("Uploads")
                usage += "; limited-tracking probe"
            if col in basic_cols:
                usage += "; basic availability probe"
            add(
                f"stats:{metric_id}:{col}",
                csv_names=[col],
                category="stats_metric",
                internal_key=metric_id,
                pages=pages,
                usage=usage,
                notes=notes,
            )

    # Minutes (not always listed as a benchmark metric alias)
    add(
        "stats:minutes",
        csv_names=["Minutes"],
        category="stats_metric",
        internal_key="minutes",
        pages={"Uploads", "Player stats", "Profiles"},
        usage="Minutes gate, per-90 derivation, limited-tracking aggregates",
    )
    seen_csv.add("Minutes")

    # Probes / basics not already covered by metric csv lists
    for col in sorted(probe_cols | basic_cols):
        if col in seen_csv:
            continue
        add(
            f"availability:{col}",
            csv_names=[col],
            category="stats_availability",
            internal_key=col,
            pages={"Uploads", "Player stats", "Profiles"},
            usage="Limited-tracking league detection (not a scored percentile)",
        )

    for col, reason in sorted(INTENTIONALLY_UNUSED.items()):
        add(
            f"unused:{col}",
            csv_names=[col],
            category="unused",
            internal_key=col,
            pages=set(),
            usage="Not parsed by any page",
            notes=reason,
        )

    return entries


def _norm_col(name: str) -> str:
    return " ".join(str(name or "").lower().split())


def _index_by_csv(entries: dict[str, ColumnEntry]) -> tuple[dict[str, ColumnEntry], dict[str, ColumnEntry]]:
    exact: dict[str, ColumnEntry] = {}
    by_norm: dict[str, ColumnEntry] = {}
    for entry in entries.values():
        for name in entry.csv_names:
            exact[name] = entry
            by_norm[_norm_col(name)] = entry
    return exact, by_norm


def _snapshot_coverage(
    combined: dict[str, str],
    by_csv: dict[str, ColumnEntry],
    by_norm: dict[str, ColumnEntry],
) -> tuple[set[str], list[str]]:
    covered: set[str] = set()
    for col in combined:
        if col in by_csv or _norm_col(col) in by_norm:
            covered.add(col)
    undocumented = sorted(set(combined) - covered)
    return covered, undocumented


def _serialize(entries: dict[str, ColumnEntry], combined: dict[str, str]) -> dict:
    by_csv, by_norm = _index_by_csv(entries)
    covered, undocumented = _snapshot_coverage(combined, by_csv, by_norm)
    extra_aliases = sorted(set(by_csv) - set(combined))

    rows = []
    for entry in sorted(entries.values(), key=lambda e: (e.category, e.primary_name())):
        rows.append(
            {
                "primary_csv": entry.primary_name(),
                "csv_aliases": entry.csv_names,
                "category": entry.category,
                "internal_key": entry.internal_key,
                "pages": sorted(entry.pages),
                "usage": entry.usage,
                "notes": entry.notes,
            }
        )

    return {
        "generated_by": "scripts/audit_column_usage.py",
        "source_snapshot": "config/export_formats/fm26_moneyball_combined_columns.json",
        "column_count_snapshot": len(combined),
        "mapped_entry_count": len(entries),
        "snapshot_columns_covered": len(covered),
        "undocumented_in_snapshot": undocumented,
        "aliases_not_in_snapshot": extra_aliases,
        "page_eligibility": {
            "role_scores": "Name + ≥1 attribute + Club/Age/Position",
            "player_stats": "Name + stats markers + Club/Age/Position",
            "squad_finance": "Name + Salary + Appearance Fee + Unused Sub Fee + Club/Age/Position",
            "profiles": "Requires stats-eligible saved file for save / replace",
        },
        "entries": rows,
    }


def _markdown(data: dict) -> str:
    lines = [
        "# Column & metric usage reference",
        "",
        "Living reference for which FM export columns FMScouter reads and where they appear.",
        "Regenerate after parser or stats config changes:",
        "",
        "```bash",
        "python scripts/audit_column_usage.py",
        "```",
        "",
        "**Source of truth:** parsers in `scoring/role_scorer.py`, `scoring/stats_scorer.py`,",
        "`scoring/squad_finance.py`, plus `config/stats_benchmarks.json` and",
        "`config/stats_availability.json`.",
        "",
        "Snapshot column list: `config/export_formats/fm26_moneyball_combined_columns.json`",
        f"({data['column_count_snapshot']} columns). Custom upload views may add headers not",
        "listed here — unknown columns are ignored until mapped in `scripts/audit_column_usage.py`.",
        "",
        "## Page eligibility (saved uploads)",
        "",
        "| Page | Gate |",
        "|------|------|",
        f"| Role scores | {data['page_eligibility']['role_scores']} |",
        f"| Player stats | {data['page_eligibility']['player_stats']} |",
        f"| Squad finance | {data['page_eligibility']['squad_finance']} |",
        f"| Profiles | {data['page_eligibility']['profiles']} |",
        "",
        "Uploads classifies files and precomputes role scores + stats percentiles.",
        "",
        "## Categories",
        "",
        "| Category | Role |",
        "|----------|------|",
        "| `identity` | Player info, positions, personality, international fields |",
        "| `attribute` | FM attributes → role scores, set pieces, attribute modals |",
        "| `stats_metric` | Moneyball stats → percentiles / charts |",
        "| `stats_availability` | Limited-tracking detection only |",
        "| `career` | Career totals in player modal |",
        "| `discipline` | Cards / fouls / appearances in player modal |",
        "| `finance` | Contract, wages, fees, clauses |",
        "| `unused` | In export snapshot but intentionally not parsed |",
        "",
    ]

    if data["undocumented_in_snapshot"]:
        lines.extend(
            [
                "## Needs product decision",
                "",
                "These columns appear in the combined export snapshot but are **not mapped**",
                "in code or the `INTENTIONALLY_UNUSED` list. Ask the product owner, then either",
                "wire them in a parser or add them to `INTENTIONALLY_UNUSED` in",
                "`scripts/audit_column_usage.py`.",
                "",
            ]
        )
        for col in data["undocumented_in_snapshot"]:
            lines.append(f"- `{col}`")
        lines.append("")

    by_category: dict[str, list[dict]] = defaultdict(list)
    for row in data["entries"]:
        by_category[row["category"]].append(row)

    category_titles = {
        "identity": "Identity & player info",
        "attribute": "Attributes",
        "stats_metric": "Stats metrics (percentiles)",
        "stats_availability": "Stats availability probes",
        "career": "Career totals",
        "discipline": "Discipline",
        "finance": "Contract & finance",
        "unused": "Not parsed (intentional)",
    }

    for cat in (
        "identity",
        "attribute",
        "stats_metric",
        "stats_availability",
        "career",
        "discipline",
        "finance",
        "unused",
    ):
        rows = by_category.get(cat)
        if not rows:
            continue
        lines.append(f"## {category_titles.get(cat, cat)}")
        lines.append("")
        lines.append("| CSV column(s) | Internal key | Pages | Usage |")
        lines.append("|---------------|--------------|-------|-------|")
        for row in rows:
            cols = ", ".join(f"`{c}`" for c in row["csv_aliases"][:3])
            if len(row["csv_aliases"]) > 3:
                cols += ", …"
            pages = ", ".join(row["pages"]) or "—"
            usage = row["usage"].replace("|", "\\|")
            if row["notes"]:
                note_esc = row["notes"].replace("|", "\\|")
                usage += f" — {note_esc}"
            lines.append(
                f"| {cols} | `{row['internal_key']}` | {pages} | {usage} |"
            )
        lines.append("")

    if data["aliases_not_in_snapshot"]:
        lines.extend(
            [
                "## Aliases in code but not in combined snapshot",
                "",
                "Extra CSV header aliases the parsers accept (older exports / custom views):",
                "",
            ]
        )
        for col in data["aliases_not_in_snapshot"][:40]:
            lines.append(f"- `{col}`")
        if len(data["aliases_not_in_snapshot"]) > 40:
            lines.append(f"- … and {len(data['aliases_not_in_snapshot']) - 40} more")
        lines.append("")

    lines.extend(
        [
            "## Maintenance",
            "",
            "1. Run `python scripts/audit_column_usage.py` after changing parsers or stats config.",
            "2. Review **Needs product decision** for new snapshot columns.",
            "3. For columns that should stay ignored, add them to `INTENTIONALLY_UNUSED` in",
            "   `scripts/audit_column_usage.py`. For columns to support, wire the parser first.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    combined = _load_combined_columns()
    entries = _build_entries()
    data = _serialize(entries, combined)

    docs = ROOT / "docs"
    docs.mkdir(exist_ok=True)
    (docs / "column-usage.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (docs / "column-usage.md").write_text(_markdown(data), encoding="utf-8")

    print(f"Wrote docs/column-usage.md ({len(data['entries'])} mapped entries)")
    print(f"Snapshot columns: {data['column_count_snapshot']} covered: {data['snapshot_columns_covered']}")
    print(f"Needs product decision: {len(data['undocumented_in_snapshot'])}")
    if data["undocumented_in_snapshot"]:
        print("  →", ", ".join(data["undocumented_in_snapshot"][:8]), "…")


if __name__ == "__main__":
    main()
