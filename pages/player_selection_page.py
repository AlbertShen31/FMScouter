import dash
from dash import dcc, html, callback, Input, Output, State, register_page
import uuid
from urllib.parse import parse_qs
from flask import request  # Import the request object

# Register the page with a specific path
register_page(__name__, path='/player_selection')

# Define initial player data with 11 players
PLAYERS = {
    'goalkeeper': [
        {'id': f'player_{i}', 'content': f'Player {i+1}', 'position': 'gk'[i]}
        for i in range(1)
    ],
    'defenders': [
        {'id': f'player_{i}', 'content': f'Player {i+1}', 'position': f'{['dl', 'dcl', 'dcr', 'dr'][i-1]}'}
        for i in range(1, 5)
    ],
    'defensive_midfielders': [
        {'id': f'player_{i}', 'content': f'Player {i+1}', 'position': f'{['dmc'][i-5]}'}
        for i in range(5, 6)
    ],
    'midfielders': [
        {'id': f'player_{i}', 'content': f'Player {i+1}', 'position': f'{['mcl', 'mcr'][i-6]}'}
        for i in range(6, 8)
    ],
    'attacking_midfielders': [
        {'id': f'player_{i}', 'content': f'Player {i+1}', 'position': f'{['aml', 'amr'][i-8]}'}
        for i in range(8, 10)
    ],
    'forwards': [
        {'id': f'player_{i}', 'content': f'Player {i+1}', 'position': f'{['stc'][i-10]}'}
        for i in range(10, 11)
    ]
}

id_prefixes = {
        'goalkeeper': ['gk'],
        'defenders': ['dl', 'dcl', 'dc', 'dcr', 'dr'],
        'defensive_midfielders': ['wbl', 'dmcl', 'dmc', 'dmcr', 'wbr'],
        'midfielders': ['ml', 'mcl', 'mc', 'mcr', 'mr'],
        'attacking_midfielders': ['aml', 'amcl', 'amc', 'amcr', 'amr'],
        'forwards': ['stl', 'stc', 'str'],
    }

def create_player_divs(position_name, border_color, background_color, players=[], number_of_players=1):
    position_id = position_name.lower().replace(' ', '_')
    return html.Div([
        html.H4(position_name),
        html.Div(
            style={
                'display': 'flex',
                'justifyContent': 'space-between',
                'width': '100%',
                'marginBottom': '20px'
            },
            children=[
                html.Div(
                    id=f'{id_prefixes[position_id][i]}',  # Generate IDs based on position
                    className='droppable row-container',
                    style={
                        'border': f'2px dashed {border_color}', 
                        'minHeight': '100px', 
                        'width': '22%',
                        'display': 'flex',
                        'justifyContent': 'center',
                        'alignItems': 'center',
                        'padding': '10px'
                    },
                    children=[html.Div(f'Empty Slot {id_prefixes[position_id][i]}', style={'color': 'gray'})]  # Placeholder for empty slots
                ) for i in range(number_of_players)  # Adjust range based on the maximum number of players
            ]
        )
    ])

# Update layout to use the defined positions
layout = html.Div([
    # Add a script tag for custom JavaScript
    html.Script(src='/assets/drag_and_drop.js'),
    
    html.H1('Player Selection', style={'textAlign': 'center'}),
    
    # Formation Layout
    html.Div([
        create_player_divs('Forwards', 'red', 'salmon', PLAYERS['forwards'], 3),
        create_player_divs('Attacking Midfielders', 'purple', 'lavender', PLAYERS['attacking_midfielders'], 5),
        create_player_divs('Midfielders', 'purple', 'lavender', PLAYERS['midfielders'], 5),
        create_player_divs('Defensive Midfielders', 'purple', 'lavender', PLAYERS['defensive_midfielders'], 5),
        create_player_divs('Defenders', 'blue', 'lightblue', PLAYERS['defenders'], 5),
        create_player_divs('Goalkeeper', 'green', 'lightgreen', PLAYERS['goalkeeper'], 1),
    ] + [
        html.Div(
            f"{player['content']}",  # Use player content for draggable object
            id=f"draggable_{player['id']}",  # Unique ID for draggable
            className='draggable',  # Class for draggable styling
            draggable='true',
            style={
                'cursor': 'move',
                'color': 'white',  # Change text color for better contrast
                'border': '2px solid black',  # Border for visibility
                'borderRadius': '50%',  # Make it circular
                'width': '75px',  # Adjust width
                'height': '75px',  # Adjust height
                'display': 'flex',
                'justifyContent': 'center',
                'alignItems': 'center',
                'backgroundColor': '#007BFF',  # Change background color to a vibrant blue
                'fontSize': '14px',  # Adjust font size for better fit
                'textAlign': 'center',
                'marginBottom': '20px',
                'marginTop': '20px'
            }  # Style for draggable
        ) for position in PLAYERS.values() for player in position  # Create draggable for each player
    ]),
])