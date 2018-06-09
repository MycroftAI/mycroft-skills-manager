import git


class Git(git.cmd.Git):
    """Prevents asking for password for private repos"""
    env = {'GIT_ASKPASS': 'echo'}

    def __getattr__(self, item):
        def wrapper(*args, **kwargs):
            env = kwargs.pop('env', {})
            env.update(self.env)
            return super(Git, self).__getattr__(item)(*args, env=env, **kwargs)
        return wrapper
