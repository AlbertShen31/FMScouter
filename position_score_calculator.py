#!/usr/bin/env python
import pandas as pd
import sys
import glob
import os
from typing import List
import position_config as pc
from utils import calculate_score, format_position_name
from formation import *
import heapq

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
    """Calculate position scores for a given dataset and return DataFrames."""
    position_lists = [pc.gk_positions, pc.fb_positions, pc.cb_positions, pc.dm_positions, 
                      pc.cm_positions, pc.am_positions, pc.w_positions, pc.st_positions]
    
    results = calculate_positions(rawdata, formation, position_lists, min_score=0)

    # Add position group column to each DataFrame in results
    for group_name, group_df in zip(['all'] + formation, results):
        if group_name == "all":
            group_df['Position'] = "All"
        else:
            group_df['Position'] = format_position_name(group_name)
    
    return results

