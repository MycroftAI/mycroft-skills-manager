from os.path import dirname, abspath, join, exists

import pytest
from shutil import rmtree

from msm.__main__ import main


class TestMain(object):
    def setup(self):
        self.root = root = dirname(abspath(__file__))
        self.base_params = [
            '-u', 'https://github.com/mycroftai/mycroft-skills-manager',
            '-b', 'test-repo',
            '-c', join(root, 'repo-instance'),
            '-d', join(root, 'test-skills')
        ]

    def teardown(self):
        for i in ['repo-instance', 'test-skills']:
            if join(self.root, i):
                rmtree(join(self.root, i))

    def __call__(self, *args):
        params = self.base_params + ' '.join(map(str, args)).split(' ')

        lines = []

        def printer(text):
            lines.extend(map(str.strip, text.split('\n')))
        print('CALLING:', params)
        ret = main(params, printer)
        if ret != 0:
            raise ValueError('Returned: {} with output {}'.format(
                ret, ' '.join(lines)
            ))
        return lines

    def test(self):
        skill_names = {'skill-a', 'skill-b', 'skill-cd', 'skill-ce'}
        assert set(self('-r list')) == skill_names
        self('install skill-a')
        self('install skill-b')
        self('remove skill-a')
        with pytest.raises(ValueError):
            self('remove skill-a')
        self('search skill-c')
        with pytest.raises(ValueError):
            self('info skill-c')
        self('info skill-cd')
        self('list')
        self('default')
