from __future__ import print_function

import logging
import subprocess
from difflib import SequenceMatcher
from glob import glob
from itertools import chain
from logging import ERROR, DEBUG
from os import makedirs
from shutil import rmtree

from git import Repo
from git.cmd import Git
from git.exc import GitCommandError
from os.path import exists, expanduser, join, isdir, dirname, basename
from typing import Dict, List

from py_msm.exceptions import PipRequirementsException, \
    SystemRequirementsException, AlreadyInstalled, SkillModified, \
    AlreadyRemoved, RemoveException, MsmException, InstallException, \
    SkillNotFound, MultipleSkillMatches, CloneException

__author__ = "JarbasAI"
MainModule = '__init__'

logging.basicConfig(level=DEBUG, format='%(levelname)s - %(message)s')
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
            (2, self._compare(name_common, search_common))
        ]
        if author:
            weights.append((5, self._compare(self.author, author)))
        return (
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


class SkillRepo(object):
    def __init__(self, path=None, url=None, branch=None):
        self.path = path or "/opt/mycroft/.skills-repo"
        self.url = url or "https://github.com/MycroftAI/mycroft-skills"
        self.branch = branch or "18.02"

    def read_file(self, filename):
        with open(join(self.path, filename)) as f:
            return f.read()

    def update(self):
        if not exists(dirname(self.path)):
            makedirs(dirname(self.path))

        if not isdir(self.path):
            Repo.clone_from(self.url, self.path)

        git = Git(self.path)
        git.config('remote.origin.url', self.url)
        git.fetch()
        try:
            git.reset('origin/' + self.branch, hard=True)
        except GitCommandError as e:
            raise MsmException('Invalid branch: ' + self.branch)

    def get_submodules(self):
        """ generates tuples of skill_name, skill_url """
        modules = self.read_file('.gitmodules').split('[submodule "')
        for module in modules:
            if not module:
                continue
            name = module.split('"]')[0].strip()
            url = module.split('url = ')[1].strip()
            yield name, url

    def get_default_skill_names(self):
        for defaults_file in glob(join(self.path, 'DEFAULT-SKILLS*')):
            with open(defaults_file) as f:
                skills = filter(
                    lambda x: x and not x.startswith('#'),
                    map(str.strip, f.read().split('\n'))
                )
            platform = basename(defaults_file).replace('DEFAULT-SKILLS', '')
            platform = platform.replace('.', '') or 'default'
            yield platform, skills


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
            for skill_file in glob(join(self.skills_dir, '*',
                                        MainModule + '.py'))
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
            LOG.debug('Best match ({}): {} by {}'.format(
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


def skill_info(skill):
    print('\n'.join([
        'Name: ' + skill.name,
        'Author: ' + str(skill.author),
        'Url: ' + str(skill.url),
        'Path: ' + str(skill.path) if skill.is_local else 'Not installed'
    ]))


def main():
    import argparse
    platforms = list(MycroftSkillsManager.SKILL_GROUPS)
    parser = argparse.ArgumentParser()
    parser.add_argument('-p', '--platform', choices=platforms)
    parser.add_argument('-u', '--repo-url')
    parser.add_argument('-b', '--repo-branch')
    parser.add_argument('-d', '--skills-dir')
    parser.add_argument('-r', '--raw', action='store_true')
    parser.set_defaults(raw=False)
    subparsers = parser.add_subparsers(dest='action')
    subparsers.required = True

    def add_search_args(subparser):
        subparser.add_argument('skill')
        subparser.add_argument('author', nargs='?')

    add_search_args(subparsers.add_parser('install'))
    add_search_args(subparsers.add_parser('remove'))
    add_search_args(subparsers.add_parser('search'))
    add_search_args(subparsers.add_parser('info'))
    subparsers.add_parser('list').add_argument('-i', '--installed',
                                               action='store_true')
    subparsers.add_parser('update')
    subparsers.add_parser('default')
    args = parser.parse_args()

    if args.raw:
        LOG.level = ERROR

    repo = SkillRepo(url=args.repo_url, branch=args.repo_branch)
    msm = MycroftSkillsManager(args.platform, args.skills_dir, repo)
    main_functions = {
        'install': lambda: msm.install(args.skill, args.author),
        'remove': lambda: msm.remove(args.skill, args.author),
        'list': lambda: print('\n'.join(
            skill.name + (
                '\t[installed]' if skill.is_local and not args.raw else ''
            )
            for skill in msm.list()
            if not args.installed or skill.is_local
        )),
        'update': msm.update,
        'default': msm.install_defaults,
        'search': lambda: print('\n'.join(
            skill.name
            for skill in msm.list()
            if skill.match(args.skill, args.author) >= 0.3
        )),
        'info': lambda: skill_info(msm.find_skill(args.skill, args.author))
    }
    try:
        main_functions[args.action]()
    except MsmException as e:
        exc_type = e.__class__.__name__
        print('{}: {}'.format(exc_type, str(e)))
        return 1 + (sum(map(ord, exc_type)) % 255)


if __name__ == "__main__":
    main()
