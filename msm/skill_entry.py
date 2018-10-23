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
import os
import subprocess
import sys
from contextlib import contextmanager
from difflib import SequenceMatcher
from os.path import exists, join, basename, dirname, isfile
from shutil import rmtree, move
from subprocess import PIPE, Popen
from tempfile import mktemp

from git import Repo, GitError
from git.exc import GitCommandError
from threading import Lock

from msm import SkillRequirementsException, git_to_msm_exceptions
from msm.exceptions import PipRequirementsException, \
    SystemRequirementsException, AlreadyInstalled, SkillModified, \
    AlreadyRemoved, RemoveException, CloneException, NotInstalled
from msm.util import Git

LOG = logging.getLogger(__name__)

# Branches which can be switched from when updating
# TODO Make this configurable
SWITCHABLE_BRANCHES = ['master']

# default constraints to use if no are given
DEFAULT_CONSTRAINTS = '/etc/mycroft/constraints.txt'

@contextmanager
def work_dir(directory):
    old_dir = os.getcwd()
    os.chdir(directory)
    try:
        yield
    finally:
        os.chdir(old_dir)


class SkillEntry(object):
    pip_lock = Lock()

    def __init__(self, name, path, url='', sha='', msm=None):
        url = url.rstrip('/')
        self.name = name
        self.path = path
        self.url = url
        self.sha = sha
        self.msm = msm
        self.author = self.extract_author(url) if url else ''
        self.id = self.extract_repo_id(url) if url else name
        self.is_local = exists(path)

    @property
    def is_beta(self):
        return not self.sha or self.sha == 'HEAD'

    def __str__(self):
        return self.name

    def attach(self, remote_entry):
        """Attach a remote entry to a local entry"""
        self.name = remote_entry.name
        self.sha = remote_entry.sha
        self.url = remote_entry.url
        self.author = remote_entry.author
        return self

    @classmethod
    def from_folder(cls, path, msm=None):
        return cls(basename(path), path, cls.find_git_url(path), msm=msm)

    @classmethod
    def create_path(cls, folder, url, name=''):
        return join(folder, '{}.{}'.format(
            name or cls.extract_repo_name(url), cls.extract_author(url)
        ).lower())

    @staticmethod
    def extract_repo_name(url):
        s = url.rstrip('/').split("/")[-1]
        a, b, c = s.rpartition('.git')
        if not c:
            return a
        return s

    @staticmethod
    def extract_author(url):
        return url.rstrip('/').split("/")[-2].split(':')[-1]

    @classmethod
    def extract_repo_id(cls, url):
        return '{}:{}'.format(cls.extract_author(url).lower(),
                              cls.extract_repo_name(url)).lower()

    @staticmethod
    def _tokenize(x):
        return x.replace('-', ' ').split()

    @staticmethod
    def _extract_tokens(s, tokens):
        s = s.lower().replace('-', ' ')
        extracted = []
        for token in tokens:
            extracted += [token] * s.count(token)
            s = s.replace(token, '')
        s = ' '.join(i for i in s.split(' ') if i)
        tokens = [i for i in s.split(' ') if i]
        return s, tokens, extracted

    @classmethod
    def _compare(cls, a, b):
        return SequenceMatcher(a=a, b=b).ratio()

    def match(self, query, author=None):
        search, search_tokens, search_common = self._extract_tokens(
            query, ['skill', 'fallback', 'mycroft']
        )

        name, name_tokens, name_common = self._extract_tokens(
            self.name, ['skill', 'fallback', 'mycroft']
        )

        weights = [
            (9, self._compare(name, search)),
            (9, self._compare(name.split(' '), search_tokens)),
            (2, self._compare(name_common, search_common)),
        ]
        if author:
            author_weight = self._compare(self.author, author)
            weights.append((5, author_weight))
            author_weight = author_weight
        else:
            author_weight = 1.0
        return author_weight * (
                sum(weight * val for weight, val in weights) /
                sum(weight for weight, val in weights)
        )

    def run_pip(self, constraints):
        requirements_file = join(self.path, "requirements.txt")
        if not exists(requirements_file):
            return False

        # Use constraints to limit the installed versions
        if constraints and not exists(constraints):
            LOG.error('Couldn\'t find the constraints file')
            return False
        elif exists(DEFAULT_CONSTRAINTS):
            constraints = DEFAULT_CONSTRAINTS

        LOG.info('Installing requirements.txt for ' + self.name)
        can_pip = os.access(dirname(sys.executable), os.W_OK | os.X_OK)
        pip_args = [
            sys.executable, '-m', 'pip', 'install', '-r', requirements_file
        ]
        if constraints:
            pip_args += ['-c', constraints]

        if not can_pip:
            pip_args = ['sudo', '-n'] + pip_args

        with self.pip_lock:
            proc = Popen(pip_args, stdout=PIPE, stderr=PIPE)
            pip_code = proc.wait()
        if pip_code != 0:
            stderr = proc.stderr.read().decode()
            if pip_code == 1 and 'sudo:' in stderr and pip_args[0] == 'sudo':
                raise PipRequirementsException(
                    2, '', 'Permission denied while installing pip '
                           'dependencies. Please run in virtualenv or use sudo'
                )
            raise PipRequirementsException(
                pip_code, proc.stdout.read().decode(), stderr
            )

        return True

    def run_requirements_sh(self):
        setup_script = join(self.path, "requirements.sh")
        if not exists(setup_script):
            return False

        with work_dir(self.path):
            rc = subprocess.call(["bash", setup_script])

        if rc != 0:
            LOG.error("Requirements.sh failed with error code: " + str(rc))
            raise SystemRequirementsException(rc)
        LOG.info("Successfully ran requirements.sh for " + self.name)
        return True

    def run_skill_requirements(self):
        if not self.msm:
            raise ValueError('Pass msm to SkillEntry to install skill deps')
        try:
            for skill_dep in self.get_dependent_skills():
                LOG.info("Installing skill dependency: {}".format(skill_dep))
                try:
                    self.msm.install(skill_dep)
                except AlreadyInstalled:
                    pass
        except Exception as e:
            raise SkillRequirementsException(e)

    def get_dependent_skills(self):
        reqs = join(self.path, "skill_requirements.txt")
        if not exists(reqs):
            return []

        with open(reqs, "r") as f:
            return [i.strip() for i in f.readlines() if i.strip()]

    def install(self, constraints=None):
        if self.is_local:
            raise AlreadyInstalled(self.name)

        if self.msm:
            self.run_skill_requirements()

        LOG.info("Downloading skill: " + self.url)
        try:
            tmp_location = mktemp()
            Repo.clone_from(self.url, tmp_location)
            self.is_local = True
            Git(tmp_location).reset(self.sha or 'HEAD', hard=True)
        except GitCommandError as e:
            raise CloneException(e.stderr)

        if isfile(join(tmp_location, '__init__.py')):
            move(join(tmp_location, '__init__.py'),
                 join(tmp_location, '__init__'))

        try:
            move(tmp_location, self.path)

            self.run_requirements_sh()
            self.run_pip(constraints)
        finally:
            if isfile(join(self.path, '__init__')):
                move(join(self.path, '__init__'),
                     join(self.path, '__init__.py'))

        LOG.info('Successfully installed ' + self.name)

    def update_deps(self, constraints=None):
        if self.msm:
            self.run_skill_requirements()
        self.run_requirements_sh()
        self.run_pip(constraints)

    def _find_sha_branch(self):
        git = Git(self.path)
        sha_branches = git.branch(
            contains=self.sha, all=True
        ).split('\n')
        sha_branch = [b for b in sha_branches if ' -> ' not in b][0]
        sha_branch = sha_branch.strip('* \n').replace('remotes/', '')
        for remote in git.remote().split('\n'):
            sha_branch = sha_branch.replace(remote + '/', '')
        return sha_branch

    def update(self):
        if not self.is_local:
            raise NotInstalled('{} is not installed'.format(self.name))
        git = Git(self.path)

        with git_to_msm_exceptions():
            sha_before = git.rev_parse('HEAD')

            modified_files = git.status(porcelain=True, untracked='no')
            if modified_files != '':
                raise SkillModified('Uncommitted changes:\n' + modified_files)

            git.fetch()
            current_branch = git.rev_parse('--abbrev-ref', 'HEAD').strip()
            if self.sha and current_branch in SWITCHABLE_BRANCHES:
                # Check out correct branch
                git.checkout(self._find_sha_branch())

            git.merge(self.sha or 'origin/HEAD', ff_only=True)

        sha_after = git.rev_parse('HEAD')

        if sha_before != sha_after:
            self.update_deps()
            LOG.info('Updated ' + self.name)
            # Trigger reload by modifying the timestamp
            os.utime(join(self.path, '__init__.py'))
            return True
        else:
            LOG.info('Nothing new for ' + self.name)
            return False

    def remove(self):
        if not self.is_local:
            raise AlreadyRemoved(self.name)
        try:
            rmtree(self.path)
        except OSError as e:
            raise RemoveException(str(e))

        LOG.info('Successfully removed ' + self.name)
        self.is_local = False

    @staticmethod
    def find_git_url(path):
        """Get the git url from a folder"""
        try:
            return Git(path).config('remote.origin.url')
        except GitError:
            return ''

    def __repr__(self):
        return '<SkillEntry {}>'.format(' '.join(
            '{}={}'.format(attr, self.__dict__[attr])
            for attr in ['name', 'author', 'is_local']
        ))
