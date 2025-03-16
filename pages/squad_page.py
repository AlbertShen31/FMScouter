import os
import glob
import pandas as pd
from dash import dcc, html, callback, Input, Output, register_page
from dotenv import load_dotenv
from config.formation_config import formation_dict
from position_score_calculator import calculate_positions_for_file
import dash_ag_grid as dag
import dash_bootstrap_components as dbc

# Function to create a page for either squad or scouting data
def create_page(page_type):
    # Register the page with a specific path
    path = f'/{page_type}'
    register_page(__name__, path=path)
    
    # Load environment variables and configure file paths
    class AppConfig:
        load_dotenv()
        directory_path = os.getenv('FM_24_path')
        # Use the page_type to determine which files to look for
        files = sorted(glob.glob(os.path.join(directory_path, f'**/*{page_type.capitalize()}*'), recursive=True))
    
    get_row_style = {
        "styleConditions": [
            {
                "condition": "params.data['Data Source'] === 'Squad'",
                "style": {"backgroundColor": "dodgerblue", "color": "white"},
            },
            {
                "condition": "params.data['Data Source'] === 'Scouting' && (!params.data.Club || params.data.Club === '')",
                "style": {"backgroundColor": "limegreen", "color": "black"},
            },
            {
                "condition": "params.data['Data Source'] === 'Scouting' && params.data.Club && params.data.Club !== ''",
                "style": {"backgroundColor": "hotpink", "color": "white"},
            },
        ],
        "defaultStyle": {"backgroundColor": "grey", "color": "white"},
    }
    
    # Define the layout for the page
    layout = html.Div([
        html.H1(f"{page_type.capitalize()} Data View", 
                style={'textAlign': 'center', 'marginBottom': '30px', 'color': '#333', 'fontSize': '36px', 'fontWeight': 'bold'}),
        
        # Control panel with dropdowns in a card
        dbc.Card([
            dbc.CardHeader(html.H4("Data Controls", className="card-title", 
                                   style={'color': '#0056b3', 'fontWeight': 'bold'})),
            dbc.CardBody([
                dbc.Row([
                    # File selection dropdown
                    dbc.Col([
                        html.Label(f"Select {page_type.capitalize()} File:", 
                                  style={'fontWeight': 'bold', 'color': '#495057', 'fontSize': '16px', 'marginBottom': '8px'}),
                        dcc.Dropdown(
                            id=f'{page_type}-file-dropdown',
                            options=[{'label': os.path.basename(file), 'value': file} for file in AppConfig.files],
                            value=None,
                            placeholder='Choose a file',
                            clearable=False,
                            persistence=True,
                            style={'backgroundColor': '#f8f9fa', 'borderRadius': '4px'}
                        ),
                    ], width=4),
                    
                    # Formation dropdown
                    dbc.Col([
                        html.Label("Select Formation:", 
                                  style={'fontWeight': 'bold', 'color': '#495057', 'fontSize': '16px', 'marginBottom': '8px'}),
                        dcc.Dropdown(
                            id=f'{page_type}-formation-dropdown',
                            options=[{'label': name.replace('_', ' ').title(), 'value': name} for name in sorted(formation_dict.keys())],
                            value=None,
                            clearable=False,
                            persistence=True,
                            style={'backgroundColor': '#f8f9fa', 'borderRadius': '4px'}
                        ),
                    ], width=4),
                    
                    # Position filter dropdown
                    dbc.Col([
                        html.Label("Filter by Position:", 
                                  style={'fontWeight': 'bold', 'color': '#495057', 'fontSize': '16px', 'marginBottom': '8px'}),
                        dcc.Dropdown(
                            id=f'{page_type}-position-filter',
                            options=[],
                            value=None,
                            clearable=False,
                            persistence=True,
                            style={'backgroundColor': '#f8f9fa', 'borderRadius': '4px'}
                        ),
                    ], width=4, id=f'{page_type}-position-filter-container'),
                ]),
                
                # Add checkbox for including scouting data
                dbc.Row([
                    dbc.Col([
                        dbc.Checkbox(
                            id=f'{page_type}-include-scouting',
                            label="Include Scouting Data",
                            value=False,
                            persistence=True,
                            style={'marginTop': '15px'}
                        ),
                    ], width=12),
                ]),
            ]),
        ], className="mb-4", style={'boxShadow': '0 4px 8px rgba(0,0,0,0.1)', 'border': 'none'}),
        
        # Ag-Grid to display the DataFrame
        dbc.Card([
            dbc.CardHeader(html.H4(f"{page_type.capitalize()} Data", className="card-title", 
                                  style={'color': '#0056b3', 'fontWeight': 'bold'})),
            dbc.CardBody([
                dag.AgGrid(
                    id=f'{page_type}-player-grid',
                    columnDefs=[],
                    rowData=[],
                    defaultColDef={
                        'sortable': True,
                        'filter': True,
                        'resizable': True,
                        'cellStyle': {'wordBreak': 'normal', 'textAlign': 'center'},
                        'wrapText': True,
                        'headerClass': 'centered-header',
                        'autoHeight': True,
                        'flex': 1,
                        'minWidth': 100,
                    },
                    dashGridOptions={
                        'domLayout': 'autoHeight',
                        'pagination': True,
                        'paginationPageSize': 25,
                        'columnHoverHighlight': True,
                        'multiSortKey': 'ctrl',
                        "enableCellTextSelection": True,
                        'ensureDomOrder': True,
                    },
                    columnSize='sizeToFit',
                    getRowStyle=get_row_style,
                    persistence=True,
                    style={'height': '70vh', 'width': '100%'}
                )
            ]),
        ], style={'boxShadow': '0 4px 8px rgba(0,0,0,0.1)', 'border': 'none'}),
    ], style={'padding': '20px', 'backgroundColor': '#f5f5f5', 'minHeight': '100vh'})
    
    @callback(
        [Output(f'{page_type}-position-filter', 'options'),
         Output(f'{page_type}-position-filter', 'value'),
         Output(f'{page_type}-player-grid', 'columnDefs'),
         Output(f'{page_type}-player-grid', 'rowData')],
        [Input(f'{page_type}-file-dropdown', 'value'),
         Input(f'{page_type}-formation-dropdown', 'value'),
         Input(f'{page_type}-position-filter', 'value'),
         Input(f'{page_type}-include-scouting', 'value')]
    )
    def update_data(selected_file, selected_formation, selected_position, include_scouting):
        if selected_file and selected_formation:
            if selected_formation not in formation_dict:
                return [], None, [], []
    
            rawdata = pd.read_html(selected_file, header=0, encoding="utf-8", keep_default_na=False)[0]
            
            # Always add the Data Source column to rawdata
            rawdata['Data Source'] = 'Squad'
            
            # If include_scouting is True and we're on the squad page, load scouting data
            if include_scouting and page_type == 'squad':
                # Get the directory of the selected file
                file_dir = os.path.dirname(selected_file)
                # Look for scouting files in the same directory
                scouting_files = glob.glob(os.path.join(file_dir, '*Scouting*'))
                
                if scouting_files:
                    # Use the first scouting file found
                    scouting_file = scouting_files[0]
                    scouting_data = pd.read_html(scouting_file, header=0, encoding="utf-8", keep_default_na=False)[0]
                    
                    # Mark the source of each row
                    scouting_data['Data Source'] = 'Scouting'
                    
                    # Combine the dataframes
                    rawdata = pd.concat([rawdata, scouting_data], ignore_index=True)
            
            positions_list = formation_dict[selected_formation]
            group_dfs = calculate_positions_for_file(positions_list, rawdata)
    
            position_options = [group['Selected'].iloc[0] for group in group_dfs if not group.empty]
            selected_position_group = selected_position if selected_position else position_options[0] if position_options else None
            
            df = next((group for group in group_dfs if group['Selected'].iloc[0] == selected_position_group), pd.DataFrame())
            
            # Ensure 'Data Source' column is preserved in the final dataframe
            if 'Data Source' not in df.columns and 'Data Source' in rawdata.columns:
                # Find matching rows from rawdata to get their Data Source
                if 'Name' in df.columns and 'Name' in rawdata.columns:
                    name_to_source = dict(zip(rawdata['Name'], rawdata['Data Source']))
                    df['Data Source'] = df['Name'].map(name_to_source).fillna('Squad')
            
            # Define columnDefs with dynamic sizing and centered headers
            columnDefs = [
                {
                    "headerName": i,
                    "field": i,
                    "headerClass": "centered-header",
                    "cellStyle": {"textAlign": "center"},
                    "hide": i == "Data Source"
                } for i in df.columns if i != 'Selected'
            ]
            rowData = df.drop(columns=['Selected']).to_dict('records')
    
            return position_options, selected_position_group, columnDefs, rowData
        
        return [], None, [], []
    
    return layout

# Create the squad page
layout = create_page('squad') 