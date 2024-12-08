import os
import glob
import pandas as pd
from dash import dcc, html, dash_table, callback, Input, Output, register_page
from dotenv import load_dotenv
from formation import formation_dict
from position_score_calculator import calculate_positions_for_file

# Register the page with a specific path
register_page(__name__, path='/squad')

# Load environment variables and configure file paths
class AppConfig:
    load_dotenv()
    directory_path = os.getenv('FM_24_path')
    squad_files = sorted(glob.glob(os.path.join(directory_path, '**/*Squad*'), recursive=True))

# Define the layout for the Squad page
layout = html.Div([
    html.H1("Squad Data View", style={'textAlign': 'center', 'marginBottom': '20px', 'color': '#333'}),
    
    # Dropdown for selecting squad files
    html.Div([
        html.Label("Select Squad File:", style={'fontWeight': 'bold', 'color': '#007BFF'}),
        dcc.Dropdown(
            id='squad-file-dropdown',
            options=[{'label': os.path.basename(file), 'value': file} for file in AppConfig.squad_files],
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
            id='squad-formation-dropdown',
            options=[{'label': name.replace('_', ' ').title(), 'value': name} for name in sorted(formation_dict.keys())],
            value=None,
            clearable=False,
            style={'marginBottom': '20px', 'backgroundColor': '#e9ecef', 'color': '#495057'}
        ),
    ], style={'marginBottom': '20px', 'backgroundColor': '#ffffff', 'padding': '10px', 'borderRadius': '5px', 'boxShadow': '0 2px 5px rgba(0,0,0,0.1)'}),
    
    # Dropdown for filtering by position
    html.Div(id='squad-position-filter-container', children=[
        html.Label("Filter by Position:", style={'fontWeight': 'bold', 'color': '#007BFF'}),
        dcc.Dropdown(
            id='squad-position-filter',
            options=[],
            value=None,
            clearable=False,
            style={'marginBottom': '20px', 'backgroundColor': '#e9ecef', 'color': '#495057'}
        ),
    ]),
    
    # DataTable to display the DataFrame
    dash_table.DataTable(
        id='squad-player-table',
        columns=[],
        data=[],
        page_size=10,
        sort_action='native',
        filter_action='native',
        style_table={'overflowX': 'auto'},
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
    [Output('squad-position-filter', 'options'),
     Output('squad-position-filter', 'value'),
     Output('squad-player-table', 'columns'),
     Output('squad-player-table', 'data'),
     Output('squad-player-table', 'sort_by')],  # Added sort_by output
    [Input('squad-file-dropdown', 'value'),
     Input('squad-formation-dropdown', 'value'),
     Input('squad-position-filter', 'value')]
)
def update_data(selected_file, selected_formation, selected_position):
    if selected_file and selected_formation:
        if selected_formation not in formation_dict:
            return [], None, [], [], []  # Return empty sort_by

        squad_rawdata = pd.read_html(selected_file, header=0, encoding="utf-8", keep_default_na=False)[0]
        positions_list = formation_dict[selected_formation]
        group_dfs = calculate_positions_for_file(positions_list, squad_rawdata, selected_file)

        position_options = [{'label': group['Position'].iloc[0], 'value': group['Position'].iloc[0]} for group in group_dfs if not group.empty]
        selected_position_group = position_options[0]['value'] if position_options else None
        
        if selected_position:
            df = next((group for group in group_dfs if group['Position'].iloc[0] == selected_position), pd.DataFrame())
        else:
            df = next((group for group in group_dfs if group['Position'].iloc[0] == selected_position_group), pd.DataFrame())
        
        columns = [{"name": i, "id": i} for i in df.columns if i != 'Position']
        data = df.drop(columns=['Position']).to_dict('records')

        # Determine the last column for sorting
        last_column_id = columns[-1]['id'] if columns else ''

        return position_options, selected_position_group, columns, data, [{'column_id': last_column_id, 'direction': 'desc'}]
    
    return [], None, [], [], [] 
