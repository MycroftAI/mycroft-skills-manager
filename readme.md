## Py MSM

Mycroft Skill Manager, in python!

## install

    pip install py_msm

## Usage

```python
from py_msm import MycroftSkillsManager, SkillRepo, MultipleSkillMatches

msm = MycroftSkillsManager(repo=SkillRepo(branch='master'))

# msm = MycroftSkillsManager(platform='picroft', skills_dir='/some/path', repo=SkillRepo(branch='master', url='https://github.com/me/my-repo.git')

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

- permissions issues in mark1/picroft - prepare_msm.sh script
- get hashes before git pulling to decide if pip and res.sh should be run
- handle pip sudo if not in venv
- requirements.sh guide / template
- parse readme.md from skills

## New Features

- checks for skill_requirements.txt, will install skills listed there

## troubleshooting

got problem? most likely you forgot 

    workon mycroft

## Credits

JarbasAI
