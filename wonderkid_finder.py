import numpy as np
import os
import pandas as pd # type: ignore
import sys
import glob
from formation import spartans, france, notts_county, short_kings
from utils import format_position_name
from dotenv import load_dotenv
from position_score_calculator import calculate_positions
import position_config as pc

load_dotenv()


# Age	skd	wbs	bpdd	sva	box2	ifa	afa
# 15	10.1	10.5	9.3	10.2	10.6	10.8	10.4
# 16	10.5	11	10	10.6	11.1	11.5	11.1
# 17	10.9	11.5	10.8	11	11.6	12.2	11.8
# 18	11.1	12	11.6	11.8	12.2	12.7	12.6
# 19	11.5	12.6	11.8	12.1	12.6	13.4	13.1
# 20	11.8	13.2	12.1	12.4	12.9	13.6	13.3
# 21	12.1	13.4	12.2	12.8	13.1	14.1	13.7
# 22	12	13.5	12.2	13.1	13.5	14.3	14
# 23	12.3	13.5	12.7	13.3	13.6	14.5	14.3
# 24	12.6	13.5	13.4	13.5	13.6	14.5	14.5
# 25	13.1	13.5	13.4	13.5	13.6	14.5	14.5
# 26	13.3	13.5	13.4	13.5	13.6	14.5	14.5
# 27	13.5	13.5	13.4	13.5	13.6	14.5	14.5
# 28	13.5	13.5	13.4	13.5	13.6	14.5	14.5
# 29	13.5	13.5	13.4	13.5	13.6	14.5	14.5
# 30	13.5	13.5	13.4	13.5	13.6	14.5	14.5
# 31	13.5	13.5	13.4	13.5	13.6	14.5	14.5
# 32	13.5	13.5	13.4	13.5	13.6	14.5	14.5
# 33	13.5	13.5	13.4	13.5	13.6	14.5	14.5
# 34	13.5	13.5	13.4	13.5	13.6	14.5	14.5
# 35	13.5	13.5	13.4	13.5	13.6	14.5	14.5
# 36	13.5	13.5	13.4	13.5	13.6	14.5	14.5
# 37	13.5	13.5	13.4	13.5	13.6	14.5	14.5
# 38	13.5	13.5	13.4	13.5	13.6	14.5	14.5
# 39	13.5	13.5	13.4	13.5	13.6	14.5	14.5
# 40	13.5	13.5	13.4	13.5	13.6	14.5	14.5
# 41	13.5	13.5	13.4	13.5	13.6	14.5	14.5
# 42	13.5	13.5	13.4	13.5	13.6	14.5	14.5
# 43	13.5	13.5	13.4	13.5	13.6	14.5	14.5
# 44	13.5	13.5	13.4	13.5	13.6	14.5	14.5
# 45	13.5	13.5	13.4	13.5	13.6	14.5	14.5
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

# import matplotlib.pyplot as plt

# age = trajectory_data['Age']
# positions = ['skd', 'wbs', 'bpdd', 'sva', 'box2', 'ifa', 'afa']
# values = np.array([trajectory_data[position] for position in positions])

# # Plot each position
# ## Generate multiple plots for each position
# for idx, position in enumerate(positions):
#     plt.plot(age, values[idx], label=position)

# plt.legend()
# plt.xlabel('Age')
# plt.ylabel('Value')
# plt.title(f'Player Performance - {position}')
# # plt.show()


## Function to output position scores for based on age and position
def get_position_scores(age, position):
    idx = age - 15
    return trajectory_data[position][idx] 

# print(get_position_scores(15, 'skd'))

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

    position_lists = [pc.gk_positions, pc.fb_positions, pc.cb_positions, pc.dm_positions, pc.cm_positions, pc.am_positions, pc.w_positions, pc.st_positions]
    notts_county.append('advanced_forward_attack')
    squad = calculate_positions(squad_rawdata, notts_county, position_lists, min_score=0)
    scouting = calculate_positions(scouting_rawdata, notts_county, position_lists, min_score=0)
    

    # Calculate the trajectories for each player at each position in squad and scouting data (traj = position score/trajectory_data)
    squad_trajectories = {}
    scouting_trajectories = {}

    # print(squad[-1])


    def add_trajectory_data(df, trajectory_dict, cutoff = 100, name_col='Name'):
        for idx, row in df.iterrows():
            player_scores = []
            add_player = False

            for position in notts_county:
                p = format_position_name(position)
                age = row['Age']
                trajectory_score = round(row[p] / get_position_scores(age, p) * 100, 1)

                player_scores.append(str(trajectory_score) + '%')

                if trajectory_score >= cutoff:
                    add_player = True

            if add_player:
                trajectory_dict[row[name_col]] = player_scores
                for i, position in enumerate(notts_county):
                    df.loc[idx, f'Traj_{format_position_name(position)}'] = player_scores[i]

    # Add trajectory data to squad and scouting data
    add_trajectory_data(squad[-1], squad_trajectories, cutoff=0)
    add_trajectory_data(scouting[-1], scouting_trajectories)

    combined_trajectory_df = pd.concat([squad[-1], scouting[-1]], ignore_index=True)

    # Save the transformed DataFrame to a CSV file
    combined_trajectory_df.to_csv('spartans_trajectory_data.csv', index=False)

    # Print the updated DataFrames for verification
    # print(squad[-1])
    # print('\n\n')
    # print(scouting[-1])


if __name__ == "__main__":
    main()