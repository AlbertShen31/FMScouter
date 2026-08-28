# Column & metric usage reference

Living reference for which FM export columns FMScouter reads and where they appear.
Regenerate after parser or stats config changes:

```bash
python scripts/audit_column_usage.py
```

**Source of truth:** parsers in `scoring/role_scorer.py`, `scoring/stats_scorer.py`,
`scoring/squad_finance.py`, plus `config/stats_benchmarks.json` and
`config/stats_availability.json`.

Snapshot column list: `config/export_formats/fm26_moneyball_combined_columns.json`
(248 columns). Custom upload views may add headers not
listed here — unknown columns are ignored until mapped in `scripts/audit_column_usage.py`.

## Page eligibility (saved uploads)

| Page | Gate |
|------|------|
| Role scores | Name + ≥1 attribute + Club/Age/Position |
| Player stats | Name + stats markers + Club/Age/Position |
| Squad finance | Name + Salary + Appearance Fee + Unused Sub Fee + Club/Age/Position |
| Profiles | Requires stats-eligible saved file for save / replace |

Uploads classifies files and precomputes role scores + stats percentiles.

## Categories

| Category | Role |
|----------|------|
| `identity` | Player info, positions, personality, international fields |
| `attribute` | FM attributes → role scores, set pieces, attribute modals |
| `stats_metric` | Moneyball stats → percentiles / charts |
| `stats_availability` | Limited-tracking detection only |
| `career` | Career totals in player modal |
| `discipline` | Cards / fouls / appearances in player modal |
| `finance` | Contract, wages, fees, clauses |
| `unused` | In export snapshot but intentionally not parsed |

## Identity & player info

| CSV column(s) | Internal key | Pages | Usage |
|---------------|--------------|-------|-------|
| `2nd Nat`, `Second Nationality`, `Second Nation` | `second_nation` | Player stats, Profiles, Role scores, Uploads | Parsed into player dict; shortlist / modal when configured |
| `Ability`, `CA` | `ability` | Player stats, Profiles, Role scores, Uploads | Parsed but hidden in UI (unreliable FM26 star ratings) |
| `Ability Gold` | `ability_gold` | Player stats, Profiles, Role scores, Uploads | Parsed but hidden in UI (unreliable FM26 star ratings) |
| `Ability Silver` | `ability_silver` | Player stats, Profiles, Role scores, Uploads | Parsed but hidden in UI (unreliable FM26 star ratings) |
| `Age` | `age` | Player stats, Profiles, Role scores, Uploads | Page eligibility gate + identity |
| `Average Rating International`, `Avg Rating International` | `avg_rating_int` | Player stats, Profiles, Role scores, Uploads | Parsed into player dict; shortlist / modal when configured |
| `Based In` | `based_in` | Player stats, Profiles, Role scores, Uploads | Parsed into player dict; shortlist / modal when configured |
| `Best Pos`, `Best Position` | `best_pos` | Player stats, Profiles, Role scores, Uploads | Role eligibility, position groups, shortlist / modal |
| `Best Role` | `best_role` | Player stats, Profiles, Role scores, Uploads | Role eligibility, position groups, shortlist / modal |
| `Club` | `club` | Player stats, Profiles, Role scores, Uploads | Page eligibility gate + identity |
| `Division`, `Div` | `division` | Player stats, Profiles, Role scores, Uploads | Division tier + limited-tracking stripe (Player stats / Profiles) |
| `Form International`, `Form Int` | `form_int` | Player stats, Profiles, Role scores, Uploads | Parsed into player dict; shortlist / modal when configured |
| `Height` | `height` | Player stats, Profiles, Role scores, Uploads | Parsed into player dict; shortlist / modal when configured |
| `Home Grown Status` | `home_grown_status` | Player stats, Profiles, Role scores, Uploads | Parsed into player dict; shortlist / modal when configured |
| `Inf` | `inf` | Player stats, Profiles, Role scores, Uploads | Parsed into player dict; shortlist / modal when configured |
| `Injury` | `injury` | Player stats, Profiles, Role scores, Uploads | Parsed into player dict; shortlist / modal when configured |
| `Int Apps`, `International Appearances` | `int_apps` | Player stats, Profiles, Role scores, Uploads | Parsed into player dict; shortlist / modal when configured |
| `Int Gls`, `International Goals` | `int_gls` | Player stats, Profiles, Role scores, Uploads | Parsed into player dict; shortlist / modal when configured |
| `International Appearances (Season)`, `Int Apps (Season)` | `int_apps_season` | Player stats, Profiles, Role scores, Uploads | Parsed into player dict; shortlist / modal when configured |
| `International Assists`, `Int Assists` | `int_assists` | Player stats, Profiles, Role scores, Uploads | Parsed into player dict; shortlist / modal when configured |
| `International Goals Conceded` | `int_goals_conceded` | Player stats, Profiles, Role scores, Uploads | Parsed into player dict; shortlist / modal when configured |
| `Last 5 Games International`, `Last 5 Games Int` | `last5_int` | Player stats, Profiles, Role scores, Uploads | Parsed into player dict; shortlist / modal when configured |
| `Left Foot`, `LFoot`, `L` | `left_foot` | Player stats, Profiles, Role scores, Uploads | Parsed into player dict; shortlist / modal when configured |
| `Media Handling` | `media_handling` | Player stats, Profiles, Role scores, Uploads | Parsed into player dict; shortlist / modal when configured |
| `Nation`, `Nat`, `Nationality` | `nation` | Player stats, Profiles, Role scores, Uploads | Parsed into player dict; shortlist / modal when configured |
| `National Team` | `national_team` | Player stats, Profiles, Role scores, Uploads | Parsed into player dict; shortlist / modal when configured |
| `Personality` | `personality` | Player stats, Profiles, Role scores, Uploads | Personality tier classification + modal |
| `Picked` | `picked` | Player stats, Profiles, Role scores, Uploads | Parsed into player dict; shortlist / modal when configured |
| `Player`, `Name` | `name` | Player stats, Profiles, Role scores, Uploads | Player identity key across all pages |
| `Position` | `position` | Player stats, Profiles, Role scores, Uploads | Role eligibility, position groups, shortlist / modal |
| `Position/Role`, `Position / Role` | `position_role` | Player stats, Profiles, Role scores, Uploads | Parsed into player dict; shortlist / modal when configured |
| `Potential`, `PA` | `potential` | Player stats, Profiles, Role scores, Uploads | Parsed but hidden in UI (unreliable FM26 star ratings) |
| `Potential Gold` | `potential_gold` | Player stats, Profiles, Role scores, Uploads | Parsed but hidden in UI (unreliable FM26 star ratings) |
| `Potential Silver` | `potential_silver` | Player stats, Profiles, Role scores, Uploads | Parsed but hidden in UI (unreliable FM26 star ratings) |
| `Rec.`, `Rec` | `rec` | Player stats, Profiles, Role scores, Uploads | Parsed into player dict; shortlist / modal when configured |
| `Right Foot`, `RFoot`, `R` | `right_foot` | Player stats, Profiles, Role scores, Uploads | Parsed into player dict; shortlist / modal when configured |
| `Sec. Position`, `Secondary Position`, `Sec Position` | `sec_position` | Player stats, Profiles, Role scores, Uploads | Role eligibility, position groups, shortlist / modal |
| `Squad` | `squad` | Player stats, Profiles, Role scores, Uploads | Parsed into player dict; shortlist / modal when configured |
| `Style` | `style` | Player stats, Profiles, Role scores, Uploads | Parsed into player dict; shortlist / modal when configured |
| `World Reputation` | `world_reputation` | Player stats, Profiles, Role scores, Uploads | Parsed but hidden in UI (unreliable FM26 star ratings) |
| `World Reputation Gold` | `world_reputation_gold` | Player stats, Profiles, Role scores, Uploads | Parsed but hidden in UI (unreliable FM26 star ratings) |
| `World Reputation Silver` | `world_reputation_silver` | Player stats, Profiles, Role scores, Uploads | Parsed but hidden in UI (unreliable FM26 star ratings) |
| `Yth Apps`, `Youth Apps` | `yth_apps` | Player stats, Profiles, Role scores, Uploads | Parsed into player dict; shortlist / modal when configured |
| `Yth Gls`, `Youth Goals` | `yth_gls` | Player stats, Profiles, Role scores, Uploads | Parsed into player dict; shortlist / modal when configured |

## Attributes

| CSV column(s) | Internal key | Pages | Usage |
|---------------|--------------|-------|-------|
| `Acceleration` | `Acc` | Formulas, Profiles, Role scores, Uploads | Role score weights (Role scores / Formulas); attribute grid in modals |
| `Aerial Reach` | `Aer` | Formulas, Profiles, Role scores, Uploads | Role score weights (Role scores / Formulas); attribute grid in modals |
| `Aggression` | `Agg` | Formulas, Profiles, Role scores, Uploads | Role score weights (Role scores / Formulas); attribute grid in modals |
| `Agility` | `Agi` | Formulas, Profiles, Role scores, Uploads | Role score weights (Role scores / Formulas); attribute grid in modals |
| `Anticipation` | `Ant` | Formulas, Profiles, Role scores, Uploads | Role score weights (Role scores / Formulas); attribute grid in modals |
| `Balance` | `Bal` | Formulas, Profiles, Role scores, Uploads | Role score weights (Role scores / Formulas); attribute grid in modals |
| `Bravery` | `Bra` | Formulas, Profiles, Role scores, Uploads | Role score weights (Role scores / Formulas); attribute grid in modals |
| `Command Of Area`, `Command of Area` | `Cmd` | Formulas, Profiles, Role scores, Uploads | Role score weights (Role scores / Formulas); attribute grid in modals |
| `Communication` | `Com` | Formulas, Profiles, Role scores, Uploads | Role score weights (Role scores / Formulas); attribute grid in modals |
| `Composure` | `Cmp` | Formulas, Profiles, Role scores, Uploads | Role score weights (Role scores / Formulas); attribute grid in modals |
| `Concentration` | `Cnt` | Formulas, Profiles, Role scores, Uploads | Role score weights (Role scores / Formulas); attribute grid in modals |
| `Corners` | `Cor` | Formulas, Profiles, Role scores, Uploads | Role score weights (Role scores / Formulas); attribute grid in modals; set-piece raw column when checked on Role scores |
| `Crossing` | `Cro` | Formulas, Profiles, Role scores, Uploads | Role score weights (Role scores / Formulas); attribute grid in modals |
| `Decisions` | `Dec` | Formulas, Profiles, Role scores, Uploads | Role score weights (Role scores / Formulas); attribute grid in modals |
| `Determination` | `Det` | Player stats, Profiles, Role scores, Uploads | Personality hidden-range estimation (Player stats parser) |
| `Dribbling` | `Dri` | Formulas, Profiles, Role scores, Uploads | Role score weights (Role scores / Formulas); attribute grid in modals |
| `Eccentricity` | `Ecc` | Formulas, Profiles, Role scores, Uploads | Role score weights (Role scores / Formulas); attribute grid in modals |
| `Finishing` | `Fin` | Formulas, Profiles, Role scores, Uploads | Role score weights (Role scores / Formulas); attribute grid in modals |
| `First Touch` | `Fir` | Formulas, Profiles, Role scores, Uploads | Role score weights (Role scores / Formulas); attribute grid in modals |
| `Flair` | `Fla` | Formulas, Profiles, Role scores, Uploads | Role score weights (Role scores / Formulas); attribute grid in modals |
| `Free Kick Taking` | `Fre` | Formulas, Profiles, Role scores, Uploads | Role score weights (Role scores / Formulas); attribute grid in modals; set-piece raw column when checked on Role scores |
| `Handling` | `Han` | Formulas, Profiles, Role scores, Uploads | Role score weights (Role scores / Formulas); attribute grid in modals |
| `Heading` | `Hea` | Formulas, Profiles, Role scores, Uploads | Role score weights (Role scores / Formulas); attribute grid in modals |
| `Jumping Reach` | `Jum` | Formulas, Profiles, Role scores, Uploads | Role score weights (Role scores / Formulas); attribute grid in modals |
| `Kicking` | `Kic` | Formulas, Profiles, Role scores, Uploads | Role score weights (Role scores / Formulas); attribute grid in modals |
| `Leadership` | `Ldr` | Player stats, Profiles, Role scores, Uploads | Personality hidden-range estimation (Player stats parser) |
| `Long Shots` | `Lon` | Formulas, Profiles, Role scores, Uploads | Role score weights (Role scores / Formulas); attribute grid in modals |
| `Long Throws` | `LTh` | Formulas, Profiles, Role scores, Uploads | Role score weights (Role scores / Formulas); attribute grid in modals; set-piece raw column when checked on Role scores |
| `Marking` | `Mar` | Formulas, Profiles, Role scores, Uploads | Role score weights (Role scores / Formulas); attribute grid in modals |
| `Natural Fitness` | `Nat` | Formulas, Profiles, Role scores, Uploads | Role score weights (Role scores / Formulas); attribute grid in modals |
| `Off The Ball`, `Off the Ball` | `OtB` | Formulas, Profiles, Role scores, Uploads | Role score weights (Role scores / Formulas); attribute grid in modals |
| `One On Ones`, `One on Ones` | `1v1` | Formulas, Profiles, Role scores, Uploads | Role score weights (Role scores / Formulas); attribute grid in modals |
| `Pace` | `Pac` | Formulas, Profiles, Role scores, Uploads | Role score weights (Role scores / Formulas); attribute grid in modals |
| `Passing` | `Pas` | Formulas, Profiles, Role scores, Uploads | Role score weights (Role scores / Formulas); attribute grid in modals |
| `Penalty Taking` | `Pen` | Formulas, Profiles, Role scores, Uploads | Role score weights (Role scores / Formulas); attribute grid in modals; set-piece raw column when checked on Role scores |
| `Positioning` | `Pos` | Formulas, Profiles, Role scores, Uploads | Role score weights (Role scores / Formulas); attribute grid in modals |
| `Punching` | `Pun` | Formulas, Profiles, Role scores, Uploads | Role score weights (Role scores / Formulas); attribute grid in modals |
| `Reflexes` | `Ref` | Formulas, Profiles, Role scores, Uploads | Role score weights (Role scores / Formulas); attribute grid in modals |
| `Rushing Out (Tendency)`, `Rushing Out` | `TRO` | Formulas, Profiles, Role scores, Uploads | Role score weights (Role scores / Formulas); attribute grid in modals |
| `Stamina` | `Sta` | Formulas, Profiles, Role scores, Uploads | Role score weights (Role scores / Formulas); attribute grid in modals |
| `Strength` | `Str` | Formulas, Profiles, Role scores, Uploads | Role score weights (Role scores / Formulas); attribute grid in modals |
| `Tackling` | `Tck` | Formulas, Profiles, Role scores, Uploads | Role score weights (Role scores / Formulas); attribute grid in modals |
| `Team Work`, `Teamwork` | `Tea` | Formulas, Profiles, Role scores, Uploads | Role score weights (Role scores / Formulas); attribute grid in modals |
| `Technique` | `Tec` | Formulas, Profiles, Role scores, Uploads | Role score weights (Role scores / Formulas); attribute grid in modals |
| `Throwing` | `Thr` | Formulas, Profiles, Role scores, Uploads | Role score weights (Role scores / Formulas); attribute grid in modals |
| `Vision` | `Vis` | Formulas, Profiles, Role scores, Uploads | Role score weights (Role scores / Formulas); attribute grid in modals |
| `Work Rate` | `Wor` | Formulas, Profiles, Role scores, Uploads | Role score weights (Role scores / Formulas); attribute grid in modals |

## Stats metrics (percentiles)

| CSV column(s) | Internal key | Pages | Usage |
|---------------|--------------|-------|-------|
| `Assists` | `assists` | Player stats, Profiles, Uploads | Stats percentile metric «Assists per 90» (assists) |
| `Asts/90` | `assists` | Player stats, Profiles, Uploads | Stats percentile metric «Assists per 90» (assists) |
| `Blk/90` | `blocks` | Player stats, Profiles, Uploads | Stats percentile metric «Blocks per 90» (blocks) |
| `Clearances per 90` | `clearances` | Player stats, Profiles, Uploads | Stats percentile metric «Clearances per 90» (clearances); limited-tracking probe |
| `Conv %` | `conversion_rate` | Player stats, Profiles, Uploads | Stats percentile metric «Conversion Rate» (conversion_rate) |
| `Conversion %` | `conversion_rate` | Player stats, Profiles, Uploads | Stats percentile metric «Conversion Rate» (conversion_rate) |
| `Conversion Rate` | `conversion_rate` | Player stats, Profiles, Uploads | Stats percentile metric «Conversion Rate» (conversion_rate) |
| `Crosses Completed per 90` | `crosses_completed` | Player stats, Profiles, Uploads | Stats percentile metric «Open-Play Crosses Completed per 90» (crosses_completed) |
| `Dribbles` | `dribbles` | Player stats, Profiles, Uploads | Stats percentile metric «Dribbles per 90» (dribbles) |
| `Dribbles per 90` | `dribbles` | Player stats, Profiles, Uploads | Stats percentile metric «Dribbles per 90» (dribbles) |
| `Goals` | `goals` | Player stats, Profiles, Uploads | Stats percentile metric «Goals per 90» (goals) |
| `Goals Allowed` | `goals_conceded` | Player stats, Profiles, Uploads | Stats percentile metric «Goals Conceded per 90» (goals_conceded); basic availability probe |
| `Goals per 90 minutes` | `goals` | Player stats, Profiles, Uploads | Stats percentile metric «Goals per 90» (goals) |
| `Hdrs W/90` | `headers_won` | Player stats, Profiles, Uploads | Stats percentile metric «Headers Won per 90» (headers_won) |
| `Headers Attempted per 90` | `headers_attempted` | Player stats, Profiles, Uploads | Stats percentile metric «Headers Attempted per 90» (headers_attempted) |
| `Headers Won` | `headers_won` | Player stats, Profiles, Uploads | Stats percentile metric «Headers Won per 90» (headers_won) |
| `Headers Won Percentage` | `header_win_rate` | Player stats, Profiles, Uploads | Stats percentile metric «Header Win Rate» (header_win_rate) |
| `Headers Won per 90` | `headers_won` | Player stats, Profiles, Uploads | Stats percentile metric «Headers Won per 90» (headers_won) |
| `Interceptions per 90` | `interceptions` | Player stats, Profiles, Uploads | Stats percentile metric «Interceptions per 90» (interceptions); limited-tracking probe |
| `Key Passes` | `key_passes` | Player stats, Profiles, Uploads | Stats percentile metric «Key Passes per 90» (key_passes); limited-tracking probe |
| `Key Passes per 90` | `key_passes` | Player stats, Profiles, Uploads | Stats percentile metric «Key Passes per 90» (key_passes); limited-tracking probe |
| `Minutes` | `minutes` | Player stats, Profiles, Uploads | Minutes gate, per-90 derivation, limited-tracking aggregates |
| `OP Cr C/90` | `crosses_completed` | Player stats, Profiles, Uploads | Stats percentile metric «Open-Play Crosses Completed per 90» (crosses_completed) |
| `OP Crosses Completed per 90` | `crosses_completed` | Player stats, Profiles, Uploads | Stats percentile metric «Open-Play Crosses Completed per 90» (crosses_completed) |
| `Open Play Crosses Completed per 90` | `crosses_completed` | Player stats, Profiles, Uploads | Stats percentile metric «Open-Play Crosses Completed per 90» (crosses_completed) |
| `Pass Completion %` | `pass_completion` | Player stats, Profiles, Uploads | Stats percentile metric «Pass Completion» (pass_completion) |
| `Pass Completion Percentage` | `pass_completion` | Player stats, Profiles, Uploads | Stats percentile metric «Pass Completion» (pass_completion) |
| `Pass Completion Ratio` | `pass_completion` | Player stats, Profiles, Uploads | Stats percentile metric «Pass Completion» (pass_completion) |
| `Passes Attempted per 90` | `passes_attempted` | Player stats, Profiles, Uploads | Stats percentile metric «Passes Attempted per 90» (passes_attempted); basic availability probe |
| `Possession Lost per 90` | `possession_lost` | Player stats, Profiles, Uploads | Stats percentile metric «Possession Lost per 90» (possession_lost) |
| `Possession Won per 90` | `possession_won` | Player stats, Profiles, Uploads | Stats percentile metric «Possession Won per 90» (possession_won) |
| `Pres C/90` | `pressures` | Player stats, Profiles, Uploads | Stats percentile metric «Pressures Completed per 90» (pressures) |
| `Pressures Completed` | `pressures` | Player stats, Profiles, Uploads | Stats percentile metric «Pressures Completed per 90» (pressures) |
| `Pressures Completed per 90` | `pressures` | Player stats, Profiles, Uploads | Stats percentile metric «Pressures Completed per 90» (pressures) |
| `Progressive Passes per 90` | `progressive_passes` | Player stats, Profiles, Uploads | Stats percentile metric «Progressive Passes per 90» (progressive_passes); limited-tracking probe |
| `Ps C %` | `pass_completion` | Player stats, Profiles, Uploads | Stats percentile metric «Pass Completion» (pass_completion) |
| `SOT/90` | `shots_on_target` | Player stats, Profiles, Uploads | Stats percentile metric «Shots On Target per 90» (shots_on_target) |
| `Shot Conversion %` | `conversion_rate` | Player stats, Profiles, Uploads | Stats percentile metric «Conversion Rate» (conversion_rate) |
| `Shot/90` | `shots` | Player stats, Profiles, Uploads | Stats percentile metric «Shots per 90» (shots); basic availability probe |
| `Shots` | `shots` | Player stats, Profiles, Uploads | Stats percentile metric «Shots per 90» (shots); basic availability probe |
| `Shots Conversion %` | `conversion_rate` | Player stats, Profiles, Uploads | Stats percentile metric «Conversion Rate» (conversion_rate) |
| `Shots On Target` | `shots_on_target` | Player stats, Profiles, Uploads | Stats percentile metric «Shots On Target per 90» (shots_on_target) |
| `Shots On Target per 90` | `shots_on_target` | Player stats, Profiles, Uploads | Stats percentile metric «Shots On Target per 90» (shots_on_target) |
| `Shots on Target` | `shots_on_target` | Player stats, Profiles, Uploads | Stats percentile metric «Shots On Target per 90» (shots_on_target) |
| `Shots on Target per 90` | `shots_on_target` | Player stats, Profiles, Uploads | Stats percentile metric «Shots On Target per 90» (shots_on_target) |
| `Shots on Target/90` | `shots_on_target` | Player stats, Profiles, Uploads | Stats percentile metric «Shots On Target per 90» (shots_on_target) |
| `Shts Blckd/90` | `blocks` | Player stats, Profiles, Uploads | Stats percentile metric «Blocks per 90» (blocks) |
| `Sprints` | `sprints` | Player stats, Profiles, Uploads | Stats percentile metric «Sprints per 90» (sprints) |
| `Sprints per 90` | `sprints` | Player stats, Profiles, Uploads | Stats percentile metric «Sprints per 90» (sprints) |
| `Sprints/90` | `sprints` | Player stats, Profiles, Uploads | Stats percentile metric «Sprints per 90» (sprints) |
| `Tackle Completion Percentage` | `tackle_win_rate` | Player stats, Profiles, Uploads | Stats percentile metric «Tackle Win Rate» (tackle_win_rate) |
| `Tackles Attempted` | `tackles_attempted` | Player stats, Profiles, Uploads | Stats percentile metric «Tackles Attempted per 90» (tackles_attempted); basic availability probe |
| `xA` | `expected_assists` | Player stats, Profiles, Uploads | Stats percentile metric «Expected Assists per 90» (expected_assists) |
| `xA/90` | `expected_assists` | Player stats, Profiles, Uploads | Stats percentile metric «Expected Assists per 90» (expected_assists) |
| `xG` | `expected_goals` | Player stats, Profiles, Uploads | Stats percentile metric «Expected Goals per 90» (expected_goals) |
| `xG/90` | `expected_goals` | Player stats, Profiles, Uploads | Stats percentile metric «Expected Goals per 90» (expected_goals) |
| `xGP` | `xg_prevented` | Player stats, Profiles, Uploads | Stats percentile metric «xG Prevented per 90» (xg_prevented) |
| `xGP/90` | `xg_prevented` | Player stats, Profiles, Uploads | Stats percentile metric «xG Prevented per 90» (xg_prevented) |

## Stats availability probes

| CSV column(s) | Internal key | Pages | Usage |
|---------------|--------------|-------|-------|
| `Clearances` | `Clearances` | Player stats, Profiles, Uploads | Limited-tracking league detection (not a scored percentile) |
| `Interceptions` | `Interceptions` | Player stats, Profiles, Uploads | Limited-tracking league detection (not a scored percentile) |
| `Passes Attempted` | `Passes Attempted` | Player stats, Profiles, Uploads | Limited-tracking league detection (not a scored percentile) |

## Career totals

| CSV column(s) | Internal key | Pages | Usage |
|---------------|--------------|-------|-------|
| `AT Apps` | `at_apps` | Player stats, Profiles, Role scores, Uploads | Player modal → Career totals |
| `AT Gls` | `at_gls` | Player stats, Profiles, Role scores, Uploads | Player modal → Career totals |
| `AT League Apps` | `at_league_apps` | Player stats, Profiles, Role scores, Uploads | Player modal → Career totals |
| `AT League Goals` | `at_league_goals` | Player stats, Profiles, Role scores, Uploads | Player modal → Career totals |

## Discipline

| CSV column(s) | Internal key | Pages | Usage |
|---------------|--------------|-------|-------|
| `Appearances` | `appearances` | Player stats, Profiles, Role scores, Uploads | Player modal → Discipline |
| `Fouls Against` | `fouls_against` | Player stats, Profiles, Role scores, Uploads | Player modal → Discipline |
| `Fouls Made` | `fouls_made` | Player stats, Profiles, Role scores, Uploads | Player modal → Discipline |
| `Red cards`, `Red Cards` | `red_cards` | Player stats, Profiles, Role scores, Uploads | Player modal → Discipline |
| `Yellow Cards` | `yellow_cards` | Player stats, Profiles, Role scores, Uploads | Player modal → Discipline |

## Contract & finance

| CSV column(s) | Internal key | Pages | Usage |
|---------------|--------------|-------|-------|
| `Active Non Promotion Release Clause` | `active_non_promotion_release` | Player stats, Profiles, Role scores, Uploads | Parsed + stored; not shown in UI (granular release clause) — Consider surfacing or dropping if unused long-term |
| `Active Relegation Release Clause` | `active_relegation_release` | Player stats, Profiles, Role scores, Uploads | Parsed + stored; not shown in UI (granular release clause) — Consider surfacing or dropping if unused long-term |
| `Appearance Fee` | `appearance_fee` | Player stats, Profiles, Role scores, Squad finance, Uploads | Squad finance wage / match-fee calculations |
| `Assist Bonus` | `assist_bonus` | Player stats, Profiles, Role scores, Uploads | Player modal → Contract & finance |
| `Expires` | `contract_expires` | Player stats, Profiles, Role scores, Uploads | Player modal → Contract & finance |
| `FFP Contribution` | `ffp_contribution` | Player stats, Profiles, Role scores, Squad finance, Uploads | Displayed on Squad finance; excluded from totals |
| `Goal Bonus` | `goal_bonus` | Player stats, Profiles, Role scores, Uploads | Player modal → Contract & finance |
| `Int Cap Bonus` | `int_cap_bonus` | Player stats, Profiles, Role scores, Uploads | Player modal → Contract & finance |
| `Minimum Fee Release Clause` | `min_release_clause` | Player stats, Profiles, Role scores, Uploads | Player modal → Contract & finance |
| `Minimum Fee Release Clause (Clubs in a Continental Competition)` | `min_release_clause_continental` | Player stats, Profiles, Role scores, Uploads | Parsed + stored; not shown in UI (granular release clause) — Consider surfacing or dropping if unused long-term |
| `Minimum Fee Release Clause (Clubs in a Continental Competition) - Expiry Date` | `min_release_clause_continental_expires` | Player stats, Profiles, Role scores, Uploads | Parsed + stored; not shown in UI (granular release clause) — Consider surfacing or dropping if unused long-term |
| `Minimum Fee Release Clause (Clubs in a Major Continental Competition)` | `min_release_clause_major_continental` | Player stats, Profiles, Role scores, Uploads | Parsed + stored; not shown in UI (granular release clause) — Consider surfacing or dropping if unused long-term |
| `Minimum Fee Release Clause (Clubs in a Major Continental Competition) - Expiry Date` | `min_release_clause_major_continental_expires` | Player stats, Profiles, Role scores, Uploads | Parsed + stored; not shown in UI (granular release clause) — Consider surfacing or dropping if unused long-term |
| `Minimum Fee Release Clause (Domestic Clubs in Higher Division)` | `min_release_clause_higher_division` | Player stats, Profiles, Role scores, Uploads | Parsed + stored; not shown in UI (granular release clause) — Consider surfacing or dropping if unused long-term |
| `Minimum Fee Release Clause (Domestic Clubs in Higher Division) - Expiry Date` | `min_release_clause_higher_division_expires` | Player stats, Profiles, Role scores, Uploads | Parsed + stored; not shown in UI (granular release clause) — Consider surfacing or dropping if unused long-term |
| `Minimum Fee Release Clause (Domestic Clubs)` | `min_release_clause_domestic` | Player stats, Profiles, Role scores, Uploads | Parsed + stored; not shown in UI (granular release clause) — Consider surfacing or dropping if unused long-term |
| `Minimum Fee Release Clause (Domestic Clubs) - Expiry Date` | `min_release_clause_domestic_expires` | Player stats, Profiles, Role scores, Uploads | Parsed + stored; not shown in UI (granular release clause) — Consider surfacing or dropping if unused long-term |
| `Minimum Fee Release Clause (Foreign Clubs)` | `min_release_clause_foreign` | Player stats, Profiles, Role scores, Uploads | Parsed + stored; not shown in UI (granular release clause) — Consider surfacing or dropping if unused long-term |
| `Minimum Fee Release Clause (Foreign Clubs) - Expiry Date` | `min_release_clause_foreign_expires` | Player stats, Profiles, Role scores, Uploads | Parsed + stored; not shown in UI (granular release clause) — Consider surfacing or dropping if unused long-term |
| `Minimum Fee Release Clause - Expiry Date` | `min_release_clause_expires` | Player stats, Profiles, Role scores, Uploads | Parsed + stored; not shown in UI (granular release clause) — Consider surfacing or dropping if unused long-term |
| `Non Promotion Release Clause` | `non_promotion_release` | Player stats, Profiles, Role scores, Uploads | Parsed + stored; not shown in UI (granular release clause) — Consider surfacing or dropping if unused long-term |
| `Promotion Salary Raise` | `promotion_salary_raise` | Player stats, Profiles, Role scores, Squad finance, Uploads | Squad finance wage / match-fee calculations |
| `Relegation Release Clause` | `relegation_release` | Player stats, Profiles, Role scores, Uploads | Parsed + stored; not shown in UI (granular release clause) — Consider surfacing or dropping if unused long-term |
| `Relegation Salary Drop` | `relegation_salary_drop` | Player stats, Profiles, Role scores, Squad finance, Uploads | Squad finance wage / match-fee calculations |
| `Salary` | `salary` | Player stats, Profiles, Role scores, Squad finance, Uploads | Squad finance wage / match-fee calculations |
| `Shutout Bonus` | `shutout_bonus` | Player stats, Profiles, Role scores, Uploads | Player modal → Contract & finance |
| `Top Division Promotion Salary raise`, `Top Division Promotion Salary Raise` | `top_division_promotion_salary_raise` | Player stats, Profiles, Role scores, Squad finance, Uploads | Squad finance wage / match-fee calculations |
| `Top Division Relegation Salary Drop` | `top_division_relegation_salary_drop` | Player stats, Profiles, Role scores, Squad finance, Uploads | Squad finance wage / match-fee calculations |
| `Transfer Value` | `transfer_value` | Player stats, Profiles, Role scores, Uploads | Player modal → Contract & finance |
| `Unused Substitute Fee` | `unused_sub_fee` | Player stats, Profiles, Role scores, Squad finance, Uploads | Squad finance wage / match-fee calculations |
| `WP Needed` | `wp_needed` | Player stats, Profiles, Role scores, Uploads | Player modal → Contract & finance |
| `Work Permit Required` | `work_permit_required` | Player stats, Profiles, Role scores, Uploads | Player modal → Contract & finance |
| `Yearly Salary Raise` | `yearly_salary_raise` | Player stats, Profiles, Role scores, Squad finance, Uploads | Squad finance wage / match-fee calculations |

## Not parsed (intentional)

| CSV column(s) | Internal key | Pages | Usage |
|---------------|--------------|-------|-------|
| `All/90` | `All/90` | — | Not parsed by any page — Season overview aggregate |
| `Average Rating Club` | `Average Rating Club` | — | Not parsed by any page — Club form rating; international variant is parsed |
| `Blk` | `Blk` | — | Not parsed by any page — Block total; Blk/90 is the scored metric |
| `Chances Created per 90` | `Chances Created per 90` | — | Not parsed by any page — Not in stats benchmarks |
| `Clear Cut Chances Created` | `Clear Cut Chances Created` | — | Not parsed by any page — Not in stats benchmarks |
| `Cln/90` | `Cln/90` | — | Not parsed by any page — Clean sheets per 90 (GK); not scored |
| `Crosses Attempted` | `Crosses Attempted` | — | Not parsed by any page — Cross totals; only OP crosses completed /90 scored |
| `Crosses Attempted per 90` | `Crosses Attempted per 90` | — | Not parsed by any page — Not in stats benchmarks |
| `Crosses Completed` | `Crosses Completed` | — | Not parsed by any page — Cross totals; only OP crosses completed /90 scored |
| `Crosses Completed Ratio` | `Crosses Completed Ratio` | — | Not parsed by any page — Not in stats benchmarks |
| `Dist/90` | `Dist/90` | — | Not parsed by any page — Physical distance; not scored |
| `Distance` | `Distance` | — | Not parsed by any page — Physical distance total; not scored |
| `Expected Save Percentage` | `Expected Save Percentage` | — | Not parsed by any page — GK detail; xGP/90 used instead |
| `Form` | `Form` | — | Not parsed by any page — Generic form string; not parsed |
| `Form Club` | `Form Club` | — | Not parsed by any page — Club form; Int form fields are parsed via identity |
| `Free Kick Shots` | `Free Kick Shots` | — | Not parsed by any page — Shooting detail; not scored |
| `Game Win Ratio` | `Game Win Ratio` | — | Not parsed by any page — Results aggregate; not parsed |
| `Games Drawn` | `Games Drawn` | — | Not parsed by any page — Results aggregate; not parsed |
| `Games Lost` | `Games Lost` | — | Not parsed by any page — Results aggregate; not parsed |
| `Games Missed In A Row` | `Games Missed In A Row` | — | Not parsed by any page — Availability streak; not parsed |
| `Games Won` | `Games Won` | — | Not parsed by any page — Results aggregate; not parsed |
| `Goals From Outside The Box` | `Goals From Outside The Box` | — | Not parsed by any page — Shooting detail; not scored |
| `Headers Attempted` | `Headers Attempted` | — | Not parsed by any page — Header total; per-90 / % variants scored |
| `Headers Lost per 90` | `Headers Lost per 90` | — | Not parsed by any page — Not in stats benchmarks |
| `Key Headers per 90` | `Key Headers per 90` | — | Not parsed by any page — Not in stats benchmarks |
| `Key Tackles` | `Key Tackles` | — | Not parsed by any page — Tackle detail; not scored |
| `Key Tackles per 90` | `Key Tackles per 90` | — | Not parsed by any page — Not in stats benchmarks |
| `Last 5 Games Club` | `Last 5 Games Club` | — | Not parsed by any page — Club form; Last 5 Games International is parsed |
| `Last Match Rating` | `Last Match Rating` | — | Not parsed by any page — Single-match rating; not parsed |
| `Mins/Gl` | `Mins/Gl` | — | Not parsed by any page — Minutes per goal; not parsed |
| `Mins/Gm` | `Mins/Gm` | — | Not parsed by any page — Minutes per game; not parsed |
| `Minutes Since Last Conceded` | `Minutes Since Last Conceded` | — | Not parsed by any page — GK streak; not parsed |
| `Minutes Since Last Goal` | `Minutes Since Last Goal` | — | Not parsed by any page — Scoring streak; not parsed |
| `Mistakes Leading to Goals` | `Mistakes Leading to Goals` | — | Not parsed by any page — GK error count; not scored |
| `NP-xG` | `NP-xG` | — | Not parsed by any page — Non-penalty xG total; xG/90 scored |
| `NP-xG/90` | `NP-xG/90` | — | Not parsed by any page — Not in stats benchmarks (xG/90 used) |
| `Off` | `Off` | — | Not parsed by any page — Unclear FM column; not parsed |
| `Open Play Cross Completion Percentage` | `Open Play Cross Completion Percentage` | — | Not parsed by any page — Cross %; not scored |
| `Open Play Crosses Attempted` | `Open Play Crosses Attempted` | — | Not parsed by any page — Cross totals; OP crosses completed /90 scored |
| `Open Play Crosses Attempted per 90` | `Open Play Crosses Attempted per 90` | — | Not parsed by any page — Not in stats benchmarks |
| `Open Play Crosses Completed` | `Open Play Crosses Completed` | — | Not parsed by any page — Cross total; per-90 variant scored |
| `Open Play Key Passes per 90` | `Open Play Key Passes per 90` | — | Not parsed by any page — Not in stats benchmarks |
| `Passes Completed` | `Passes Completed` | — | Not parsed by any page — Pass total; passes attempted /90 scored |
| `Passes Completed per 90` | `Passes Completed per 90` | — | Not parsed by any page — Not in stats benchmarks |
| `Penalties Faced` | `Penalties Faced` | — | Not parsed by any page — Penalty detail; not parsed |
| `Penalties Saved` | `Penalties Saved` | — | Not parsed by any page — Penalty detail; not parsed |
| `Penalties Saved Ratio` | `Penalties Saved Ratio` | — | Not parsed by any page — Penalty detail; not parsed |
| `Penalties Scored` | `Penalties Scored` | — | Not parsed by any page — Penalty detail; not parsed |
| `Penalties Scored Ratio` | `Penalties Scored Ratio` | — | Not parsed by any page — Penalty detail; not parsed |
| `Penalties Taken` | `Penalties Taken` | — | Not parsed by any page — Penalty detail; not parsed |
| `Player of the Match` | `Player of the Match` | — | Not parsed by any page — Awards; not parsed |
| `Pres A` | `Pres A` | — | Not parsed by any page — Pressures attempted total; Pres C/90 scored |
| `Pres A/90` | `Pres A/90` | — | Not parsed by any page — Not in stats benchmarks |
| `Pres C` | `Pres C` | — | Not parsed by any page — Pressures completed total; Pres C/90 scored |
| `PsP` | `PsP` | — | Not parsed by any page — Progressive passes total; per-90 variant scored |
| `Pts/Gm` | `Pts/Gm` | — | Not parsed by any page — League points per game; not parsed |
| `Rating` | `Rating` | — | Not parsed by any page — Average rating alias; Average Rating Club not parsed either |
| `Save Percentage` | `Save Percentage` | — | Not parsed by any page — GK save %; not scored |
| `Saves Held` | `Saves Held` | — | Not parsed by any page — GK save type; not parsed |
| `Saves Parried` | `Saves Parried` | — | Not parsed by any page — GK save type; not parsed |
| `Saves Tipped` | `Saves Tipped` | — | Not parsed by any page — GK save type; not parsed |
| `Saves per 90` | `Saves per 90` | — | Not parsed by any page — GK saves rate; not in benchmarks |
| `Shots From Outside The Box Per 90 minutes` | `Shots From Outside The Box Per 90 minutes` | — | Not parsed by any page — Shooting detail; not scored |
| `Shots on Target Percentage` | `Shots on Target Percentage` | — | Not parsed by any page — SOT %; SOT per-90 scored |
| `Shts Blckd` | `Shts Blckd` | — | Not parsed by any page — Block total; Blk/90 scored |
| `Shutouts` | `Shutouts` | — | Not parsed by any page — GK shutouts; not scored |
| `Starts` | `Starts` | — | Not parsed by any page — Lineup count; not parsed |
| `Tackled Completed` | `Tackled Completed` | — | Not parsed by any page — Tackle total (FM typo); per-90 from attempts scored |
| `Tackles Completed per 90` | `Tackles Completed per 90` | — | Not parsed by any page — Not in stats benchmarks |
| `Tall` | `Tall` | — | Not parsed by any page — Unknown FM flag; not parsed |
| `Tcon/90` | `Tcon/90` | — | Not parsed by any page — Team conceded per 90; not parsed |
| `Team Goals` | `Team Goals` | — | Not parsed by any page — Team context; not parsed |
| `Tgls/90` | `Tgls/90` | — | Not parsed by any page — Team goals per 90; not parsed |
| `xG-OP` | `xG-OP` | — | Not parsed by any page — Open-play xG delta; not scored |
| `xG/shot` | `xG/shot` | — | Not parsed by any page — Shot quality average; not scored |

## Aliases in code but not in combined snapshot

Extra CSV header aliases the parsers accept (older exports / custom views):

- `Avg Rating International`
- `Best Position`
- `CA`
- `Command of Area`
- `Conversion %`
- `Conversion Rate`
- `Div`
- `Form Int`
- `Hdrs W/90`
- `Injury`
- `Int Apps (Season)`
- `Int Assists`
- `International Appearances`
- `International Goals`
- `L`
- `LFoot`
- `Last 5 Games Int`
- `Name`
- `Nat`
- `Nationality`
- `OP Cr C/90`
- `OP Crosses Completed per 90`
- `Off the Ball`
- `One on Ones`
- `PA`
- `Pass Completion %`
- `Pass Completion Ratio`
- `Position / Role`
- `Pressures Completed`
- `Pressures Completed per 90`
- `Ps C %`
- `R`
- `RFoot`
- `Rec`
- `Rec.`
- `Red Cards`
- `Rushing Out`
- `SOT/90`
- `Sec Position`
- `Second Nation`
- … and 14 more

## Maintenance

1. Run `python scripts/audit_column_usage.py` after changing parsers or stats config.
2. Review **Needs product decision** for new snapshot columns.
3. For columns that should stay ignored, add them to `INTENTIONALLY_UNUSED` in
   `scripts/audit_column_usage.py`. For columns to support, wire the parser first.
