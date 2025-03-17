import os
import glob
import pandas as pd
from dash import dcc, html, callback, Input, Output, register_page, State
from dotenv import load_dotenv
from config.formation_config import formation_dict
from position_score_calculator import calculate_positions_for_file
import dash_ag_grid as dag
import dash_bootstrap_components as dbc
import dash

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
                "condition": "params.data.Club && params.data.Club === params.context.teamName",
                "style": {"backgroundColor": "dodgerblue", "color": "white"},
            },
            {
                "condition": "params.data.Club && params.data.Club !== params.context.teamName && params.data.Club === ''",
                "style": {"backgroundColor": "limegreen", "color": "black"},
            },
            {
                "condition": "params.data.Club && params.data.Club !== params.context.teamName && params.data.Club !== ''",
                "style": {"backgroundColor": "hotpink", "color": "white"},
            },
        ],
        "defaultStyle": {"backgroundColor": "grey", "color": "white"},
    }
    
    # Define the layout for the page
    layout = html.Div([
        html.H1(f"{page_type.capitalize()} Data View", 
                style={'textAlign': 'center', 'marginBottom': '30px', 'color': '#333', 'fontSize': '36px', 'fontWeight': 'bold'}),
        
        # Add a component to display the team name
        html.Div(id=f'{page_type}-team-display', 
                 style={'textAlign': 'center', 'marginBottom': '20px', 'fontSize': '24px', 'fontWeight': 'bold', 'color': '#0056b3'}),
        
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
                
                # Add column visibility controls
                dbc.Row([
                    dbc.Col([
                        html.Div([
                            html.H5("Column Visibility", 
                                   style={'fontWeight': 'bold', 'color': '#495057', 'fontSize': '16px', 'marginTop': '15px'}),
                            html.Div(id=f'{page_type}-column-toggles', style={'display': 'flex', 'flexWrap': 'wrap', 'gap': '10px'})
                        ])
                    ], width=12),
                ]),
            ]),
        ], className="mb-4", style={'boxShadow': '0 4px 8px rgba(0,0,0,0.1)', 'border': 'none'}),
        
        # Ag-Grid to display the DataFrame
        dbc.Card([
            dbc.CardHeader(html.H4(f"{page_type.capitalize()} Data", className="card-title", 
                                  style={'color': '#0056b3', 'fontWeight': 'bold'})),
            dbc.CardBody([
                # Add loading spinner around the AgGrid
                dcc.Loading(
                    id=f"{page_type}-loading",
                    type="circle", # Options: "graph", "cube", "circle", "dot", or "default"
                    color="#0056b3",
                    children=[
                        # Message to show when no data is loaded
                        html.Div(
                            id=f"{page_type}-no-data-message",
                            children=[
                                html.H5("No data loaded", style={'textAlign': 'center', 'color': '#6c757d', 'marginTop': '50px'}),
                                html.P("Please select a file and formation to view data", 
                                      style={'textAlign': 'center', 'color': '#6c757d'})
                            ],
                            style={'display': 'block', 'height': '200px'}
                        ),
                        # The AgGrid component
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
                                'paginationPageSize': 50,
                                'columnHoverHighlight': True,
                                'multiSortKey': 'ctrl',
                                "enableCellTextSelection": True,
                                'ensureDomOrder': True,
                                'context': {'teamName': ''},  # Initialize with empty team name
                            },
                            columnSize='sizeToFit',
                            getRowStyle=get_row_style,
                            persistence=True,
                            persistence_type='session',
                            persisted_props=['columnDefs', 'rowData', 'dashGridOptions'],
                            style={'height': '70vh', 'width': '100%'}
                        )
                    ]
                )
            ]),
        ], style={'boxShadow': '0 4px 8px rgba(0,0,0,0.1)', 'border': 'none'}),
    ], style={'padding': '20px', 'backgroundColor': '#f5f5f5', 'minHeight': '100vh'})
    
    @callback(
        Output(f'{page_type}-column-toggles', 'children'),
        [Input(f'{page_type}-player-grid', 'columnDefs')]
    )
    def create_column_toggles(column_defs):
        if not column_defs:
            return []
        
        # Create a checkbox for each column except 'Data Source'
        checkboxes = []
        for col in column_defs:
            if col['field'] != 'Data Sourcee':
                checkboxes.append(
                    dbc.Checkbox(
                        id={'type': f'{page_type}-column-toggle', 'index': col['field']},
                        label=col['field'],
                        value=not col.get('hide', False),
                        persistence=True,
                        className='column-toggle-checkbox'
                    )
                )
        
        return checkboxes
    
    @callback(
        Output(f'{page_type}-player-grid', 'columnDefs', allow_duplicate=True),
        [Input({'type': f'{page_type}-column-toggle', 'index': dash.ALL}, 'value'),
         Input({'type': f'{page_type}-column-toggle', 'index': dash.ALL}, 'id')],
        [State(f'{page_type}-player-grid', 'columnDefs')],
        prevent_initial_call=True
    )
    def update_column_visibility(values, ids, column_defs):
        if not column_defs or not ids or not values:
            return dash.no_update
        
        # Create a dictionary mapping column field to visibility
        visibility = {id_obj['index']: value for id_obj, value in zip(ids, values)}
        
        # Update the hide property for each column
        for col in column_defs:
            if col['field'] in visibility:
                col['hide'] = not visibility[col['field']]
        
        return column_defs
    
    @callback(
        [Output(f'{page_type}-position-filter', 'options'),
         Output(f'{page_type}-position-filter', 'value'),
         Output(f'{page_type}-player-grid', 'columnDefs'),
         Output(f'{page_type}-player-grid', 'rowData'),
         Output(f'{page_type}-team-display', 'children'),
         Output(f'{page_type}-player-grid', 'dashGridOptions'),
         Output(f'{page_type}-no-data-message', 'style')],
        [Input(f'{page_type}-file-dropdown', 'value'),
         Input(f'{page_type}-formation-dropdown', 'value'),
         Input(f'{page_type}-position-filter', 'value'),
         Input(f'{page_type}-include-scouting', 'value')],
        [State(f'{page_type}-player-grid', 'rowData'),
         State(f'{page_type}-player-grid', 'columnDefs'),
         State(f'{page_type}-player-grid', 'dashGridOptions')]
    )
    def update_data(selected_file, selected_formation, selected_position, include_scouting, 
                   existing_row_data, existing_column_defs, existing_grid_options):
        # Style to hide the no-data message when data is loaded
        hide_message_style = {'display': 'none'}
        # Style to show the no-data message when no data is loaded
        show_message_style = {'display': 'block', 'height': '200px'}
        
        print(f"existing_row_data: {existing_row_data}")
        print(f"existing_column_defs: {existing_column_defs}")
        print(f"existing_grid_options: {existing_grid_options}")

        # Check if there's already data loaded due to persistence
        if not selected_file and not selected_formation and existing_row_data and existing_column_defs:
            # Extract position options from existing data if available
            position_options = []
            if existing_row_data and 'Selected' in existing_row_data[0]:
                position_options = list(set(row.get('Selected', '') for row in existing_row_data if 'Selected' in row))
            
            # Get team name from existing grid options
            team_name = ""
            if existing_grid_options and 'context' in existing_grid_options and 'teamName' in existing_grid_options['context']:
                team_name = existing_grid_options['context']['teamName']
            
            team_display = f"Team: {team_name}" if team_name else ""
            
            # Keep existing data and hide the no-data message
            return position_options, selected_position, existing_column_defs, existing_row_data, team_display, existing_grid_options, hide_message_style
        
        if selected_file and selected_formation:
            if selected_formation not in formation_dict:
                return [], None, [], [], "", {'context': {'teamName': ''}}, show_message_style
    
            rawdata = pd.read_html(selected_file, header=0, encoding="utf-8", keep_default_na=False)[0]
            
            # Extract team name from the dataframe
            # Check if 'Club' column exists and has consistent values for squad players
            if 'Club' in rawdata.columns:
                # Get the most common club name in the dataframe
                team_name = rawdata['Club'].value_counts().idxmax()
                team_display = f"Team: {team_name}"
            else:
                # Fallback to filename if Club column doesn't exist
                file_name = os.path.basename(selected_file)
                team_name = file_name.split('_')[0] if '_' in file_name else "Team"
                team_display = f"Team: {team_name}"
            
            # Always add the Data Source column to rawdata
            rawdata['Data Source'] = 'Squad'
            
            # If include_scouting is True and we're on the squad page, load scouting data
            if include_scouting and page_type == 'squad':
                # Get the directory and base filename of the selected file
                file_dir = os.path.dirname(selected_file)
                base_filename = os.path.basename(selected_file)
                
                # Replace '_Squad' with '_Scouting' in the filename
                scouting_filename = base_filename.replace('_Squad', '_Scouting')
                scouting_file_path = os.path.join(file_dir, scouting_filename)
                
                # Check if the matching scouting file exists
                if os.path.exists(scouting_file_path):
                    scouting_data = pd.read_html(scouting_file_path, header=0, encoding="utf-8", keep_default_na=False)[0]
                    
                    # Mark the source of each row
                    scouting_data['Data Source'] = 'Scouting'
                    
                    # Combine the dataframes
                    rawdata = pd.concat([rawdata, scouting_data], ignore_index=True)
                else:
                    # Fallback: Look for any scouting files in the same directory
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
                    "hide": i == "Data Source",
                    # Set specific widths for Name, Position, Club, and Price columns
                    "minWidth": 200 if i == "Name" else 
                               150 if i == "Position" or i == "Club" or i == "Price" else 100,
                    "flex": 2 if i == "Name" else 
                           1.5 if i == "Position" or i == "Club" or i == "Price" else 1
                } for i in df.columns if i != 'Selected'
            ]
            rowData = df.drop(columns=['Selected']).to_dict('records')
    
            # Update dashGridOptions with team context
            dashGridOptions = {
                'domLayout': 'autoHeight',
                'pagination': True,
                'paginationPageSize': 25,
                'columnHoverHighlight': True,
                'multiSortKey': 'ctrl',
                "enableCellTextSelection": True,
                'ensureDomOrder': True,
                'context': {'teamName': team_name},  # Set the team name in context
            }
    
            return position_options, selected_position_group, columnDefs, rowData, team_display, dashGridOptions, hide_message_style
        
        # If we reach here, there's no data to display
        # Check if there's existing data from persistence
        if existing_row_data and len(existing_row_data) > 0 and existing_column_defs and len(existing_column_defs) > 0:
            # Extract position options from existing data if available
            position_options = []
            if 'Selected' in existing_row_data[0]:
                position_options = list(set(row.get('Selected', '') for row in existing_row_data if 'Selected' in row))
            
            # Get team name from existing grid options
            team_name = ""
            if existing_grid_options and 'context' in existing_grid_options and 'teamName' in existing_grid_options['context']:
                team_name = existing_grid_options['context']['teamName']
            
            team_display = f"Team: {team_name}" if team_name else ""
            
            # Keep existing data and hide the no-data message
            return position_options, selected_position, existing_column_defs, existing_row_data, team_display, existing_grid_options, hide_message_style
        
        # No data at all
        return [], None, [], [], "", {'context': {'teamName': ''}}, show_message_style
    
    return layout

# Create the squad page
layout = create_page('squad') 