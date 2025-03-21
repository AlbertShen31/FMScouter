import os
from typing import List, Dict, Union
import logging
import config.role_weight_config as pc

logger = logging.getLogger(__name__)

    # Calculate the score for each position
def calculate_score(
    data: Dict[str, Union[str, int]], 
    key_attrs: List[str], 
    green_attrs: List[str], 
    blue_attrs: List[str], 
    key_weight: float, 
    green_weight: float, 
    blue_weight: float, 
    divisor: float
) -> float:
    """Calculate position score based on attributes and weights."""
    try:
        processed_data = {}
        for attr in key_attrs + green_attrs + blue_attrs:
            value = data.get(attr, 0)
            if value == '-' or value == '':
                processed_data[attr] = 0
            elif isinstance(value, str) and '-' in value:
                processed_data[attr] = int(value.split('-')[0])
            else:
                processed_data[attr] = int(value)

        key_score = sum(processed_data[attr] for attr in key_attrs)
        green_score = sum(processed_data[attr] for attr in green_attrs)
        blue_score = sum(processed_data[attr] for attr in blue_attrs)

        total_score = (key_score * key_weight + green_score * green_weight + blue_score * blue_weight) / divisor
        return round(total_score, 1)
    except Exception as e:
        logger.error(f"Error calculating score: {e}")
        return 0.0

def format_position_name(position):
    # Remove the underscores and use the initial of each word
    single_letter_pos = ["goalkeeper_defend", "winger_support", "winger_attack", "anchor_defend", "poacher_attack"]
    if position.lower() == "raumdeter_attack":
        return "RMD(A)"
    elif "segundo_volante" in position.lower():
        return "VOL(" + position.upper().split('_')[2][0] + ")"
    elif position.lower() == "box_to_box_midfielder_support":
        return "BBM(S)"
    elif position.lower() == "false_nine_support":
        return "F9(S)"
    elif position.lower() == "roaming_playmaker_support":
        return "RPM(S)"
    elif len(position.split('_')) == 2 and (position.lower() not in single_letter_pos):
        initials = position.split('_')
        return ("".join(initials[0][:3]) + "(" + initials[1][0] + ")").upper()

    initials = [word[0] for word in position.split('_')]
    return ("".join(initials[:-1]) + "(" + initials[-1] + ")").upper()

def translate_position_to_field_area(position: str) -> str:
    """Translate player position to field area."""    
    roles = set()

    parsed_pos = parse_positions(position)

    for parsed in parsed_pos:
        if parsed['position'] == 'GK':
            roles.add('Goalkeeper')
        elif parsed['position'] == 'D':
            if 'L' in parsed['area'] or 'R' in parsed['area']:
                roles.add('Wide Defender')
            else:
                roles.add('Center Defender')
        elif parsed['position'] == 'WB':
            roles.add('Wide Defender')
        elif parsed['position'] == 'DM':
            roles.add('Center Midfielder')
        elif parsed['position'] == 'M':
            if 'C' in parsed['area']:
                roles.add('Center Midfielder')
            else:
                roles.add('Winger')
        elif parsed['position'] == 'AM':
            roles.add('Attacker')
        elif parsed['position'] == 'ST':
            roles.add('Attacker')

    return roles

def parse_positions(position_str):
    """
    Parse complex position strings into a structured format.
    
    Args:
        position_str (str): A string representing player positions
    
    Returns:
        list: A list of dictionaries, each containing position and area details
    """
    # Split multiple position groups
    position_groups = [group.strip() for group in position_str.split(',')]
    
    parsed_positions = []
    
    for group in position_groups:
        # Split position and area (if exists)
        parts = group.split('(')
        
        # Clean up positions and areas
        positions = [pos.strip() for pos in parts[0].split('/')]
        area = parts[1].strip(')') if len(parts) > 1 else ''
        
        for pos in positions:
            if pos == 'DM':
                area = 'C'
            parsed_positions.append({
                'position': pos,
                'area': area
            })
    
    return parsed_positions




