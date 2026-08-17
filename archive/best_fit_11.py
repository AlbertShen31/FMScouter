import random
import pandas as pd
from deap import base, creator, tools, algorithms

# Updated data setup
data = {
    'Player': [
        'Jonathan Mohammed', 'Maximiliano Signorelli', 'Guilherme Toda', 'Lisandro Machado', 'Alex Ockmonek',
        'Kevin', 'Rogério Rosano', 'Antonio Usai', 'Hrvoje Mulac', 'Luis Uribe',
        'Kim Gwangyun', 'Fabio Schwarz', 'Pedro Henrique', 'Kadher Gnakabi', 'Eustacio Luis',
        'Craig Evans', 'Daniel Alzamendi', 'Ian Corcoran', 'Brandon Mason', 'Gareth McAllister',
        'Keirrison Cruz', 'Mario Gallinetta', 'Juan Carlos Mendoza', 'Mario Pérez',
    ],
    'Top_Positions': [
        [('DM(S)', 15.8), ('BPD(D)', 15.7), ('DW(S)', 15.0), ('IWB(A)', 14.8), ('IF(A)', 14.4)],
        [('AF(A)', 15.9), ('IF(A)', 15.4), ('IWB(A)', 13.9), ('DW(S)', 13.8), ('DM(S)', 12.8)],
        [('IF(A)', 15.4), ('IWB(A)', 15.0), ('AF(A)', 15.0), ('DW(S)', 14.8), ('DM(S)', 13.8)],
        [('AF(A)', 15.9), ('IF(A)', 15.3), ('DW(S)', 14.0), ('IWB(A)', 13.6), ('DM(S)', 12.7)],
        [('IF(A)', 14.6), ('DW(S)', 14.4), ('AF(A)', 14.0), ('IWB(A)', 13.9), ('DM(S)', 13.2)],
        [('IF(A)', 14.8), ('DW(S)', 14.7), ('IWB(A)', 14.5), ('DM(S)', 14.5), ('AF(A)', 14.0)],
        [('IF(A)', 14.5), ('DW(S)', 14.1), ('AF(A)', 14.1), ('IWB(A)', 13.3), ('DM(S)', 12.6)],
        [('IWB(A)', 14.1), ('IF(A)', 14.0), ('DW(S)', 13.8), ('DM(S)', 13.6), ('AF(A)', 13.5)],
        [('IWB(A)', 13.7), ('BPD(D)', 13.7), ('DM(S)', 13.7), ('DW(S)', 13.5), ('IF(A)', 13.3)],
        [('BPD(D)', 14.5), ('DM(S)', 14.1), ('IWB(A)', 13.4), ('DW(S)', 13.2), ('IF(A)', 12.7)],
        [('DW(S)', 13.7), ('IF(A)', 13.7), ('DM(S)', 13.4), ('IWB(A)', 13.3), ('AF(A)', 13.0)],
        [('IF(A)', 13.7), ('DM(S)', 13.6), ('DW(S)', 13.6), ('IWB(A)', 13.4), ('AF(A)', 13.4)],
        [('DM(S)', 14.9), ('DW(S)', 13.9), ('IWB(A)', 13.6), ('IF(A)', 12.9), ('BPD(D)', 12.6)],
        [('IF(A)', 13.7), ('AF(A)', 13.5), ('DW(S)', 13.1), ('IWB(A)', 12.9), ('DM(S)', 12.2)],
        [('IF(A)', 13.3), ('DW(S)', 13.1), ('AF(A)', 13.1), ('IWB(A)', 13.0), ('DM(S)', 12.4)],
        [('DM(S)', 14.1), ('BPD(D)', 13.0), ('DW(S)', 12.5), ('IWB(A)', 12.4), ('IF(A)', 12.0)],
        [('BPD(D)', 13.6), ('DM(S)', 13.1), ('IWB(A)', 12.5), ('DW(S)', 12.3), ('IF(A)', 12.0)],
        [('DW(S)', 14.2), ('DM(S)', 13.7), ('IWB(A)', 13.5), ('IF(A)', 13.3), ('AF(A)', 12.6)],
        [('AF(A)', 14.2), ('IF(A)', 13.8), ('DW(S)', 12.6), ('IWB(A)', 12.0), ('DM(S)', 11.4)],
        [('AF(A)', 14.9), ('IF(A)', 14.2), ('IWB(A)', 12.7), ('DW(S)', 12.4), ('DM(S)', 11.3)],
        [('IF(A)', 14.5), ('AF(A)', 14.4), ('DW(S)', 13.9), ('IWB(A)', 13.4), ('DM(S)', 12.6)],
        [('IWB(A)', 13.7), ('IF(A)', 13.5), ('DW(S)', 13.0), ('AF(A)', 13.0), ('DM(S)', 12.9)],
        [('IF(A)', 13.5), ('IWB(A)', 13.3), ('DW(S)', 13.2), ('AF(A)', 13.0), ('DM(S)', 12.7)],
        [('AF(A)', 13.9), ('IF(A)', 13.8), ('DW(S)', 12.1), ('IWB(A)', 11.8), ('DM(S)', 10.9)],
    ]
}

df = pd.DataFrame(data)

# Define the positions needed for the team
positions_needed = ['IWB(A)', 'BPD(D)', 'BPD(D)', 'IWB(A)', 'DW(S)', 'DM(S)', 'DW(S)', 'IF(A)', 'AF(A)', 'IF(A)']  # Example positions for a 4-4-2 formation

# Create a dictionary to map positions to valid player indices
position_to_players = {pos: [] for pos in positions_needed}
for idx, player in df.iterrows():
    for pos, score in player['Top_Positions']:
        if pos in position_to_players:
            position_to_players[pos].append(idx)

# Genetic Algorithm Setup
creator.create("FitnessMax", base.Fitness, weights=(1.0,))
creator.create("Individual", list, fitness=creator.FitnessMax)

toolbox = base.Toolbox()

def valid_player_for_position(position):
    return random.choice(position_to_players[position])

def create_individual():
    individual = []
    used_players = set()
    for pos in positions_needed:
        valid_players = [idx for idx in position_to_players[pos] if idx not in used_players]
        if not valid_players:
            print(f"No valid player found for position {pos}")
            return creator.Individual([None] * len(positions_needed))  # Return an invalid individual
        player = random.choice(valid_players)
        individual.append(player)
        used_players.add(player)
    return creator.Individual(individual)

toolbox.register("individual", create_individual)
toolbox.register("population", tools.initRepeat, list, toolbox.individual)

def evaluate(individual):
    used_players = set()
    total_score = 0
    for i, idx in enumerate(individual):
        if idx in used_players:
            # print(f"Duplicate player detected: {df.iloc[idx]['Player']} at position {positions_needed[i]}")
            return (0,)
        player_data = df.iloc[idx]
        position_filled = False
        for pos, score in player_data['Top_Positions']:
            if pos == positions_needed[i]:
                total_score += score
                used_players.add(idx)
                position_filled = True
                break
        if not position_filled:
            # print(f"Position {positions_needed[i]} not filled by player {df.iloc[idx]['Player']}")
            return (0,)
    if len(used_players) != len(positions_needed):
        # print(f"Invalid combination: used {len(used_players)} players, needed {len(positions_needed)}")
        return (0,)
    # print(f"Valid combination: used players {used_players} with score {total_score}")
    return (total_score / len(positions_needed),)


toolbox.register("evaluate", evaluate)
toolbox.register("mate", tools.cxTwoPoint)
toolbox.register("mutate", tools.mutShuffleIndexes, indpb=0.05)
toolbox.register("select", tools.selTournament, tournsize=3)

def prioritize_positions():
    position_counts = {pos: len(players) for pos, players in position_to_players.items()}
    sorted_positions = sorted(position_counts, key=position_counts.get)
    return sorted_positions

def main():
    random.seed()
    pop = toolbox.population(n=500)  # Increase population size
    hof = tools.HallOfFame(1)
    
    stats = tools.Statistics(lambda ind: ind.fitness.values)
    stats.register("avg", lambda x: sum([ind[0] for ind in x]) / len(x))  # Average fitness
    stats.register("min", lambda x: min([ind[0] for ind in x]))          # Minimum fitness
    stats.register("max", lambda x: max([ind[0] for ind in x]))          # Maximum fitness

    algorithms.eaSimple(pop, toolbox, cxpb=0.7, mutpb=0.3, ngen=100, stats=stats, halloffame=hof, verbose=True)
    
    return hof, stats, pop

# Function to evaluate and print the best 11
def evaluate_and_print_best_11(hof, df, title):
    best_individual = hof[0]
    best_11 = [(df.iloc[idx]['Player'], positions_needed[i], next(score for pos, score in df.iloc[idx]['Top_Positions'] if pos == positions_needed[i])) for i, idx in enumerate(best_individual)]
    
    print(title)
    for player, position, score in best_11:
        print(f"Player: {player}, Position: {position}, Score: {score}")

    average_score = evaluate(best_individual)[0]
    print(f"Average Score: {average_score}")
    return [idx for idx in best_individual]

if __name__ == "__main__":
    # Function to evaluate and print the best 11
    def evaluate_and_print_best_11(hof, df, title):
        best_individual = hof[0]
        best_11 = []
        for i, idx in enumerate(best_individual):
            player = df.iloc[idx]['Player']
            position = positions_needed[i]
            score = next((score for pos, score in df.iloc[idx]['Top_Positions'] if pos == position), None)
            if score is None:
                print(f"Player {player} does not have a score for position {position}.")
                score = 0
            best_11.append((player, position, score))
        
        print(title)
        for player, position, score in best_11:
            print(f"Player: {player}, Position: {position}, Score: {score}")

        average_score = evaluate(best_individual)[0]
        print(f"Average Score: {average_score}")
        return [idx for idx in best_individual]

    # Generate the first best_11 team
    hof, stats, pop = main()
    first_best_11_indices = evaluate_and_print_best_11(hof, df, "First best_11 team:")

    # Remove selected players from the DataFrame
    remaining_df = df.drop(first_best_11_indices).reset_index(drop=True)

    # Update the position_to_players dictionary for remaining players
    position_to_players = {pos: [] for pos in positions_needed}
    for idx, player in remaining_df.iterrows():
        for pos, score in player['Top_Positions']:
            if pos in position_to_players:
                position_to_players[pos].append(idx)

    # Prioritize positions before creating the second best_11 team
    prioritized_positions = prioritize_positions()

    # Redefine the valid_player_for_position function for remaining players
    def valid_player_for_position(position):
        valid_players = position_to_players[position]
        if not valid_players:
            return None
        return random.choice(valid_players)

    # Register the individual creation function for remaining players
    toolbox.unregister("individual")
    toolbox.register("individual", create_individual)

    # Generate the second best_11 team
    hof, stats, pop = main()
    second_best_11_indices = evaluate_and_print_best_11(hof, remaining_df, "Second best_11 team:")

    # Print statistics for the second run
    print(f"Generation statistics for the second run:")
    gen_stats = stats.compile(pop)
    print(f"avg: {gen_stats['avg']}, min: {gen_stats['min']}, max: {gen_stats['max']}")

    # Determine which players haven't been used
    all_indices = set(range(len(df)))
    used_indices = set(first_best_11_indices + second_best_11_indices)
    unused_indices = all_indices - used_indices

    print("Players not used in either best 11 team:")
    for idx in unused_indices:
        print(f"Player: {df.iloc[idx]['Player']}")
