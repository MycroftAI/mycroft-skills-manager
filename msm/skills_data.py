"""
    Functions related to manipulating the skills_data.json
"""

import json
from os.path import expanduser, isfile


def load_skills_data() -> dict:
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


def write_skills_data(data: dict):
    skills_data_file = expanduser('~/.mycroft/skills.json')
    with open(skills_data_file, 'w') as f:
        json.dump(data, f, indent=4, separators=(',', ':'))


def get_skill_entry(name, skills_data) -> dict:
    """ Find a skill entry in the skills_data and returns it. """
    for e in skills_data.get('skills', []):
        if e.get('name') == name:
            return e
    return {}


def build_skill_entry(name, origin, beta, skill_gid) -> dict:
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


def skills_data_hash(data):
    return hash(json.dumps(data, sort_keys=True))
