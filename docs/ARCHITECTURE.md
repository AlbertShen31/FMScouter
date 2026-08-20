# FMScouter architecture

Dash app that scores Football Manager 26 players from an attribute CSV using role weight configs.

```
score = (5 * sum(key) + 3 * sum(preferred) + 1 * sum(useful)) / divisor
```

`divisor` is `5 * n_key + 3 * n_preferred + 1 * n_useful` so a player with 20 in every listed attribute scores 20.

Attribute tiers: **Key** ×5 (neon green), **Preferred** ×3 (yellow-green), **Useful** ×1 (blue). Colors are display-only. Packs store `key_attrs` / `preferred_attrs` / `useful_attrs`; older files used `green_attrs` / `blue_attrs` and are remapped on load.

## File map

| Path | Role |
| --- | --- |
| `app.py` | Dash shell and nav (Role scores, Role configs). |
| `pages/role_scores_page.py` | Upload CSV, pick roles, filter, export. |
| `pages/role_config_page.py` | Edit key/preferred/useful attributes and position groups. |
| `config/fm26_role_weight_config.py` | Factory roles, group ids, home-group resolution. |
| `role_scorer.py` | Parse CSV, eligibility, scoring, player POS cards. |
| `role_config.py` | Packs, live overlays, saved-group migration. |
| `phases.py` | IP / OOP / GK badges and GK detection. |
| `utils.py` | Weighted-average formula. |
| `canvas_export.py` | Cursor canvas export from scored rows. |
| `config/packs/` | Named JSON weight packs. |
| `config/active_pack.json` | Which pack is live. |
| `config/default_overrides.json` | Optional overlay applied under Built-in defaults. |
| `fm26_player_scoring_system_v2_0.html` | Historical HTML scorer the Python weights were ported from. Not used at runtime. |

## Three different winger names

These collide in everyday FM language. Keep them separate:

1. **Role group `wm` — Wide midfielders.** Home of Wide Midfielder, **Winger (`W`)**, Half-Space Winger, Inside Winger, and the other wide-mid roles. Dict: `wm_positions`.
2. **Role group `w` — Wingers.** Home of Wide Forward and Inside Forward. Dict: `w_positions`.
3. **Player filter card “Winger” (AML / AMR)** on Role scores. That card is about where the *player* can play, not which role group a *role* belongs to. It matches both `wm` and `w`. CSS class `.rs-pos-card.w` is this card.

Inside Winger is `wm` plus `w`. Inside Forward is **only** `w`. Role `Winger_IP` is **only** `wm` (plus `w` via `groups`).

## Position groups

Each role has a `groups` list. Eligibility is **OR** across that list (`score_players` in `role_scorer.py`).

Home group comes from which dict the role is defined in (`_HOME_GROUPS` at the bottom of the factory config). Extra buckets are passed as `role(..., groups=('w',))`. A role must live in **one** dict only; if it belongs to two buckets (Wing Back in `wb` and `fb`, Attacking Midfielder in `am` and `cm`), use `groups` instead of copying the role into both dicts.

Current ids: `gk`, `cb`, `fb`, `wb`, `dm`, `cm`, `am`, `wm`, `w`, `st`.

UI labels live in `GROUP_DEFS` in `role_scorer.py`. The Role configs **Positions** chips toggle membership (`toggle_role_group`); at least one group is required.

### Saved pack group ids

JSON packs store `groups` per role. Current packs set `group_schema` to 2, where `wm` is wide midfielders and `w` is wingers.

Older packs omit that field (treated as 1). In those files the id `w` meant wide midfielders, and the retired wide-attacker id meant wingers. `role_config.migrate_group_ids` rewrites those lists on load so a saved `w` is not treated as the new Wingers group. New writes always include the current schema number.

## Eligibility vs player cards

`is_eligible(positions, group)` tests a parsed FM Position string against one **role group**.

- `wm`: `M` or `AM` on L/R
- `w`: `AM` or `M` on L/R, or `ST`

`POS_CARD_GROUPS["W"]` includes both `wm` and `w`, so the AML/AMR player card still covers both wide role buckets.

## Phases

Roles are tagged IP, OOP, GK, IP_GK, or OOP_GK. Keeper IP/OOP variants still count as GK for filters and attribute sheets. Display badges show **IP** or **OOP**, never the raw keeper-phase token. UI monograms show the base role code (`CF`); score columns use `column_label()` when the same code appears in both phases (`CF-IP`, `CF-OOP`).

## Role scores UI concepts

The Role scores page uses three labels so “role” is not overloaded:

1. **Scored roles** — the FM26 roles you calculate. Phase and group chips under **Find roles** only narrow that picker; they are not extra role types.
2. **Hybrid roles** — optional IP/OOP weighted columns, created from **+ Create hybrid role**. Scoring still needs both constituent roles; adding a hybrid adds them to scored roles.
3. **Displayed roles** — which scored (and hybrid) columns the shortlist table, chart, min-score filter, and exports currently use.

Position groups and IP/OOP tags remain part of the data model. They are not a fourth picker called “role.”

## Config packs

Factory Python weights are the source of truth. The Role configs page loads a pack and edits in memory. **Save** writes a named pack; Built-in cannot be overwritten. **New config** makes a named file that is either a copy of the selected config or a blank slate (attributes off, groups kept). **Reset** reloads the selected role from the last saved pack. **Clear this role** turns off that role’s attributes. Named packs overlay `key_attrs` / `preferred_attrs` / `useful_attrs` / `groups`. Role scores step **2. Scored roles** picks which pack to score with.
