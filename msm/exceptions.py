from contextlib import contextmanager
from future.utils import raise_from

from git import CommandError


class MsmException(Exception):
    def __repr__(self):
        s = self.__str__().rstrip('\n')
        if '\n' in s:
            s = s.replace('\n', '\n\t') + '\n'
        return '{}({})'.format(self.__class__.__name__, s)


class GitException(MsmException):
    pass


class SkillModified(MsmException):
    """
    Raised when a skill cannot be updated because
    it has been modified by the user
    """
    pass


class RemoveException(MsmException):
    pass


class AlreadyRemoved(RemoveException):
    pass


class InstallException(MsmException):
    pass


class SkillNotFound(InstallException):
    pass


class SkillRequirementsException(InstallException):
    pass


class CloneException(InstallException):
    pass


class AlreadyInstalled(InstallException):
    pass


class SystemRequirementsException(InstallException):
    pass


class PipRequirementsException(InstallException):
    def __init__(self, code, stdout, stderr):
        self.code, self.stdout, self.stderr = code, stdout, stderr

    def __str__(self):
        return '\nPip returned code {}:\n{}\n{}'.format(
            self.code, self.stdout, self.stderr
        )


class MultipleSkillMatches(MsmException):
    def __init__(self, skills):
        self.skills = skills

    def __str__(self):
        return ', '.join(skill.name for skill in self.skills)


@contextmanager
def git_to_msm_exceptions():
    try:
        yield
    except CommandError as e:
        raise_from(GitException('Git command failed: {}'.format(repr(e))), e)
