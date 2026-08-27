# AGENTS.md — FMScouter (FM24)

Guidance for AI agents working in this repo. Prefer this over rediscovering conventions from chat history. Keep changes scoped; match existing patterns.

Also see: `.cursor/rules/theme-styling.mdc` (always-on dark-first CSS).

---

## App map

Dash + dash-mantine-components scouting app for Football Manager exports.

| Area | Location |
|------|----------|
| Entry | `app.py` |
| Pages | `pages/` — role scores, player stats, profiles, formations, uploads, settings, squad finance, role config, formulas |
| Shared UI | `components/` — tables, filters, modals, scouting shell, profile save |
| Scoring | `scoring/` — role scorer, stats scorer, availability, personality, division tiers |
| Services | `services/` — upload cache, formations, profile libraries, export library, UI settings |
| Config | `config/` — role weights, formations, stats thresholds, availability, paths |
| Styles | `assets/styles.css` — theme tokens (`--app-bg`, `--app-card`, `--app-text`, …) |
| Profile data | `data/profiles/packs/<id>/` (`meta.json`, `index.json`, `slot_depth.json`) + `data/profiles/active.json` |

Prefer editing existing shared components over duplicating page-local table/modal logic.

---

## Working style

- **New feature area → treat as fresh context.** Do not assume prior chat covered unrelated pages.
- **Front-load decisions** in the first implementation pass (storage shape, UX toggles, acceptance checks). Avoid build-then-reverse.
- **Batch UI polish** into one pass after behavior works (widths, centering, labels, dark+light). Do not drip layout nits across many turns unless blocked.
- **Do not scan the whole repo** for “anything that could be a setting.” Propose settings only when values already differ across pages or the user asked.
- Prefer small, targeted reads/greps over loading entire large page files when fixing a narrow bug.
- Paste / cite the failing Dash callback id and error text; avoid dumping whole terminal logs unless asked.

---

## Theme & UI

- Dark mode is primary; light must stay readable. Use CSS variables from `assets/styles.css`.
- New surfaces (modals, panels, forms, tooltips): style **both** themes in the same change.
- Match existing table/header/filter patterns on role scores / stats / profiles before inventing new chrome.
- Role phase colors: IP green, OOP red, hybrid purple. Keep status colors distinguishable in both themes.
- Metric labels: full = `{metric} per 90`; abbreviated = `{abbr}/90`.

---

## Dash callbacks

- Never add a duplicate `Output` without `allow_duplicate=True` and a clear `prevent_initial_call` strategy.
- Avoid store ↔ control dependency cycles (`A.data` → `B.value` → `A.data`).
- Row marking / select-all / clear-marked must update checkbox UI **without** rebuilding the whole shortlist table when possible.
- After callback-touching UI work, sanity-check for: `Output … already in use`, `Dependency Cycle Found`, `Maximum update depth exceeded`, nonexistent component ids.
- Busy overlays: only animate the section that actually changes (e.g. First/Second XI toggle → depth chart only, not squad depth).

---

## Scoring & limited tracking

Source of truth: `config/stats_availability.json` + `scoring/stats_availability.py`.

- Some leagues export advanced stats as `0` instead of blank; do not treat those zeros as real rates for percentiles.
- **Probe metrics** (used to detect limited tracking): interceptions, key passes, progressive passes, clearances (and their `/90` columns).
- **Not probes** (universal when present): includes **xA** and **possession won** — they appear even in limited leagues.
- **League limited** when: minutes-weighted averages of probe `/90` rates (players with minutes only) have **max ≤ 0.25**, and division has **≥ 300 total minutes**. Sparse leftovers (transfers / continental) must **not** veto. Zero-minute rows do not affect aggregates.
- **Player limited**: ≥90 minutes + basics present + all probes zero → show “Not tracked”; exclude unavailable metrics from percentile averages.
- Limited divisions get striped Division pills via upload-cache `limited_tracking_divisions`.
- Bump formula/cache version when availability or scoring semantics change so recomputes pick up the rule.
- Goalkeeping percentile caps (e.g. xG prevented): use max(settings ceiling, observed data max) where that pattern already exists — do not invent a third scheme.

Acceptance examples (do not regress without an explicit rule change):

- Stripe: Ligat Ha'Al, UAE, CFL1, CSL (typical limited probes).
- Do not stripe: Liga I, Eredivisie when probes are real.
- Eredivisie player with continental/transfer noise elsewhere should not force their domestic league limited if league aggregates are healthy.

---

## Profiles & formations

- Multiple **profile libraries** under `data/profiles/packs/<id>/`. Active id in `data/profiles/active.json`.
- Creating a library requires **name + formation_id**.
- Role-scores save flow: user chooses target library (`components/profile_save.py`).
- Library dropdown labels: profile **display name** + formation **display name** from formation packs — **not** the slug id (e.g. `5-1-4-0 Dracula`, not `5-1-4-0-dracula`).
- Depth chart: First XI = depth rank #1 per slot; Second XI = #2. Formation slots drive squad depth; remember last formation per library meta.
- Same player in multiple active XI slots → conflict styling (red). Slot order follows formation config.
- Auto-rank: sorts players still on that slot by role score, then OVR on ties. Slot removals stay off until Recently removed restore or a newer Role-scores export (re-export reinstates immediately; brand-new exports still use Refresh exports).
- Prefer per-library slot depth; switching active library remounts Profiles via rev/store pattern already used.

---

## Data & uploads

- Prefer saved exports via upload library / cache over re-parsing huge CSVs in every callback.
- Precompute on upload / “Compute All” when extending heavy paths; shortlist callbacks should mostly choose columns/filters, not rescore.
- Historical compare: when a historical export is loaded, comparison is on; don’t leave redundant enable toggles.
- Player identity across refresh/replace: match primarily by **player name** (clubs change mid-season).

---

## What not to do

- Do not commit unless the user explicitly asks.
- Do not add markdown docs the user did not request (except when asked, like this file).
- Do not expand scope into refactors, new settings pages, or drive-by cleanup unrelated to the ask.
- Do not reintroduce removed features (e.g. custom formation slot-name editor, shortlist column settings UI) unless requested again.
- Do not attach or re-read entire external HTML/CSV guides when a short extracted rule list suffices.
