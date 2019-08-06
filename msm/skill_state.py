"""
    Functions related to manipulating the skills_data.json
"""

import json
from os.path import expanduser, isfile


def load_device_skill_state() -> dict:
    """Contains info on how skills should be updated"""
    skills_data_file = expanduser('~/.mycroft/skills.json')
    if isfile(skills_data_file):
        try:
            with open(skills_data_file) as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}
    else:
        return {}


def write_device_skill_state(data: dict):
    skills_data_file = expanduser('~/.mycroft/skills.json')
    with open(skills_data_file, 'w') as f:
        json.dump(data, f, indent=4, separators=(',', ':'))


def get_skill_state(name, device_skill_state) -> dict:
    """ Find a skill entry in the skills_data and returns it. """
    for skill_state in device_skill_state.get('skills', []):
        if skill_state.get('name') == name:
            return skill_state
    return {}


def initialize_skill_state(name, origin, beta, skill_gid) -> dict:
    """ Create a new skill entry
    
    Arguments:
        name: skill name
        origin: the source of the installation
        beta: Boolean indicating wether the skill is in beta
        skill_gid: skill global id
    Returns:
        populated skills entry
    """
    return {
        'name': name,
        'origin': origin,
        'beta': beta,
        'status': 'active',
        'installed': 0,
        'updated': 0,
        'installation': 'installed',
        'skill_gid': skill_gid
    }


def device_skill_state_hash(data):
    return hash(json.dumps(data, sort_keys=True))
