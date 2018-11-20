# Copyright (c) 2018 Mycroft AI, Inc.
#
# This file is part of Mycroft Skills Manager
# (see https://github.com/MatthewScholefield/mycroft-light).
#
# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
import logging
from glob import glob
from itertools import chain
from multiprocessing.pool import ThreadPool
from os.path import expanduser, join, dirname, isdir
from functools import wraps
import time

from typing import Dict, List

from msm import GitException
from msm.exceptions import (MsmException, SkillNotFound, MultipleSkillMatches,
                            AlreadyInstalled)
from msm.skill_entry import SkillEntry
from msm.skill_repo import SkillRepo
from msm.skills_data import (build_skill_entry, get_skill_entry,
                             write_skills_data, load_skills_data,
                             skills_data_hash)

from msm.util import MsmProcessLock

LOG = logging.getLogger(__name__)

CURRENT_SKILLS_DATA_VERSION = 1


def save_skills_data(func):
    @wraps(func)
    def func_wrapper(self, *args, **kwargs):
        will_save = False
        if not self.saving_handled:
            will_save = self.saving_handled = True
        try:
            ret = func(self, *args, **kwargs)
            # Write only if no exception occurs
            if will_save:
                self.write_skills_data()
        finally:
            # Always restore saving_handled flag
            if will_save:
                self.saving_handled = False

        return ret

    return func_wrapper


class MycroftSkillsManager(object):
    SKILL_GROUPS = {'default', 'mycroft_mark_1', 'picroft', 'kde'}
    DEFAULT_SKILLS_DIR = "/opt/mycroft/skills"

    def __init__(self, platform='default', skills_dir=None, repo=None,
                 versioned=True):
        self.platform = platform
        self.skills_dir = expanduser(skills_dir or '') \
                          or self.DEFAULT_SKILLS_DIR
        self.repo = repo or SkillRepo()
        self.versioned = versioned
        self.lock = MsmProcessLock()

        self.skills_data = None
        self.saving_handled = False
        with self.lock:
            self.sync_skills_data()

    def __upgrade_skills_data(self, skills_data):
        new = {}
        if skills_data.get('version', 0) == 0:
            new['blacklist'] = []
            new['version'] = 1
            new['skills'] = []
            local_skills = [s for s in self.list() if s.is_local]
            default_skills = [s.name for s in self.list_defaults()]
            for skill in local_skills:
                if 'origin' in skills_data.get(skill.name, {}):
                    origin = skills_data[skill.name]['origin']
                elif skill.name in default_skills:
                    origin = 'default'
                elif skill.url:
                    origin = 'cli'
                else:
                    origin = 'non-msm'
                beta = skills_data.get(skill.name, {}).get('beta', False)
                entry = build_skill_entry(skill.name, origin, beta)
                entry['installed'] = \
                    skills_data.get(skill.name, {}).get('installed') or 0
                if isinstance(entry['installed'], bool):
                    entry['installed'] = 0

                entry['update'] = \
                    skills_data.get(skill.name, {}).get('updated') or 0

                new['skills'].append(entry)
            new['upgraded'] = True
        return new

    def curate_skills_data(self, skills_data):
        """ Sync skills_data with actual skills on disk. """
        local_skills = [s for s in self.list() if s.is_local]
        default_skills = [s.name for s in self.list_defaults()]
        local_skill_names = [s.name for s in local_skills]
        skills_data_skills = [s['name'] for s in skills_data['skills']]

        # Check for skills that aren't in the list
        for skill in local_skills:
            if skill.name not in skills_data_skills:
                if skill.name in default_skills:
                    origin = 'default'
                elif skill.url:
                    origin = 'cli'
                else:
                    origin = 'non-msm'
                entry = build_skill_entry(skill.name, origin, False)
                skills_data['skills'].append(entry)

        # Check for skills in the list that doesn't exist in the filesystem
        remove_list = []
        for s in skills_data.get('skills', []):
            if (s['name'] not in local_skill_names and
                    s['installation'] == 'installed'):
                remove_list.append(s)
        for skill in remove_list:
            skills_data['skills'].remove(skill)
        return skills_data

    def load_skills_data(self) -> dict:
        skills_data = load_skills_data()
        if skills_data.get('version', 0) < CURRENT_SKILLS_DATA_VERSION:
            skills_data = self.__upgrade_skills_data(skills_data)
        else:
            skills_data = self.curate_skills_data(skills_data)
        return skills_data

    def sync_skills_data(self):
        """ Update internal skill_data_structure from disk. """
        self.skills_data = self.load_skills_data()
        if 'upgraded' in self.skills_data:
            self.skills_data.pop('upgraded')
            self.skills_data_hash = ''
        else:
            self.skills_data_hash = skills_data_hash(self.skills_data)

    def write_skills_data(self, data=None):
        """ Write skills data hash if it has been modified. """
        data = data or self.skills_data
        if skills_data_hash(data) != self.skills_data_hash:
            write_skills_data(data)

    @save_skills_data
    def install(self, param, author=None, constraints=None, origin=''):
        """Install by url or name"""
        if isinstance(param, SkillEntry):
            skill = param
        else:
            skill = self.find_skill(param, author)
        entry = build_skill_entry(skill.name, origin, skill.is_beta)
        try:
            skill.install(constraints)
            entry['installed'] = time.time()
            entry['installation'] = 'installed'
            entry['status'] = 'active'
        except AlreadyInstalled:
            entry = None
            raise
        except MsmException as e:
            entry['installation'] = 'failed'
            entry['status'] = 'error'
            entry['failure_message'] = repr(e)
            raise
        finally:
            # Store the entry in the list
            if entry:
                self.skills_data['skills'].append(entry)

    @save_skills_data
    def remove(self, param, author=None):
        """Remove by url or name"""
        if isinstance(param, SkillEntry):
            skill = param
        else:
            skill = self.find_skill(param, author)
        skill.remove()
        skills = [s for s in self.skills_data['skills']
                  if s['name'] != skill.name]
        self.skills_data['skills'] = skills
        return

    def update_all(self):
        local_skills = [skill for skill in self.list() if skill.is_local]

        def update_skill(skill):
            entry = get_skill_entry(skill.name, self.skills_data)
            if entry:
                entry['beta'] = skill.is_beta
            if skill.update():
                if entry:
                    entry['updated'] = time.time()

        return self.apply(update_skill, local_skills)

    @save_skills_data
    def update(self, skill=None, author=None):
        """Update all downloaded skills or one specified skill."""
        if skill is None:
            return self.update_all()
        else:
            if isinstance(skill, str):
                skill = self.find_skill(skill, author)
            entry = get_skill_entry(skill.name, self.skills_data)
            if entry:
                entry['beta'] = skill.is_beta
            if skill.update():
                # On successful update update the update value
                if entry:
                    entry['updated'] = time.time()

    @save_skills_data
    def apply(self, func, skills):
        """Run a function on all skills in parallel"""

        def run_item(skill):
            try:
                func(skill)
                return True
            except MsmException as e:
                LOG.error('Error running {} on {}: {}'.format(
                    func.__name__, skill.name, repr(e)
                ))
                return False
            except:
                LOG.exception('Error running {} on {}:'.format(
                    func.__name__, skill.name
                ))

        with ThreadPool(100) as tp:
            return (tp.map(run_item, skills))

    @save_skills_data
    def install_defaults(self):
        """Installs the default skills, updates all others"""
        def install_or_update_skill(skill):
            if skill.is_local:
                self.update(skill)
            else:
                self.install(skill, origin='default')

        return self.apply(install_or_update_skill, self.list_defaults())

    def list_all_defaults(self):  # type: () -> Dict[str, List[SkillEntry]]
        """Returns {'skill_group': [SkillEntry('name')]}"""
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

    def list_defaults(self):
        skill_groups = self.list_all_defaults()

        if self.platform not in skill_groups:
            LOG.error('Unknown platform:' + self.platform)
        return skill_groups.get(self.platform,
                                skill_groups.get('default', []))

    def list(self):
        """
        Load a list of SkillEntry objects from both local and
        remote skills

        It is necessary to load both local and remote skills at
        the same time to correctly associate local skills with the name
        in the repo and remote skills with any custom path that they
        have been downloaded to
        """
        try:
            self.repo.update()
        except GitException as e:
            if not isdir(self.repo.path):
                raise
            LOG.warning('Failed to update repo: {}'.format(repr(e)))
        remote_skill_list = (
            SkillEntry(
                name, SkillEntry.create_path(self.skills_dir, url, name),
                url, sha if self.versioned else '', msm=self
            )
            for name, path, url, sha in self.repo.get_skill_data()
        )
        remote_skills = {
            skill.id: skill for skill in remote_skill_list
        }
        all_skills = []
        for skill_file in glob(join(self.skills_dir, '*', '__init__.py')):
            skill = SkillEntry.from_folder(dirname(skill_file), msm=self)
            if skill.id in remote_skills:
                skill.attach(remote_skills.pop(skill.id))
            all_skills.append(skill)
        all_skills += list(remote_skills.values())
        return all_skills

    def find_skill(self, param, author=None, skills=None):
        # type: (str, str, List[SkillEntry]) -> SkillEntry
        """Find skill by name or url"""
        if param.startswith('https://') or param.startswith('http://'):
            repo_id = SkillEntry.extract_repo_id(param)
            for skill in self.list():
                if skill.id == repo_id:
                    return skill
            name = SkillEntry.extract_repo_name(param)
            path = SkillEntry.create_path(self.skills_dir, param)
            return SkillEntry(name, path, param, msm=self)
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
