# Ideas for future development:
# Load in fm tactic and show scores for each position in tactic
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
# Add automatic filtering based on best scores