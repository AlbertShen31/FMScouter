import dash
import dash_bootstrap_components as dbc
import dash_mantine_components as dmc
from dash import ALL, Input, Output, State, callback, dcc, html

import services.ui_settings as ui_settings
import services.export_library as export_library
import services.player_profiles as player_profiles

export_library.ensure_dirs()
player_profiles.ensure_dirs()
# Mantine components require React 18 (useId); Dash 2.x defaults to React 16.
dash._dash_renderer._set_react_version("18.2.0")

# Cool slate palette aligned with --app-* CSS variables (avoids Mantine's warm gray dark mode).
APP_DARK = [
    "#e8eef6",
    "#d1dbe8",
    "#8b9bb0",
    "#6b7c90",
    "#4a6078",
    "#2a3a4c",
    "#223040",
    "#1a2430",
    "#141c26",
    "#0b1118",
]
APP_GRAY = [
    "#f4f7fb",
    "#e3eaf2",
    "#c5d0de",
    "#a3b1c2",
    "#8b9bb0",
    "#6b7c90",
    "#4a6078",
    "#2a3a4c",
    "#1a2430",
    "#0f1720",
]

MANTINE_THEME = {
    "fontFamily": "Inter, Segoe UI, sans-serif",
    "primaryColor": "teal",
    "defaultRadius": "md",
    "black": "#0b1118",
    "white": "#e8eef6",
    "primaryShade": {"light": 6, "dark": 5},
    "colors": {
        "dark": APP_DARK,
        "gray": APP_GRAY,
    },
}

app = dash.Dash(
    __name__,
    use_pages=True,
    suppress_callback_exceptions=True,
    external_stylesheets=[
        dbc.themes.BOOTSTRAP,
        "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap",
    ],
)

app.layout = dmc.MantineProvider(
    id="mantine-provider",
    forceColorScheme="dark",
    theme=MANTINE_THEME,
    children=[
        dcc.Store(
            id="theme",
            data=ui_settings.load().get("preferred_theme") or "dark",
        ),
        dcc.Store(id="ui-settings", data=ui_settings.load()),
        dcc.Store(id="rs-parsed", storage_type="session"),
        dcc.Store(id="rs-parsed-historical", storage_type="session"),
        dcc.Store(id="rs-persist", data={}, storage_type="session"),
        dcc.Store(id="st-parsed", storage_type="session"),
        dcc.Store(id="st-parsed-historical", storage_type="session"),
        dcc.Store(id="sf-parsed", storage_type="session"),
        dcc.Store(id="sf-parsed-historical", storage_type="session"),
        dcc.Store(
            id="sf-selection",
            data={"starters": [], "subs": []},
            storage_type="session",
        ),
        dcc.Store(
            id="sf-data-rev",
            data={"n": 0, "replaced": False},
            storage_type="session",
        ),
        dcc.Store(id="sf-club", data={}, storage_type="session"),
        dcc.Store(id="st-persist", data={}, storage_type="session"),
        html.Div(id="ui-settings-css"),
        dbc.Navbar(
            dbc.Container(
                [
                    dbc.NavbarBrand("FMScouter", href="/"),
                    dbc.Nav(
                        [
                            dbc.NavItem(dbc.NavLink("Uploads", href="/uploads")),
                            dbc.NavItem(dbc.NavLink("Role scores", href="/")),
                            dbc.NavItem(dbc.NavLink("Player stats", href="/stats")),
                            dbc.NavItem(dbc.NavLink("Profiles", href="/profiles")),
                            dbc.NavItem(dbc.NavLink("Squad finance", href="/squad-finance")),
                            dbc.NavItem(dbc.NavLink("Role configs", href="/role-config")),
                            dbc.NavItem(dbc.NavLink("Formations", href="/formations")),
                            dbc.NavItem(dbc.NavLink("Formulas", href="/formulas")),
                            dbc.NavItem(dbc.NavLink("Settings", href="/settings")),
                            dbc.NavItem(
                                dmc.Button(
                                    "Light mode",
                                    id="theme-toggle",
                                    n_clicks=0,
                                    variant="subtle",
                                    className="theme-toggle",
                                    buttonProps={"title": "Switch color theme"},
                                )
                            ),
                        ],
                        navbar=True,
                        className="ms-auto align-items-center gap-2",
                    ),
                ],
                fluid=True,
            ),
            className="app-navbar",
        ),
        dash.page_container,
    ],
)

app.clientside_callback(
    """
    function(theme) {
        const t = theme === "light" ? "light" : "dark";
        document.documentElement.setAttribute("data-theme", t);
        document.body.setAttribute("data-theme", t);
        return t === "dark" ? "Light mode" : "Dark mode";
    }
    """,
    Output("theme-toggle", "children"),
    Input("theme", "data"),
)

app.clientside_callback(
    """
    function(settings) {
        const colors = (settings && settings.colors) || {};
        const badges = (settings && settings.tier_badge_colors) || {};
        const pers = (settings && settings.personality_tier_colors) || {};
        const root = document.documentElement;
        ["elite", "good", "ok", "poor"].forEach(function(band) {
            const c = colors[band] || {};
            if (c.bg) root.style.setProperty("--band-" + band + "-bg", c.bg);
            if (c.fg) root.style.setProperty("--band-" + band + "-fg", c.fg);
            if (c.bar) root.style.setProperty("--band-" + band + "-bar", c.bar);
        });
        if (badges.key) root.style.setProperty("--rc-key", badges.key);
        if (badges.preferred) root.style.setProperty("--rc-green", badges.preferred);
        if (badges.useful) root.style.setProperty("--rc-blue", badges.useful);
        [
            "exemplary",
            "commendable",
            "acceptable",
            "unpredictable",
            "formative",
            "unsuitable"
        ].forEach(function(tier) {
            const c = pers[tier] || {};
            if (c.bg) root.style.setProperty("--pers-tier-" + tier + "-bg", c.bg);
            if (c.fg) root.style.setProperty("--pers-tier-" + tier + "-fg", c.fg);
        });
        return "";
    }
    """,
    Output("ui-settings-css", "className"),
    Input("ui-settings", "data"),
)


@callback(
    Output("theme", "data"),
    Output("ui-settings", "data", allow_duplicate=True),
    Output({"type": "st-preferred-theme", "index": ALL}, "value", allow_duplicate=True),
    Input("theme-toggle", "n_clicks"),
    State("theme", "data"),
    State({"type": "st-preferred-theme", "index": ALL}, "id"),
    prevent_initial_call=True,
)
def toggle_theme(_clicks, current, theme_ids):
    next_theme = "light" if (current or "dark") == "dark" else "dark"
    settings = ui_settings.set_preferred_theme(next_theme)
    return next_theme, settings, [next_theme] * len(theme_ids or [])


@callback(
    Output("mantine-provider", "forceColorScheme"),
    Input("theme", "data"),
)
def sync_mantine_theme(theme):
    return "light" if theme == "light" else "dark"


if __name__ == "__main__":
    app.run_server(debug=True)
