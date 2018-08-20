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
