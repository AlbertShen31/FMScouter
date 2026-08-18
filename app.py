import dash
import dash_bootstrap_components as dbc
from dash import html

app = dash.Dash(
    __name__,
    use_pages=True,
    suppress_callback_exceptions=True,
    external_stylesheets=[
        dbc.themes.BOOTSTRAP,
        "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap",
    ],
)

app.layout = html.Div([
    dbc.NavbarSimple(
        children=[
            dbc.NavItem(dbc.NavLink("Role scores", href="/", style={'fontSize': '18px', 'padding': '10px'})),
            dbc.NavItem(dbc.NavLink("Role configs", href="/role-config", style={'fontSize': '18px', 'padding': '10px'})),
        ],
        brand="FMScouter",
        brand_href="/",
        color="primary",
        dark=True,
        style={'marginBottom': '20px'}
    ),
    dash.page_container
])

if __name__ == '__main__':
    app.run_server(debug=True)
