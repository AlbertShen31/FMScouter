import dash
from dash import dcc, html, Input, Output, dash_table
import pandas as pd
from position_score_calculator import calculate_positions_for_file
import os
import glob
from formation import formation_dict  # Import the formation dictionary
from flask import Flask

# Initialize the Flask server
server = Flask(__name__)

# Initialize the Dash app with the Flask server
app = dash.Dash(__name__, server=server, url_base_pathname='/squad/')

# Load the available squad files
directory_path = os.getenv('FM_24_path')
squad_files = glob.glob(os.path.join(directory_path, '**/*Squad*'), recursive=True)

# Sort the squad files (you can customize the sorting logic as needed)
squad_files = sorted(squad_files)  # This sorts the files alphabetically

# Define the layout of the app
app.layout = html.Div(style={'padding': '20px', 'fontFamily': 'Arial, sans-serif'}, children=[
    html.H1("Player Data Dashboard", style={'textAlign': 'center', 'marginBottom': '20px'}),
    
    # Dropdown for selecting squad files
    html.Div([
        html.Label("Select Squad File:", style={'fontWeight': 'bold'}),
        dcc.Dropdown(
            id='squad-file-dropdown',
            options=[{'label': os.path.basename(file), 'value': file} for file in squad_files],
            value=None,  # Set default value to None
            placeholder='Choose a file',  # Informative placeholder
            clearable=False,
            style={'marginBottom': '20px'}
        ),
    ], style={'marginBottom': '20px'}),
    
    # Dropdown for selecting formation
    html.Div([
        html.Label("Select Formation:", style={'fontWeight': 'bold'}),
        dcc.Dropdown(
            id='formation-dropdown',
            options=[{'label': name.replace('_', ' ').title(), 'value': name} for name in sorted(formation_dict.keys())],  # Generate options from formation_dict
            value=None,  # Default value (set to None or a specific formation)
            clearable=False,
            style={'marginBottom': '20px'}
        ),
    ], style={'marginBottom': '20px'}),
    
    # Dropdown for filtering by position
    html.Div([
        html.Label("Filter by Position:", style={'fontWeight': 'bold'}),
        dcc.Dropdown(
            id='position-filter',
            options=[],  # This will be populated after confirming the file
            value=None,  # Default value
            clearable=False,
            style={'marginBottom': '20px'}
        ),
    ], style={'marginBottom': '20px'}),
    
    # DataTable to display the DataFrame
    dash_table.DataTable(
        id='player-table',
        columns=[],
        data=[],
        page_size=10,
        sort_action='native',
        filter_action='native',
        sort_by=[{'column_id': 'Top Score', 'direction': 'desc'}],  # Sort by 'Top Score' column in descending order
        style_table={'overflowX': 'auto'},
        style_header={'backgroundColor': 'lightgrey', 'fontWeight': 'bold'},
        style_cell={'textAlign': 'left', 'padding': '10px'},
        style_data={'whiteSpace': 'normal', 'height': 'auto'},
    )
])

# Callback to update the position filter and table based on the selected squad file and formation
@app.callback(
    [Output('position-filter', 'options'),
     Output('position-filter', 'value'),
     Output('player-table', 'columns'),
     Output('player-table', 'data')],
    Input('squad-file-dropdown', 'value'),
    Input('formation-dropdown', 'value')  # New input for formation
)
def update_data(selected_file, selected_formation):
    if selected_file and selected_formation:
        # Check if the selected formation exists in the formation_dict
        if selected_formation not in formation_dict:
            return [], None, [], []  # Return empty values if formation is invalid

        # Load the data from the selected file
        squad_rawdata = pd.read_html(selected_file, header=0, encoding="utf-8", keep_default_na=False)[0]
        
        # Get the positions list for the selected formation
        positions_list = formation_dict[selected_formation]
        group_dfs = calculate_positions_for_file(positions_list, squad_rawdata, selected_file)  # Call for specific formation

        # Update the position filter options
        position_options = [{'label': group['Position'].iloc[0], 'value': group['Position'].iloc[0]} for group in group_dfs if not group.empty]
        
        # If no position group is selected, default to the first one
        selected_position_group = position_options[0]['value'] if position_options else None
        
        # Find the DataFrame corresponding to the selected position group
        df = next((group for group in group_dfs if group['Position'].iloc[0] == selected_position_group), pd.DataFrame())
        
        # Update the DataTable columns and data
        columns = [{"name": i, "id": i} for i in df.columns if i != 'Position']  # Exclude 'Position' column from columns
        data = df.drop(columns=['Position']).to_dict('records')  # Exclude 'Position' column from data
        
        return position_options, selected_position_group, columns, data
    
    return [], None, [], []  # Return empty values if no file or formation is selected

# Run the app
if __name__ == '__main__':
    app.run_server(debug=True) 