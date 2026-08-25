"""Formulas reference — how each FMScouter page calculates its numbers."""
from __future__ import annotations

from dash import ALL, Input, Output, clientside_callback, html, register_page
import dash_bootstrap_components as dbc

from components.pack_picker import section_card_header
import config.fm26_role_weight_config as pc
from scoring.role_scorer import COMBO_IP_WEIGHT, COMBO_OOP_WEIGHT

register_page(__name__, path="/formulas", name="Formulas")

_DEFAULT_KEY = pc.KEY_WEIGHT
_DEFAULT_PREF = pc.PREFERRED_WEIGHT
_DEFAULT_USEFUL = pc.USEFUL_WEIGHT

_TOC = (
    ("role-scores", "Role scores"),
    ("player-stats", "Player stats"),
    ("squad-finance", "Squad finance"),
    ("role-config", "Role configs"),
    ("formations", "Formations"),
    ("settings", "Settings"),
)


def _formula(text: str) -> html.Pre:
    return html.Pre(text.strip(), className="fx-formula")


def _para(*parts: str) -> html.P:
    return html.P(list(parts), className="fx-note")


def _bullets(items: list[str]) -> html.Ul:
    return html.Ul([html.Li(item) for item in items], className="fx-list")


def _section(
    section_id: str,
    title: str,
    *,
    children: list,
) -> html.Div:
    return html.Div(
        [
            html.H2(title, className="fx-section-title"),
            *children,
        ],
        id=section_id,
        className="fx-section",
    )


def _subsection(title: str, *children) -> html.Div:
    return html.Div(
        [
            html.H3(title, className="fx-subhead"),
            *children,
        ],
        className="fx-subsection",
    )


def _toc_link(section_id: str, label: str) -> html.Li:
    # Buttons + clientside scroll: Dash NavLink / dcc.Link treat #hash as routes.
    return html.Li(
        html.Button(
            label,
            id={"type": "fx-toc", "section": section_id},
            n_clicks=0,
            type="button",
            className="fx-toc-link",
        )
    )


layout = dbc.Container(
    [
        html.Div(id="fx-toc-scroll", style={"display": "none"}),
        html.Div(
            [
                html.H1("Formulas", className="fx-page-title"),
                html.P(
                    "Reference for how FMScouter turns Moneyball exports into "
                    "scores, bands, and financial projections. Defaults shown; "
                    "Role configs and Settings can change weights and cutoffs.",
                    className="fx-lead",
                ),
                html.Nav(
                    html.Ul(
                        [_toc_link(sid, label) for sid, label in _TOC],
                        className="fx-toc",
                    ),
                    className="fx-toc-wrap",
                ),
            ],
            className="fx-hero",
        ),
        dbc.Card(
            [
                section_card_header("By page"),
                dbc.CardBody(
                    [
                        _section(
                            "role-scores",
                            "Role scores",
                            children=[
                                _subsection(
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
                                _subsection(
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
                                _subsection(
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
                                _subsection(
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
                                _subsection(
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
                            ],
                        ),
                        _section(
                            "player-stats",
                            "Player stats",
                            children=[
                                _subsection(
                                    "Percentile estimate",
                                    _formula(
                                        """
For each metric, MustermannFM benchmark tables supply four thresholds (20th / 40th / 60th / 80th).

higher_is_better:
  value ≤ t20  → interpolate toward 0 from t20
  t20 < value ≤ t80 → linear steps 20 → 40 → 60 → 80
  value > t80  → interpolate toward 100 at p100
                 (default: t80 + |t80|; for xGP/90: max of that and the
                  dataset max so keepers above the settings cut still spread)

lower_is_better:
  mirror the above (quality improves as values fall)
                                        """
                                    ),
                                    _para(
                                        "Cell background color runs red → yellow → green by percentile. ",
                                        "Metrics need playing minutes > 0; otherwise the cell stays blank.",
                                    ),
                                ),
                                _subsection(
                                    "Category average",
                                    _formula(
                                        """
category_avg = mean(percentiles of scorable metrics in that category)
                                        """
                                    ),
                                ),
                                _subsection(
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
                                _subsection(
                                    "Minutes filter",
                                    _formula(
                                        """
meet  if minutes ≥ required
half  if minutes ≥ required ÷ 2
fail  otherwise
                                        """
                                    ),
                                ),
                            ],
                        ),
                        _section(
                            "squad-finance",
                            "Squad finance",
                            children=[
                                _subsection(
                                    "Period wages",
                                    _formula(
                                        """
wage_period = annual_salary × (games ÷ season_games)

season_games defaults to 38; games is the modeled match count.
                                        """
                                    ),
                                ),
                                _subsection(
                                    "Matchday line costs",
                                    _formula(
                                        """
starters + subs:  wage_period + appearance_fee × games
reserves:         wage_period only (no appearance fees)

statement_total = Σ squad wages (period) + Σ matchday appearance fees
                                        """
                                    ),
                                    _para(
                                        "Starters and subs are assumed to play every modeled game.",
                                    ),
                                ),
                                _subsection(
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
                                _subsection(
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
                                _subsection(
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
                            ],
                        ),
                        _section(
                            "role-config",
                            "Role configs",
                            children=[
                                _subsection(
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
                                _subsection(
                                    "Position groups",
                                    _para(
                                        "Each role belongs to one or more groups (GK, CB, FB, …). ",
                                        "Eligibility on Role scores is OR across those groups.",
                                    ),
                                ),
                            ],
                        ),
                        _section(
                            "formations",
                            "Formations",
                            children=[
                                _subsection(
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
                            ],
                        ),
                        _section(
                            "settings",
                            "Settings",
                            children=[
                                _subsection(
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
                                _subsection(
                                    "Set-piece profiles",
                                    _para(
                                        "Each set-piece type lists key / preferred / useful attributes. ",
                                        "Formulas on Settings preview the same weighted average as Role scores.",
                                    ),
                                ),
                                _subsection(
                                    "Player stats threshold packs",
                                    _para(
                                        "Override Mustermann 20/40/60/80 benchmark values per ",
                                        "position group and metric. Percentile interpolation uses ",
                                        "the active pack’s thresholds.",
                                    ),
                                ),
                                _subsection(
                                    "Hybrid IP:OOP weight",
                                    _formula(
                                        f"""
default IP weight = {COMBO_IP_WEIGHT:g}
default OOP weight = {COMBO_OOP_WEIGHT:g}
                                        """
                                    ),
                                    _para("Adjustable under Role scores options in Settings."),
                                ),
                            ],
                        ),
                    ],
                    className="fx-body",
                ),
            ],
            className="mb-4 rs-section-card fx-card",
        ),
    ],
    fluid=True,
    className="fx-page",
)


clientside_callback(
    """
    function(n_clicks) {
        const triggered = window.dash_clientside.callback_context.triggered;
        if (!triggered || !triggered.length) {
            return window.dash_clientside.no_update;
        }
        const value = triggered[0].value;
        if (!value) {
            return window.dash_clientside.no_update;
        }
        const id = window.dash_clientside.callback_context.triggered_id;
        const section = id && id.section;
        if (!section) {
            return window.dash_clientside.no_update;
        }
        const el = document.getElementById(section);
        if (el) {
            el.scrollIntoView({ behavior: "smooth", block: "start" });
        }
        return "";
    }
    """,
    Output("fx-toc-scroll", "children"),
    Input({"type": "fx-toc", "section": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
