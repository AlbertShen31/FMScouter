#!/usr/bin/env python
import pandas as pd # type: ignore
import glob
import os
from typing import List
import position_config as pc
from utils import calculate_score, format_position_name, generate_html_multiple, select_best_teams
from formation import spartans, france, notts_county, short_kings

position_lists = [pc.gk_positions, pc.fb_positions, pc.cb_positions, pc.dm_positions, pc.cm_positions, pc.am_positions, pc.w_positions, pc.st_positions]

directory_path = os.environ.get('FM_24_path')

# Find the most recent file in the specified folder
squad_files = glob.glob(os.path.join(directory_path, '**/*Squad*'), recursive=True)
squad_file = max(squad_files, key=os.path.getctime)

scouting_files = glob.glob(os.path.join(directory_path, '**/*Scouting*'), recursive=True)
scouting_file = max(scouting_files, key=os.path.getctime)

# Read HTML file exported by FM - in this case, an example of an output from the squad page
squad_rawdata_list = pd.read_html(squad_file, header=0, encoding="utf-8", keep_default_na=False)
scouting_rawdata_list = pd.read_html(scouting_file, header=0, encoding="utf-8", keep_default_na=False)

squad_rawdata = squad_rawdata_list[0]
scouting_rawdata = scouting_rawdata_list[0]


# Calculate the score for each position
def calculate_positions(rawdata, selected_positions, min_score=0):
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

    squads_filtered = rawdata[~(rawdata[score_columns] < min_score).all(axis=1)]

    # Create and sort DataFrames for each position
    squads = []
    columns = ['Inf', 'Name', 'Age', 'Club', 'Transfer Value', 'Salary', 'Nat', 'Position', 
               'Personality', 'Left Foot', 'Right Foot', 'Height']
    for position, attrs in position_dict.items():
        score_col = format_position_name(position)
        squad = squads_filtered[columns + [score_col]].copy(deep=True)
        squad.sort_values(by=[score_col], ascending=False, inplace=True)
        squads.append(squad.head(100))

    squads.append(squads_filtered[columns + score_columns])

    return squads



def calculate_formation(formation):
    squad = calculate_positions(squad_rawdata, formation, min_score=0)
    scouting = calculate_positions(scouting_rawdata, formation, min_score=0)

    generate_html_multiple(squad, formation + ["all"], str(os.path.splitext(os.path.basename(squad_file))[0]))
    generate_html_multiple(scouting, formation + ["all"], str(os.path.splitext(os.path.basename(scouting_file))[0]))


# calculate_formation(spartans)
# calculate_formation(france)
# calculate_formation(notts_county)
calculate_formation(short_kings)