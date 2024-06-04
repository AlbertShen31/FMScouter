#!/usr/bin/env python
import pandas as pd # type: ignore
import sys
import glob
import os
from typing import List
import position_config as pc
from utils import calculate_score, format_position_name, generate_html_multiple
from formation import spartans, france, notts_county, short_kings
from dotenv import load_dotenv
from best_xi_calculator import select_best_teams
import heapq

load_dotenv()

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

    # squads.append(squads_filtered[columns + score_columns])

    def get_top_n_scores(row, n=3):
        heap = []
        for position in score_columns:
            score = row[position]
            if len(heap) < n:
                heapq.heappush(heap, (score, position))
            else:
                heapq.heappushpop(heap, (score, position))
        return sorted(heap, reverse=True)  # Return top scores in descending order

    for i in range(1, 4):
        squads_filtered[f'best_pos{i}'] = squads_filtered.apply(lambda row: get_top_n_scores(row)[i-1][1], axis=1)
        squads_filtered[f'best_pos{i}_score'] = squads_filtered.apply(lambda row: get_top_n_scores(row)[i-1][0], axis=1)
        
    squads.append(squads_filtered[columns + ['best_pos1', 'best_pos1_score', 'best_pos2', 'best_pos2_score', 'best_pos3', 'best_pos3_score']])

    return squads



def calculate_formation(formation, squad_rawdata, scouting_rawdata, squad_file, scouting_file):
    position_lists = [pc.gk_positions, pc.fb_positions, pc.cb_positions, pc.dm_positions, pc.cm_positions, pc.am_positions, pc.w_positions, pc.st_positions]
    squad = calculate_positions(squad_rawdata, formation, position_lists, min_score=0)
    scouting = calculate_positions(scouting_rawdata, formation, position_lists, min_score=0)

    generate_html_multiple(squad, formation + ["all"], str(os.path.splitext(os.path.basename(squad_file))[0]))
    generate_html_multiple(scouting, formation + ["all"], str(os.path.splitext(os.path.basename(scouting_file))[0]))



def main():
    directory_path = os.getenv('FM_24_path')

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

    if len(sys.argv) > 1:
        user_input = sys.argv[1]
    else:
        user_input = ""
        while not user_input.strip():
            user_input = input("Please type in the team name: ")

    if user_input == "spartans":
        calculate_formation(spartans, squad_rawdata, scouting_rawdata, squad_file, scouting_file)
    elif user_input == "france":
        calculate_formation(france, squad_rawdata, scouting_rawdata, squad_file, scouting_file)
    elif user_input == "notts_county":
        calculate_formation(notts_county, squad_rawdata, scouting_rawdata, squad_file, scouting_file)
    elif user_input == "gronigen":
        calculate_formation(short_kings, squad_rawdata, scouting_rawdata, squad_file, scouting_file)

    if len(sys.argv) > 2:
        min_score = int(sys.argv[2])
        select_best_teams(squad_rawdata, min_score)
    
if __name__ == "__main__":
    main()

