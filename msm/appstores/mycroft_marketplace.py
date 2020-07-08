from msm import MycroftSkillsManager


def search(name, author=None, msm=None, min_conf=0.3):
    for skill in list_skills(msm):
        if skill.match(name, author) >= min_conf:
            yield skill


def list_skills(msm=None):
    msm = msm or MycroftSkillsManager()
    for skill in msm.list():
        yield skill

