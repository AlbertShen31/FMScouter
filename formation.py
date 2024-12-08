from position_config import *

flanker = ['sweeper_keeper_defend', 
            'inverted_wing_back_attack', 
            'ball_playing_defender_defend', 
            'defensive_midfielder_support', 
            'defensive_winger_support', 
            'inside_forward_attack', 
            'advanced_forward_attack']

hulk = ['sweeper_keeper_defend', 
          'wing_back_attack', 
          'ball_playing_defender_defend', 
          'central_midfielder_defend', 
          'central_midfielder_support', 
          'advanced_playmaker_support', 
          'advanced_forward_attack']

three_striker = ['sweeper_keeper_defend', 
                'wing_back_attack', 
                'ball_playing_defender_defend', 
                'segundo_volante_attack', 
                'pressing_forward_support']

short_kings = ['sweeper_keeper_defend', 
               'wing_back_attack', 
               'ball_playing_defender_defend', 
               'deep_lying_playmaker_support', 
               'central_midfielder_attack', 
               'inside_forward_support', 
               'advanced_forward_attack']

brexit = ['sweeper_keeper_defend', 
          'full_back_support', 
          'ball_playing_defender_defend', 
          'segundo_volante_attack', 
          'winger_attack',
          'advanced_forward_attack',
          'pressing_forward_support']

wetdog = ['sweeper_keeper_defend', 
               'full_back_attack', 
               'ball_playing_defender_defend', 
               'defensive_midfielder_support', 
               'central_midfielder_support', 
               'inside_forward_support',
               'advanced_forward_attack']

four_wingbacks = ['sweeper_keeper_defend',
                    'full_back_attack',
                    'inverted_wing_back_attack',
                    'ball_playing_defender_defend',
                    'defensive_midfielder_support',
                    'attacking_midfielder_support',
                    'advanced_forward_attack']

miracle = ['sweeper_keeper_defend',
           'full_back_attack',
           'ball_playing_defender_defend',
           'defensive_midfielder_support',
           'attacking_midfielder_attack',
           'inside_forward_support',
           'advanced_forward_attack']

dragon = ['sweeper_keeper_defend',
           'inverted_wing_back_attack',
           'ball_playing_defender_defend',
           'roaming_playmaker_support',
           'shadow_striker_attack',
           'winger_support',
           'advanced_forward_attack']

heaven = ['sweeper_keeper_defend',
          'full_back_attack',
          'ball_playing_defender_defend',
          'defensive_midfielder_support',
          'attacking_midfielder_attack',
          'inside_forward_support',
          'advanced_forward_attack',
          'complete_forward_attack']

# Rewrite the above code into a dictionary
formation_dict = {
    'flanker': flanker, 
    'hulk': hulk, 
    'three_striker': three_striker, 
    'short_kings': short_kings, 
    'brexit': brexit, 
    'wetdog': wetdog, 
    'four_wingbacks': four_wingbacks, 
    'miracle': miracle, 
    'dragon': dragon,
    'heaven': heaven
                  }