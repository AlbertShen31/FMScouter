"""Documentation & FAQ — how FMScouter works and how numbers are calculated."""
from __future__ import annotations

from dash import ALL, Input, Output, callback, dcc, html, register_page
import dash_bootstrap_components as dbc

import config.fm26_role_weight_config as pc
from scoring.role_scorer import COMBO_IP_WEIGHT, COMBO_OOP_WEIGHT

register_page(__name__, path="/formulas", name="Docs")

_DEFAULT_KEY = pc.KEY_WEIGHT
_DEFAULT_PREF = pc.PREFERRED_WEIGHT
_DEFAULT_USEFUL = pc.USEFUL_WEIGHT

_SECTION_IDS = (
    "overview",
    "faq",
    "role-scores",
    "player-stats",
    "squad-finance",
    "role-config",
    "formations",
    "settings",
)

_NAV_GROUPS = (
    (
        "Guide",
        (
            ("overview", "Overview"),
            ("faq", "FAQ"),
        ),
    ),
    (
        "Formulas",
        (
            ("role-scores", "Role scores"),
            ("player-stats", "Player stats"),
            ("squad-finance", "Squad finance"),
            ("role-config", "Role configs"),
            ("formations", "Formations"),
            ("settings", "Settings"),
        ),
    ),
)


def _formula(text: str) -> html.Pre:
    return html.Pre(text.strip(), className="fx-formula")


def _para(*parts: str) -> html.P:
    return html.P(list(parts), className="fx-note")


def _bullets(items: list[str]) -> html.Ul:
    return html.Ul([html.Li(item) for item in items], className="fx-list")


def _accordion(title: str, *children) -> html.Details:
    return html.Details(
        [
            html.Summary(title, className="fx-accordion-summary"),
            html.Div(list(children), className="fx-accordion-body"),
        ],
        className="fx-accordion-item",
    )


def _faq_item(question: str, *children) -> html.Details:
    return html.Details(
        [
            html.Summary(question, className="fx-faq-summary"),
            html.Div(list(children), className="fx-faq-body"),
        ],
        className="fx-faq-item",
    )


def _nav_link(section_id: str, label: str) -> html.Li:
    return html.Li(
        html.Button(
            label,
            id={"type": "fx-nav", "section": section_id},
            n_clicks=0,
            type="button",
            className="fx-nav-link",
        )
    )


def _panel(section_id: str, title: str, *children) -> html.Div:
    return html.Div(
        [
            html.H2(title, className="fx-panel-title"),
            *children,
        ],
        id=f"fx-panel-{section_id}",
        className="fx-panel" + (" is-active" if section_id == "overview" else ""),
    )


def _overview_panel() -> html.Div:
    return _panel(
        "overview",
        "Overview",
        _para(
            "FMScouter scores Football Manager exports in your browser. Save CSVs on ",
            "Uploads, then open Role scores, Player stats, or Squad finance. ",
            "Profiles builds depth charts from saved role-score exports.",
        ),
        html.H3("Typical workflow", className="fx-subhead"),
        _bullets(
            [
                "Upload attribute, Moneyball stats, and/or salary CSVs on Uploads.",
                "Role scores — pick roles or load a formation, score, shortlist, save to a profile library.",
                "Player stats — percentile tables vs Mustermann benchmarks; compare two exports historically.",
                "Squad finance — model wages, clauses, and club sustainability.",
                "Profiles — depth chart, starting XI, and set-piece takers from saved exports.",
            ]
        ),
        html.H3("Where things live", className="fx-subhead"),
        _bullets(
            [
                "Role configs — edit attribute tiers per role; saved packs overlay factory weights.",
                "Formations — hybrid IP/OOP slot lineups for Role scores.",
                "Settings — score bands, tier weights, set-piece profiles, stats threshold packs, theme.",
            ]
        ),
        _para(
            "Use the sidebar to jump between FAQ answers and per-page formula references. ",
            "Defaults are shown in formulas; active packs on Role configs and Settings may differ.",
        ),
    )


def _faq_panel() -> html.Div:
    return _panel(
        "faq",
        "FAQ",
        _faq_item(
            "Which CSV exports do I need?",
            _para(
                "Role scores needs an attribute export (player names and FM attributes). ",
                "Player stats needs a Moneyball / analytics export with per-90 metrics. ",
                "Squad finance needs a salary export with wages, fees, and contract clauses. ",
                "Each page can use a file from Uploads without re-uploading every session.",
            ),
        ),
        _faq_item(
            "Why is a role score blank?",
            _para(
                "A player only gets a numeric score when their Position matches at least one ",
                "of the role’s position groups (GK, CB, FB, …). Ineligible players show a blank cell.",
            ),
            _para(
                "Missing or “-” attributes count as 0. Range values like 12–14 use the lower number.",
            ),
        ),
        _faq_item(
            "What are IP, OOP, and hybrid roles?",
            _para(
                "In-possession (IP) and out-of-possession (OOP) roles reflect different phases of play. ",
                "Hybrid columns combine one IP role and one OOP role into a single weighted score. ",
                "Formations assign IP/OOP pairs per slot; loading a formation adds those hybrids to Role scores.",
            ),
        ),
        _faq_item(
            'What does "Not tracked" or a striped Division pill mean?',
            _para(
                "Some leagues export advanced stats as 0 instead of leaving them blank. ",
                "FMScouter detects leagues where probe metrics (interceptions, key passes, ",
                "progressive passes, clearances) are all near zero despite real minutes, and marks ",
                "those divisions with striped pills.",
            ),
            _para(
                "Individual players with ≥90 minutes and all probes at zero show “Not tracked” on ",
                "affected metrics. Those metrics are excluded from category and overall averages.",
            ),
            _para(
                "Universal metrics like xA and possession won still appear in limited leagues.",
            ),
        ),
        _faq_item(
            "How do profile libraries work?",
            _para(
                "Each library stores saved role-score exports for one formation. ",
                "Create a library with a display name and formation, then save shortlists from Role scores. ",
                "Profiles shows depth chart (First XI = rank #1 per slot), starting XI, and set-piece charts.",
            ),
            _para(
                "The same player in multiple active XI slots is flagged in red. ",
                "Auto-rank sorts remaining players on a slot by role score, then OVR.",
            ),
        ),
        _faq_item(
            "How does historical compare work?",
            _para(
                "When a historical export is loaded alongside the current one, Player stats and ",
                "Role scores show deltas between the two files. Players are matched primarily by name ",
                "(clubs can change mid-season). Comparison is on whenever a historical file is present.",
            ),
        ),
        _faq_item(
            "Why did my scores change after an update?",
            _para(
                "Re-upload or use Compute All on Uploads after formula or availability rule changes. ",
                "Role configs and Settings packs change weights and cutoffs immediately for new scoring runs.",
            ),
        ),
    )


def _role_scores_panel() -> html.Div:
    return _panel(
        "role-scores",
        "Role scores",
        _accordion(
            "Role score",
            _formula(
                f"""
score = ({_DEFAULT_KEY:g}×Σkey + {_DEFAULT_PREF:g}×Σpreferred + {_DEFAULT_USEFUL:g}×Σuseful) ÷ divisor

divisor = {_DEFAULT_KEY:g}×n_key + {_DEFAULT_PREF:g}×n_preferred + {_DEFAULT_USEFUL:g}×n_useful
                """
            ),
            _para(
                "Each FM26 role lists attributes in three tiers. ",
                "Missing or “-” attributes count as 0. ",
                "Range values like 12-14 use the lower number. ",
                "A player with 20 in every listed attribute scores 20.",
            ),
            _bullets(
                [
                    "Eligibility: player Position must match at least one of the role’s position groups.",
                    "Only eligible players get a numeric score; others are blank.",
                ]
            ),
        ),
        _accordion(
            "Hybrid (IP + OOP) score",
            _formula(
                f"""
hybrid = ({COMBO_IP_WEIGHT:g}×IP_score + {COMBO_OOP_WEIGHT:g}×OOP_score) ÷ {COMBO_IP_WEIGHT + COMBO_OOP_WEIGHT:g}
                """
            ),
            _para(
                "Hybrid columns combine one in-possession role and one ",
                "out-of-possession role. Eligible if either constituent is eligible.",
            ),
        ),
        _accordion(
            "Set-piece scores",
            _formula(
                f"""
set_piece = ({_DEFAULT_KEY:g}×Σkey + {_DEFAULT_PREF:g}×Σpreferred + {_DEFAULT_USEFUL:g}×Σuseful) ÷ divisor_sp
                """
            ),
            _para(
                "Same tier weights as roles (Corners, DFK, IFK, Throws, Pens, Aerial). ",
                "Each type uses its own attribute list and divisor. ",
                "DFK = direct free kick; IFK = indirect / delivery.",
            ),
        ),
        _accordion(
            "Score bands (table colors)",
            _formula(
                """
elite  if score ≥ elite cutoff   (default 14)
good   if score ≥ good cutoff    (default 12)
ok     if score ≥ ok cutoff      (default 10)
poor   otherwise
                """
            ),
            _para("Cutoffs are editable on the Settings page."),
        ),
        _accordion(
            "Squad depth average",
            _formula(
                """
depth_avg = mean(selected role scores for that position group)
                """
            ),
            _para(
                "Uses the same band colors as individual scores. ",
                "Focused roles limit which columns feed the average.",
            ),
        ),
    )


def _player_stats_panel() -> html.Div:
    return _panel(
        "player-stats",
        "Player stats",
        _accordion(
            "Percentile estimate",
            _formula(
                """
For each metric, MustermannFM benchmark tables supply four thresholds (20th / 40th / 60th / 80th).

higher_is_better:
  value ≤ t20  → interpolate toward 0 at p0
  t20 < value ≤ t80 → linear steps 20 → 40 → 60 → 80
  value > t80  → interpolate toward 100 at p100

lower_is_better:
  mirror the above (quality improves as values fall)
                """
            ),
            _para(
                "Cell background color runs red → yellow → green by percentile. ",
                "Metrics need playing minutes > 0; otherwise the cell stays blank.",
            ),
        ),
        _accordion(
            "Category average",
            _formula(
                """
category_avg = mean(percentiles of scorable metrics in that category)
                """
            ),
        ),
        _accordion(
            "Overall average",
            _formula(
                """
overall_avg = mean(category averages with data)
                """
            ),
            _para(
                "Position group picks the benchmark set (GK / DEF / MID / FWD). ",
                "Division tier can filter which players appear.",
            ),
        ),
        _accordion(
            "League stat availability",
            _para(
                "Some FM leagues do not collect advanced match stats in Moneyball "
                "exports. Those columns are written as 0 rather than left blank. "
                "FMScouter detects this pattern and marks affected metrics as Not tracked."
            ),
            _para(
                "Unavailable metrics are excluded from category and overall averages.",
            ),
        ),
        _accordion(
            "Minutes filter",
            _formula(
                """
meet  if minutes ≥ required
half  if minutes ≥ required ÷ 2
fail  otherwise
                """
            ),
        ),
    )


def _squad_finance_panel() -> html.Div:
    return _panel(
        "squad-finance",
        "Squad finance",
        _accordion(
            "Period wages",
            _formula(
                """
wage_period = annual_salary × (games ÷ season_games)

season_games defaults to 38; games is the modeled match count.
                """
            ),
        ),
        _accordion(
            "Matchday line costs",
            _formula(
                """
starters + subs:  wage_period + appearance_fee × games
reserves:         wage_period only (no appearance fees)

statement_total = Σ squad wages (period) + Σ matchday appearance fees
                """
            ),
            _para("Starters and subs are assumed to play every modeled game."),
        ),
        _accordion(
            "Contract clause → dollars",
            _formula(
                """
If clause is a percentage (e.g. 25%):
  amount = annual_salary × (pct ÷ 100)

If clause is cash (e.g. $250K):
  amount = parsed money value
                """
            ),
        ),
        _accordion(
            "End-of-season wage (Yn columns)",
            _formula(
                """
base = salary ± division_change   (promotion + / relegation −)

If yearly raise is percentage r:
  wage_end(Yn) = base × (1 + r)^n

If yearly raise is flat amount A:
  wage_end(Yn) = base + n×A

Yearly raises always apply. Y1 is already end-of-year 1.
                """
            ),
        ),
        _accordion(
            "Club sustainability",
            _formula(
                """
opening_net = balance − debt

annual_squad = full-season squad bill (wages + fees, scaled from period)

annual_expenses = club P&L expenses + annual_squad + debt_payments
annual_net      = annual_income − annual_expenses

Each projected year:
  cash += annual_net
  debt  = max(0, debt − debt_payments)

surplus = opening_net + Σ annual_net over selected years (1 or 5)

Sustainable if surplus ≥ 0
                """
            ),
            _para(
                "Squad wages in the projection use per-player end-of-season ",
                "salaries summed across the squad.",
            ),
        ),
    )


def _role_config_panel() -> html.Div:
    return _panel(
        "role-config",
        "Role configs",
        _accordion(
            "Per-role divisor",
            _formula(
                f"""
divisor = {_DEFAULT_KEY:g}×|key_attrs| + {_DEFAULT_PREF:g}×|preferred_attrs| + {_DEFAULT_USEFUL:g}×|useful_attrs|
                """
            ),
            _para(
                "Editing tiers on this page changes which attributes enter ",
                "each sum and the divisor. Saved packs overlay the factory ",
                "Python weights used when scoring on Role scores.",
            ),
        ),
        _accordion(
            "Position groups",
            _para(
                "Each role belongs to one or more groups (GK, CB, FB, …). ",
                "Eligibility on Role scores is OR across those groups.",
            ),
        ),
    )


def _formations_panel() -> html.Div:
    return _panel(
        "formations",
        "Formations",
        _accordion(
            "Hybrid slots",
            _formula(
                f"""
Each filled slot → one hybrid role (IP + OOP pair)

hybrid_score = ({COMBO_IP_WEIGHT:g}×IP + {COMBO_OOP_WEIGHT:g}×OOP) ÷ {COMBO_IP_WEIGHT + COMBO_OOP_WEIGHT:g}
                """
            ),
            _para(
                "Up to 11 slots. Each slot has an IP position, optional OOP ",
                "position (defaults to IP), and chosen IP/OOP roles. ",
                "Loading a formation on Role scores adds those hybrids ",
                "and their constituent roles to the scored set.",
            ),
        ),
    )


def _settings_panel() -> html.Div:
    return _panel(
        "settings",
        "Settings",
        _accordion(
            "Role score bands",
            _formula(
                """
elite / good / ok thresholds (defaults 14 / 12 / 10)

tier weights: key / preferred / useful (defaults 5 / 3 / 1)
                """
            ),
            _para(
                "Bands color Role scores tables and depth cards. ",
                "Tier weights affect role scores and set-piece formulas.",
            ),
        ),
        _accordion(
            "Set-piece profiles",
            _para(
                "Each set-piece type lists key / preferred / useful attributes. ",
                "Formulas on Settings preview the same weighted average as Role scores.",
            ),
        ),
        _accordion(
            "Player stats threshold packs",
            _para(
                "Override Mustermann 20/40/60/80 benchmark values per ",
                "position group and metric. Percentile interpolation uses ",
                "the active pack’s thresholds.",
            ),
        ),
        _accordion(
            "Hybrid IP:OOP weight",
            _formula(
                f"""
default IP weight = {COMBO_IP_WEIGHT:g}
default OOP weight = {COMBO_OOP_WEIGHT:g}
                """
            ),
            _para("Adjustable under Role scores options in Settings."),
        ),
    )


_PANEL_BUILDERS = {
    "overview": _overview_panel,
    "faq": _faq_panel,
    "role-scores": _role_scores_panel,
    "player-stats": _player_stats_panel,
    "squad-finance": _squad_finance_panel,
    "role-config": _role_config_panel,
    "formations": _formations_panel,
    "settings": _settings_panel,
}


layout = dbc.Container(
    [
        dcc.Store(id="fx-active-section", data="overview"),
        html.Div(
            [
                html.Header(
                    [
                        html.H1("Documentation", className="fx-page-title"),
                        html.P(
                            "How FMScouter works, common questions, and formula references.",
                            className="fx-lead",
                        ),
                    ],
                    className="fx-hero",
                ),
                html.Div(
                    [
                        html.Aside(
                            [
                                html.Nav(
                                    [
                                        html.Div(
                                            [
                                                html.Div(
                                                    group_label,
                                                    className="fx-nav-group-label",
                                                ),
                                                html.Ul(
                                                    [
                                                        _nav_link(sid, label)
                                                        for sid, label in links
                                                    ],
                                                    className="fx-nav-list",
                                                ),
                                            ],
                                            className="fx-nav-group",
                                        )
                                        for group_label, links in _NAV_GROUPS
                                    ],
                                    className="fx-sidebar-nav",
                                ),
                            ],
                            className="fx-sidebar",
                        ),
                        html.Div(
                            [_PANEL_BUILDERS[sid]() for sid in _SECTION_IDS],
                            className="fx-content",
                        ),
                    ],
                    className="fx-layout",
                ),
            ],
            className="fx-page-inner",
        ),
    ],
    fluid=True,
    className="fx-page",
)


@callback(
    Output("fx-active-section", "data"),
    Input({"type": "fx-nav", "section": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def _set_active_section(_clicks):
    from dash import ctx

    triggered = ctx.triggered_id
    if not triggered or not isinstance(triggered, dict):
        from dash import no_update

        return no_update
    return triggered["section"]


@callback(
    [Output(f"fx-panel-{sid}", "className") for sid in _SECTION_IDS]
    + [Output({"type": "fx-nav", "section": sid}, "className") for sid in _SECTION_IDS],
    Input("fx-active-section", "data"),
)
def _sync_section_visibility(active: str | None):
    active = active or "overview"
    panel_classes = [
        "fx-panel is-active" if sid == active else "fx-panel" for sid in _SECTION_IDS
    ]
    nav_classes = [
        "fx-nav-link is-active" if sid == active else "fx-nav-link"
        for sid in _SECTION_IDS
    ]
    return panel_classes + nav_classes
