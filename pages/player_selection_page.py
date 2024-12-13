import dash
from dash import dcc, html, callback, Input, Output, State, register_page
import uuid
from urllib.parse import parse_qs
from flask import request  # Import the request object

# Register the page with a specific path
register_page(__name__, path='/player_selection')

# Define initial player data with 11 players
PLAYERS = [
    {'id': f'player_{i}', 'content': f'Player {i}'}
    for i in range(1, 12)
]

# Define player positions explicitly
INITIAL_FORMATION = {
    'goalkeeper': [{'id': PLAYERS[0]['id'], 'content': PLAYERS[0]['content'], 'div_id': 'gk'}],
    'defenders': [
        {'id': PLAYERS[1]['id'], 'content': PLAYERS[1]['content'], 'div_id': 'dl'},
        {'id': PLAYERS[2]['id'], 'content': PLAYERS[2]['content'], 'div_id': 'dcl'},
        {'id': PLAYERS[3]['id'], 'content': PLAYERS[3]['content'], 'div_id': 'dc'},
        {'id': PLAYERS[4]['id'], 'content': PLAYERS[4]['content'], 'div_id': 'dr'}
    ],
    'defensive_midfielders': [],
    'midfielders': [
        {'id': PLAYERS[5]['id'], 'content': PLAYERS[5]['content'], 'div_id': 'ml'},
        {'id': PLAYERS[6]['id'], 'content': PLAYERS[6]['content'], 'div_id': 'mcl'},
        {'id': PLAYERS[7]['id'], 'content': PLAYERS[7]['content'], 'div_id': 'mc'},
        {'id': PLAYERS[8]['id'], 'content': PLAYERS[8]['content'], 'div_id': 'mr'}
    ],
    'attacking_midfielders': [],
    'forwards': [
        {'id': PLAYERS[9]['id'], 'content': PLAYERS[9]['content'], 'div_id': 'stl'},
        {'id': PLAYERS[10]['id'], 'content': PLAYERS[10]['content'], 'div_id': 'str'}
    ]
}

id_prefixes = {
        "goalkeeper": ["gk"],
        "defenders": ['dl', 'dcl', 'dc', 'dcr', 'dr'],
        "defensive midfielders": ['wbl', 'dmcl', 'dmc', 'dmcr', 'wbr'],
        "midfielders": ['ml', 'mcl', 'mc', 'mcr', 'mr'],
        "attacking midfielders": ['aml', 'amcl', 'amc', 'amcr', 'amr'],
        "forwards": ['stl', 'stc', 'str'],
    }

def create_player_divs(position_name, border_color, background_color, number_of_players=1):
    return html.Div([
        html.H4(position_name),
        html.Div(
            style={
                'display': 'flex',
                'justifyContent': 'space-between',
                'width': '100%'
            },
            children=[
                html.Div(
                    id=f'{id_prefixes[position_name.lower()][i]}',  # Generate IDs based on position
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
                    children=[html.Div(f'Empty Slot {id_prefixes[position_name.lower()][i]}', style={'color': 'gray'})]  # Placeholder for empty slots
                ) for i in range(number_of_players)  # Adjust range based on the maximum number of players
            ]
        )
    ])

# Update layout to use the defined positions
layout = html.Div([
    # Add a script tag for custom JavaScript
    html.Script(src='/assets/drag_and_drop.js'),
    
    html.H1("Player Selection", style={'textAlign': 'center'}),
    
    # Formation Layout
    html.Div([
        create_player_divs("Forwards", 'red', 'salmon', 3),
        create_player_divs("Attacking Midfielders", 'purple', 'lavender', 5),
        create_player_divs("Midfielders", 'purple', 'lavender', 5),
        create_player_divs("Defensive Midfielders", 'purple', 'lavender', 5),
        create_player_divs("Defenders", 'blue', 'lightblue', 5),
        create_player_divs("Goalkeeper", 'green', 'lightgreen', 1),
    ]),
    
    # Available Players
    html.Div([
        html.H3("Substitutes"),
        html.Div(
            id='available-players',
            className='droppable',
            style={
                'display': 'flex',
                'flexWrap': 'wrap',
                'minHeight': '100px',
                'border': '2px dashed gray',
                'padding': '10px'
            },
            children=[html.Div("No Substitutes Available", style={'color': 'gray'})]  # Placeholder for empty substitutes
        )
    ]),
    
    # Store to track dropped players
    # dcc.Store(id='dropped-players')
])

# # Callback to update dropped players
# @callback(
#     Output('dropped-players', 'data'),
#     Input('available-players', 'children'),
#     Input('gk', 'children'),
#     [Input(f'{['dl','dcl','dc','dcr','dr'][i-1]}', 'children') for i in range(1, 6)],
#     [Input(f'{['wbl','dmcl','dmc','dmcr','wbr'][i-1]}', 'children') for i in range(1, 6)],
#     [Input(f'{['ml','mcl','mc','mcr','mr'][i-1]}', 'children') for i in range(1, 6)],
#     [Input(f'{['aml','amcl','amc','amcr','amr'][i-1]}', 'children') for i in range(1, 6)],
#     [Input(f'{['stl','stc','str'][i-1]}', 'children') for i in range(1, 4)],
#     prevent_initial_call=True
# )
# def update_dropped_players(available_players, goalkeeper, *position_players):
#     # Organize the data into a structured dictionary
#     data = {
#         'availablePlayers': available_players,
#         'goalkeeper': goalkeeper
#     }
    
#     positions = ['defender', 'midfielder', 'forward']
#     for pos_index, position in enumerate(positions):
#         pos_data = {}
#         start = 0 if position != 'forward' else 4
#         end = 4 if position != 'forward' else 3
        
#         for i in range(start, end):
#             pos_data[f'{position}_{i+1}'] = position_players[pos_index * 4 + i]
        
#         data[position] = pos_data
    
#     return data