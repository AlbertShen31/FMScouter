from config.role_weight_config import *

position_roles = {
    'gk': list(gk_positions.keys()),
    'dl': list(fb_positions.keys()) + list(wb_positions.keys()),
    'dcl': list(cb_positions.keys()),
    'dc': list(cb_positions.keys()),
    'dcr': list(cb_positions.keys()),
    'dr': list(fb_positions.keys()) + list(wb_positions.keys()),
    'wbl': list(wb_positions.keys()),
    'dmcl': list(dm_positions.keys())+['Roaming_Playmaker_Support'],
    'dmc': list(dm_positions.keys())+['Roaming_Playmaker_Support'],
    'dmcr': list(dm_positions.keys())+['Roaming_Playmaker_Support'],
    'wbr': list(wb_positions.keys()),
    'ml': list(w_positions.keys()),
    'mcl': list(cm_positions.keys())+['Deep_Lying_Playmaker_Support', 'Deep_Lying_Playmaker_Defend', 'Ball_Winning_Midfielder_Support', 'Ball_Winning_Midfielder_Defend', 'Advanced_Playmaker_Support', 'Advanced_Playmaker_Attack'],
    'mc': list(cm_positions.keys())+['Deep_Lying_Playmaker_Support', 'Deep_Lying_Playmaker_Defend', 'Ball_Winning_Midfielder_Support', 'Ball_Winning_Midfielder_Defend', 'Advanced_Playmaker_Support', 'Advanced_Playmaker_Attack'],
    'mcr': list(cm_positions.keys())+['Deep_Lying_Playmaker_Support', 'Deep_Lying_Playmaker_Defend', 'Ball_Winning_Midfielder_Support', 'Ball_Winning_Midfielder_Defend', 'Advanced_Playmaker_Support', 'Advanced_Playmaker_Attack'],
    'mr': list(w_positions.keys()),
    'aml': list(w_am_positions.keys())+['Winger_Support', 'Winger_Attack', 'Inverted_Winger_Support', 'Inverted_Winger_Attack', 'Advanced_Playmaker_Support', 'Advanced_Playmaker_Attack', 'Trequartista_Attack'],
    'amcl': list(am_positions.keys()),
    'amc': list(am_positions.keys()),
    'amcr': list(am_positions.keys()),
    'amr': list(w_am_positions.keys())+['Winger_Support', 'Winger_Attack', 'Inverted_Winger_Support', 'Inverted_Winger_Attack', 'Advanced_Playmaker_Support', 'Advanced_Playmaker_Attack', 'Trequartista_Attack'],
    'stl': list(st_positions.keys())+['Trequartista_Attack'],
    'stc': list(st_positions.keys())+['Trequartista_Attack'],
    'str': list(st_positions.keys())+['Trequartista_Attack'],
}

# You can add more positions and roles as needed 