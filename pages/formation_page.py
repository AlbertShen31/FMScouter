import dash
from dash import dcc, html, callback, Input, Output, State, register_page

# Register the page with a specific path
register_page(__name__, path='/formation')

# Define the layout for the Formation page
layout = html.Div([
    html.H1("Soccer Formation", style={'textAlign': 'center', 'marginBottom': '20px', 'color': '#333'}),
    
    # Add a dropdown to select formation
    dcc.Dropdown(
        id='formation-selector',
        options=[
            {'label': '4-4-2', 'value': '4-4-2'},
            {'label': '4-3-3', 'value': '4-3-3'},
            {'label': '3-5-2', 'value': '3-5-2'}
        ],
        value='4-4-2',
        style={'width': '200px', 'margin': '0 auto', 'marginBottom': '20px'}
    ),
    
    # Player info display
    html.Div(id='player-info', style={'textAlign': 'center', 'marginBottom': '20px', 'fontSize': '18px'}),
    
    # Soccer field container
    html.Div(id='formation-container', style={
        'border': '2px solid green', 
        'width': '500px', 
        'margin': '0 auto', 
        'padding': '20px',
        'backgroundColor': 'lightgreen'
    })
])

# Callback to update formation
@callback(
    Output('formation-container', 'children'),
    Input('formation-selector', 'value')
)
def update_formation(formation):
    # Common player style
    player_style = {
        'width': '60px', 
        'height': '60px', 
        'border': '1px solid black', 
        'textAlign': 'center', 
        'lineHeight': '60px',
        'cursor': 'pointer',
        'transition': 'background-color 0.3s ease',
        'borderRadius': '50%'
    }
    
    # Define formations
    if formation == '4-4-2':
        players = [
            # Goalkeeper
            html.Div(id={'type': 'player', 'index': 1}, style={**player_style, 'margin': '20px auto', 'backgroundColor': 'green'}, children="GK"),
            
            # Defenders
            html.Div(style={
                'display': 'flex', 
                'justifyContent': 'space-between', 
                'width': '400px', 
                'margin': '20px auto'
            }, children=[
                html.Div(id={'type': 'player', 'index': 2}, style={**player_style, 'backgroundColor': 'blue'}, children="DF1"),
                html.Div(id={'type': 'player', 'index': 3}, style={**player_style, 'backgroundColor': 'blue'}, children="DF2"),
                html.Div(id={'type': 'player', 'index': 4}, style={**player_style, 'backgroundColor': 'blue'}, children="DF3"),
                html.Div(id={'type': 'player', 'index': 5}, style={**player_style, 'backgroundColor': 'blue'}, children="DF4"),
            ]),
            
            # Midfielders
            html.Div(style={
                'display': 'flex', 
                'justifyContent': 'space-between', 
                'width': '400px', 
                'margin': '20px auto'
            }, children=[
                html.Div(id={'type': 'player', 'index': 6}, style={**player_style, 'backgroundColor': 'yellow'}, children="MF1"),
                html.Div(id={'type': 'player', 'index': 7}, style={**player_style, 'backgroundColor': 'yellow'}, children="MF2"),
                html.Div(id={'type': 'player', 'index': 8}, style={**player_style, 'backgroundColor': 'yellow'}, children="MF3"),
                html.Div(id={'type': 'player', 'index': 9}, style={**player_style, 'backgroundColor': 'yellow'}, children="MF4"),
            ]),
            
            # Forwards
            html.Div(style={
                'display': 'flex', 
                'justifyContent': 'space-between', 
                'width': '200px', 
                'margin': '20px auto'
            }, children=[
                html.Div(id={'type': 'player', 'index': 10}, style={**player_style, 'backgroundColor': 'red'}, children="FW1"),
                html.Div(id={'type': 'player', 'index': 11}, style={**player_style, 'backgroundColor': 'red'}, children="FW2"),
            ])
        ]
    elif formation == '4-3-3':
        players = [
            # Goalkeeper
            html.Div(id={'type': 'player', 'index': 1}, style={**player_style, 'margin': '20px auto', 'backgroundColor': 'green'}, children="GK"),
            
            # Defenders
            html.Div(style={
                'display': 'flex', 
                'justifyContent': 'space-between', 
                'width': '400px', 
                'margin': '20px auto'
            }, children=[
                html.Div(id={'type': 'player', 'index': 2}, style={**player_style, 'backgroundColor': 'blue'}, children="DF1"),
                html.Div(id={'type': 'player', 'index': 3}, style={**player_style, 'backgroundColor': 'blue'}, children="DF2"),
                html.Div(id={'type': 'player', 'index': 4}, style={**player_style, 'backgroundColor': 'blue'}, children="DF3"),
                html.Div(id={'type': 'player', 'index': 5}, style={**player_style, 'backgroundColor': 'blue'}, children="DF4"),
            ]),
            
            # Midfielders
            html.Div(style={
                'display': 'flex', 
                'justifyContent': 'space-between', 
                'width': '400px', 
                'margin': '20px auto'
            }, children=[
                html.Div(id={'type': 'player', 'index': 6}, style={**player_style, 'backgroundColor': 'yellow'}, children="MF1"),
                html.Div(id={'type': 'player', 'index': 7}, style={**player_style, 'backgroundColor': 'yellow'}, children="MF2"),
                html.Div(id={'type': 'player', 'index': 8}, style={**player_style, 'backgroundColor': 'yellow'}, children="MF3"),
            ]),
            
            # Forwards
            html.Div(style={
                'display': 'flex', 
                'justifyContent': 'space-between', 
                'width': '300px', 
                'margin': '20px auto'
            }, children=[
                html.Div(id={'type': 'player', 'index': 9}, style={**player_style, 'backgroundColor': 'red'}, children="FW1"),
                html.Div(id={'type': 'player', 'index': 10}, style={**player_style, 'backgroundColor': 'red'}, children="FW2"),
                html.Div(id={'type': 'player', 'index': 11}, style={**player_style, 'backgroundColor': 'red'}, children="FW3"),
            ])
        ]
    else:  # 3-5-2
        players = [
            # Goalkeeper
            html.Div(id={'type': 'player', 'index': 1}, style={**player_style, 'margin': '20px auto', 'backgroundColor': 'green'}, children="GK"),
            
            # Defenders
            html.Div(style={
                'display': 'flex', 
                'justifyContent': 'space-between', 
                'width': '300px', 
                'margin': '20px auto'
            }, children=[
                html.Div(id={'type': 'player', 'index': 2}, style={**player_style, 'backgroundColor': 'blue'}, children="DF1"),
                html.Div(id={'type': 'player', 'index': 3}, style={**player_style, 'backgroundColor': 'blue'}, children="DF2"),
                html.Div(id={'type': 'player', 'index': 4}, style={**player_style, 'backgroundColor': 'blue'}, children="DF3"),
            ]),
            
            # Midfielders
            html.Div(style={
                'display': 'flex', 
                'justifyContent': 'space-between', 
                'width': '400px', 
                'margin': '20px auto'
            }, children=[
                html.Div(id={'type': 'player', 'index': 5}, style={**player_style, 'backgroundColor': 'yellow'}, children="MF1"),
                html.Div(id={'type': 'player', 'index': 6}, style={**player_style, 'backgroundColor': 'yellow'}, children="MF2"),
                html.Div(id={'type': 'player', 'index': 7}, style={**player_style, 'backgroundColor': 'yellow'}, children="MF3"),
                html.Div(id={'type': 'player', 'index': 8}, style={**player_style, 'backgroundColor': 'yellow'}, children="MF4"),
                html.Div(id={'type': 'player', 'index': 9}, style={**player_style, 'backgroundColor': 'yellow'}, children="MF5"),
            ]),
            
            # Forwards
            html.Div(style={
                'display': 'flex', 
                'justifyContent': 'space-between', 
                'width': '200px', 
                'margin': '20px auto'
            }, children=[
                html.Div(id={'type': 'player', 'index': 10}, style={**player_style, 'backgroundColor': 'red'}, children="FW1"),
                html.Div(id={'type': 'player', 'index': 11}, style={**player_style, 'backgroundColor': 'red'}, children="FW2"),
            ])
        ]
    
    return players

# Pattern matching callback for player info
@callback(
    Output('player-info', 'children'),
    Input({'type': 'player', 'index': dash.ALL}, 'n_clicks'),
    prevent_initial_call=True
)
def display_player_info(n_clicks):
    # Determine which player was clicked
    ctx = dash.callback_context
    if not ctx.triggered:
        return "Click a player to see details"
    
    # Get the player ID from the triggered input
    triggered_id = ctx.triggered[0]['prop_id'].split('.')[0]
    player_id = eval(triggered_id)['index']
    
    # Map player IDs to more readable information
    player_info = {
        1: "Goalkeeper: Responsible for defending the goal",
        2: "Defender 1: Left-back or center-back",
        3: "Defender 2: Center-back",
        4: "Defender 3: Center-back or right-back",
        5: "Defender 4: Right-back or center-back",
        6: "Midfielder 1: Defensive midfielder",
        7: "Midfielder 2: Central midfielder",
        8: "Midfielder 3: Attacking midfielder",
        9: "Midfielder 4: Right midfielder",
        10: "Forward 1: Striker or Left Wing",
        11: "Forward 2: Second striker or Right Wing"
    }
    
    return player_info.get(player_id, "Player details not found")