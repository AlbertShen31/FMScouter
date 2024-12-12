import os
import glob
import pandas as pd
from dash import dcc, html, dash_table, callback, Input, Output, register_page
from dotenv import load_dotenv
from config.formation_config import formation_dict
from position_score_calculator import calculate_positions_for_file

# Register the page with a specific path
register_page(__name__, path='/scouting')

# Load environment variables and configure file paths
class AppConfig:
    load_dotenv()
    directory_path = os.getenv('FM_24_path')
    scouting_files = sorted(glob.glob(os.path.join(directory_path, '**/*Scouting*'), recursive=True))

# Define the layout for the Scouting page
layout = html.Div([
    html.H1("Scouting Data View", style={'textAlign': 'center', 'marginBottom': '20px', 'color': '#333'}),
    
    # Dropdown for selecting scouting files
    html.Div([
        html.Label("Select Scouting File:", style={'fontWeight': 'bold', 'color': '#007BFF'}),
        dcc.Dropdown(
            id='scouting-file-dropdown',
            options=[{'label': os.path.basename(file), 'value': file} for file in AppConfig.scouting_files],
            value=None,
            placeholder='Choose a file',
            clearable=False,
            style={'marginBottom': '20px', 'backgroundColor': '#e9ecef', 'color': '#495057'}
        ),
    ], style={'marginBottom': '20px', 'backgroundColor': '#ffffff', 'padding': '10px', 'borderRadius': '5px', 'boxShadow': '0 2px 5px rgba(0,0,0,0.1)'}),
    
    # Dropdown for selecting formation
    html.Div([
        html.Label("Select Formation:", style={'fontWeight': 'bold', 'color': '#007BFF'}),
        dcc.Dropdown(
            id='scouting-formation-dropdown',
            options=[{'label': name.replace('_', ' ').title(), 'value': name} for name in sorted(formation_dict.keys())],
            value=None,
            clearable=False,
            style={'marginBottom': '20px', 'backgroundColor': '#e9ecef', 'color': '#495057'}
        ),
    ], style={'marginBottom': '20px', 'backgroundColor': '#ffffff', 'padding': '10px', 'borderRadius': '5px', 'boxShadow': '0 2px 5px rgba(0,0,0,0.1)'}),
    
    # Dropdown for filtering by position
    html.Div(id='scouting-position-filter-container', children=[
        html.Label("Filter by Position:", style={'fontWeight': 'bold', 'color': '#007BFF'}),
        dcc.Dropdown(
            id='scouting-position-filter',
            options=[],
            value=None,
            clearable=False,
            style={'marginBottom': '20px', 'backgroundColor': '#e9ecef', 'color': '#495057'}
        ),
    ]),
    
    # DataTable to display the DataFrame
    dash_table.DataTable(
        id='scouting-player-table',
        columns=[],
        data=[],
        page_size=20,
        cell_selectable=False,
        sort_action='native',
        filter_action='native',
        style_table={
            'overflowX': 'auto',
            'paddingBottom': '50px'
        },
        style_header={'backgroundColor': '#007BFF', 'fontWeight': 'bold', 'color': 'white'},
        style_cell={'textAlign': 'left', 'padding': '10px', 'backgroundColor': '#f8f9fa', 'color': '#212529'},
        style_data={'whiteSpace': 'normal', 'height': 'auto'},
        style_data_conditional=[
            {
                'if': {'row_index': 'odd'},
                'backgroundColor': '#f2f2f2'
            }
        ],
        sort_by=[{'column_id': '', 'direction': 'desc'}]  # Default sort by last column will be set in the callback
    )
])

@callback(
    [Output('scouting-position-filter', 'options'),
     Output('scouting-position-filter', 'value'),
     Output('scouting-player-table', 'columns'),
     Output('scouting-player-table', 'data'),
     Output('scouting-player-table', 'sort_by')],  # Added sort_by output
    [Input('scouting-file-dropdown', 'value'),
     Input('scouting-formation-dropdown', 'value'),
     Input('scouting-position-filter', 'value')]
)
def update_data(selected_file, selected_formation, selected_position):
    if selected_file and selected_formation:
        if selected_formation not in formation_dict:
            return [], None, [], [], []  # Return empty sort_by

        scouting_rawdata = pd.read_html(selected_file, header=0, encoding="utf-8", keep_default_na=False)[0]
        positions_list = formation_dict[selected_formation]
        group_dfs = calculate_positions_for_file(positions_list, scouting_rawdata)

        position_options = [{'label': group['Selected'].iloc[0], 'value': group['Selected'].iloc[0]} for group in group_dfs if not group.empty]
        selected_position_group = position_options[0]['value'] if position_options else None
        
        if selected_position:
            df = next((group for group in group_dfs if group['Selected'].iloc[0] == selected_position), pd.DataFrame())
        else:
            df = next((group for group in group_dfs if group['Selected'].iloc[0] == selected_position_group), pd.DataFrame())
        
        columns = [{"name": i, "id": i} for i in df.columns if i != 'Selected']
        data = df.drop(columns=['Selected']).to_dict('records')

        # Determine the last column for sorting
        last_column_id = columns[-1]['id'] if columns else ''
        
        return position_options, selected_position_group, columns, data, [{'column_id': last_column_id, 'direction': 'desc'}]  # Set default sort by last column
    
    return [], None, [], [], []  # Return empty sort_by
