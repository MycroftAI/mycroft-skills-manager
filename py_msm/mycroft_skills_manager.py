from __future__ import print_function

import logging
from glob import glob
from itertools import chain

from os.path import exists, expanduser, join, dirname
from typing import Dict, List

from py_msm.exceptions import MsmException, InstallException, \
    SkillNotFound, MultipleSkillMatches
from py_msm.skill_entry import SkillEntry
from py_msm.skill_repo import SkillRepo

LOG = logging.getLogger(__name__)


class MycroftSkillsManager(object):
    SKILL_GROUPS = {'default', 'mycroft_mark_1', 'picroft', 'kde'}
    DEFAULT_SKILLS_DIR = "/opt/mycroft/skills"

    def __init__(self, platform='default', skills_dir=None, repo=None):
        self.platform = platform
        self.skills_dir = expanduser(skills_dir or '') \
                          or self.DEFAULT_SKILLS_DIR
        self.repo = repo or SkillRepo()

    def install(self, param, author=None):
        """ install by url or name """
        skill = self.find_skill(param, author)
        skill.install()
        for skill_dep in skill.get_dependent_skills():
            LOG.info("Installing skill dependency: {}".format(skill_dep))
            self.install(skill_dep)

    def remove(self, param, author=None):
        """ remove by url or name"""
        self.find_skill(param, author).remove()

    def update(self):
        """ update all downloaded skills """
        errored = False
        for skill in self.load_local_skill_data():
            try:
                skill.update()
            except MsmException as e:
                LOG.error('Error updating {}: {}'.format(skill, repr(e)))
                errored = True
        return not errored

    def install_defaults(self):
        """ installs the default skills, updates all others """
        errored = False
        default_skills = self.get_defaults()
        for group in {"default", self.platform}:
            if group not in default_skills:
                LOG.warning('No such platform: {}'.format(group))
                continue
            LOG.info("Installing {} skills".format(group))
            for skill in default_skills[group]:
                try:
                    if not skill.is_local:
                        skill.install()
                    else:
                        skill.update()
                except InstallException as e:
                    LOG.error('Error installing {}: {}'.format(skill, repr(e)))
                    errored = True
        return not errored

    def get_defaults(self):  # type: () -> Dict[str, List[SkillEntry]]
        """ returns {'skill_group': [SkillEntry('name')]} """
        self.repo.update()
        skills = self.list()
        name_to_skill = {skill.name: skill for skill in skills}
        defaults = {group: [] for group in self.SKILL_GROUPS}

        for section_name, skill_names in self.repo.get_default_skill_names():
            section_skills = []
            for skill_name in skill_names:
                if skill_name in name_to_skill:
                    section_skills.append(name_to_skill[skill_name])
                else:
                    LOG.warning('No such default skill: ' + skill_name)
                defaults[section_name] = section_skills

        return defaults

    @staticmethod
    def _unique_skills(skills):
        return list({i.repo: i for i in skills}.values())

    def _generate_repo_to_name(self):
        return {
            SkillEntry.extract_repo(url): name
            for name, url in self.repo.get_submodules()
        }

    def list(self):
        return self._unique_skills(chain(
            self.load_remote_skill_data(),
            self.load_local_skill_data()
        ))

    def load_local_skill_data(self):
        """ load data about downloaded skills """
        if not exists(self.skills_dir):
            return []

        repo_to_name = self._generate_repo_to_name()
        return (
            SkillEntry.from_folder(dirname(skill_file), repo_to_name)
            for skill_file in glob(join(self.skills_dir, '*', '__init__.py'))
        )

    def load_remote_skill_data(self):
        """ get skills list from skills repo """
        self.repo.update()
        repo_to_name = self._generate_repo_to_name()

        for name, url in self.repo.get_submodules():
            yield SkillEntry.from_url(url, self.skills_dir, repo_to_name)

    def find_skill(self, param, author=None, skills=None):
        # type: (str, str, List[SkillEntry]) -> SkillEntry
        """Find skill by name or url"""
        if param.startswith('https://') or param.startswith('http://'):
            repo_to_name = self._generate_repo_to_name()
            return SkillEntry.from_url(param, self.skills_dir, repo_to_name)
        else:
            skill_confs = {
                skill: skill.match(param, author)
                for skill in skills or self.list()
            }
            best_skill, score = max(skill_confs.items(), key=lambda x: x[1])
            LOG.info('Best match ({}): {} by {}'.format(
                round(score, 2), best_skill.name, best_skill.author)
            )
            if score < 0.3:
                raise SkillNotFound(param)
            low_bound = (score * 0.7) if score != 1.0 else 1.0

            close_skills = [
                skill for skill, conf in skill_confs.items()
                if conf >= low_bound and skill != best_skill
            ]
            if close_skills:
                raise MultipleSkillMatches([best_skill] + close_skills)
            return best_skill
