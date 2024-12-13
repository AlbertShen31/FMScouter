import dash
from dash import dcc, html, callback, Input, Output, State, register_page, callback_context
import uuid
from urllib.parse import parse_qs
from flask import request  # Import the request object

# Register the page with a specific path
register_page(__name__, path='/player_selection')

def generate_players(positions):
    formation = []
    player_num = 0
    for position in positions:
        field_area = {}
        for i in range(len(position)):
            field_area[position[i]] = {'id': f'player_{player_num}', 'content': f'Player {player_num+1}'}
            player_num += 1
        formation.append(field_area)
    return formation

# Define initial player data with 11 players
PLAYERS = generate_players([
    ['gk'],  # Goalkeeper
    ['dl', 'dcl', 'dc', 'dcr', 'dr'],  # Defenders
    [],  # Defensive Midfielders
    ['mcl', 'mcr'],  # Midfielders
    ['aml', 'amr'],  # Attacking Midfielders
    ['stc']  # Forwards
])

id_prefixes = {
        'goalkeeper': ['gk'],
        'defenders': ['dl', 'dcl', 'dc', 'dcr', 'dr'],
        'defensive_midfielders': ['wbl', 'dmcl', 'dmc', 'dmcr', 'wbr'],
        'midfielders': ['ml', 'mcl', 'mc', 'mcr', 'mr'],
        'attacking_midfielders': ['aml', 'amcl', 'amc', 'amcr', 'amr'],
        'forwards': ['stl', 'stc', 'str'],
    }

def create_container_divs(position_name, border_color, background_color, players=[], number_of_players=1):
    position_id = position_name.lower().replace(' ', '_')
    print(players)
    print(position_id)
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
                        'justifyContent': 'center',  # Center content horizontally
                        'alignItems': 'center',  # Center content vertically
                        'padding': '10px',
                        'margin': '0 auto'  # Center the droppable div itself
                    },
                    children=[
                        html.Div(f'Empty Slot {id_prefixes[position_id][i]}', style={'color': 'gray'}) 
                        if id_prefixes[position_id][i] not in players else create_draggable_player_div(players[id_prefixes[position_id][i]]) 
                    ]  # Placeholder for empty slots
                ) for i in range(number_of_players)  # Adjust range based on the maximum number of players
            ]
        )
    ])

# Function to create a draggable player div
def create_draggable_player_div(player):
    return html.Div(
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
    )

# Update layout to use the defined positions
layout = html.Div([
    # Add a script tag for custom JavaScript
    html.Script(src='/assets/drag_and_drop.js'),
    
    html.H1('Player Selection', style={'textAlign': 'center'}),
    
    # Formation Layout
    html.Div([
        create_container_divs('Forwards', 'red', 'salmon', PLAYERS[5], 3),
        create_container_divs('Attacking Midfielders', 'purple', 'lavender', PLAYERS[4], 5),
        create_container_divs('Midfielders', 'purple', 'lavender', PLAYERS[3], 5),
        create_container_divs('Defensive Midfielders', 'purple', 'lavender', PLAYERS[2], 5),
        create_container_divs('Defenders', 'blue', 'lightblue', PLAYERS[1], 5),
        create_container_divs('Goalkeeper', 'green', 'lightgreen', PLAYERS[0], 1),
    ]),
])