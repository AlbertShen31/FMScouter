# FMScouter architecture

Dash app that scores Football Manager 26 players from an attribute CSV using role weight configs.

```
score = (5 * sum(key) + 3 * sum(preferred) + 1 * sum(useful)) / divisor
```

`divisor` is `5 * n_key + 3 * n_preferred + 1 * n_useful` so a player with 20 in every listed attribute scores 20.

Attribute tiers: **Key** ×5 (neon green), **Preferred** ×3 (yellow-green), **Useful** ×1 (blue). Colors are display-only. Packs store `key_attrs` / `preferred_attrs` / `useful_attrs`; older files used `green_attrs` / `blue_attrs` and are remapped on load.

## Layout

```
app.py                 # Dash entry, nav, session stores
pages/                 # one module per route (Dash use_pages)
components/            # shared UI (tables, filters, upload shell)
scoring/               # CSV parse + role/stats scoring domain
services/              # packs, formations, settings persistence
config/                # JSON/Python data (weights, formations, settings)
assets/                # CSS
docs/
```

| Path | Role |
| --- | --- |
| `app.py` | Dash shell and nav (Role scores, Player stats, Squad finance, Role configs, Formations, Settings). |
| `pages/` | Route modules: Role scores, Player stats, Squad finance, Role configs, Formations, Settings. |
| `components/scouting_shell.py` | Shared upload / pos-foot / marks / hist layout + callback registrars. |
| `components/player_table.py` | Shared DataTable shell, identity styles, Feet/Rec. |
| `components/player_modal.py` | Shared player detail modal. |
| `components/player_filters.py` | Position / foot / category filter chrome. |
| `components/pack_picker.py` | Pack select + edit-link toolbar. |
| `components/attr_columns.py` | Attribute grid for Role configs / player profile. |
| `scoring/role_scorer.py` | Parse attribute CSV, eligibility, role scoring, POS cards. |
| `scoring/stats_scorer.py` | Parse Moneyball stats CSV, Mustermann percentiles. |
| `scoring/squad_finance.py` | Parse salary / match-fee CSV; best/worst matchday XVI statement. |
| `scoring/phases.py` | IP / OOP / GK badges and GK detection. |
| `scoring/utils.py` | Weighted-average formula. |
| `scoring/division_tiers.py` | Map FM Division (+ Based In) to top / pro / amateur. |
| `scoring/personality_ranges.py` | Estimate hidden personality attrs. |
| `services/role_config.py` | Role-weight packs, live overlays, group-id migration. |
| `services/formations.py` | Formation packs, validation, combo export. |
| `services/ui_settings.py` | UI thresholds/colors packs. |
| `services/stats_threshold_packs.py` | Percentile-threshold packs for Player stats. |
| `config/paths.py` | Canonical directories for role weights, formations, and settings. |
| `config/role_weights/` | Role weight domain: factory Python, `active.json`, `packs/`. |
| `config/role_weights/fm26_role_weight_config.py` | Factory roles, group ids, home-group resolution. |
| `config/formations/` | Formation domain: `active.json`, `packs/`. |
| `config/settings/` | UI settings domain: `active.json`, `default-overrides.json`, `packs/`. |
| `fm26_player_scoring_system_v2_0.html` | Historical HTML scorer the Python weights were ported from. Not used at runtime. |

### Scouting shell

`components/scouting_shell.py` owns the shared plumbing between Role scores (`rs-*`) and Player stats (`st-*`):

- **Upload** — decode CSV, parse via a page-supplied function, write `{prefix}-parsed` (plain `{players, filename}` or zlib-packed).
- **Pos / foot** — pattern-matching card toggles into filter stores.
- **Marks** — DataTable `selected_row_ids` synced to a marked-keys store (stable row `id` / `_key`).
- **Hist** — show/hide score-distribution wrap.

Domain scoring, columns, and workflow gates stay page-local: Role scores still gates results until roles are scored; Stats reveals the shortlist on upload (`reveal_ids=["st-main"]`). Division tier filtering stays on Stats only.

### Config layout

Each saved-config domain uses the same shape under `config/`:

```
config/
  role_weights/          # scoring weights
    fm26_role_weight_config.py
    active.json
    packs/*.json
    default-overrides.json   # optional Built-in overlay
  formations/            # hybrid lineups
    active.json
    packs/*.json
  settings/              # Role scores UI thresholds/colors
    active.json
    default-overrides.json
    packs/*.json
```

`config/fm26_role_weight_config.py` is a thin import shim for older `import config.fm26_role_weight_config` call sites. Older role-weight files at `config/packs/` or `config/active_pack.json` are moved into `role_weights/` on load.


## Three different winger names

These collide in everyday FM language. Keep them separate:

1. **Role group `wm` — Wide midfielders.** Home of Wide Midfielder, **Winger (`W`)**, Half-Space Winger, Inside Winger, and the other wide-mid roles. Dict: `wm_positions`.
2. **Role group `w` — Wingers.** Home of Wide Forward and Inside Forward. Dict: `w_positions`.
3. **Player filter cards** on Role scores / Stats:
   - **Wide Midfielders** (`WM`, ML / MR) — CSS `.rs-pos-card.wm`
   - **Winger** (`W`, AML / AMR) — CSS `.rs-pos-card.w`

Inside Winger is `wm` plus `w`. Inside Forward is **only** `w`. Role `Winger_IP` is **only** `wm` (plus `w` via `groups`).

## Position groups

Each role has a `groups` list. Eligibility is **OR** across that list (`score_players` in `scoring/role_scorer.py`).

Home group comes from which dict the role is defined in (`_HOME_GROUPS` at the bottom of the factory config). Extra buckets are passed as `role(..., groups=('w',))`. A role must live in **one** dict only; if it belongs to two buckets (Wing Back in `wb` and `fb`, Attacking Midfielder in `am` and `cm`), use `groups` instead of copying the role into both dicts.

Current ids: `gk`, `cb`, `fb`, `wb`, `dm`, `cm`, `am`, `wm`, `w`, `st`.

UI labels live in `GROUP_DEFS` in `scoring/role_scorer.py`. The Role configs **Positions** chips toggle membership (`toggle_role_group`); at least one group is required.

### Saved pack group ids

JSON packs store `groups` per role. Current packs set `group_schema` to 2, where `wm` is wide midfielders and `w` is wingers.

Older packs omit that field (treated as 1). In those files the id `w` meant wide midfielders, and the retired wide-attacker id meant wingers. `services.role_config.migrate_group_ids` rewrites those lists on load so a saved `w` is not treated as the new Wingers group. New writes always include the current schema number.

## Eligibility vs player cards

`is_eligible(positions, group)` tests a parsed FM Position string against one **role group** (whether a player can be scored as eligible for that role).

- `wm`: `M` on L/R (ML / MR)
- `w`: `AM` on L/R (AML / AMR), or `ST`

Position-bar filters use `matches_pos_card` — exact FM positions only:

- Defensive Midfield: `DM`, `M (C)`
- Attacking Midfield: `M (C)`, `AM (C)` (CM appears on both midfield cards)
- Wide Midfielders: `M` on L/R
- Winger: `AM` on L/R
- Striker: `ST`
- and so on for GK / CB / FB

On the Stats page, Defensive Midfield, Attacking Midfield, and Wide Midfielders all use Mustermann **midfielder** thresholds (`POS_CARD_BENCH` → `mid`). Winger stays on forward thresholds.
## Phases

Roles are tagged IP, OOP, GK, IP_GK, or OOP_GK. Keeper IP/OOP variants still count as GK for filters and attribute sheets. Display badges show **IP** or **OOP**, never the raw keeper-phase token. UI monograms show the base role code (`CF`); score columns use `column_label()` when the same code appears in both phases (`CF-IP`, `CF-OOP`).

## Role scores UI concepts

The Role scores page uses three labels so “role” is not overloaded:

1. **Scored roles** — the FM26 roles you calculate. Phase and group chips under **Find roles** only narrow that picker; they are not extra role types.
2. **Hybrid roles** — optional IP/OOP weighted columns, created from **+ Create hybrid role**. Scoring still needs both constituent roles; adding a hybrid adds them to scored roles.
3. **Displayed roles** — which scored (and hybrid) columns the shortlist table, chart, min-score filter, and exports currently use. Squad depth cards toggle this set: click to add or remove focused roles; with none focused, every scored role is shown. **Show only hybrid roles** limits depth cards and table/export columns to hybrid IP+OOP scores (hides standalone roles and the expanded IP/OOP part columns).

Position groups and IP/OOP tags remain part of the data model. They are not a fourth picker called “role.”

## Config packs

Factory Python weights are the source of truth. The Role configs page loads a pack and edits in memory. **Save** writes a named pack; Built-in cannot be overwritten. **New config** makes a named file that is either a copy of the selected config or a blank slate (attributes off, groups kept). **Reset** reloads the selected role from the last saved pack. **Clear this role** turns off that role’s attributes. Named packs overlay `key_attrs` / `preferred_attrs` / `useful_attrs` / `groups`. Role scores step **2. Scored roles** picks which pack to score with.

## Formations

A formation is a named list of up to 11 **hybrid-only** slots. Each slot has an IP position (required) and an optional OOP position that filter the role pickers. If OOP position is blank, both role lists use the IP position. A filled scoring slot still needs both an IP role and an OOP role. `services.formations.combos_from_formation()` turns filled slots into the same combo objects Role scores already scores.

The Formations page opens on a new unsaved lineup. **Save** writes a new file when none is selected, or updates the selected one. Role scores **Load a saved formation** replaces the current hybrid list, adds the constituent roles to scored roles, and switches to Hybrid mode.
