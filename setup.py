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
from setuptools import setup

setup(
    name='msm',
    version='0.6.3',
    packages=['msm'],
    install_requires=['GitPython', 'typing', 'fasteners'],
    url='https://github.com/MycroftAI/mycroft-skills-manager',
    license='Apache-2.0',
    author='jarbasAI, Matthew Scholefield',
    author_email='jarbasai@mailfence.com, matthew331199@gmail.com',
    description='Mycroft Skills Manager',
    entry_points={
        'console_scripts': {
            'msm=msm.__main__:main'
        }
    },
    data_files=[('msm', ['LICENSE'])]
)
