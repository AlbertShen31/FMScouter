#!/usr/bin/env python

# Import necessary libraries
import pandas as pd
import glob
import os
from typing import List
import position_config as pc
from utils import format_position_name, generate_html_multiple, select_best_teams

position_score_lists = [pc.gk_positions, pc.fb_positions, pc.cb_positions, pc.dm_positions, pc.cm_positions, pc.am_positions, pc.w_positions, pc.st_positions]

directory_path = '/Users/albertwshen/Library/Application Support/Sports Interactive/Football Manager 2024/all_attributes'

# Find the most recent file in the specified folder
list_of_files = glob.glob(os.path.join(directory_path, '**/*Squad*'), recursive=True)
squad_file = max(list_of_files, key=os.path.getctime)

list_of_files = glob.glob(os.path.join(directory_path, '**/*Scouting*'), recursive=True)
scouting_file = max(list_of_files, key=os.path.getctime)

# Read HTML file exported by FM - in this case, an example of an output from the squad page
# This reads as a list, not a dataframe
squad_rawdata_list = pd.read_html(squad_file, header=0, encoding="utf-8", keep_default_na=False)


# Calculate the score for each position
def calculate_score(data, key_attrs, green_attrs, blue_attrs, key_weight, green_weight, blue_weight, divisor):
    key_score = sum(data[attr] for attr in key_attrs)
    green_score = sum(data[attr] for attr in green_attrs)
    blue_score = sum(data[attr] for attr in blue_attrs)
    
    total_score = (key_score * key_weight + green_score * green_weight + blue_score * blue_weight) / divisor
    return round(total_score, 1)

squad_rawdata = squad_rawdata_list[0]


# Calculate the score for each position
def calculate_positions(squad_rawdata, selected_positions, position_lists, min_score=0):
    # Build a dictionary of selected positions
    position_dict = {pos: attrs for plist in position_lists for pos, attrs in plist.items()
                     if pos.lower() in selected_positions}

    # Calculate the score for each position
    score_columns = []
    for position, attrs in position_dict.items():
        score_col = format_position_name(position)
        squad_rawdata[score_col] = squad_rawdata.apply(
            lambda row: calculate_score(
                row, 
                attrs['key_attrs'], attrs['green_attrs'], attrs['blue_attrs'], 
                attrs['key_weight'], attrs['green_weight'], attrs['blue_weight'], 
                attrs['divisor']
            ), axis=1)
        score_columns.append(score_col)

    squads_filtered = squad_rawdata[~(squad_rawdata[score_columns] < min_score).all(axis=1)]

    # Create and sort DataFrames for each position
    squads = []
    columns = ['Inf', 'Name', 'Age', 'Club', 'Transfer Value', 'Salary', 'Nat', 'Position', 'Personality', 'Media Handling', 'Left Foot', 'Right Foot', 'Height']
    for position, attrs in position_dict.items():
        score_col = format_position_name(position)
        squad = squads_filtered[columns + [score_col]].copy(deep=True)
        squad.sort_values(by=[score_col], ascending=False, inplace=True)
        squads.append(squad.head(100))

    squads.append(squads_filtered[columns + score_columns])

    return squads


def calculate_all_positions(squad_rawdata, position_list):
    # Calculate the score for each position
    for positions in position_list:
        for position, attrs in positions.items():
            squad_rawdata[f'{format_position_name(position)}'] = squad_rawdata.apply(
                lambda row: calculate_score(row, attrs['key_attrs'], attrs['green_attrs'], attrs['blue_attrs'], attrs['key_weight'], 
                                            attrs['green_weight'], attrs['blue_weight'], attrs['divisor']), axis=1)

    squads = []
    for positions in position_score_lists:
        squad = squad_rawdata[['Inf', 'Name', 'Age', 'Club', 'Transfer Value', 'Salary', 'Nat', 'Position', 'Personality', 'Media Handling', 'Left Foot', 'Right Foot', 'Height']]
        for position, attrs in positions.items():
            squad = squad.join(squad_rawdata[[f'{format_position_name(position)}']])
        squads.append(squad)

    return squads

# selected_positions = ['sweeper_keeper_defend', 'inverted_wing_back_attack', 'ball_playing_defender_defend', 'defensive_midfielder_support', 'defensive_winger_support', 'inside_forward_attack', 'advanced_forward_attack']
# selected_positions = ['sweeper_keeper_defend', 'wing_back_attack', 'ball_playing_defender_defend', 'ball_winning_midfielder_defend', 'attacking_midfielder_support', 'advanced_forward_attack']
# selected_positions = ['sweeper_keeper_defend', 'wing_back_attack', 'ball_playing_defender_defend', 'central_midfielder_defend', 'central_midfielder_support', 'advanced_playmaker_support', 'advanced_forward_attack']
selected_positions = ['sweeper_keeper_defend', 'wing_back_attack', 'ball_playing_defender_defend', 'segundo_volante_attack', 'pressing_forward_support']

squads = calculate_positions(squad_rawdata, selected_positions, position_score_lists, min_score=0)

# squads = calculate_all_positions(position_lists)

generate_html_multiple(squads, selected_positions + ["all"], str(os.path.splitext(os.path.basename(squad_file))[0]))


# Ideas for future development:
# Load in fm tactic and show scores for each position in tactic
# Best XI for you squad based on tactic
# show which players could be retrained into a new position
# Show other squads scores in comparison to yours
# generate potential hidden attributes based on personality and media handling
# custom sorting for certain attributes
# better highlighting for selected rows
# create mac app to run script and open html file
# Custom filtering for each column

# Foot strength mapping
foot_strength_map = {
    "Very Weak": 1, "Weak": 2, "Reasonable": 3,
    "Fairly Strong": 4, "Strong": 5, "Very Strong": 6
}



invert_left = 'Reasonable'
invert_right = 'Reasonable'
wing_left = 'Strong'
wing_right = 'Strong'

# Updated position counts
position_requirements = {
    "SK(D)": {"count": 1},
    "IWB(A)": {"count": 2, "foot_strength": [{"min_left_foot": invert_left}, {"min_right_foot": invert_right}]},
    "BPD(D)": {"count": 2},
    "DM(S)": {"count": 1},
    "DW(S)": {"count": 2, "foot_strength": [{"min_left_foot": wing_left}, {"min_right_foot": invert_right}]},
    "IF(A)": {"count": 2, "foot_strength": [{"min_left_foot": invert_left}, {"min_right_foot": invert_right}]},
    "AF(A)": {"count": 1}
}

# position_requirements = {
#     "SK(D)": {"count": 1},
#     "WB(A)": {"count": 2},
#     "BPD(D)": {"count": 2},
#     "BWM(D)": {"count": 1},
#     "AM(S)": {"count": 2},
#     "AF(A)": {"count": 3}
# }

# Locked players (example)
locked_players = {
    "Andy Troncoso": ["IWB(A)"],
    "Maurizio Gardoni": ["IWB(A)"],
}

# Excluded positions (example)
excluded_positions = {
    "Gabriel Recoba": ["IF(A)"],
    "Gustavo Centurión": ["DM(S)"],
    "Isah Igwe": ["IF(A)"],
    "Pedro": ["DM(S)"],
    "Ryan McAulay": ["IWB(A)"],
    "Carlos Miranda": ["IWB(A)"],
    "Leonard Nafiu": ["IF(A)"],
    "Yun Tae-Min": ["DM(S)"],
    "Kieran Tierney": ["DM(S)", "DW(S)"],
    "José Luis Moré": ["DM(S)"],
}

global_exclusions = ["Cheng Hao", "Colin Hanna"]

# # Assuming squad_rawdata is your DataFrame
# (first_team, first_team_avg_score), (second_team, second_team_avg_score), (third_team, third_team_avg_score) = select_best_teams(squad_rawdata, position_requirements, 10, locked_players, excluded_positions, global_exclusions)

# print("First Eleven:", first_team)
# print("First Eleven Average Score:", first_team_avg_score)
# print("\nSecond Eleven:", second_team)
# print("Second Eleven Average Score:", second_team_avg_score)
# print("\nThird Eleven:", third_team)
# print("Third Eleven Average Score:", third_team_avg_score)

## TODO:
# Tiebreaker for players with the same score, use agreed playing time, salary, transfer value, etc.