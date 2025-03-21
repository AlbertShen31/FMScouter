import dash
import dash_bootstrap_components as dbc
from dash import html

# Initialize the Dash app with Bootstrap
app = dash.Dash(__name__, use_pages=True, external_stylesheets=[dbc.themes.BOOTSTRAP])

# Define the layout with a Bootstrap Navbar
app.layout = html.Div([
    dbc.NavbarSimple(
        children=[
            dbc.NavItem(dbc.NavLink("Squad", href="/squad", style={'fontSize': '18px', 'padding': '10px'})),
            dbc.NavItem(dbc.NavLink("Formation", href="/formation", style={'fontSize': '18px', 'padding': '10px'})),
            dbc.NavItem(dbc.NavLink("Player Selection", href="/player_selection", style={'fontSize': '18px', 'padding': '10px'})),
        ],
        brand="FMScouter",
        brand_href="/player_selection",
        color="primary",
        dark=True,
        style={'marginBottom': '20px'}
    ),
    
    # Page content will be rendered here
    dash.page_container
])

if __name__ == '__main__':
    app.run_server(debug=True)