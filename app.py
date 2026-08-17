import dash
import dash_bootstrap_components as dbc
from dash import html

app = dash.Dash(
    __name__,
    use_pages=True,
    suppress_callback_exceptions=True,
    external_stylesheets=[dbc.themes.BOOTSTRAP],
)

app.layout = html.Div([
    dbc.NavbarSimple(
        children=[
            dbc.NavItem(dbc.NavLink("Role scores", href="/", style={'fontSize': '18px', 'padding': '10px'})),
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
