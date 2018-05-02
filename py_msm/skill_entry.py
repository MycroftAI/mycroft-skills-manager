from __future__ import print_function

import logging
import subprocess
from difflib import SequenceMatcher
from shutil import rmtree

from git import Repo
from git.cmd import Git
from git.exc import GitCommandError
from os.path import exists, join, basename

from py_msm.exceptions import PipRequirementsException, \
    SystemRequirementsException, AlreadyInstalled, SkillModified, \
    AlreadyRemoved, RemoveException, CloneException

LOG = logging.getLogger(__name__)


class SkillEntry(object):
    def __init__(self, path, name=None, author=None, url=None):
        self.path = path
        self.name = name or basename(path)
        self.author = author
        self.url = url
        self.repo = SkillEntry.extract_repo(url)
        self.is_local = exists(path)

    @classmethod
    def from_folder(cls, path, repo_to_name):
        url = cls.find_git_url(path).rstrip('/')

        author = cls._extract_author(url) if url else None
        repo = cls.extract_repo(url) if url else None
        name = repo_to_name.get(repo, basename(path))
        return cls(path, name, author, url)

    @classmethod
    def from_url(cls, url, skill_dir, repo_to_name):
        """ shows information about the skill in the specified repo """
        url = url.rstrip('/')

        author = cls._extract_author(url)
        repo = cls.extract_repo(url)

        path = join(skill_dir, '{}.{}'.format(
            cls._extract_folder(url), author
        ))

        name = repo_to_name.get(repo, basename(path))
        return cls(path, name, author, url)

    @staticmethod
    def _extract_folder(url):
        s = url.split("/")[-1]
        a, b, c = s.rpartition('.git')
        if not c:
            return a
        return s

    @staticmethod
    def _extract_author(url):
        return url.split("/")[-2].split(':')[-1]

    @classmethod
    def extract_repo(cls, url):
        return '{}:{}'.format(cls._extract_author(url),
                              cls._extract_folder(url))

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
        # no need for sudo if in venv
        # TODO handle sudo if not in venv
        # TODO check hash before re running
        requirements_file = join(self.path, "requirements.txt")
        if not exists(requirements_file):
            return False

        import pip  # must be here or pip throws error code 2 on threads
        LOG.info('Installing requirements.txt')
        pip_code = pip.main(['install', '-r', requirements_file])
        # TODO parse pip code

        if pip_code != 0:
            LOG.error("pip code: " + str(pip_code))
            raise PipRequirementsException(pip_code)

        return True

    def run_requirements_sh(self):
        setup_script = join(self.path, "requirements.sh")
        # TODO check hash before re running
        if not exists(setup_script):
            return False

        subprocess.call(["chmod", "+x", setup_script])
        rc = subprocess.call(["bash", setup_script])
        if rc != 0:
            LOG.error("Requirements.sh failed with error code: " + str(rc))
            raise SystemRequirementsException(rc)
        LOG.info("Successfully ran requirements.sh for " + self.name)
        return True

    def get_dependent_skills(self):
        reqs = join(self.path, "skill_requirements.txt")
        if not exists(reqs):
            return []

        with open(reqs, "r") as f:
            return [i.strip() for i in f.readlines() if i.strip()]

    def install(self):
        """ installs or updates skill by url """
        if self.is_local:
            raise AlreadyInstalled(self.name)

        LOG.info("Downloading skill: " + self.url)
        try:
            Repo.clone_from(self.url, self.path)
        except GitCommandError as e:
            raise CloneException(str(e))

        self.run_requirements_sh()
        self.run_pip()
        LOG.info('Successfully installed ' + self.name)
        self.is_local = True

    def update(self):
        # TODO compare hashes to decide if pip and res.sh should be run
        # TODO ensure skill master branch is checked out, else dont update
        try:
            Git(self.path).pull(ff_only=True)
        except GitCommandError as e:
            raise SkillModified(e.stderr)

        self.run_requirements_sh()
        self.run_pip()
        LOG.info('Updated ' + self.name)

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
        """ get the git url from a folder"""
        try:
            return Git(path).config('remote.origin.url')
        except GitCommandError:
            return None

    def __repr__(self):
        return '<SkillEntry {}>'.format(' '.join(
            '{}={}'.format(attr, self.__dict__[attr])
            for attr in ['name', 'author', 'is_local']
        ))
