#!/usr/bin/env python

# Import necessary libraries
import pandas as pd
import glob
import os
from typing import List

# Find the most recent file in the specified folder
list_of_files = glob.glob(os.path.join('/Users/albertwshen/Library/Application Support/Sports Interactive/Football Manager 2024/all_attributes', '*'))
latest_file = max(list_of_files, key=os.path.getctime)

# Read HTML file exported by FM - in this case, an example of an output from the squad page
# This reads as a list, not a dataframe
squad_rawdata_list = pd.read_html(latest_file, header=0, encoding="utf-8", keep_default_na=False)

single_letter_pos = ["goalkeeper_defend", "winger_support", "winger_attack", "anchor_defend", "poacher_attack"]
def format_position_name(position):
    # Remove the underscores and use the initial of each word
    if position.lower() == "raumdeter_attack":
        return "RMD(A)"
    elif "segundo_volante" in position.lower():
        return "VOL(" + position.upper().split('_')[2][0] + ")"
    elif position.lower() == "box_to_box_midfielder_support":
        return "BBM(S)"
    elif position.lower() == "false_nine_support":
        return "F9(S)"
    elif len(position.split('_')) == 2 and (position.lower() not in single_letter_pos):
        initials = position.split('_')
        return ("".join(initials[0][:3]) + "(" + initials[1][0] + ")").upper()

    initials = [word[0] for word in position.split('_')]
    return ("".join(initials[:-1]) + "(" + initials[-1] + ")").upper()



gk_positions = {
    'Goalkeeper_Defend': {
        'key_attrs': ['Agi', 'Ref'],
        'green_attrs': ['Aer', 'Cmd', 'Han', 'Kic', 'Cnt', 'Pos'],
        'blue_attrs': ['1v1', 'Thr', 'Ant', 'Dec'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 32
    },
    'Sweeper_keeper_Defend': {
        'key_attrs': ['Agi', 'Ref'],
        'green_attrs': ['Cmd', 'Kic', '1v1', 'Ant', 'Cnt', 'Pos'],
        'blue_attrs': ['Aer', 'Fir', 'Han', 'Pas', 'TRO', 'Dec', 'Vis', 'Acc'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 36
    },
    'Sweeper_keeper_Support': {
        'key_attrs': ['Agi', 'Ref'],
        'green_attrs': ['Cmd', 'Kic', '1v1', 'Ant', 'Cnt', 'Pos'],
        'blue_attrs': ['Aer', 'Fir', 'Han', 'Pas', 'TRO', 'Dec', 'Vis', 'Acc'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 36
    },
    'Sweeper_keeper_Attack': {
        'key_attrs': ['Agi', 'Ref'],
        'green_attrs': ['Cmd', 'Kic', '1v1', 'Ant', 'Cnt', 'Pos'],
        'blue_attrs': ['Aer', 'Fir', 'Han', 'Pas', 'TRO', 'Dec', 'Vis', 'Acc'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 36
    },
    # Add more positions if needed
}

cb_positions = {
    'Ball_playing_defender_Defend': {
        'key_attrs': ['Acc', 'Pac', 'Jum', 'Cmp'],
        'green_attrs': ['Hea', 'Mar', 'Pas', 'Tck', 'Pos', 'Str'],
        'blue_attrs': ['Fir', 'Tec', 'Agg', 'Ant', 'Bra', 'Cnt', 'Dec', 'Vis'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 46
    },
    'Ball_playing_defender_Stopper': {
        'key_attrs': ['Acc', 'Pac', 'Jum', 'Cmp'],
        'green_attrs': ['Hea', 'Pas', 'Tck', 'Pos', 'Str', 'Agg', 'Bra', 'Dec'],
        'blue_attrs': ['Fir', 'Tec', 'Mar'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 50
    },
    'Ball_playing_defender_Cover': {
        'key_attrs': ['Acc', 'Pac', 'Jum', 'Cmp'],
        'green_attrs': ['Mar', 'Pas', 'Tck', 'Pos', 'Ant', 'Cnt', 'Dec'],
        'blue_attrs': ['Fir', 'Tec', 'Bra', 'Vis', 'Str', 'Hea'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 47
    },
    'Central_defender_Defend': {
        'key_attrs': ['Acc', 'Pac', 'Jum', 'Cmp'],
        'green_attrs': ['Hea', 'Mar', 'Tck', 'Pos', 'Str'],
        'blue_attrs': ['Agg', 'Ant', 'Bra', 'Cnt', 'Dec'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 40
    },
    'Central_defender_Stopper': {
        'key_attrs': ['Acc', 'Pac', 'Jum', 'Cmp'],
        'green_attrs': ['Hea', 'Tck', 'Agg', 'Bra', 'Dec', 'Pos', 'Str'],
        'blue_attrs': ['Mar', 'Ant', 'Cnt'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 44
    },
    'Central_defender_Cover': {
        'key_attrs': ['Acc', 'Pac', 'Jum', 'Cmp'],
        'green_attrs': ['Mar', 'Tck', 'Ant', 'Cnt', 'Dec', 'Pos'],
        'blue_attrs': ['Hea', 'Bra', 'Str'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 41
    },
    'Libero_Defend': {
        'key_attrs': ['Acc', 'Pac', 'Jum', 'Cmp'],
        'green_attrs': ['Fir', 'Hea', 'Mar', 'Pas', 'Tck', 'Tec', 'Dec', 'Pos', 'Tea', 'Str'],
        'blue_attrs': ['Ant', 'Bra', 'Cnt', 'Sta'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 54
    },
    'Libero_Support': {
        'key_attrs': ['Acc', 'Pac', 'Jum', 'Cmp'],
        'green_attrs': ['Fir', 'Hea', 'Mar', 'Pas', 'Tck', 'Tec', 'Dec', 'Pos', 'Tea', 'Str'],
        'blue_attrs': ['Dri', 'Ant', 'Bra', 'Cnt', 'Vis', 'Sta'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 56
    },
    'No-nonsense_centre_back_Defend': {
        'key_attrs': ['Acc', 'Pac', 'Jum', 'Cmp'],
        'green_attrs': ['Hea', 'Mar', 'Tck', 'Pos', 'Str'],
        'blue_attrs': ['Agg', 'Ant', 'Bra', 'Cnt'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 39
    },
    'No-nonsense_centre_back_Stopper': {
        'key_attrs': ['Acc', 'Pac', 'Jum', 'Cmp'],
        'green_attrs': ['Hea', 'Tck', 'Agg', 'Bra', 'Pos', 'Str'],
        'blue_attrs': ['Mar', 'Ant', 'Cnt'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 41
    },
    'No-nonsense_centre_back_Cover': {
        'key_attrs': ['Acc', 'Pac', 'Jum', 'Cmp'],
        'green_attrs': ['Mar', 'Tck', 'Ant', 'Cnt', 'Pos'],
        'blue_attrs': ['Hea', 'Bra', 'Str'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 38
    },
    'Wide_centre_back_Defend': {
        'key_attrs': ['Acc', 'Pac', 'Jum', 'Cmp'],
        'green_attrs': ['Hea', 'Mar', 'Tck', 'Pos', 'Str'],
        'blue_attrs': ['Dri', 'Fir', 'Pas', 'Tec', 'Agg', 'Ant', 'Bra', 'Cnt', 'Dec', 'Wor', 'Agi'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 46
    },
    'Wide_centre_back_Support': {
        'key_attrs': ['Acc', 'Pac', 'Jum', 'Cmp'],
        'green_attrs': ['Dri', 'Hea', 'Mar', 'Tck', 'Pos', 'Str'],
        'blue_attrs': ['Cro', 'Fir', 'Pas', 'Tec', 'Agg', 'Ant', 'Bra', 'Cnt', 'Dec', 'OtB', 'Wor', 'Agi', 'Sta'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 51
    },
    'Wide_centre_back_Attack': {
        'key_attrs': ['Acc', 'Pac', 'Jum', 'Cmp'],
        'green_attrs': ['Cro', 'Dri', 'Hea', 'Mar', 'Tck', 'OtB', 'Sta', 'Str'],
        'blue_attrs': ['Fir', 'Pas', 'Tec', 'Agg', 'Ant', 'Bra', 'Cnt', 'Dec', 'Pos', 'Wor', 'Agi'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 55
    },
    # Add more positions if needed
}

fb_positions = {
    'Complete_Wing_Back_Support': {
        'key_attrs': ['Acc', 'Pac', 'Sta', 'Wor'],
        'green_attrs': ['Cro', 'Dri', 'Tec', 'OtB', 'Tea'],
        'blue_attrs': ['Fir', 'Mar', 'Pas', 'Tck', 'Ant', 'Dec', 'Fla', 'Pos', 'Agi', 'Bal'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 45
    },
    'Complete_Wing_Back_Attack': {
        'key_attrs': ['Acc', 'Pac', 'Sta', 'Wor'],
        'green_attrs': ['Cro', 'Dri', 'Tec', 'Fla', 'OtB', 'Tea'],
        'blue_attrs': ['Fir', 'Mar', 'Pas', 'Tck', 'Ant', 'Dec', 'Pos', 'Agi', 'Bal'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 47
    },
    'Full_Back_Defend': {
        'key_attrs': ['Acc', 'Pac', 'Sta', 'Wor'],
        'green_attrs': ['Mar', 'Tck', 'Ant', 'Cnt', 'Pos', 'Pos'],
        'blue_attrs': ['Cro', 'Pas', 'Dec', 'Tea'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 42
    },
    'Full_Back_Support': {
        'key_attrs': ['Acc', 'Pac', 'Sta', 'Wor'],
        'green_attrs': ['Mar', 'Tck', 'Ant', 'Cnt', 'Pos', 'Tea'],
        'blue_attrs': ['Cro', 'Dri', 'Pas', 'Tec', 'Dec'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 43
    },
    'Full_Back_Attack': {
        'key_attrs': ['Acc', 'Pac', 'Sta', 'Wor'],
        'green_attrs': ['Cro', 'Mar', 'Tck', 'Ant', 'Pos', 'Tea'],
        'blue_attrs': ['Dri', 'Fir', 'Pas', 'Tec', 'Cnt', 'Dec', 'OtB', 'Agi'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 46
    },
    'Inverted_Full_Back_Defend': {
        'key_attrs': ['Acc', 'Pac', 'Sta', 'Wor'],
        'green_attrs': ['Hea', 'Mar', 'Tck', 'Pos', 'Str'],
        'blue_attrs': ['Dri', 'Fir', 'Pas', 'Tec', 'Agg', 'Ant', 'Bra', 'Cmp', 'Cnt', 'Dec', 'Agi', 'Jum'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 47
    },
    'Inverted_Wing_Back_Defend': {
        'key_attrs': ['Acc', 'Pac', 'Sta', 'Wor'],
        'green_attrs': ['Pas', 'Tck', 'Ant', 'Dec', 'Pos', 'Tea'],
        'blue_attrs': ['Fir', 'Mar', 'Tec', 'Com', 'Cnt', 'OtB', 'Agi'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 45
    },
    'Inverted_Wing_Back_Support': {
        'key_attrs': ['Acc', 'Pac', 'Sta', 'Wor'],
        'green_attrs': ['Fir', 'Pas', 'Tck', 'Cmp', 'Dec', 'Tea'],
        'blue_attrs': ['Mar', 'Tec', 'Ant', 'Cnt', 'OtB', 'Pos', 'Vis', 'Agi'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 46
    },
    'Inverted_Wing_Back_Attack': {
        'key_attrs': ['Acc', 'Pac', 'Sta', 'Wor'],
        'green_attrs': ['Fir', 'Pas', 'Tck', 'Tec', 'Cmp', 'Dec', 'OtB', 'Tea', 'Vis'],
        'blue_attrs': ['Cro', 'Dri', 'Lon', 'Mar', 'Ant', 'Cnt', 'Fla', 'Pos', 'Agi'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 56
    },
    'No-nonsense_Full_Back_Defend': {
        'key_attrs': ['Acc', 'Pac', 'Sta', 'Wor'],
        'green_attrs': ['Mar', 'Tck', 'Ant', 'Pos', 'Str'],
        'blue_attrs': ['Hea', 'Agg', 'Bra', 'Cnt', 'Tea'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 40
    },
    'Wing_Back_Defend': {
        'key_attrs': ['Acc', 'Pac', 'Sta', 'Wor'],
        'green_attrs': ['Mar', 'Tck', 'Ant', 'Pos', 'Tea'],
        'blue_attrs': ['Cro', 'Dri', 'Fir', 'Pas', 'Tec', 'Cnt', 'Dec', 'OtB', 'Agi', 'Bal'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 45
    },
    'Wing_Back_Support': {
        'key_attrs': ['Acc', 'Pac', 'Sta', 'Wor'],
        'green_attrs': ['Cro', 'Dri', 'Mar', 'Tck', 'OtB', 'Tea'],
        'blue_attrs': ['Fir', 'Pas', 'Tec', 'Ant', 'Cnt', 'Dec', 'Pos', 'Agi', 'Bal'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 47
    },
    'Wing_Back_Attack': {
        'key_attrs': ['Acc', 'Pac', 'Sta', 'Wor'],
        'green_attrs': ['Cro', 'Dri', 'Tck', 'Tec', 'OtB', 'Tea'],
        'blue_attrs': ['Fir', 'Mar', 'Pas', 'Ant', 'Cnt', 'Dec', 'Fla', 'Pos', 'Agi', 'Bal'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 48
    },
    # Add more positions if needed
}

dm_positions = {
    'Anchor_Defend': {
        'key_attrs': ['Wor', 'Sta', 'Acc', 'Pac'],
        'green_attrs': ['Mar', 'Tck', 'Ant', 'Cnt', 'Dec', 'Pos'],
        'blue_attrs': ['Cmp', 'Tea', 'Str'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 41
    },
    'Ball_winning_midfielder_Defend': {
        'key_attrs': ['Wor', 'Sta', 'Acc', 'Pac'],
        'green_attrs': ['Tck', 'Agg', 'Ant', 'Tea'],
        'blue_attrs': ['Mar', 'Bra', 'Cnt', 'Pos', 'Agi', 'Str'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 38
    },
    'Ball_winning_midfielder_Support': {
        'key_attrs': ['Wor', 'Sta', 'Acc', 'Pac'],
        'green_attrs': ['Tck', 'Agg', 'Ant', 'Tea'],
        'blue_attrs': ['Mar', 'Pas', 'Bra', 'Cnt', 'Agi', 'Str'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 38
    },
    'Deep_lying_playmaker_Defend': {
        'key_attrs': ['Wor', 'Sta', 'Acc', 'Pac'],
        'green_attrs': ['Fir', 'Pas', 'Tec', 'Cmp', 'Dec', 'Tea', 'Vis'],
        'blue_attrs': ['Tck', 'Ant', 'Pos', 'Bal'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 45
    },
    'Deep_lying_playmaker_Support': {
        'key_attrs': ['Wor', 'Sta', 'Acc', 'Pac'],
        'green_attrs': ['Fir', 'Pas', 'Tec', 'Cmp', 'Dec', 'Tea', 'Vis'],
        'blue_attrs': ['Ant', 'OtB', 'Pos', 'Bal'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 45
    },
    'Defensive_midfielder_Defend': {
        'key_attrs': ['Wor', 'Sta', 'Acc', 'Pac'],
        'green_attrs': ['Tck', 'Ant', 'Cnt', 'Pos', 'Tea'],
        'blue_attrs': ['Mar', 'Pas', 'Agg', 'Cmp', 'Dec'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 40
    },
    'Defensive_midfielder_Support': {
        'key_attrs': ['Wor', 'Sta', 'Acc', 'Pac'],
        'green_attrs': ['Tck', 'Ant', 'Cnt', 'Pos', 'Tea'],
        'blue_attrs': ['Fir', 'Mar', 'Pas', 'Agg', 'Cmp', 'Dec', 'Str'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 42
    },
    'Half_back_Defend': {
        'key_attrs': ['Wor', 'Sta', 'Acc', 'Pac'],
        'green_attrs': ['Mar', 'Tck', 'Ant', 'Cmp', 'Cnt', 'Dec', 'Pos', 'Tea'],
        'blue_attrs': ['Fir', 'Pas', 'Agg', 'Bra', 'Jum', 'Str'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 50
    },
    'Regista_Support': {
        'key_attrs': ['Wor', 'Sta', 'Acc', 'Pac'],
        'green_attrs': ['Fir', 'Pas', 'Tec', 'Cmp', 'Dec', 'Fla', 'OtB', 'Tea', 'Vis'],
        'blue_attrs': ['Dri', 'Lon', 'Ant', 'Bal'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 51
    },
    'Segundo_volante_Support': {
        'key_attrs': ['Wor', 'Sta', 'Acc', 'Pac'],
        'green_attrs': ['Mar', 'Pas', 'Tck', 'OtB', 'Pos'],
        'blue_attrs': ['Fin', 'Fir', 'Lon', 'Ant', 'Cmp', 'Cnt', 'Dec', 'Bal', 'Str'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 44
    },
    'Segundo_volante_Attack': {
        'key_attrs': ['Wor', 'Sta', 'Acc', 'Pac'],
        'green_attrs': ['Fin', 'Lon', 'Pas', 'Tck', 'Ant', 'OtB', 'Pos'],
        'blue_attrs': ['Fir', 'Mar', 'Cmp', 'Cnt', 'Dec', 'Bal'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 47
    },
    # Add more positions if needed
}

cm_positions = {
    'Box_to_box_midfielder_Support': {
        'key_attrs': ['Acc', 'Pac', 'Sta', 'Wor'],
        'green_attrs': ['Pas', 'Tck', 'OtB', 'Tea'],
        'blue_attrs': ['Dri', 'Fin', 'Fir', 'Lon', 'Tec', 'Agg', 'Ant', 'Cmp', 'Dec', 'Pos', 'Bal', 'Str'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 44
    },
    'Carrilero_Support': {
        'key_attrs': ['Wor', 'Sta', 'Acc', 'Pac'],
        'green_attrs': ['Fir', 'Pas', 'Tck', 'Dec', 'Pos', 'Tea'],
        'blue_attrs': ['Tec', 'Ant', 'Cmp', 'Cnt', 'OtB', 'Vis'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 44
    },
    'Central_midfielder_Defend': {
        'key_attrs': ['Acc', 'Pac', 'Sta', 'Wor'],
        'green_attrs': ['Tck', 'Cnt', 'Dec', 'Pos', 'Tea'],
        'blue_attrs': ['Fir', 'Mar', 'Pas', 'Tec', 'Agg', 'Ant', 'Cmp'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 42
    },
    'Central_midfielder_Support': {
        'key_attrs': ['Acc', 'Pac', 'Sta', 'Wor'],
        'green_attrs': ['Fir', 'Pas', 'Tck', 'Dec', 'Tea'],
        'blue_attrs': ['Tec', 'Ant', 'Cmp', 'Cnt', 'OtB', 'Vis'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 41
    },
    'Central_midfielder_Attack': {
        'key_attrs': ['Acc', 'Pac', 'Sta', 'Wor'],
        'green_attrs': ['Fir', 'Pas', 'Dec', 'OtB'],
        'blue_attrs': ['Lon', 'Tck', 'Tec', 'Ant', 'Cmp', 'Tea', 'Vis'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 39
    },
    'Mezzala_Support': {
        'key_attrs': ['Acc', 'Pac', 'Sta', 'Wor'],
        'green_attrs': ['Pas', 'Tec', 'Dec', 'OtB'],
        'blue_attrs': ['Dri', 'Fir', 'Lon', 'Tck', 'Ant', 'Cmp', 'Vis', 'Bal'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 40
    },
    'Mezzala_Attack': {
        'key_attrs': ['Acc', 'Pac', 'Sta', 'Wor'],
        'green_attrs': ['Dri', 'Pas', 'Tec', 'Dec', 'OtB', 'Vis'],
        'blue_attrs': ['Fin', 'Fir', 'Lon', 'Ant', 'Cmp', 'Fla', 'Bal'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 45
    },
    'Roaming_playmaker_Support': {
        'key_attrs': ['Acc', 'Pac', 'Sta', 'Wor'],
        'green_attrs': ['Fir', 'Pas', 'Tec', 'Ant', 'Cmp', 'Dec', 'OtB', 'Tea', 'Vis'],
        'blue_attrs': ['Dri', 'Lon', 'Cnt', 'Pos', 'Agi', 'Bal'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 53
    },
    # Add more positions if needed
}

am_positions = {
    'Advanced_playmaker_Support': {
        'key_attrs': ['Acc', 'Pac', 'Sta', 'Wor'],
        'green_attrs': ['Fir', 'Pas', 'Tec', 'Cmp', 'Dec', 'OtB', 'Tea', 'Vis'],
        'blue_attrs': ['Dri', 'Ant', 'Fla', 'Agi'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 48
    },
    'Advanced_playmaker_Attack': {
        'key_attrs': ['Acc', 'Pac', 'Sta', 'Wor'],
        'green_attrs': ['Fir', 'Pas', 'Tec', 'Cmp', 'Dec', 'OtB', 'Tea', 'Vis'],
        'blue_attrs': ['Dri', 'Ant', 'Fla', 'Agi'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 48
    },
    'Attacking_midfielder_Support': {
        'key_attrs': ['Acc', 'Pac', 'Sta', 'Wor'],
        'green_attrs': ['Fir', 'Lon', 'Pas', 'Tec', 'Ant', 'Dec', 'Fla', 'OtB'],
        'blue_attrs': ['Dri', 'Cmp', 'Vis', 'Agi'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 48
    },
    'Attacking_midfielder_Attack': {
        'key_attrs': ['Acc', 'Pac', 'Sta', 'Wor'],
        'green_attrs': ['Dri', 'Fir', 'Lon', 'Pas', 'Tec', 'Ant', 'Dec', 'Fla', 'OtB'],
        'blue_attrs': ['Fin', 'Cmp', 'Vis', 'Agi'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 51
    },
    'Enganche_Support': {
        'key_attrs': ['Acc', 'Pac', 'Sta', 'Wor'],
        'green_attrs': ['Fir', 'Pas', 'Tec', 'Cmp', 'Dec', 'Vis'],
        'blue_attrs': ['Dri', 'Ant', 'Fla', 'OtB', 'Tea', 'Agi'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 44
    },
    'Shadow_striker_Attack': {
        'key_attrs': ['Acc', 'Pac', 'Sta', 'Wor'],
        'green_attrs': ['Dri', 'Fin', 'Fir', 'Ant', 'Cmp', 'OtB'],
        'blue_attrs': ['Pas', 'Tec', 'Cnt', 'Dec', 'Agi', 'Bal'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 44
    },
    'Trequartista_Attack': {
        'key_attrs': ['Acc', 'Pac', 'Fin'],
        'green_attrs': ['Dri', 'Fir', 'Pas', 'Tec', 'Cmp', 'Dec', 'Fla', 'OtB', 'Vis'],
        'blue_attrs': ['Ant', 'Agi', 'Bal'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 45
    },
    # Add more positions if needed
}

w_positions = {
    'Defensive_winger_Defend': {
        'key_attrs': ['Acc', 'Pac', 'Sta', 'Wor'],
        'green_attrs': ['Tec', 'Ant', 'OtB', 'Pos', 'Tea'],
        'blue_attrs': ['Cro', 'Dri', 'Fir', 'Mar', 'Tck', 'Agg', 'Cnt', 'Dec'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 43
    },
    'Defensive_winger_Support': {
        'key_attrs': ['Acc', 'Pac', 'Sta', 'Wor'],
        'green_attrs': ['Cro', 'Pas', 'Tec', 'OtB', 'Tea'],
        'blue_attrs': ['Dri', 'Fir', 'Mar', 'Pas', 'Tck', 'Agg', 'Ant', 'Cmp', 'Cnt', 'Dec', 'Pos'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 46
    },
    'Inside_forward_Support': {
        'key_attrs': ['Acc', 'Pac', 'Sta', 'Wor'],
        'green_attrs': ['Dri', 'Fin', 'Fir', 'Tec', 'OtB', 'Agi'],
        'blue_attrs': ['Lon', 'Pas', 'Ant', 'Cmp', 'Fla', 'Vis', 'Bal'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 45
    },
    'Inside_forward_Attack': {
        'key_attrs': ['Acc', 'Pac', 'Sta', 'Wor'],
        'green_attrs': ['Dri', 'Fin', 'Fir', 'Tec', 'Ant', 'OtB', 'Agi'],
        'blue_attrs': ['Lon', 'Pas', 'Cmp', 'Fla', 'Bal'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 46
    },
    'Inverted_winger_Support': {
        'key_attrs': ['Acc', 'Pac', 'Sta', 'Wor'],
        'green_attrs': ['Cro', 'Dri', 'Pas', 'Tec', 'Agi'],
        'blue_attrs': ['Fir', 'Lon', 'Cmp', 'Dec', 'OtB', 'Vis', 'Bal'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 42
    },
    'Inverted_winger_Attack': {
        'key_attrs': ['Acc', 'Pac', 'Sta', 'Wor'],
        'green_attrs': ['Cro', 'Dri', 'Pas', 'Tec', 'Agi'],
        'blue_attrs': ['Fir', 'Lon', 'Ant', 'Cmp', 'Dec', 'Fla', 'OtB', 'Vis', 'Bal'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 44
    },
    'Raumdeuter_Attack': {
        'key_attrs': ['Acc', 'Pac', 'Sta', 'Wor'],
        'green_attrs': ['Fin', 'Ant', 'Cmp', 'Cnt', 'Dec', 'OtB', 'Bal'],
        'blue_attrs': ['Fir', 'Tec'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 43
    },
    'Wide_midfielder_Defend': {
        'key_attrs': ['Acc', 'Pac', 'Sta', 'Wor'],
        'green_attrs': ['Pas', 'Tck', 'Cnt', 'Dec', 'Pos', 'Tea'],
        'blue_attrs': ['Cro', 'Fir', 'Mar', 'Tec', 'Ant', 'Cmp'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 44
    },
    'Wide_midfielder_Support': {
        'key_attrs': ['Acc', 'Pac', 'Sta', 'Wor'],
        'green_attrs': ['Pas', 'Tck', 'Dec', 'Tea'],
        'blue_attrs': ['Cro', 'Fir', 'Tec', 'Ant', 'Cmp', 'Cnt', 'OtB', 'Pos', 'Vis'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 41
    },
    'Wide_midfielder_Attack': {
        'key_attrs': ['Acc', 'Pac', 'Sta', 'Wor'],
        'green_attrs': ['Cro', 'Fir', 'Pas', 'Dec', 'Tea'],
        'blue_attrs': ['Tck', 'Tec', 'Ant', 'Cmp', 'OtB', 'Vis'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 41
    },
    'Wide_playmaker_Support': {
        'key_attrs': ['Acc', 'Pac', 'Sta', 'Wor'],
        'green_attrs': ['Fir', 'Pas', 'Tec', 'Cmp', 'Dec', 'Tea', 'Vis'],
        'blue_attrs': ['Dri', 'OtB', 'Agi'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 44
    },
    'Wide_playmaker_Attack': {
        'key_attrs': ['Acc', 'Pac', 'Sta', 'Wor'],
        'green_attrs': ['Dri', 'Fir', 'Pas', 'Tec', 'Cmp', 'Dec', 'OtB', 'Tea', 'Vis'],
        'blue_attrs': ['Ant', 'Fla', 'Agi'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 50
    },
    'Wide_target_forward_Support': {
        'key_attrs': ['Acc', 'Pac', 'Sta', 'Wor'],
        'green_attrs': ['Hea', 'Bra', 'Tea', 'Jum', 'Str'],
        'blue_attrs': ['Cro', 'Fir', 'Ant', 'OtB', 'Bal'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 40
    },
    'Wide_target_forward_Attack': {
        'key_attrs': ['Acc', 'Pac', 'Sta', 'Wor'],
        'green_attrs': ['Hea', 'Bra', 'OtB', 'Jum', 'Str'],
        'blue_attrs': ['Cro', 'Fin', 'Fir', 'Ant', 'Tea', 'Bal'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 41
    },
    'Winger_Support': {
        'key_attrs': ['Acc', 'Pac', 'Sta', 'Wor'],
        'green_attrs': ['Cro', 'Dri', 'Tec', 'Agi'],
        'blue_attrs': ['Fir', 'Pas', 'OtB', 'Bal'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 36
    },
    'Winger_Attack': {
        'key_attrs': ['Acc', 'Pac', 'Sta', 'Wor'],
        'green_attrs': ['Cro', 'Dri', 'Tec', 'Agi'],
        'blue_attrs': ['Fir', 'Pas', 'Ant', 'Fla', 'OtB', 'Bal'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 38
    },
    # Add more positions if needed
}

st_positions = {
    'Advanced_forward_Attack': {
        'key_attrs': ['Acc', 'Pac', 'Fin'],
        'green_attrs': ['Dri', 'Fir', 'Tec', 'Cmp', 'OtB'],
        'blue_attrs': ['Pas', 'Ant', 'Dec', 'Wor', 'Agi', 'Bal', 'Sta'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 37
    },
    'Complete_forward_Support': {
        'key_attrs': ['Acc', 'Pac', 'Fin'],
        'green_attrs': ['Dri', 'Fir', 'Hea', 'Lon', 'Pas', 'Tec', 'Ant', 'Cmp', 'Dec', 'OtB', 'Vis', 'Agi', 'Str'],
        'blue_attrs': ['Tea', 'Wor', 'Bal', 'Jum', 'Sta'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 59
    },
    'Complete_forward_Attack': {
        'key_attrs': ['Acc', 'Pac', 'Fin'],
        'green_attrs': ['Dri', 'Fir', 'Hea', 'Tec', 'Ant', 'Cmp', 'OtB', 'Agi', 'Str'],
        'blue_attrs': ['Lon', 'Pas', 'Dec', 'Tea', 'Vis', 'Wor', 'Bal', 'Jum', 'Sta'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 51
    },
    'Deep_lying_forward_Support': {
        'key_attrs': ['Acc', 'Pac', 'Fin'],
        'green_attrs': ['Fir', 'Pas', 'Tec', 'Cmp', 'Dec', 'OtB', 'Tea'],
        'blue_attrs': ['Ant', 'Fla', 'Vis', 'Bal', 'Str'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 41
    },
    'Deep_lying_forward_Attack': {
        'key_attrs': ['Acc', 'Pac', 'Fin'],
        'green_attrs': ['Fir', 'Pas', 'Tec', 'Cmp', 'Dec', 'OtB', 'Tea'],
        'blue_attrs': ['Dri', 'Ant', 'Fla', 'Vis', 'Bal', 'Str'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 42
    },
    'False_nine_Support': {
        'key_attrs': ['Acc', 'Pac', 'Fin'],
        'green_attrs': ['Dri', 'Fir', 'Pas', 'Tec', 'Cmp', 'Dec', 'OtB', 'Vis', 'Agi'],
        'blue_attrs': ['Ant', 'Fla', 'Tea', 'Bal'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 46
    },
    'Poacher_Attack': {
        'key_attrs': ['Acc', 'Pac', 'Fin'],
        'green_attrs': ['Ant', 'Cmp', 'OtB'],
        'blue_attrs': ['Fir', 'Hea', 'Tec', 'Dec'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 28
    },
    'Pressing_forward_Defend': {
        'key_attrs': ['Acc', 'Pac', 'Fin'],
        'green_attrs': ['Agg', 'Ant', 'Bra', 'Dec', 'Tea', 'Wor', 'Sta'],
        'blue_attrs': ['Fir', 'Cmp', 'Cnt', 'Agi', 'Bal', 'Str'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 42
    },
    'Pressing_forward_Support': {
        'key_attrs': ['Acc', 'Pac', 'Fin'],
        'green_attrs': ['Agg', 'Ant', 'Bra', 'Dec', 'Tea', 'Wor', 'Sta'],
        'blue_attrs': ['Fir', 'Pas', 'Cmp', 'Cnt', 'OtB', 'Agi', 'Bal', 'Str'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 44
    },
    'Pressing_forward_Attack': {
        'key_attrs': ['Acc', 'Pac', 'Fin'],
        'green_attrs': ['Agg', 'Ant', 'Bra', 'OtB', 'Tea', 'Wor', 'Sta'],
        'blue_attrs': ['Fir', 'Cmp', 'Cnt', 'Dec', 'Agi', 'Bal', 'Str'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 43
    },
    'Target_forward_Support': {
        'key_attrs': ['Acc', 'Pac', 'Fin'],
        'green_attrs': ['Hea', 'Bra', 'Tea', 'Bal', 'Jum', 'Str'],
        'blue_attrs': ['Fir', 'Agg', 'Ant', 'Cmp', 'Dec', 'OtB'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 39
    },
    'Target_forward_Attack': {
        'key_attrs': ['Acc', 'Pac', 'Fin'],
        'green_attrs': ['Hea', 'Bra', 'Cmp', 'OtB', 'Bal', 'Jum', 'Str'],
        'blue_attrs': ['Fir', 'Agg', 'Ant', 'Dec', 'Tea'],
        'key_weight': 5,
        'green_weight': 3,
        'blue_weight': 1,
        'divisor': 41
    },
}

# Calculate the score for each position
def calculate_score(data, key_attrs, green_attrs, blue_attrs, key_weight, green_weight, blue_weight, divisor):
    key_score = sum(data[attr] for attr in key_attrs)
    green_score = sum(data[attr] for attr in green_attrs)
    blue_score = sum(data[attr] for attr in blue_attrs)
    
    total_score = (key_score * key_weight + green_score * green_weight + blue_score * blue_weight) / divisor
    return round(total_score, 1)

squad_rawdata = squad_rawdata_list[0]

def calculate_positions(squad_rawdata, selected_positions, position_lists, min_score=0):
    # Build a dictionary of selected positions
    position_dict = {pos: attrs for plist in position_lists for pos, attrs in plist.items()
                     if pos.lower() in selected_positions}

    # Calculate the score for each position
    score_columns = []
    for position, attrs in position_dict.items():
        score_col = format_position_name(position)
        squad_rawdata[score_col] = squad_rawdata.apply(
            lambda row: calculate_score(
                row, 
                attrs['key_attrs'], attrs['green_attrs'], attrs['blue_attrs'], 
                attrs['key_weight'], attrs['green_weight'], attrs['blue_weight'], 
                attrs['divisor']
            ), axis=1)
        score_columns.append(score_col)

    squads_filtered = squad_rawdata[~(squad_rawdata[score_columns] < min_score).all(axis=1)]

    # Create and sort DataFrames for each position
    squads = []
    columns = ['Inf', 'Name', 'Age', 'Club', 'Transfer Value', 'Salary', 'Nat', 'Position', 'Personality', 'Media Handling', 'Left Foot', 'Right Foot', 'Height']
    for position, attrs in position_dict.items():
        score_col = format_position_name(position)
        squad = squads_filtered[columns + [score_col]].copy(deep=True)
        squad.sort_values(by=[score_col], ascending=False, inplace=True)
        squads.append(squad.head(100))

    squads.append(squads_filtered[columns + score_columns])

    return squads

        

def calculate_best_positions(squad_rawdata, position_list):
    # Calculate the score for each position
    for positions in position_list:
        for position, attrs in positions.items():
            squad_rawdata[f'{format_position_name(position)}'] = squad_rawdata.apply(
                lambda row: calculate_score(row, attrs['key_attrs'], attrs['green_attrs'], attrs['blue_attrs'], attrs['key_weight'], 
                                            attrs['green_weight'], attrs['blue_weight'], attrs['divisor']), axis=1)

    squads = []
    for positions in [gk_positions, fb_positions, cb_positions, dm_positions, cm_positions, am_positions, w_positions, st_positions]:
        squad = squad_rawdata[['Inf', 'Name', 'Age', 'Club', 'Transfer Value', 'Salary', 'Nat', 'Position', 'Personality', 'Media Handling', 'Left Foot', 'Right Foot', 'Height']]
        for position, attrs in positions.items():
            squad = squad.join(squad_rawdata[[f'{format_position_name(position)}']])
        squads.append(squad)

    return squads

def calculate_all_positions(squad_rawdata, position_list):
    # Calculate the score for each position
    for positions in position_list:
        for position, attrs in positions.items():
            squad_rawdata[f'{format_position_name(position)}'] = squad_rawdata.apply(
                lambda row: calculate_score(row, attrs['key_attrs'], attrs['green_attrs'], attrs['blue_attrs'], attrs['key_weight'], 
                                            attrs['green_weight'], attrs['blue_weight'], attrs['divisor']), axis=1)

    squads = []
    for positions in [gk_positions, fb_positions, cb_positions, dm_positions, cm_positions, am_positions, w_positions, st_positions]:
        squad = squad_rawdata[['Inf', 'Name', 'Age', 'Club', 'Transfer Value', 'Salary', 'Nat', 'Position', 'Personality', 'Media Handling', 'Left Foot', 'Right Foot', 'Height']]
        for position, attrs in positions.items():
            squad = squad.join(squad_rawdata[[f'{format_position_name(position)}']])
        squads.append(squad)

    return squads

selected_positions = ['sweeper_keeper_defend', 'inverted_wing_back_attack', 'ball_playing_defender_defend', 'defensive_midfielder_support', 'defensive_winger_support', 'inside_forward_attack', 'advanced_forward_attack']
# selected_positions = ['sweeper_keeper_defend', 'wing_back_attack', 'ball_playing_defender_defend', 'ball_winning_midfielder_defend', 'attacking_midfielder_support', 'advanced_forward_attack']
# selected_positions = ['sweeper_keeper_defend', 'wing_back_attack', 'ball_playing_defender_defend', 'central_midfielder_defend', 'central_midfielder_support', 'advanced_playmaker_support', 'advanced_forward_attack']
# selected_positions = ['sweeper_keeper_defend', 'wing_back_attack', 'ball_playing_defender_defend', 'segundo_volante_attack', 'pressing_forward_support']
position_lists = [gk_positions, fb_positions, cb_positions, dm_positions, cm_positions, am_positions, w_positions, st_positions]

squads = calculate_positions(squad_rawdata, selected_positions, position_lists, min_score=0)

# squads = calculate_all_positions(position_lists)

def generate_html_multiple(dataframes, table_names, folder_name):
    def create_option_list(table_names):
        return "\n".join(f'        <option value="table{i}">{name}</option>' for i, name in enumerate(table_names))

    def create_table_divs(dataframes):
        divs = ""
        for i, df in enumerate(dataframes):
            display_style = "block" if i == 0 else "none"
            df_html = df.to_html(classes='display', border=0, index=False, table_id=f'table_{i}')
            divs += f'    <div id="table{i}" style="display:{display_style};">\n        {df_html}\n    </div>\n'
        return divs

    def create_datatable_script(dataframes):
        script = "    $(document).ready(function() {\n"
        for i in range(len(dataframes)):
            script += f'        $("#table_{i}").DataTable({{paging: false, order: [[13, "desc"]]}});\n'
        script += "    });\n"
        return script

    def create_hide_tables_script(dataframes):
        script = ""
        for i in range(len(dataframes)):
            script += f'            document.getElementById("table{i}").style.display = "none";\n'
        return script

    if not os.path.exists(folder_name):
        os.makedirs(folder_name)

    html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Table Display</title>
            <link rel="stylesheet" type="text/css" href="https://cdn.datatables.net/1.11.5/css/jquery.dataTables.min.css">
            <script type="text/javascript" src="https://code.jquery.com/jquery-3.5.1.js"></script>
            <script type="text/javascript" src="https://cdn.datatables.net/1.11.5/js/jquery.dataTables.min.js"></script>
            <style>
                table, th, td {{
                    border: 1px solid black;
                    border-collapse: collapse;
                }}
                th, td {{
                    padding: 5px;
                    text-align: left;
                }}
            </style>
        </head>
        <body>

            <h2>Select a Table to Display</h2>

            <select id="tableSelect" onchange="showTable()">
        {create_option_list(table_names)}
            </select>

        {create_table_divs(dataframes)}

            <script>
        {create_datatable_script(dataframes)}

                function showTable() {{
                    var selectedTable = document.getElementById("tableSelect").value;
                    
                    // Hide all tables
        {create_hide_tables_script(dataframes)}
                    // Show the selected table
                    document.getElementById(selectedTable).style.display = "block";
                }}
            </script>

        </body>
        </html>
        """
    
    with open(f"{folder_name}/tables.html", "w") as file:
        file.write(html_content)


generate_html_multiple(squads, selected_positions + ["all"], str(os.path.splitext(os.path.basename(latest_file))[0]))


# Ideas for future development:
# Load in fm tactic and show scores for each position in tactic
# Best XI for you squad based on tactic
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

def select_best_teams(squad_rawdata, position_requirements, min_score, locked_players=None, excluded_positions=None, global_exclusions=None):
    # Use the existing DataFrame
    df = squad_rawdata.copy()

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

        print(melted_df)

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

    return (first_team, first_team_avg_score), (second_team, second_team_avg_score), (third_team, third_team_avg_score)


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