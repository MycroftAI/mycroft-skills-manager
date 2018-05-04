from shutil import rmtree

import pytest
from os.path import join, dirname, exists, abspath

from msm import MycroftSkillsManager, AlreadyInstalled, AlreadyRemoved
from msm.exceptions import SkillNotFound, MultipleSkillMatches
from msm.skill_repo import SkillRepo


class TestMycroftSkillsManager(object):
    def setup(self):
        self.root = root = dirname(abspath(__file__))
        self.msm = MycroftSkillsManager(
            platform='default', skills_dir=join(root, 'test-skills'),
            repo=SkillRepo(
                join(root, 'repo-instance'), branch='test-repo',
                url='https://github.com/mycroftai/mycroft-skills-manager'
            ), versioned=True
        )

    def teardown(self):
        if exists(self.msm.skills_dir):
            rmtree(self.msm.skills_dir)
        if exists(self.msm.repo.path):
            rmtree(self.msm.repo.path)

    def test_install(self):
        """Install by url or name"""
        self.msm.install('skill-a')
        with pytest.raises(AlreadyInstalled):
            self.msm.install('skill-a')
        self.msm.install('skill-b')

    def test_remove(self):
        """Remove by url or name"""
        with pytest.raises(AlreadyRemoved):
            self.msm.remove('skill-a')
        self.msm.install('skill-a')
        self.msm.remove('skill-a')

    def test_update(self):
        """Update all downloaded skills"""
        self.msm.install('skill-a')
        self.msm.update()

    def test_install_defaults(self):
        """Installs the default skills, updates all others"""
        assert not self.msm.find_skill('skill-a').is_local
        self.msm.install_defaults()
        assert self.msm.find_skill('skill-a').is_local
        assert not self.msm.find_skill('skill-b').is_local
        self.msm.platform = 'platform-1'
        self.msm.install_defaults()
        assert self.msm.find_skill('skill-b').is_local

    def test_list(self):
        all_skills = {
            'skill-a', 'skill-b', 'skill-cd', 'skill-ce'
        }
        assert {i.name for i in self.msm.list()} == all_skills

    def test_find_skill(self):
        with pytest.raises(MultipleSkillMatches):
            self.msm.find_skill('skill-c')
        with pytest.raises(SkillNotFound):
            self.msm.find_skill('jsafpcq')
