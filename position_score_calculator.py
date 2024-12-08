#!/usr/bin/env python
import pandas as pd # type: ignore
import sys
import glob
import os
from typing import List
import position_config as pc
from utils import calculate_score, format_position_name, generate_html_multiple
from formation import *
from dotenv import load_dotenv
from best_xi_calculator import select_best_teams
import heapq

load_dotenv()

OUTPUT_DIR = "position_scores"

# Create output directory if it doesn't exist
os.makedirs(OUTPUT_DIR, exist_ok=True)

trajectory_data = {
    'Age': [15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45],
    'skd': [10.1, 10.5, 10.9, 11.1, 11.5, 11.8, 12.1, 12.0, 12.3, 12.6, 13.1, 13.3, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5],
    'wbs': [10.5, 11.0, 11.5, 12.0, 12.6, 13.2, 13.4, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5],
    'bpdd': [9.3, 10.0, 10.8, 11.6, 11.8, 12.1, 12.2, 12.2, 12.7, 13.4, 13.4, 13.4, 13.4, 13.4, 13.4, 13.4, 13.4, 13.4, 13.4, 13.4, 13.4, 13.4, 13.4, 13.4, 13.4, 13.4, 13.4, 13.4, 13.4, 13.4, 13.4],
    'sva': [10.2, 10.6, 11.0, 11.8, 12.1, 12.4, 12.8, 13.1, 13.3, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5],
    'box2': [10.6, 11.1, 11.6, 12.2, 12.6, 12.9, 13.1, 13.5, 13.6, 13.6, 13.6, 13.6, 13.6, 13.6, 13.6, 13.6, 13.6, 13.6, 13.6, 13.6, 13.6, 13.6, 13.6, 13.6, 13.6, 13.6, 13.6, 13.6, 13.6, 13.6, 13.6],
    'ifa': [10.8, 11.5, 12.2, 12.7, 13.4, 13.6, 14.1, 14.3, 14.5, 14.5, 14.5, 14.5, 14.5, 14.5, 14.5, 14.5, 14.5, 14.5, 14.5, 14.5, 14.5, 14.5, 14.5, 14.5, 14.5, 14.5, 14.5, 14.5, 14.5, 14.5, 14.5],
    'AF(A)': [10.4, 11.1, 11.8, 12.6, 13.1, 13.3, 13.7, 14.0, 14.3, 14.5, 14.5, 14.5, 14.5, 14.5, 14.5, 14.5, 14.5, 14.5, 14.5, 14.5, 14.5, 14.5, 14.5, 14.5, 14.5, 14.5, 14.5, 14.5, 14.5, 14.5, 14.5],
    'SK(D)': [10.1, 10.5, 10.9, 11.1, 11.5, 11.8, 12.1, 12.0, 12.3, 12.6, 13.1, 13.3, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5], 
    'WB(A)': [10.5, 11.0, 11.5, 12.0, 12.6, 13.2, 13.4, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5],
    'BPD(D)': [9.3, 10.0, 10.8, 11.6, 11.8, 12.1, 12.2, 12.2, 12.7, 13.4, 13.4, 13.4, 13.4, 13.4, 13.4, 13.4, 13.4, 13.4, 13.4, 13.4, 13.4, 13.4, 13.4, 13.4, 13.4, 13.4, 13.4, 13.4, 13.4, 13.4, 13.4],
    'VOL(A)': [10.2, 10.6, 11.0, 11.8, 12.1, 12.4, 12.8, 13.1, 13.3, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5, 13.5],
    'PF(S)': [10.4, 11.1, 11.8, 12.6, 13.1, 13.3, 13.7, 14.0, 14.3, 14.5, 14.5, 14.5, 14.5, 14.5, 14.5, 14.5, 14.5, 14.5, 14.5, 14.5, 14.5, 14.5, 14.5, 14.5, 14.5, 14.5, 14.5, 14.5, 14.5, 14.5, 14.5],
}

# Calculate the score for each position
def calculate_positions(rawdata, selected_positions, position_lists, min_score=0):
    # Build a dictionary of selected positions
    position_dict = {pos: attrs for plist in position_lists for pos, attrs in plist.items()
                     if pos.lower() in selected_positions}

    # Calculate the score for each position
    score_columns = []
    for position, attrs in position_dict.items():
        score_col = format_position_name(position)
        rawdata[score_col] = rawdata.apply(
            lambda row: calculate_score(
                row, 
                attrs['key_attrs'], attrs['green_attrs'], attrs['blue_attrs'], 
                attrs['key_weight'], attrs['green_weight'], attrs['blue_weight'], 
                attrs['divisor']
            ), axis=1)
        score_columns.append(score_col)

    # Ensure that we are not filtering out too many players
    squads_filtered = rawdata[~(rawdata[score_columns] < min_score).all(axis=1)]

    # Create and sort DataFrames for each position
    squads = []
    columns = ['Inf', 'Name', 'Age', 'Club', 'Transfer Value', 'Salary', 'Nat', 'Position', 
               'Personality', 'Left Foot', 'Right Foot', 'Height']

    squads_filtered.rename(columns={'Transfer Value': 'Price', 'Salary': 'Wage', 'Position': 'Pos', 'Personality': 'Pers', 'Left Foot': 'LFoot', 'Right Foot': 'RFoot'}, inplace=True)
    
    # Include only columns that appear in the rawdata
    columns = [col for col in columns if col in squads_filtered.columns]

    for position, attrs in position_dict.items():
        score_col = format_position_name(position)
        squad = squads_filtered[columns + [score_col]].copy(deep=True)
        squad.sort_values(by=[score_col], ascending=False, inplace=True)
        squads.append(squad.head(100))  # Ensure you are getting the top 100 players

    # squads.append(squads_filtered[columns + score_columns])

    def keep_top_5_scores(row, score_columns):
        heap = []
        for score_col in score_columns:
            score = row[score_col]
            if len(heap) < 5:
                heapq.heappush(heap, (score, score_col))
            else:
                heapq.heappushpop(heap, (score, score_col))
        top_5_columns = [col for score, col in heap]
        for col in score_columns:
            if col not in top_5_columns:
                row[col] = 0
        return row

    squads_filtered = squads_filtered.apply(lambda row: keep_top_5_scores(row, score_columns), axis=1)
    squads = [squads_filtered[columns + score_columns]] + squads

    # Add top score column to the last DataFrame
    squads[0] = squads[0].copy()  # Create a copy to avoid SettingWithCopyWarning
    squads[0].loc[:, 'Top Score'] = squads[0][score_columns].max(axis=1)  # Calculate the top score for each row

    return squads

def calculate_positions_for_file(formation, rawdata, file_path):
    """Calculate position scores for a given dataset and generate HTML output."""
    position_lists = [pc.gk_positions, pc.fb_positions, pc.cb_positions, pc.dm_positions, 
                      pc.cm_positions, pc.am_positions, pc.w_positions, pc.st_positions]
    
    results = calculate_positions(rawdata, formation, position_lists, min_score=0)
    file_name = str(os.path.splitext(os.path.basename(file_path))[0])
    output_path = os.path.join(OUTPUT_DIR, file_name)
    generate_html_multiple(results, ['all'] + formation, output_path)

    # Add position group column to each DataFrame in results
    for group_name, group_df in zip(['all'] + formation, results):
        if group_name == "all":
            group_df['Position'] = "All"
        else:
            group_df['Position'] = format_position_name(group_name)
        
    return results

def calculate_all_positions(rawdata, file_path):
    """Calculate position scores for all positions and return a list of DataFrames for each position group."""
    position_lists = [pc.gk_positions, pc.fb_positions, pc.cb_positions, pc.dm_positions, 
                      pc.cm_positions, pc.am_positions, pc.w_positions, pc.st_positions]
    
    # Calculate scores for all positions
    results = calculate_positions(rawdata, ['all'], position_lists, min_score=0)
    
    # Add position group column to each DataFrame in results
    for group_name, group_df in zip(['all'] + ['gk', 'fb', 'cb', 'dm', 'cm', 'am', 'w', 'st'], results):
        group_df['Position'] = format_position_name(group_name)
    
    return results

def main():
    directory_path = os.getenv('FM_24_path')
    formation_input = sys.argv[1] if len(sys.argv) > 1 else input("Please type in the team name: ").strip()
    run_scouting = True if len(sys.argv) <= 2 else sys.argv[2].lower() in ['y', 'yes', 'true', '1']

    if formation_input not in formation_dict and formation_input != 'all':
        print(f"Formation '{formation_input}' not found. Available formations: {', '.join(formation_dict.keys())}")
        return

    # Process squad data
    squad_files = glob.glob(os.path.join(directory_path, '**/*Squad*'), recursive=True)
    if squad_files:
        squad_file = max(squad_files, key=os.path.getctime)
        squad_rawdata = pd.read_html(squad_file, header=0, encoding="utf-8", keep_default_na=False)[0]
        
        if formation_input == 'all':
            squad_results = calculate_all_positions(squad_rawdata, squad_file)
        else:
            squad_results = calculate_positions_for_file(formation_dict[formation_input], squad_rawdata, squad_file)
            print(squad_results[-1])

    # Process scouting data if enabled
    if run_scouting:
        scouting_files = glob.glob(os.path.join(directory_path, '**/*Scouting*'), recursive=True)
        if scouting_files:
            scouting_file = max(scouting_files, key=os.path.getctime)
            scouting_rawdata = pd.read_html(scouting_file, header=0, encoding="utf-8", keep_default_na=False)[0]
            
            print('\n\nScouting Results:')
            if formation_input == 'all':
                scouting_results = calculate_all_positions(scouting_rawdata, scouting_file)
            else:
                scouting_results = calculate_positions_for_file(formation_dict[formation_input], scouting_rawdata, scouting_file)
                print(scouting_results[-1])
        else:
            print("No scouting files found in the specified directory.")

if __name__ == "__main__":
    main()

