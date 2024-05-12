# Ideas for future development:
# show which players could be retrained into a new position
# Show other squads scores in comparison to yours
# generate potential hidden attributes based on personality and media handling
# custom sorting for certain attributes
# better highlighting for selected rows
# create mac app to run script and open html file
# Custom filtering for each column
# Tiebreaker for players with the same score, use agreed playing time, salary, transfer value, etc.

# Foot strength mapping
foot_strength_map = {
    "Very Weak": 1, "Weak": 2, "Reasonable": 3,
    "Fairly Strong": 4, "Strong": 5, "Very Strong": 6
}



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
