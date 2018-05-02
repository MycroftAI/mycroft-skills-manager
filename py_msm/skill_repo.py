from __future__ import print_function

from glob import glob
from os import makedirs

from git import Repo
from git.cmd import Git
from git.exc import GitCommandError
from os.path import exists, join, isdir, dirname, basename

from py_msm.exceptions import MsmException


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
