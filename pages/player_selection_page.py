# Imports
import dash
from dash import dcc, html, callback, Input, Output, register_page
from config.position_config import position_roles
from utils import format_position_name

# Constants
DEFAULT_FORMATION = 'heaven'  # Default formation
FORMATIONS = [
    {'label': '4-1-3-2', 'value': 'heaven'},
    {'label': '4-1-2-2-1', 'value': 'flanker'},
    {'label': '3-4-3', 'value': 'three_striker'},
]

FORMATION_DICT = {
    'heaven': [
        ['gk'],  # Goalkeeper
        ['dl', 'dcl', 'dcr', 'dr'],  # Defenders
        ['dmc'],  # Defensive Midfielders 
        [],  # Midfielders
        ['aml', 'amc', 'amr'],  # Attacking Midfielders
        ['stl', 'str']  # Forwards
    ],
    'flanker': [
        ['gk'],  # Goalkeeper
        ['dl', 'dcl', 'dcr', 'dr'],  # Defenders
        ['dmc'],  # Defensive Midfielders 
        ['mr', 'ml'],  # Midfielders
        ['aml', 'amr'],  # Attacking Midfielders
        ['stc']  # Forwards
    ],
    'three_striker': [
        ['gk'],  # Goalkeeper
        ['dc', 'dcl', 'dcr'],  # Defenders
        ['wbl', 'dmcl', 'dmcr', 'wbr'],  # Defensive Midfielders 
        [],  # Midfielders
        [],  # Attacking Midfielders
        ['stl', 'str', 'stc']  # Forwards
    ],
}

ID_PREFIXES = {
    'goalkeeper': ['gk'],
    'defenders': ['dl', 'dcl', 'dc', 'dcr', 'dr'],
    'defensive_midfielders': ['wbl', 'dmcl', 'dmc', 'dmcr', 'wbr'],
    'midfielders': ['ml', 'mcl', 'mc', 'mcr', 'mr'],
    'attacking_midfielders': ['aml', 'amcl', 'amc', 'amcr', 'amr'],
    'forwards': ['stl', 'stc', 'str'],
}

POSITION_COLORS = {
    'Goalkeeper': ('green', 'lightgreen'),
    'Defenders': ('blue', 'lightblue'),
    'Defensive Midfielders': ('purple', 'lavender'),
    'Midfielders': ('orange', 'peachpuff'),
    'Attacking Midfielders': ('red', 'salmon'),
    'Forwards': ('yellow', 'lightyellow'),
}

# Functions
def generate_players(positions):
    formation = []
    player_num = 0
    for position in positions:
        field_area = {}
        for i in range(len(position)):
            field_area[position[i]] = {'id': f'player_{player_num}', 'content': f'{player_num + 1}'}
            player_num += 1
        formation.append(field_area)
    return formation

def create_container_divs(position_name, players=[], number_of_players=1):
    border_color, background_color = POSITION_COLORS.get(position_name, ('black', 'white'))
    position_id = position_name.lower().replace(' ', '_')
    return html.Div([
        html.H4(position_name),
        html.Div(
            style={
                'display': 'flex',
                'justifyContent': 'space-between',
                'width': '100%',
                'marginBottom': '20px',
            },
            children=[
                html.Div(
                    id=f'{ID_PREFIXES[position_id][i]}',
                    className='droppable row-container',
                    style={
                        'border': f'2px dashed {border_color}',
                        'minHeight': '100px',
                        'width': '18%',
                        'display': 'flex',
                        'justifyContent': 'center',
                        'alignItems': 'center',
                        'padding': '10px',
                        'margin': '0 auto'
                    },
                    children=[
                        html.Div(f'Empty Slot {ID_PREFIXES[position_id][i]}', style={'color': 'gray'})
                        if ID_PREFIXES[position_id][i] not in players else create_draggable_player_div(players[ID_PREFIXES[position_id][i]], ID_PREFIXES[position_id][i])
                    ]
                ) for i in range(number_of_players)
            ]
        )
    ])

def create_draggable_player_div(player, position_id):
    available_roles = position_roles.get(position_id, [])
    available_options = [{'label': format_position_name(role), 'value': role.lower()} for role in sorted(available_roles)]

    return html.Div(
        [
            html.Div(
                f"{player['content']}",
                style={
                    'fontSize': '20px',
                    'fontWeight': 'bold',
                    'textAlign': 'center',
                    'marginBottom': '2px',
                }
            ),
            dcc.Dropdown(
                id={'type': 'dropdown', 'index': player['id']},
                options=available_options,
                value=available_options[0]['value'] if available_options else None,
                clearable=False,
                style={
                    'width': '100%',
                    'fontSize': '12px',
                    'color': 'black',
                    'textAlign': 'center',
                    'border': 'none',
                    'backgroundColor': 'transparent',
                }
            )
        ],
        id=f"draggable_{player['id']}",
        className='draggable',
        draggable='true',
        style={
            'cursor': 'move',
            'color': 'white',
            'backgroundColor': '#007BFF',
            'border': '2px solid black',
            'borderRadius': '50%',
            'width': '100px',
            'height': '100px',
            'display': 'flex',
            'flexDirection': 'column',
            'justifyContent': 'center',
            'alignItems': 'center',
            'padding': '5px',
        }
    )

def generate_players_from_formation(formation):
    return generate_players(FORMATION_DICT[formation])

# Register the page with a specific path
register_page(__name__, path='/player_selection')

# Layout
layout = html.Div([
    dcc.Dropdown(
        id='formation-dropdown',
        options=FORMATIONS,
        value=DEFAULT_FORMATION,  # Default value
        clearable=False,
        style={'width': '40%', 'margin': '20px auto'}  # Center the dropdown
    ),
    
    dcc.Store(id='players-store', data=generate_players_from_formation(DEFAULT_FORMATION)),  # Initialize with default players
    
    html.Script(src='/assets/drag_and_drop.js'),
    
    html.H1('Player Selection', style={'textAlign': 'center'}),
 
    html.Div(id='formation-layout', children=[
        create_container_divs('Forwards', [], 3),
        create_container_divs('Attacking Midfielders', [], 5),
        create_container_divs('Midfielders', [], 5),
        create_container_divs('Defensive Midfielders', [], 5),
        create_container_divs('Defenders', [], 5),
        create_container_divs('Goalkeeper', [], 1),
    ]),
    
    html.Div(id='click-counter', children='Player Click Count: 0', style={'textAlign': 'center', 'marginTop': '20px'}),  # Display for click count
])

# Callbacks
@callback(
    Output('players-store', 'data'),  # Update the players store
    Input('formation-dropdown', 'value'),  # Listen for changes in the dropdown
    prevent_initial_call=True
)
def update_players(selected_formation):
    players = generate_players_from_formation(selected_formation)  # Regenerate players based on the selected formation
    return players  # Return the updated players and click count

@callback(
    Output('formation-layout', 'children'),
    Input('players-store', 'data')
)
def update_formation_layout(players):
    return [
        create_container_divs('Forwards', players[5], 3),
        create_container_divs('Attacking Midfielders', players[4], 5),
        create_container_divs('Midfielders', players[3], 5),
        create_container_divs('Defensive Midfielders', players[2], 5),
        create_container_divs('Defenders', players[1], 5),
        create_container_divs('Goalkeeper', players[0], 1),
    ]