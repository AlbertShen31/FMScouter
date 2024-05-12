spartans = ['sweeper_keeper_defend', 
            'inverted_wing_back_attack', 
            'ball_playing_defender_defend', 
            'defensive_midfielder_support', 
            'defensive_winger_support', 
            'inside_forward_attack', 
            'advanced_forward_attack']

france = ['sweeper_keeper_defend', 
          'wing_back_attack', 
          'ball_playing_defender_defend', 
          'central_midfielder_defend', 
          'central_midfielder_support', 
          'advanced_playmaker_support', 
          'advanced_forward_attack']

notts_county = ['sweeper_keeper_defend', 
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


invert_left = 'Reasonable'
invert_right = 'Reasonable'
wing_left = 'Strong'
wing_right = 'Strong'

# Position counts for each formation
spartans_requirements = {
    "SK(D)": {"count": 1},
    "IWB(A)": {"count": 2, "foot_strength": [{"min_left_foot": invert_left}, {"min_right_foot": invert_right}]},
    "BPD(D)": {"count": 2},
    "DM(S)": {"count": 1},
    "DW(S)": {"count": 2, "foot_strength": [{"min_left_foot": wing_left}, {"min_right_foot": invert_right}]},
    "IF(A)": {"count": 2, "foot_strength": [{"min_left_foot": invert_left}, {"min_right_foot": invert_right}]},
    "AF(A)": {"count": 1}
}