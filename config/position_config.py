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
    }
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
    }
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
    }
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
    }
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
    }
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
    }
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
    }
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

all_positions = {**gk_positions, **fb_positions, **cb_positions, **dm_positions, **cm_positions, **am_positions, **w_positions, **st_positions}