"""FM26 role attribute weights (factory defaults).

Ported from `fm26_player_scoring_system_v2_0.html`. Each role is a
weighted average of attributes:

    score = (5 * sum(key) + 3 * sum(preferred) + 1 * sum(useful)) / divisor

Tiers are Key (×5, neon green), Preferred (×3, yellow-green), and
Useful (×1, blue). Colors are display-only; saved packs use
`key_attrs` / `preferred_attrs` / `useful_attrs`. Older packs still
use `green_attrs` / `blue_attrs` and are remapped on load.

FM26 roles have no Attack/Support/Defend duty. `phase` is IP, OOP, GK,
IP_GK, or OOP_GK. Keeper IP/OOP variants still count as GK. `role_code`
is the short id used by the HTML scorer.

Position groups (`GROUP_IDS`) are not the same thing as a role name or
the player filter cards on Role scores:

- `wm` Wide midfielders — home of Wide Midfielder, Winger (`W`), Inside
  Winger, etc. Dict: `wm_positions`.
- `w` Wingers — home of Wide Forward and Inside Forward. Dict:
  `w_positions`.
- Role `Winger_IP` (code `W`) lives in `wm`, not in `w`.
- The Role scores “Winger” card (AML / AMR) is a player-position filter
  covering both `wm` and `w`.

A role’s `groups` list is extra buckets on top of the dict it lives in.
Import-time `_HOME_GROUPS` prepends the home id. Eligibility is OR
across that list. Saved packs use `group_schema` 2; older files mapped
`w` → wide mids and `wam` → wingers. See docs/ARCHITECTURE.md.
"""

KEY_WEIGHT = 5
PREFERRED_WEIGHT = 3
USEFUL_WEIGHT = 1


def role(key_attrs, preferred_attrs=(), useful_attrs=(), *, phase, role_code, groups=()):
    """Build a scorer-compatible role dict and derive the divisor.

    `groups` lists extra position buckets besides the dict this role lives
    in, e.g. `groups=('w',)` on a wide-midfielder role so it is also
    eligible as a winger.
    """
    key_attrs = list(key_attrs)
    preferred_attrs = list(preferred_attrs)
    useful_attrs = list(useful_attrs)
    return {
        "key_attrs": key_attrs,
        "preferred_attrs": preferred_attrs,
        "useful_attrs": useful_attrs,
        "key_weight": KEY_WEIGHT,
        "preferred_weight": PREFERRED_WEIGHT,
        "useful_weight": USEFUL_WEIGHT,
        "divisor": (
            KEY_WEIGHT * len(key_attrs)
            + PREFERRED_WEIGHT * len(preferred_attrs)
            + USEFUL_WEIGHT * len(useful_attrs)
        ),
        "phase": phase,
        "role_code": role_code,
        "groups": list(groups),
    }


# Goalkeepers
gk_positions = {
    'Goalkeeper_IP_GK': role(
        ['1v1', 'Han', 'Ref'],
        ['Ant', 'Cmd', 'Cmp', 'Cnt', 'Dec', 'Jum', 'Pos'],
        ['Kic', 'Thr'],
        phase='IP_GK',
        role_code='GK',
    ),
    'Goalkeeper_OOP_GK': role(
        ['1v1', 'Han', 'Ref'],
        ['Ant', 'Cmd', 'Cmp', 'Cnt', 'Dec', 'Jum', 'Pos'],
        ['Kic', 'Thr'],
        phase='OOP_GK',
        role_code='GK',
    ),
    'No_Nonsense_Goalkeeper_IP_GK': role(
        ['Cmd', 'Han', 'Jum', 'Ref'],
        ['1v1', 'Ant', 'Cnt', 'Hea', 'Pos'],
        ['Cmp', 'Dec', 'Kic', 'Thr'],
        phase='IP_GK',
        role_code='NGK',
    ),
    'Line_Holding_Keeper_OOP_GK': role(
        ['Cnt', 'Han', 'Pos', 'Ref'],
        ['1v1', 'Ant', 'Cmd', 'Dec'],
        ['Kic', 'Thr'],
        phase='OOP_GK',
        role_code='LHK',
    ),
    'Sweeper_Keeper_OOP_GK': role(
        ['1v1', 'Acc', 'Ant', 'Han', 'Pac', 'Ref'],
        ['Cmd', 'Dec', 'Pos'],
        [],
        phase='OOP_GK',
        role_code='SKP',
    ),
    'Ball_Playing_Goalkeeper_IP_GK': role(
        ['Cmp', 'Han', 'Kic', 'Ref', 'Thr'],
        ['1v1', 'Ant', 'Cmd', 'Dec', 'Pas'],
        ['Cnt', 'Pos'],
        phase='IP_GK',
        role_code='BGK',
    ),
}


# Centre-backs (including wide CBs)
cb_positions = {
    'Centre_Back_IP': role(
        ['Hea', 'Mar', 'Pos', 'Str', 'Tck'],
        ['Ant', 'Cmp', 'Cnt', 'Dec', 'Jum'],
        ['Acc', 'Pac'],
        phase='IP',
        role_code='CB',
    ),
    'No_Nonsense_Centre_Back_OOP': role(
        ['Hea', 'Jum', 'Mar', 'Pos', 'Str', 'Tck'],
        ['Ant', 'Bra', 'Cnt'],
        ['Cmp', 'Dec'],
        phase='OOP',
        role_code='NCB',
    ),
    'Covering_Centre_Back_OOP': role(
        ['Ant', 'Cnt', 'Mar', 'Pos', 'Str'],
        ['Acc', 'Dec', 'Hea', 'Pac'],
        [],
        phase='OOP',
        role_code='CCB',
    ),
    'Stopping_Centre_Back_OOP': role(
        ['Acc', 'Ant', 'Pac', 'Str', 'Tck'],
        ['Agg', 'Bra', 'Dec', 'Pos'],
        [],
        phase='OOP',
        role_code='SCB',
    ),
    'Ball_Playing_Centre_Back_IP': role(
        ['Cmp', 'Dec', 'Pas'],
        ['Ant', 'Cnt', 'Fir', 'Hea', 'Mar', 'Pos', 'Str', 'Tck', 'Tec', 'Vis'],
        ['Dri'],
        phase='IP',
        role_code='BCB',
    ),
    'Overlapping_Centre_Back_IP': role(
        ['Acc', 'Pac', 'Sta'],
        ['Ant', 'Cnt', 'Cro', 'Hea', 'Mar', 'OtB', 'Pos', 'Str', 'Tck', 'Wor'],
        [],
        phase='IP',
        role_code='OCB',
    ),
    'Advanced_Centre_Back_IP': role(
        ['Dec', 'Pas', 'Sta'],
        ['Acc', 'Ant', 'Cmp', 'Cnt', 'Dri', 'Fir', 'Hea', 'Mar', 'Pac', 'Pos', 'Str', 'Tck'],
        [],
        phase='IP',
        role_code='ACB',
    ),
    'Wide_Centre_Back_IP': role(
        ['Mar', 'Pos', 'Sta', 'Str', 'Tck'],
        ['Acc', 'Ant', 'Cnt', 'Hea', 'Pac', 'Wor'],
        [],
        phase='IP',
        role_code='WCB',
    ),
    'Covering_Wide_Centre_Back_OOP': role(
        ['Ant', 'Cnt', 'Mar', 'Pos', 'Str'],
        ['Dec', 'Pac'],
        [],
        phase='OOP',
        role_code='CWCB',
    ),
    'Stopping_Wide_Centre_Back_OOP': role(
        ['Acc', 'Agg', 'Ant', 'Pac', 'Tck'],
        ['Bra', 'Dec', 'Pos'],
        [],
        phase='OOP',
        role_code='SWCB',
    ),
}


# Full-backs
fb_positions = {
    'Full_Back_IP': role(
        ['Acc', 'Pac', 'Sta'],
        ['Ant', 'Cnt', 'Cro', 'Dec', 'Mar', 'OtB', 'Pos', 'Str', 'Tck'],
        [],
        phase='IP',
        role_code='FB',
    ),
    'Holding_Full_Back_OOP': role(
        ['Ant', 'Cnt', 'Mar', 'Pos', 'Sta', 'Str'],
        ['Dec', 'Tck'],
        ['Pac'],
        phase='OOP',
        role_code='HFB',
    ),
    'Inside_Full_Back_IP': role(
        ['Dec', 'Pas', 'Sta'],
        ['Acc', 'Ant', 'Cnt', 'Mar', 'Pac', 'Pos', 'Tck', 'Tec', 'Vis'],
        [],
        phase='IP',
        role_code='IFB',
    ),
    'Inverted_Full_Back_IP': role(
        ['Dec', 'Pas', 'Sta'],
        ['Acc', 'Ant', 'Cmp', 'Cnt', 'Mar', 'Pac', 'Pos', 'Tck', 'Tec', 'Vis'],
        [],
        phase='IP',
        role_code='IVFB',
    ),
    'Pressing_Full_Back_OOP': role(
        ['Acc', 'Ant', 'Pac', 'Sta', 'Tck', 'Wor'],
        ['Agg', 'Bra', 'Cnt'],
        [],
        phase='OOP',
        role_code='PFB',
    ),
}


# Wing-backs
wb_positions = {
    'Wing_Back_IP': role(
        ['Acc', 'Cro', 'Pac', 'Sta', 'Wor'],
        ['Ant', 'Dec', 'Fir', 'Mar', 'OtB', 'Tck'],
        [],
        phase='IP',
        role_code='WB',
    ),
    'Holding_Wing_Back_OOP': role(
        ['Ant', 'Cnt', 'Mar', 'Pos', 'Sta', 'Str'],
        ['Dec', 'Tck'],
        [],
        phase='OOP',
        role_code='HWB',
    ),
    'Inside_Wing_Back_OOP': role(
        ['Cnt', 'Pos', 'Sta', 'Tea'],
        ['Acc', 'Dec', 'Mar', 'Pac', 'Pas', 'Tck', 'Tec', 'Vis'],
        [],
        phase='OOP',
        role_code='IWB',
    ),
    'Inverted_Wing_Back_IP': role(
        ['Dec', 'Pas', 'Sta'],
        ['Acc', 'Cmp', 'Mar', 'Pac', 'Tck', 'Tec', 'Vis'],
        [],
        phase='IP',
        role_code='IVWB',
    ),
    'Pressing_Wing_Back_OOP': role(
        ['Acc', 'Ant', 'Pac', 'Sta', 'Tck', 'Wor'],
        ['Agg', 'Bra'],
        [],
        phase='OOP',
        role_code='PWB',
    ),
    'Playmaking_Wing_Back_IP': role(
        ['Dec', 'Pas', 'Sta', 'Tec', 'Vis', 'Wor'],
        ['Acc', 'Cro', 'Fir', 'OtB', 'Pac'],
        ['Mar', 'Tck'],
        phase='IP',
        role_code='PMWB',
    ),
    'Advanced_Wing_Back_IP': role(
        ['Acc', 'Cro', 'OtB', 'Pac', 'Sta', 'Wor'],
        ['Ant', 'Dri', 'Fir'],
        ['Mar', 'Tck'],
        phase='IP',
        role_code='AWB',
    ),
}


# Defensive midfield
dm_positions = {
    'Defensive_Midfielder_IP': role(
        ['Pos', 'Sta'],
        ['Ant', 'Cmp', 'Cnt', 'Dec', 'Pas', 'Str', 'Tck', 'Tea'],
        [],
        phase='IP',
        role_code='DM',
    ),
    'Dropping_Defensive_Midfielder_OOP': role(
        ['Ant', 'Cnt', 'Mar', 'Pos', 'Sta', 'Str'],
        ['Cmp', 'Dec'],
        [],
        phase='OOP',
        role_code='DDM',
    ),
    'Screening_Defensive_Midfielder_OOP': role(
        ['Ant', 'Cnt', 'Pos', 'Sta', 'Tea'],
        ['Dec', 'Mar', 'Str', 'Tck'],
        [],
        phase='OOP',
        role_code='SDM',
    ),
    'Wide_Covering_Defensive_Midfielder_OOP': role(
        ['Ant', 'Mar', 'Pos', 'Sta', 'Tck', 'Wor'],
        ['Acc', 'Dec', 'Pac'],
        [],
        phase='OOP',
        role_code='WCDM',
    ),
    'Half_Back_IP': role(
        ['Cmp', 'Dec', 'Pas', 'Pos', 'Sta'],
        ['Ant', 'Cnt', 'Mar', 'Str', 'Tck', 'Vis'],
        [],
        phase='IP',
        role_code='HB',
    ),
    'Pressing_Defensive_Midfielder_OOP': role(
        ['Ant', 'Sta', 'Tck', 'Wor'],
        ['Acc', 'Agg', 'Bra', 'Dec', 'Pac'],
        [],
        phase='OOP',
        role_code='PDM',
    ),
    'Deep_Lying_Playmaker_IP': role(
        ['Dec', 'Fir', 'Pas', 'Sta', 'Tec', 'Vis'],
        ['Ant', 'Cmp', 'Pos', 'Str', 'Tea'],
        [],
        phase='IP',
        role_code='DLP',
    ),
}


# Central midfield
cm_positions = {
    'Central_Midfielder_IP': role(
        ['Dec', 'Pas', 'Sta', 'Wor'],
        ['Ant', 'Cnt', 'Fir', 'Tea', 'Tec', 'Vis'],
        [],
        phase='IP',
        role_code='CM',
    ),
    'Screening_Central_Midfielder_OOP': role(
        ['Ant', 'Cnt', 'Pos', 'Sta', 'Tea'],
        ['Dec', 'Mar', 'Str'],
        [],
        phase='OOP',
        role_code='SCM',
    ),
    'Wide_Covering_Central_Midfielder_OOP': role(
        ['Ant', 'Mar', 'Pos', 'Sta', 'Tck', 'Wor'],
        ['Acc', 'Pac'],
        [],
        phase='OOP',
        role_code='WCM',
    ),
    'Box_to_Box_Midfielder_IP': role(
        ['Sta', 'Wor'],
        ['Acc', 'Ant', 'Dec', 'OtB', 'Pac', 'Pas', 'Str', 'Tck', 'Tea'],
        ['Fin'],
        phase='IP',
        role_code='BBM',
    ),
    'Box_to_Box_Playmaker_IP': role(
        ['Dec', 'Pas', 'Sta', 'Vis', 'Wor'],
        ['Acc', 'Dri', 'Fir', 'OtB', 'Pac', 'Tec'],
        [],
        phase='IP',
        role_code='BBPM',
    ),
    'Channel_Midfielder_IP': role(
        ['Acc', 'OtB', 'Pac', 'Sta', 'Wor'],
        ['Ant', 'Dec', 'Dri', 'Fir', 'Pas', 'Vis'],
        [],
        phase='IP',
        role_code='CHM',
    ),
    'Midfield_Playmaker_IP': role(
        ['Dec', 'Fir', 'Pas', 'Sta', 'Tec', 'Vis'],
        ['Ant', 'Cmp', 'OtB', 'Tea'],
        ['Dri'],
        phase='IP',
        role_code='MPM',
    ),
    'Pressing_Central_Midfielder_OOP': role(
        ['Acc', 'Ant', 'Pac', 'Sta', 'Tck', 'Wor'],
        ['Agg', 'Bra', 'Dec'],
        [],
        phase='OOP',
        role_code='PCM',
    ),
}


# Attacking midfield
am_positions = {
    'Attacking_Midfielder_IP': role(
        ['Dec', 'Fir', 'Pas', 'Sta', 'Tec'],
        ['Acc', 'Ant', 'Cmp', 'Dri', 'OtB', 'Pac', 'Vis'],
        [],
        phase='IP',
        role_code='AM',
    ),
    'Tracking_Attacking_Midfielder_OOP': role(
        ['Ant', 'Pos', 'Sta', 'Tea', 'Wor'],
        ['Cnt', 'Dec', 'Tck'],
        [],
        phase='OOP',
        role_code='TAM',
    ),
    'Advanced_Playmaker_IP': role(
        ['Dec', 'Fir', 'Pas', 'Tec', 'Vis'],
        ['Acc', 'Ant', 'Cmp', 'Dri', 'Fla', 'OtB', 'Pac'],
        [],
        phase='IP',
        role_code='APM',
    ),
    'Central_Outlet_Attacking_Midfielder_OOP': role(
        ['Acc', 'Ant', 'OtB', 'Pac', 'Sta'],
        ['Fin'],
        [],
        phase='OOP',
        role_code='COAM',
    ),
    'Splitting_Outlet_Attacking_Midfielder_OOP': role(
        ['Acc', 'Ant', 'OtB', 'Pac', 'Sta'],
        ['Agi', 'Dri', 'Fla'],
        [],
        phase='OOP',
        role_code='SOAM',
    ),
    'Free_Role_IP': role(
        ['Dec', 'Fir', 'Fla', 'Tec', 'Vis'],
        ['Acc', 'Cmp', 'Dri', 'OtB', 'Pac', 'Pas'],
        [],
        phase='IP',
        role_code='FR',
    ),
}


# Wide midfielders (group id: wm)
wm_positions = {
    'Wide_Midfielder_IP': role(
        ['Cro', 'Sta', 'Wor'],
        ['Acc', 'Ant', 'Dec', 'Fir', 'OtB', 'Pac', 'Pas'],
        [],
        phase='IP',
        role_code='WM',
    ),
    'Tracking_Wide_Midfielder_OOP': role(
        ['Ant', 'Pos', 'Sta', 'Tck', 'Wor'],
        ['Cnt', 'Dec', 'Mar', 'Pac'],
        [],
        phase='OOP',
        role_code='TWM',
    ),
    'Wide_Central_Midfielder_IP': role(
        ['Dec', 'Pas', 'Sta', 'Vis', 'Wor'],
        ['Acc', 'Fir', 'OtB', 'Pac', 'Tec'],
        [],
        phase='IP',
        role_code='WCMF',
    ),
    'Wide_Outlet_Wide_Midfielder_OOP': role(
        ['Acc', 'Ant', 'OtB', 'Pac', 'Sta'],
        [],
        [],
        phase='OOP',
        role_code='WOWM',
    ),
    'Winger_IP': role(
        ['Acc', 'Cro', 'Pac', 'Sta', 'Wor'],
        ['Dri', 'Fir', 'OtB', 'Tec'],
        [],
        phase='IP',
        role_code='W',
    ),
    'Half_Space_Winger_IP': role(
        ['Acc', 'OtB', 'Pac', 'Sta'],
        ['Ant', 'Dec', 'Dri', 'Fir', 'Pas', 'Tec', 'Vis'],
        [],
        phase='IP',
        role_code='HSW',
    ),
    'Inside_Winger_IP': role(
        ['Acc', 'Dri', 'OtB', 'Pac', 'Sta'],
        ['Agi', 'Ant', 'Fin', 'Fir', 'Fla', 'Tec'],
        [],
        phase='IP',
        role_code='IW',
        groups=('w',),
    ),
    'Inverting_Outlet_Winger_OOP': role(
        ['Acc', 'Ant', 'OtB', 'Pac', 'Sta'],
        ['Dec', 'Fir', 'Vis'],
        [],
        phase='OOP',
        role_code='IOW',
    ),
    'Tracking_Winger_OOP': role(
        ['Ant', 'Pos', 'Sta', 'Tck', 'Wor'],
        ['Cnt', 'Dec', 'Mar', 'Pac'],
        [],
        phase='OOP',
        role_code='TW',
    ),
    'Wide_Outlet_Winger_OOP': role(
        ['Acc', 'Ant', 'OtB', 'Pac', 'Sta'],
        [],
        [],
        phase='OOP',
        role_code='WOW',
    ),
    'Wide_Playmaker_IP': role(
        ['Dec', 'Fir', 'Pas', 'Sta', 'Tec', 'Vis'],
        ['Acc', 'Dri', 'Fla', 'OtB', 'Pac'],
        [],
        phase='IP',
        role_code='WPM',
    ),
}


# Wingers (group id: w)
w_positions = {
    'Wide_Forward_IP': role(
        ['Acc', 'Fin', 'OtB', 'Pac', 'Sta'],
        ['Agi', 'Ant', 'Cmp', 'Dri', 'Fir', 'Tec'],
        [],
        phase='IP',
        role_code='WFD',
    ),
    'Inside_Forward_IP': role(
        ['Acc', 'Dri', 'Fin', 'Pac', 'Sta'],
        ['Agi', 'Ant', 'Fir', 'Fla', 'OtB', 'Tec'],
        [],
        phase='IP',
        role_code='IF',
        groups=('wm',),
    ),
}


# Strikers
st_positions = {
    'Centre_Forward_IP': role(
        ['Ant', 'Fin', 'Hea', 'OtB', 'Str'],
        ['Acc', 'Cmp', 'Dec', 'Fir', 'Jum', 'Pac'],
        [],
        phase='IP',
        role_code='CF',
    ),
    'False_Nine_IP': role(
        ['Dec', 'Fir', 'OtB', 'Pas', 'Tec', 'Vis'],
        ['Acc', 'Ant', 'Cmp', 'Dri', 'Fin'],
        [],
        phase='IP',
        role_code='F9',
    ),
    'Deep_Lying_Forward_IP': role(
        ['Cmp', 'Dec', 'Fir', 'Pas', 'Tec'],
        ['Ant', 'Fin', 'OtB', 'Str', 'Vis'],
        [],
        phase='IP',
        role_code='DLF',
    ),
    'Half_Space_Forward_IP': role(
        ['Acc', 'Ant', 'Dri', 'Fin', 'OtB', 'Pac'],
        ['Agi', 'Dec', 'Fir', 'Tec'],
        [],
        phase='IP',
        role_code='HSF',
    ),
    'Channel_Forward_IP': role(
        ['Acc', 'Ant', 'Fin', 'OtB', 'Pac'],
        ['Agi', 'Dec', 'Dri', 'Fir'],
        [],
        phase='IP',
        role_code='CHF',
    ),
    'Second_Striker_IP': role(
        ['Ant', 'Dec', 'Fin', 'OtB', 'Sta'],
        ['Acc', 'Cmp', 'Dri', 'Fir', 'Pac', 'Tec'],
        [],
        phase='IP',
        role_code='SS',
    ),
    'Central_Outlet_Centre_Forward_OOP': role(
        ['Acc', 'Ant', 'OtB', 'Pac', 'Sta'],
        ['Fin'],
        [],
        phase='OOP',
        role_code='COCF',
    ),
    'Splitting_Outlet_Centre_Forward_OOP': role(
        ['Acc', 'Ant', 'Dri', 'OtB', 'Pac', 'Sta'],
        ['Agi', 'Fla'],
        [],
        phase='OOP',
        role_code='SOCF',
    ),
    'Tracking_Centre_Forward_OOP': role(
        ['Ant', 'Sta', 'Tea', 'Wor'],
        ['Acc', 'OtB', 'Pac', 'Str'],
        [],
        phase='OOP',
        role_code='TCF',
    ),
    'Target_Forward_IP': role(
        ['Ant', 'Hea', 'Jum', 'Str'],
        ['Agg', 'Bra', 'Cmp', 'Fin', 'Fir', 'OtB'],
        [],
        phase='IP',
        role_code='TF',
    ),
    'Poacher_IP': role(
        ['Ant', 'Cmp', 'Fin', 'OtB'],
        ['Acc', 'Agi', 'Dec', 'Fir', 'Pac'],
        [],
        phase='IP',
        role_code='P',
    ),
}


all_positions = {
    **gk_positions,
    **cb_positions,
    **fb_positions,
    **wb_positions,
    **dm_positions,
    **cm_positions,
    **am_positions,
    **wm_positions,
    **w_positions,
    **st_positions,
}

GROUP_IDS = ("gk", "cb", "fb", "wb", "dm", "cm", "am", "wm", "w", "st")

# Pack group_schema 1 (or missing): w = wide mids, wam = wingers.
# Schema 2 (current): wm = wide mids, w = wingers.
GROUP_SCHEMA = 2
GROUP_ID_LEGACY = {"w": "wm", "wam": "w"}

_HOME_GROUPS = (
    ("gk", gk_positions),
    ("cb", cb_positions),
    ("fb", fb_positions),
    ("wb", wb_positions),
    ("dm", dm_positions),
    ("cm", cm_positions),
    ("am", am_positions),
    ("wm", wm_positions),
    ("w", w_positions),
    ("st", st_positions),
)
for _home, _roles in _HOME_GROUPS:
    for _cfg in _roles.values():
        extras = [g for g in (_cfg.get("groups") or []) if g != _home and g in GROUP_IDS]
        _cfg["groups"] = [_home, *extras]

role_code_to_id = {
    cfg['role_code']: role_id
    for role_id, cfg in all_positions.items()
}
