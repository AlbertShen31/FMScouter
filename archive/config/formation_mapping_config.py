heaven = [
    {'gk': 'sweeper_keeper_defend'},
    {'dl': 'full_back_attack', 'dcl': 'ball_playing_defender_defend', 'dcr': 'ball_playing_defender_defend', 'dr': 'full_back_attack'},
    {'dmc': 'defensive_midfielder_support'},
    {},
    {'aml': 'inside_forward_support', 'amc': 'attacking_midfielder_attack', 'amr': 'inside_forward_support'},
    {'stl': 'advanced_forward_attack', 'str': 'complete_forward_support'}
]

flanker = [
    ['sweeper_keeper_defend'],
    ['full_back_attack','ball_playing_defender_defend', 'ball_playing_defender_defend', 'full_back_attack'],
    ['defensive_midfielder_support'],
    [],
    ['inside_forward_support','attacking_midfielder_attack','inside_forward_support'],
    ['advanced_forward_attack','complete_forward_support']
]

formation_mapping_dict = {
    'heaven': heaven,
    'flanker': flanker
}