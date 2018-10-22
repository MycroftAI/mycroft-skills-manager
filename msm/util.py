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
import git
from os.path import exists
from os import chmod
from fasteners.process_lock import InterProcessLock

class Git(git.cmd.Git):
    """Prevents asking for password for private repos"""
    env = {'GIT_ASKPASS': 'echo'}

    def __getattr__(self, item):
        def wrapper(*args, **kwargs):
            env = kwargs.pop('env', {})
            env.update(self.env)
            return super(Git, self).__getattr__(item)(*args, env=env, **kwargs)
        return wrapper


class MsmProcessLock(InterProcessLock):
    def __init__(self):
        lock_path = '/tmp/msm_lock'
        if not exists(lock_path):
            lock_file = open(lock_path, '+w')
            lock_file.close()
            chmod(lock_path, 0o777)
        super().__init__(lock_path)
