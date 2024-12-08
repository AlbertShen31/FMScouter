import dash
import dash_bootstrap_components as dbc
from dash import html

# Initialize the Dash app with Bootstrap
app = dash.Dash(__name__, use_pages=True, external_stylesheets=[dbc.themes.BOOTSTRAP])

# Define the layout with a Bootstrap Navbar
app.layout = html.Div([
    dbc.NavbarSimple(
        children=[
            dbc.NavItem(dbc.NavLink("Squad", href="/squad")),
            dbc.NavItem(dbc.NavLink("Scouting", href="/scouting")),
        ],
        brand="FMScouter",
        brand_href="/",
        color="primary",
        dark=True,
        style={'marginBottom': '20px'}
    ),
    
    # Page content will be rendered here
    dash.page_container
])

if __name__ == '__main__':
    app.run_server(debug=True)