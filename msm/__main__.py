from __future__ import print_function

import logging
from logging import ERROR, INFO

from msm.exceptions import MsmException
from msm.mycroft_skills_manager import MycroftSkillsManager
from msm.skill_repo import SkillRepo

LOG = logging.getLogger(__name__)


def skill_info(skill):
    print('\n'.join([
        'Name: ' + skill.name,
        'Author: ' + str(skill.author),
        'Url: ' + str(skill.url),
        'Path: ' + (str(skill.path) if skill.is_local else 'Not installed')
    ]))


def main():
    logging.basicConfig(level=INFO, format='%(levelname)s - %(message)s')

    import argparse
    platforms = list(MycroftSkillsManager.SKILL_GROUPS)
    parser = argparse.ArgumentParser()
    parser.add_argument('-p', '--platform', choices=platforms,
                        default='default')
    parser.add_argument('-u', '--repo-url')
    parser.add_argument('-b', '--repo-branch')
    parser.add_argument('-d', '--skills-dir')
    parser.add_argument('-l', '--latest', action='store_false',
                        dest='versioned', help="Disable skill versioning")
    parser.add_argument('-r', '--raw', action='store_true')
    parser.set_defaults(raw=False, versioned=True)
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
    msm = MycroftSkillsManager(args.platform, args.skills_dir, repo,
                               args.versioned)
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
        result = main_functions[args.action]()
        if result is False:
            return 1
    except MsmException as e:
        exc_type = e.__class__.__name__
        print('{}: {}'.format(exc_type, str(e)))
        return 1 + (sum(map(ord, exc_type)) % 255)


if __name__ == "__main__":
    main()
