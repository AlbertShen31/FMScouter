import dash
import dash_bootstrap_components as dbc
import dash_mantine_components as dmc
from dash import Input, Output, State, callback, dcc, html

import ui_settings

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
        dcc.Store(id="theme", data="dark", storage_type="local"),
        dcc.Store(id="ui-settings", data=ui_settings.load()),
        dcc.Store(id="rs-parsed", storage_type="session"),
        dcc.Store(id="rs-persist", data={}, storage_type="session"),
        html.Div(id="ui-settings-css"),
        dbc.Navbar(
            dbc.Container(
                [
                    dbc.NavbarBrand("FMScouter", href="/"),
                    dbc.Nav(
                        [
                            dbc.NavItem(dbc.NavLink("Role scores", href="/")),
                            dbc.NavItem(dbc.NavLink("Role configs", href="/role-config")),
                            dbc.NavItem(dbc.NavLink("Formations", href="/formations")),
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
        const root = document.documentElement;
        ["elite", "good", "ok", "poor"].forEach(function(band) {
            const c = colors[band] || {};
            if (c.bg) root.style.setProperty("--band-" + band + "-bg", c.bg);
            if (c.fg) root.style.setProperty("--band-" + band + "-fg", c.fg);
            if (c.bar) root.style.setProperty("--band-" + band + "-bar", c.bar);
        });
        return "";
    }
    """,
    Output("ui-settings-css", "className"),
    Input("ui-settings", "data"),
)


@callback(
    Output("theme", "data"),
    Input("theme-toggle", "n_clicks"),
    State("theme", "data"),
    prevent_initial_call=True,
)
def toggle_theme(_clicks, current):
    return "light" if (current or "dark") == "dark" else "dark"


@callback(
    Output("mantine-provider", "forceColorScheme"),
    Input("theme", "data"),
)
def sync_mantine_theme(theme):
    return "light" if theme == "light" else "dark"


if __name__ == "__main__":
    app.run_server(debug=True)
