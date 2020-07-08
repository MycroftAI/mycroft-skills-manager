import requests
from msm import MycroftSkillsManager
from msm.util import xml2dict
from msm.skill_entry import SkillEntry
import json


def _parse_pling(skill, msm):

    if isinstance(skill, str):
        json_data = json.loads(skill)
    else:
        json_data = skill

    # TODO is it a safe assumption downloadlink1 is always the skill.json ?
    # this can be made smarter
    url = json_data["downloadlink1"]
    skill_json = requests.get(url).json()

    # save useful data to skill.meta_info
    skill_json["category"] = json_data['typename']
    skill_json["created"] = json_data['created']
    skill_json["modified"] = json_data['changed']
    skill_json["description"] = json_data["description"]
    skill_json["tags"] = json_data['tags'].split(",")
    skill_json["author"] = json_data['personid']
    skill_json["version"] = json_data["version"]

    # appstore data
    # TODO also provide this from mycroft appstore
    skill_json["appstore"] = "pling.opendesktop"
    skill_json["appurl"] = json_data["detailpage"]

    return SkillEntry.from_json(skill_json, msm)


def list_skills(msm=None):
    msm = msm or MycroftSkillsManager()

    url = "https://api.kde-look.org/ocs/v1/content/data"
    params = {"categories": "608", "page": 0}
    xml = requests.get(url, params=params).text

    data = xml2dict(xml)
    meta = data["ocs"]["meta"]
    n_pages = int(meta["totalitems"]) // int(meta["itemsperpage"])

    for skill in data["ocs"]["data"]["content"]:
        yield _parse_pling(skill, msm)

    for n in range(1, n_pages + 1):
        params = {"categories": "608", "page": n}
        xml = requests.get(url, params=params).text

        for skill in xml2dict(xml)["ocs"]["data"]["content"]:
            yield _parse_pling(skill, msm)


def search(name, author=None, msm=None, min_conf=0.3):
    msm = msm or MycroftSkillsManager()
    for skill in list_skills(msm):
        if skill.match(name, author) >= min_conf:
            yield skill
