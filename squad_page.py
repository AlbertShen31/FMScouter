import dash
from dash import dcc, html, Input, Output, dash_table
import pandas as pd
import os
import glob
from position_score_calculator import calculate_positions_for_file
from formation import formation_dict

class AppConfig:
    directory_path = os.getenv('FM_24_path')
    squad_files = sorted(glob.glob(os.path.join(directory_path, '**/*Squad*'), recursive=True))

layout = html.Div(style={'padding': '20px', 'fontFamily': 'Arial, sans-serif', 'backgroundColor': '#f4f4f4'}, children=[
    html.H1("Player Data Dashboard", style={'textAlign': 'center', 'marginBottom': '20px', 'color': '#333'}),
    
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
            id='formation-dropdown',
            options=[{'label': name.replace('_', ' ').title(), 'value': name} for name in sorted(formation_dict.keys())],
            value=None,
            clearable=False,
            style={'marginBottom': '20px', 'backgroundColor': '#e9ecef', 'color': '#495057'}
        ),
    ], style={'marginBottom': '20px', 'backgroundColor': '#ffffff', 'padding': '10px', 'borderRadius': '5px', 'boxShadow': '0 2px 5px rgba(0,0,0,0.1)'}),
    
    # Store component to manage visibility of the position filter
    dcc.Store(id='store-position-filter-visible', data=False),
    
    # Dropdown for filtering by position
    html.Div(id='position-filter-container', style={'display': 'none'}, children=[
        html.Label("Filter by Position:", style={'fontWeight': 'bold', 'color': '#007BFF'}),
        dcc.Dropdown(
            id='position-filter',
            options=[],
            value=None,
            clearable=False,
            style={'marginBottom': '20px', 'backgroundColor': '#e9ecef', 'color': '#495057'}
        ),
    ]),
    
    # DataTable to display the DataFrame
    dash_table.DataTable(
        id='player-table',
        columns=[],
        data=[],
        page_size=10,
        sort_action='native',
        filter_action='native',
        sort_by=[{'column_id': 'Top Score', 'direction': 'desc'}],
        style_table={'overflowX': 'auto'},
        style_header={'backgroundColor': '#007BFF', 'fontWeight': 'bold', 'color': 'white'},
        style_cell={'textAlign': 'left', 'padding': '10px', 'backgroundColor': '#f8f9fa', 'color': '#212529'},
        style_data={'whiteSpace': 'normal', 'height': 'auto'},
        style_data_conditional=[
            {
                'if': {'row_index': 'odd'},
                'backgroundColor': '#f2f2f2'
            }
        ]
    )
])

def register_callbacks(app):
    @app.callback(
        [Output('position-filter', 'options'),
         Output('position-filter', 'value'),
         Output('player-table', 'columns'),
         Output('player-table', 'data'),
         Output('store-position-filter-visible', 'data')],
        Input('squad-file-dropdown', 'value'),
        Input('formation-dropdown', 'value')
    )
    def update_data(selected_file, selected_formation):
        if selected_file and selected_formation:
            if selected_formation not in formation_dict:
                return [], None, [], [], False

            squad_rawdata = pd.read_html(selected_file, header=0, encoding="utf-8", keep_default_na=False)[0]
            positions_list = formation_dict[selected_formation]
            group_dfs = calculate_positions_for_file(positions_list, squad_rawdata, selected_file)

            position_options = [{'label': group['Position'].iloc[0], 'value': group['Position'].iloc[0]} for group in group_dfs if not group.empty]
            selected_position_group = position_options[0]['value'] if position_options else None
            df = next((group for group in group_dfs if group['Position'].iloc[0] == selected_position_group), pd.DataFrame())
            columns = [{"name": i, "id": i} for i in df.columns if i != 'Position']
            data = df.drop(columns=['Position']).to_dict('records')

            return position_options, selected_position_group, columns, data, True
        
        return [], None, [], [], False

    @app.callback(
        Output('position-filter-container', 'style'),
        Input('store-position-filter-visible', 'data')
    )
    def toggle_position_filter(visible):
        return {'display': 'block'} if visible else {'display': 'none'}