## Py MSM

Mycroft Skill Manager, in python!

## Install

    pip install py_msm

## Usage

```python
from msm import MycroftSkillsManager, SkillRepo, MultipleSkillMatches

msm = MycroftSkillsManager(repo=SkillRepo(branch='master'))

# msm = MycroftSkillsManager(platform='picroft', skills_dir='/some/path', repo=SkillRepo(branch='master', url='https://github.com/me/my-repo.git'))

print(msm.find_skill('bitcoin price'))
msm.install('bitcoin', 'dmp1ce')
print(msm.list())
print(msm.find_skill("https://github.com/JarbasAl/skill-stephen-hawking"))
msm.update()
msm.install_defaults()

try:
    msm.install('google')
except MultipleSkillMatches as e:
    e.skills[0].install()
```

```bash
msm -b master install bitcoin
msm -b master -p kde default
# ...
```

## TODO

- Parse readme.md from skills

## New Features

- Checks for skill_requirements.txt, will install skills listed there

## Credits

JarbasAI and Mycroft AI
