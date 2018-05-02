class MsmException(Exception):
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


class CloneException(InstallException):
    pass


class AlreadyInstalled(InstallException):
    pass


class SystemRequirementsException(InstallException):
    pass


class PipRequirementsException(InstallException):
    pass


class MultipleSkillMatches(MsmException):
    def __init__(self, skills):
        self.skills = skills

    def __repr__(self):
        return 'MultipleSkillMatches({})'.format(self.__str__())

    def __str__(self):
        return ', '.join(skill.name for skill in self.skills)