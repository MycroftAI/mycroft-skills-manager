import logging
import subprocess
from difflib import SequenceMatcher
from shutil import rmtree

import sys

import os

from git import Repo, CommandError
from git.cmd import Git
from git.exc import GitCommandError
from os.path import exists, join, basename, dirname
from subprocess import call, PIPE, Popen

from msm import SkillRequirementsException, git_to_msm_exceptions
from msm.exceptions import PipRequirementsException, \
    SystemRequirementsException, AlreadyInstalled, SkillModified, \
    AlreadyRemoved, RemoveException, CloneException

LOG = logging.getLogger(__name__)


class SkillEntry(object):
    def __init__(self, name, path, url='', sha='', msm=None):
        url = url.rstrip('/')
        self.name = name
        self.path = path
        self.url = url
        self.sha = sha
        self.msm = msm
        self.author = self._extract_author(url) if url else ''
        self.id = self.extract_repo_id(url) if url else name
        self.is_local = exists(path)

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
            name or cls.extract_repo_name(url), cls._extract_author(url)
        ))

    @staticmethod
    def extract_repo_name(url):
        s = url.rstrip('/').split("/")[-1]
        a, b, c = s.rpartition('.git')
        if not c:
            return a
        return s

    @staticmethod
    def _extract_author(url):
        return url.rstrip('/').split("/")[-2].split(':')[-1]

    @classmethod
    def extract_repo_id(cls, url):
        return '{}:{}'.format(cls._extract_author(url),
                              cls.extract_repo_name(url)).lower()

    @staticmethod
    def _tokenize(x):
        return x.replace('-', ' ').split()

    @staticmethod
    def _extract_tokens(s, tokens):
        s = s.lower().replace('-', '')
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
            query.lower(), ['skill', 'fallback', 'mycroft']
        )

        name, name_tokens, name_common = self._extract_tokens(
            self.name.lower(), ['skill', 'fallback', 'mycroft']
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

    def run_pip(self):
        requirements_file = join(self.path, "requirements.txt")
        if not exists(requirements_file):
            return False

        LOG.info('Installing requirements.txt for ' + self.name)
        can_pip = os.access(dirname(sys.executable), os.W_OK | os.X_OK)
        pip_args = [
            sys.executable, '-m', 'pip', 'install', '-r', requirements_file
        ]

        if not can_pip:
            pip_args = ['sudo', '-n'] + pip_args

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

        subprocess.call(["chmod", "+x", setup_script])
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

    def install(self):
        if self.is_local:
            raise AlreadyInstalled(self.name)

        if self.msm:
            self.run_skill_requirements()

        LOG.info("Downloading skill: " + self.url)
        try:
            Repo.clone_from(self.url, self.path)
            self.is_local = True
            Git(self.path).reset(self.sha or 'HEAD', hard=True)
        except GitCommandError as e:
            raise CloneException(e.stderr)

        self.run_requirements_sh()
        self.run_pip()

        LOG.info('Successfully installed ' + self.name)

    def update_deps(self):
        if self.msm:
            self.run_skill_requirements()
        self.run_requirements_sh()
        self.run_pip()

    def update(self):
        git = Git(self.path)

        with git_to_msm_exceptions():
            sha_before = git.rev_parse('HEAD')

        try:
            git.fetch()
            git.merge(self.sha or 'origin/HEAD', ff_only=True)
        except GitCommandError as e:
            raise SkillModified(e.stderr)

        sha_after = git.rev_parse('HEAD')

        if sha_before != sha_after:
            self.update_deps()
            LOG.info('Updated ' + self.name)
        else:
            LOG.info('Nothing new for ' + self.name)

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
        except CommandError:
            return ''

    def __repr__(self):
        return '<SkillEntry {}>'.format(' '.join(
            '{}={}'.format(attr, self.__dict__[attr])
            for attr in ['name', 'author', 'is_local']
        ))
