import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, State, dcc, html

import ui_settings

app = dash.Dash(
    __name__,
    use_pages=True,
    suppress_callback_exceptions=True,
    external_stylesheets=[
        dbc.themes.BOOTSTRAP,
        "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap",
    ],
)

app.layout = html.Div(
    [
        dcc.Store(id="theme", data="dark", storage_type="local"),
        dcc.Store(id="ui-settings", data=ui_settings.load()),
        html.Div(id="ui-settings-css"),
        dbc.Navbar(
            dbc.Container(
                [
                    dbc.NavbarBrand("FMScouter", href="/"),
                    dbc.Nav(
                        [
                            dbc.NavItem(dbc.NavLink("Role scores", href="/")),
                            dbc.NavItem(dbc.NavLink("Role configs", href="/role-config")),
                            dbc.NavItem(dbc.NavLink("Settings", href="/settings")),
                            dbc.NavItem(
                                html.Button(
                                    "Light mode",
                                    id="theme-toggle",
                                    n_clicks=0,
                                    className="theme-toggle",
                                    title="Switch color theme",
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
    id="app-shell",
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


@app.callback(
    Output("theme", "data"),
    Input("theme-toggle", "n_clicks"),
    State("theme", "data"),
    prevent_initial_call=True,
)
def toggle_theme(_clicks, current):
    return "light" if (current or "dark") == "dark" else "dark"


if __name__ == "__main__":
    app.run_server(debug=True)
