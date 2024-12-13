import dash
from dash import dcc, html, callback, Input, Output, State, register_page, callback_context
import uuid
from urllib.parse import parse_qs
from flask import request  # Import the request object
from dash import ctx  # Import ctx to determine which component was clicked
from config.position_config import position_roles
from utils import format_position_name  # Import the position roles

# Register the page with a specific path
register_page(__name__, path='/player_selection')

def generate_players(positions):
    formation = []
    player_num = 0
    for position in positions:
        field_area = {}
        for i in range(len(position)):
            field_area[position[i]] = {'id': f'player_{player_num}', 'content': f'{player_num+1}'}
            player_num += 1
        formation.append(field_area)
    return formation

# Define initial player data with 11 players
PLAYERS = generate_players([
    ['gk'],  # Goalkeeper
    ['dcl', 'dcr', 'dr'],  # Defenders
    ['wbl', 'dmcl'],  # Defensive Midfielders 
    ['mcl', 'ml'],  # Midfielders
    ['aml', 'amcl'],  # Attacking Midfielders
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
                    id=f'{id_prefixes[position_id][i]}',  # Generate IDs based on position
                    className='droppable row-container',
                    style={
                        'border': f'2px dashed {border_color}', 
                        'minHeight': '100px', 
                        'width': '18%',
                        'display': 'flex',
                        'justifyContent': 'center',  # Center content horizontally
                        'alignItems': 'center',  # Center content vertically
                        'padding': '10px',
                        'margin': '0 auto'  # Center the droppable div itself
                    },
                    children=[
                        html.Div(f'Empty Slot {id_prefixes[position_id][i]}', style={'color': 'gray'}) 
                        if id_prefixes[position_id][i] not in players else create_draggable_player_div(players[id_prefixes[position_id][i]], id_prefixes[position_id][i]) 
                    ]  # Placeholder for empty slots
                ) for i in range(number_of_players)  # Adjust range based on the maximum number of players
            ]
        )
    ])

# Initialize a click counter
click_count = 0

# Callback to update click count
@callback(
    Output('click-counter', 'children'),  # Output to display the click count
    Input({'type': 'dropdown', 'index': dash.dependencies.ALL}, 'value'),  # Input for all dropdowns in player divs
    prevent_initial_call=True
)
def update_click_count(dropdown_values):
    global click_count
    if ctx.triggered:
        # Increment the counter only if a dropdown is selected
        if dropdown_values and any(dropdown_values):
            click_count += 1  # Increment for each dropdown selection
    return f'Player Click Count: {click_count}'  # Return the updated count

# Function to create a draggable player div with a dropdown
def create_draggable_player_div(player, position_id):
    # Get the available roles for the given position ID
    available_roles = position_roles.get(position_id, [])

    available_options = [{'label': format_position_name(role), 'value': role.lower()} for role in sorted(available_roles)]

    print(available_options)

    return html.Div(
        [
            html.Div(
                f"{player['content']}",  # Use player content for draggable object
                style={
                    'fontSize': '20px',  # Increase font size for better visibility
                    'fontWeight': 'bold',
                    'textAlign': 'center',
                    'marginBottom': '2px',  # Space between text and dropdown
                }
            ),
            dcc.Dropdown(
                id={'type': 'dropdown', 'index': player['id']},  # Unique ID for dropdown
                options=available_options,  # Set options based on position
                value=available_roles[0] if available_roles else None,  # Default value
                clearable=False,  # Remove the clearable "x"
                style={
                    'width': '100%',  # Set width to fill the parent div
                    'fontSize': '12px',  # Adjust font size for dropdown
                    'color': 'black',  # Set dropdown font color to black for better visibility
                    'textAlign': 'center',  # Center the text in the dropdown
                    'border': 'none',  # Remove border for a cleaner look
                    'backgroundColor': 'transparent',  # Make background transparent
                }
            )
        ],
        id=f"draggable_{player['id']}",  # Unique ID for draggable
        className='draggable',  # Class for draggable styling
        draggable='true',
        style={
            'cursor': 'move',
            'color': 'white',  # Change text color for better contrast
            'backgroundColor': '#007BFF',  # Change background color to a vibrant blue
            'border': '2px solid black',  # Border for visibility
            'borderRadius': '50%',  # Make it circular
            'width': '100px',  # Increase width for better visibility
            'height': '100px',  # Increase height for better visibility
            'display': 'flex',
            'flexDirection': 'column',  # Stack content vertically
            'justifyContent': 'center',
            'alignItems': 'center',
            'padding': '5px',  # Add padding
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
    
    html.Div(id='click-counter', children='Player Click Count: 0', style={'textAlign': 'center', 'marginTop': '20px'}),  # Display for click count
])
