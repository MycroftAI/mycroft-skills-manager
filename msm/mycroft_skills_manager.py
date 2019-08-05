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
"""Install, remove, update and track the skills on a device

MSM can be used on the command line but is also used by Mycroft core daemons.
"""
import time
import logging
from functools import wraps
from glob import glob
from multiprocessing.pool import ThreadPool
from os.path import expanduser, join, dirname, isdir
from typing import Dict, List

from msm import GitException
from msm.exceptions import (
    MsmException,
    SkillNotFound,
    MultipleSkillMatches,
    AlreadyInstalled
)
from msm.skill_entry import SkillEntry
from msm.skill_repo import SkillRepo
from msm.skills_data import (
    build_skill_entry,
    get_skill_entry,
    write_skills_data,
    load_skills_data,
    skills_data_hash
)
from msm.util import cached_property, MsmProcessLock

LOG = logging.getLogger(__name__)

CURRENT_SKILLS_DATA_VERSION = 2
ONE_DAY = 86400


def save_skills_data(func):
    """Decorator to write the skills.json file when skills manifest changes.

    The methods decorated with this function are executed in threads.  So,
    this contains some funky logic to keep the threads from stepping on one
    another.
    """
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
    _all_skills = None
    _default_skills = None
    _local_skills = None
    SKILL_GROUPS = {'default', 'mycroft_mark_1', 'picroft', 'kde',
                    'respeaker', 'mycroft_mark_2', 'mycroft_mark_2pi'}
    DEFAULT_SKILLS_DIR = "/opt/mycroft/skills"

    def __init__(self, platform='default', skills_dir=None, repo=None,
                 versioned=True):
        self.platform = platform
        self.skills_dir = (
                expanduser(skills_dir or '') or self.DEFAULT_SKILLS_DIR
        )
        self.repo = repo or SkillRepo()
        self.versioned = versioned
        self.lock = MsmProcessLock()

        self.skills_data = None
        self.saving_handled = False
        self.skills_data_hash = ''
        with self.lock:
            self._init_skills_data()

    @cached_property(ttl=ONE_DAY)
    def all_skills(self) -> List[SkillEntry]:
        """Getting a list of skills can take a while so cache it.

        The list method is called several times in this class and in core.
        Skill data on a device just doesn't change that frequently so
        getting a fresh list that many times does not make a lot of sense.
        The cache will expire every hour to pick up any changes in the
        mycroft-skills repo.

        Skill installs and updates will invalidate the cache, which will
        cause this property to refresh next time is is referenced.

        The list method can be called directly if a fresh skill list is needed.
        """
        if self._all_skills is None:
            self._all_skills = self.list()

        return self._all_skills

    def list(self):
        """Load a list of SkillEntry objects from both local and remote skills

        It is necessary to load both local and remote skills at
        the same time to correctly associate local skills with the name
        in the repo and remote skills with any custom path that they
        have been downloaded to.

        The return value of this function is cached in the all_skills property.
        Only call this method if you need a fresh version of the SkillEntry
        objects.
        """
        LOG.info('building SkillEntry objects for all skills')
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

        self._invalidate_skills_cache(new_value=all_skills)

        return all_skills

    @property
    def local_skills(self) -> Dict[str: SkillEntry]:
        """Property containing a dictionary of local skills keyed by name."""
        if self._local_skills is None:
            self._local_skills = {
                s.name: s for s in self.all_skills if s.is_local
            }

        return self._local_skills

    @property
    def default_skills(self) -> Dict[str: SkillEntry]:
        """Property containing dictionary of default skills keyed by name."""
        if self._default_skills is None:
            default_skill_groups = self.list_all_defaults()
            try:
                default_skill_group = default_skill_groups[self.platform]
            except KeyError:
                LOG.error(
                    'No default skill list found for platform "{}".  '
                    'Using base list.'.format(self.platform)
                )
                default_skill_group = default_skill_groups.get('default', [])
            self._default_skills = {s.name: s for s in default_skill_group}

        return self._default_skills

    def list_all_defaults(self) -> Dict[str, List[SkillEntry]]:
        """Generate dictionary of default skills in all default skill groups"""
        all_skills = {skill.name: skill for skill in self.all_skills}
        default_skills = {group: [] for group in self.SKILL_GROUPS}

        for group_name, skill_names in self.repo.get_default_skill_names():
            group_skills = []
            for skill_name in skill_names:
                try:
                    group_skills.append(all_skills[skill_name])
                except KeyError:
                    LOG.warning('No such default skill: ' + skill_name)
            default_skills[group_name] = group_skills

        return default_skills

    def _upgrade_skills_data(self, skills_data):
        """Upgrade the contents of the skill manifest if needed."""
        if skills_data.get('version', 0) == 0:
            skills_data = self._upgrade_to_v1(skills_data)
        if skills_data['version'] == 1:
            skills_data = self._upgrade_to_v2(skills_data)
        return skills_data

    def _upgrade_to_v1(self, skills_data):
        """Upgrade the skills manifest data to version one."""
        new = {
            'blacklist': [],
            'version': 1,
            'skills': []
        }
        for skill in self.local_skills.values():
            if 'origin' in skills_data.get(skill.name, {}):
                origin = skills_data[skill.name]['origin']
            elif skill.name in self.default_skills:
                origin = 'default'
            elif skill.url:
                origin = 'cli'
            else:
                origin = 'non-msm'
            beta = skills_data.get(skill.name, {}).get('beta', False)
            entry = build_skill_entry(skill.name, origin, beta,
                                      skill.skill_gid)
            entry['installed'] = \
                skills_data.get(skill.name, {}).get('installed') or 0
            if isinstance(entry['installed'], bool):
                entry['installed'] = 0

            entry['update'] = \
                skills_data.get(skill.name, {}).get('updated') or 0

            new['skills'].append(entry)
        new['upgraded'] = True
        return new

    def _upgrade_to_v2(self, skills_data):
        """Upgrade the skill manifest to version 2.

        This adds the skill_gid field to skill entries.
        """
        for s in skills_data['skills']:
            if s['name'] in self.local_skills:
                skill_info = self.local_skills[s['name']]
                s['skill_gid'] = skill_info.skill_gid
            else:
                s['skill_gid'] = ''
        skills_data['version'] = 2
        skills_data['upgraded'] = True
        return skills_data

    def curate_skills_data(self, skills_data):
        """Sync skills_data with actual skills on disk."""
        skills_data_skills = [s['name'] for s in skills_data['skills']]

        # Check for skills that aren't in the list
        for skill in self.local_skills.values():
            if skill.name not in skills_data_skills:
                if skill.name in self.default_skills:
                    origin = 'default'
                elif skill.url:
                    origin = 'cli'
                else:
                    origin = 'non-msm'
                entry = build_skill_entry(skill.name, origin, False,
                                          skill.skill_gid)
                skills_data['skills'].append(entry)

        # Check for skills in the list that doesn't exist in the filesystem
        remove_list = []
        for s in skills_data.get('skills', []):
            if (s['name'] not in self.local_skills and
                    s['installation'] == 'installed'):
                remove_list.append(s)
        for skill in remove_list:
            skills_data['skills'].remove(skill)

        # Update skill gids
        for s in self.local_skills.values():
            for e in skills_data['skills']:
                if e['name'] == s.name:
                    e['skill_gid'] = s.skill_gid

        return skills_data

    def _init_skills_data(self):
        """Initial load of the skills manifest that occurs upon instantiation.

        If the skills manifest was upgraded after it was loaded, write the
        updated manifest to disk.
        """
        self.skills_data = self.load_skills_data()
        if 'upgraded' in self.skills_data:
            self.skills_data.pop('upgraded')
            self.write_skills_data()
        else:
            self.skills_data_hash = skills_data_hash(self.skills_data)

    def load_skills_data(self) -> dict:
        """Load internal skill manifest from disk and update if needed."""
        skills_data = load_skills_data()
        if skills_data.get('version', 0) < CURRENT_SKILLS_DATA_VERSION:
            skills_data = self._upgrade_skills_data(skills_data)
        else:
            skills_data = self.curate_skills_data(skills_data)

        return skills_data

    def write_skills_data(self, data: dict = None):
        """Write skills manifest to disk if it has been modified."""
        data = data or self.skills_data
        if skills_data_hash(data) != self.skills_data_hash:
            write_skills_data(data)
            self.skills_data_hash = skills_data_hash(data)

    @save_skills_data
    def install(self, param, author=None, constraints=None, origin=''):
        """Install by url or name"""
        if isinstance(param, SkillEntry):
            skill = param
        else:
            skill = self.find_skill(param, author)
        entry = build_skill_entry(skill.name, origin, skill.is_beta,
                                  skill.skill_gid)
        try:
            skill.install(constraints)
            entry['installed'] = time.time()
            entry['installation'] = 'installed'
            entry['status'] = 'active'
            entry['beta'] = skill.is_beta
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
                self._invalidate_skills_cache()

    @save_skills_data
    def remove(self, param, author=None):
        """Remove by url or name"""
        if isinstance(param, SkillEntry):
            skill = param
        else:
            skill = self.find_skill(param, author)
        skill.remove()
        skills = [
            s for s in self.skills_data['skills'] if s['name'] != skill.name
        ]
        self.skills_data['skills'] = skills
        self._invalidate_skills_cache()

    def update_all(self):
        def update_skill(skill: SkillEntry):
            entry = get_skill_entry(skill.name, self.skills_data)
            if entry:
                entry['beta'] = skill.is_beta
            if skill.update():
                self._invalidate_skills_cache()
                if entry:
                    entry['updated'] = time.time()

        return self.apply(update_skill, self.local_skills.values())

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
                    self._invalidate_skills_cache()

    @save_skills_data
    def apply(self, func, skills, max_threads=20):
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

        with ThreadPool(max_threads) as tp:
            return tp.map(run_item, skills)

    @save_skills_data
    def install_defaults(self):
        """Installs the default skills, updates all others"""

        def install_or_update_skill(skill):
            if skill.is_local:
                self.update(skill)
            else:
                self.install(skill, origin='default')

        return self.apply(
            install_or_update_skill,
            self.default_skills.values()
        )

    def _invalidate_skills_cache(self, new_value: List[SkillEntry] = None):
        """Reset the cached skill lists in case something changed.

        The cached_property decorator builds a _cache instance attribute
        storing a dictionary of cached values.  Deleting from this attribute
        invalidates the cache.
        """
        LOG.info('invalidating skills cache')
        if hasattr(self, '_cache'):
            del self._cache['all_skills']
        self._all_skills = None if new_value is None else new_value
        self._local_skills = None
        self._default_skills = None

    def find_skill(
            self,
            param: str,
            author: str = None,
            skills: List[SkillEntry] = None
    ) -> SkillEntry:
        """Find skill by name or url"""
        if param.startswith('https://') or param.startswith('http://'):
            repo_id = SkillEntry.extract_repo_id(param)
            for skill in self.all_skills:
                if skill.id == repo_id:
                    return skill
            name = SkillEntry.extract_repo_name(param)
            path = SkillEntry.create_path(self.skills_dir, param)
            return SkillEntry(name, path, param, msm=self)
        else:
            skill_confs = {
                skill: skill.match(param, author)
                for skill in skills or self.all_skills
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
