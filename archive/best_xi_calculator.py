# Ideas for future development:
# Load in fm tactic and show scores for each position in tactic
# show which players could be retrained into a new position
# Show other squads scores in comparison to yours
# generate potential hidden attributes based on personality and media handling
# custom sorting for certain attributes
# better highlighting for selected rows
# create mac app to run script and open html file
# Custom filtering for each column
import pandas as pd # type: ignore

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


def select_best_teams(squad_rawdata, min_score=0, locked_players={}, excluded_positions={}, global_exclusions=[]):
    # Use the existing DataFrame
    df = squad_rawdata.copy()

    # Print the top 3 postions scores from position_requirements for each player
    for player in df['Name']:
        player_scores = []
        for position in position_requirements.keys():
            score = df.loc[df['Name'] == player, position].values[0]
            player_scores.append((position, score))
        player_scores.sort(key=lambda x: x[1], reverse=True)
        print(player, player_scores[:5])

    # Apply exclusions and adjustments based on locked_players, excluded_positions, and global_exclusions
    for player in global_exclusions:
        for position in position_requirements.keys():
            df.loc[df['Name'] == player, position] = 0

    for player, positions in locked_players.items():
        if not isinstance(positions, list):
            positions = [positions]
        for position in position_requirements.keys():
            if position not in positions:
                df.loc[df['Name'] == player, position] = 0

    for player, positions in excluded_positions.items():
        for position in positions:
            df.loc[df['Name'] == player, position] = 0

    # Function to select a team
    def select_team(df):
        best_players = {position: [] for position in position_requirements}
        total_score = 0

        # Flatten the DataFrame to have one row per player-position combination
        melted_df = df.melt(id_vars=["Name", "Left Foot", "Right Foot"], value_vars=position_requirements.keys(), var_name="Position", value_name="Score")
        
        # Filter for players with a score above min_score
        melted_df = melted_df[melted_df['Score'] >= min_score]

        # Sort by Score in descending order
        melted_df = melted_df.sort_values(by="Score", ascending=False)

        # Iterate over each player-position combination
        for _, row in melted_df.iterrows():
            position = row['Position']
            player_name = row['Name']
            score = row['Score']

            # Check if the player can be added to the position
            if len(best_players[position]) < position_requirements[position]['count'] and player_name not in [p for players in best_players.values() for p, _ in players]:
                best_players[position].append((player_name, score))
                total_score += score
                # Exclude this player from further consideration in other positions
                melted_df = melted_df[melted_df['Name'] != player_name]

        # Fill empty positions with placeholder
        for position, players in best_players.items():
            while len(players) < position_requirements[position]['count']:
                players.append(("Empty Player", 0))

        # Calculate the average score
        average_score = total_score / sum(req['count'] for req in position_requirements.values())

        return best_players, average_score


    # Select the first team
    first_team, first_team_avg_score = select_team(df)

    # Remove players of the first team from the DataFrame
    players_in_first_team = [player for players in first_team.values() for player, _ in players]
    df = df[~df['Name'].isin(players_in_first_team)]

    # Select the second team
    second_team, second_team_avg_score = select_team(df)

    # Remove players of the second team from the DataFrame
    players_in_second_team = [player for players in second_team.values() for player, _ in players]
    df = df[~df['Name'].isin(players_in_second_team)]

    # Select the third team
    third_team, third_team_avg_score = select_team(df)

    print("First Eleven:", first_team)
    print("First Eleven Average Score:", first_team_avg_score)
    print("\nSecond Eleven:", second_team)
    print("Second Eleven Average Score:", second_team_avg_score)
    print("\nThird Eleven:", third_team)
    print("Third Eleven Average Score:", third_team_avg_score)




## TODO:
# Tiebreaker for players with the same score, use agreed playing time, salary, transfer value, etc.
# Add automatic filtering based on best scores