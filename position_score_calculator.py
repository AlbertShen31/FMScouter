#!/usr/bin/env python
import pandas as pd
import sys
import glob
import os
from typing import List
import config.position_config as pc
from utils import calculate_score, format_position_name, parse_positions, translate_position_to_field_area
import heapq

# Calculate the score for each position
def calculate_positions(rawdata, position_dict, min_score=0):
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
    
    squads_filtered.rename(columns={'Transfer Value': 'Price', 'Salary': 'Wage', 'Personality': 'Pers', 'Left Foot': 'LFoot', 'Right Foot': 'RFoot'}, inplace=True)
    
    columns = ['Name', 'Age', 'Club', 'Price', 'Nat', 'Position', 
               'Pers', 'LFoot', 'RFoot', 'Height']
    
    # Include only columns that appear in the rawdata
    columns = [col for col in columns if col in squads_filtered.columns]

    for position, attrs in position_dict.items():
        score_col = format_position_name(position)
        squad = squads_filtered[columns + [score_col]].copy(deep=True)
        squad.sort_values(by=[score_col], ascending=False, inplace=True)
        squads.append(squad.head(100))  # Ensure you are getting the top 100 players

    # Add top score column to the first DataFrame
    squads_filtered = squads_filtered.copy()  # Create a copy to avoid SettingWithCopyWarning
    squads_filtered.loc[:, 'Top Score'] = squads_filtered[score_columns].max(axis=1)  # Calculate the top score for each row

    squads = [squads_filtered[columns + score_columns + ['Top Score']]] + squads

    return squads

def calculate_positions_for_file(formation, rawdata):
    """Calculate position scores for a given dataset and return DataFrames."""
    position_lists = pc.all_positions
    
    position_maps = {
        'Goalkeepers': [pc.gk_positions], 
        'Wide Defenders': [pc.fb_positions],
        'Center Defenders': [pc.cb_positions], 
        'Center Midfielders': [pc.dm_positions, pc.cm_positions], 
        'Wingers': [pc.am_positions, pc.w_positions],
        'Attackers': [pc.am_positions, pc.w_positions, pc.st_positions]
    }

    # Build a dictionary of selected positions
    position_dict = {}
    
    # If position_lists is already a dictionary (which it appears to be), 
    # directly iterate over its items
    for pos, attrs in position_lists.items():
        if pos.lower() in formation:
            position_dict[pos] = attrs
    

    print(position_dict.keys())
    rawdata['Field Area'] = rawdata['Position'].apply(translate_position_to_field_area)
    
    results = calculate_positions(rawdata, position_dict, min_score=0)

    # Add position group column to each DataFrame in results
    for group_name, group_df in zip(['all'] + formation, results):
        if group_name == "all":
            group_df['Selected'] = "All"
        else:
            group_df['Selected'] = format_position_name(group_name)
    
    return results

