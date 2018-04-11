from mycroft.configuration.config import Configuration, LocalConf, USER_CONFIG
from mycroft.skills.core import MainModule
from mycroft.util.parse import match_one
from mycroft.util.log import LOG
from os.path import exists, expanduser, join, isdir
from os import makedirs, listdir, remove
import requests
import subprocess
import pip
from git import Repo
from git.cmd import Git
from time import sleep


__author__ = "JarbasAI"


class MycroftSkillsManager(object):
    DEFAULT_SKILLS = {}
    SKILLS_MODULES = "https://raw.githubusercontent.com/MycroftAI/mycroft-skills/master/.gitmodules"
    SKILLS_DEFAULTS_URL = "https://raw.githubusercontent.com/MycroftAI/mycroft-skills/master/DEFAULT-SKILLS"

    def __init__(self, emitter=None, skills_config=None, defaults_url=None, modules_url=None):
        self.skills_config = skills_config or Configuration.get().get("skills", {})
        self.skills_dir = self.skills_config.get("directory") or '/opt/mycroft/skills'
        self.modules_url = modules_url or self.SKILLS_MODULES
        self.defaults_url = defaults_url or self.SKILLS_DEFAULTS_URL
        self.emitter = emitter
        self.skills = {}
        self.default_skills = {}
        self.installed_skills = []
        self.platform = Configuration.get().get("enclosure", {}).get("platform", "desktop")
        LOG.info("platform: " + self.platform)
        self.prepare_msm()

    def get_default_skills_list(self):
        """ get default skills list from url """
        LOG.info("retrieving default skills list")
        defaults = {}
        try:
            # get core and common skillw
            text = requests.get(self.defaults_url).text
            core = text.split("# core")[1]
            core, common = core.split("# common")
            core = [c for c in core.split("\n") if c]
            common = [c for c in common.split("\n") if c]
        except:
            core = common = []
        defaults["core"] = core
        defaults["common"] = common
        # get picroft
        try:
            text = requests.get(self.defaults_url + ".picroft").text
            picroft = text.split("# picroft")[1]
            picroft = [c for c in picroft.split("\n") if c]
        except:
            picroft = []
        defaults["picroft"] = picroft
        # get kde
        try:
            text = requests.get(self.defaults_url+".kde").text
            kde = text.split("# desktop")[1]
            kde = [c for c in kde.split("\n") if c]
        except:
            kde = []
        defaults["desktop"] = kde
        # get mark 1
        try:
            text = requests.get(self.defaults_url+".mycroft_mark_1").text
            mk1 = text.split("# mark 1")[1]
            mk1 = [c for c in mk1.split("\n") if c]
        except:
            mk1 = []
        defaults["mycroft_mark_1"] = mk1
        # on error use hard coded defaults
        self.default_skills = defaults or self.DEFAULT_SKILLS
        LOG.info("default skills: " + str(defaults))
        return self.default_skills

    def prepare_msm(self):
        """ prepare msm execution """
        # find home dir
        if "~" in self.skills_dir:
            self.skills_dir = expanduser(self.skills_dir)

        # create skills dir if missing
        if not exists(self.skills_dir):
            LOG.info("creating skills dir")
            makedirs(self.skills_dir)

        # update default skills list
        self.get_default_skills_list()

        # scan skills folder
        self.installed_skills = self.scan_skills_folder()

        # scan skills repo
        self.scan_skills_repo()

        if self.platform in ["picroft", "mycroft_mark_1"]:
            pass
            # TODO permissions stuff

    def scan_skills_folder(self):
        """ scan installed skills """
        LOG.info("scanning installed skills")
        skills = []
        if exists(self.skills_dir):
            # checking skills dir and getting all skills there
            skill_list = [folder for folder in filter(
                lambda x: isdir(join(self.skills_dir, x)),
                listdir(self.skills_dir))]
            for skill_folder in skill_list:
                skills.append(skill_folder)
                self.read_skill_folder(skill_folder)
        LOG.info("scanned: " + str(skills))
        return skills

    def scan_skills_repo(self):
        """ get skills list from skills repo """
        LOG.info("scanning skills repo")
        text = requests.get(self.modules_url).text
        modules = text.split('[submodule "')
        skills = []
        for module in modules:
            if not module:
                continue
            name = module.split('"]')[0].strip()
            skills.append(name)
            url = module.split('url = ')[1].strip()
            skill_folder = url.split("/")[-1]
            if skill_folder[-4:] == '.git':
                skill_folder = skill_folder[:-4]
            skill_path = join(self.skills_dir, skill_folder)
            skill_id = hash(skill_path)
            skill_author = url.split("/")[-2]
            installed = False
            if skill_folder in self.installed_skills:
                installed = True
            self.skills[skill_folder] = {"repo": url, "folder": skill_folder, "path": skill_path, "id": skill_id, "author": skill_author, "name": name, "installed": installed}
        LOG.info("scanned: " + str(skills))
        return skills

    def is_skill(self, skill_folder):
        """
            Check if folder is a skill and perform mapping.
        """
        LOG.info("checking if " + skill_folder + " is a skill")
        path = join(self.skills_dir, skill_folder)
        # check if folder is a skill (must have __init__.py)
        if not MainModule + ".py" in listdir(path):
            LOG.warning("not a skill!")
            return False

    def read_skill_folder(self, skill_folder):
        if not self.is_skill(skill_folder):
            return False
        path = join(self.skills_dir, skill_folder)
        if skill_folder not in self.skills:
            self.skills[skill_folder] = {"id": hash(path)}
        git_url = self.git_from_folder(path)
        if git_url:
            author = git_url.split("/")[-2]
        else:
            author = "unknown"
        self.skills[skill_folder]["path"] = path
        self.skills[skill_folder]["folder"] = skill_folder
        if "name" not in self.skills[skill_folder].keys():
            self.skills[skill_folder]["name"] = skill_folder
        self.skills[skill_folder]["repo"] = git_url
        self.skills[skill_folder]["author"] = author
        self.skills[skill_folder]["installed"] = True
        return True

    def install_defaults(self):
        """ installs the default skills, updates all others """
        for skill in self.default_skills["core"]:
            LOG.info("installing core skills")
            self.install_by_name(skill)
        for skill in self.default_skills["common"]:
            LOG.info("installing common skills")
            self.install_by_name(skill)
        for skill in self.default_skills.get(self.platform, []):
            LOG.info("installing platform specific skills")
            self.install_by_name(skill)
        self.update_skills()

    def install_by_url(self, url):
        """ installs from the specified github repo """
        self.github_url_check(url)
        skill_folder = url.split("/")[-1]
        path = join(self.skills_dir, skill_folder)
        if exists(path):
            LOG.info("skill exists, updating")
            g = Git(path)
            g.pull()
        else:
            LOG.info("Downloading skill: " + url)
            Repo.clone_from(url, path)
        if skill_folder not in self.skills:
            self.skills[skill_folder] = {"folder": skill_folder, "path": path,
                                         "id": hash(path), "repo": url,
                                         "name": skill_folder, "installed": True,
                                         "author": url.split("/")[-2]}
        self.run_requirements_sh(skill_folder)
        self.run_pip(skill_folder)

    def install_by_name(self, name):
        """ installs the mycroft-skill matching <name> """
        LOG.info("searching skill by name: " + name)
        skill_folder = self.match_name_to_folder(name)
        if skill_folder is not None:
            skill = self.skills[skill_folder]
            return self.install_by_url(skill["repo"])
        return False

    def update_skills(self):
        """ update all installed skills """
        LOG.info("updating installed skills")
        for skill in self.skills:
            if self.skills[skill]["installed"]:
                LOG.info("updating " + skill)
                self.install_by_url(self.skills[skill]["repo"])

    def remove_by_url(self, url):
        """ removes the specified github repo """
        LOG.info("searching skill by github url: " + url)
        for skill in self.skills:
            if url == self.skills[skill]["repo"]:
                LOG.info("found skill!")
                if self.skills[skill]["installed"]:
                    remove(self.skills[skill]["path"])
                    return True
                break
        LOG.warning("skill not found!")
        return False

    def remove_by_name(self, name):
        """ removes the specified skill folder name """
        skill_folder = self.match_name_to_folder(name)
        installed = self.skills[skill_folder]["installed"]
        self.skills[skill_folder]["installed"] = False
        if not installed:
            LOG.warning("skill is not installed!")
            return False
        remove(self.skills[skill_folder]["path"])
        LOG.info("skill removed")
        return True

    def list_skills(self):
        """ list all mycroft-skills in the skills repo and installed """
        # scan skills folder
        self.scan_skills_folder()
        # scan skills repo
        self.scan_skills_repo()
        return self.skills

    def url_info(self, url):
        """ shows information about the skill in the specified repo """
        LOG.info("searching skill by github url: " + url)
        for skill in self.skills:
            if url == self.skills[skill]["repo"]:
                LOG.info("found skill!")
                return self.skills[skill]
        self.github_url_check(url)
        skill_folder = name = url.split("/")[-1]
        skill_path = join(self.skills_dir, skill_folder)
        skill_id = hash(skill_path)
        skill_author = url.split("/")[-2]
        installed = False
        LOG.info("skill not found!")
        return {"repo": url, "folder": skill_folder, "path": skill_path, "id": skill_id, "author": skill_author, "name": name, "installed": installed}

    def name_info(self, name):
        """ shows information about the skill matching <name> """
        LOG.info("searching skill by name: " + name)
        skill = self.match_name_to_folder(name)
        if skill is not None:
            return self.skills[skill]
        LOG.warning("skill not found")
        return {}

    def run_pip(self, skill_folder):
        LOG.info("running pip for: " + skill_folder)
        skill = self.skills[skill_folder]
        # no need for sudo if in venv
        # TODO handle sudo if not in venv
        if exists(join(skill["path"], "requirements.txt")):
            pip_code = pip.main(['install', '-r', join(skill["path"], "requirements.txt")])
            # TODO parse pip code
            return True
        return False

    def run_requirements_sh(self, skill_folder):
        LOG.info("running requirements.sh for: " + skill_folder)
        skill = self.skills[skill_folder]
        reqs = join(skill["path"], "requirements.sh")
        if exists(reqs):
            # make exec
            subprocess.call((["chmod", "+x", reqs]))
            # handle sudo
            if self.platform == "desktop":
                # gksudo
                output = subprocess.check_output(["gksudo", "bash", reqs])
            else:  # no sudo
                output = subprocess.check_output(["bash", reqs])
            return True
        return False

    def match_name_to_folder(self, name):
        LOG.info("searching skill by name: " + name)
        folders = self.skills.keys()
        names = [self.skills[skill]["name"] for skill in folders]
        f_skill, f_score = match_one(name, folders)
        n_skill, n_score = match_one(name, names)
        if n_score > 0.5:
            for s in self.skills:
                if self.skills[s]["name"] == n_skill:
                    LOG.info("found skill by name")
                    return s
        elif f_score > 0.5:
            LOG.info("found skill by folder name")
            return f_skill
        return None

    @staticmethod
    def git_from_folder(path):
        try:
            website = subprocess.check_output(["git", "remote", "-v"], cwd=path)
            website = website.replace("origin\t", "").replace(" (fetch)", "").split("\n")[0]
        except:
            website = None
        return website

    @staticmethod
    def github_url_check(url=""):
        if not url.startswith("https://github.com"):
            raise AttributeError("this url does not seem to be form github: " + url)

    # handling skills config

    def remove_from_priority_list(self, skill_name, save=True):
        skill_folder = self.match_name_to_folder(skill_name)
        if skill_folder is None:
            LOG.error("could not find skill to remove from priority list")
            return False

        if "priority_skills" not in self.skills_config:
            self.skills_config["priority_skills"] = []
        if skill_folder in self.skills_config["priority_skills"]:
            if not self.skills[skill_folder]["installed"]:
                LOG.debug("removing skill from priority list, but it is not installed")
            self.skills_config["priority_skills"].remove(skill_folder)
            LOG.info("Skill removed  from priority list: " + skill_folder)
            if save:
                self.update_skills_config()
        else:
            LOG.info("Skill is not in priority list: " + skill_folder)
        return True

    def add_to_priority_list(self, skill_name, save=True):
        skill_folder = self.match_name_to_folder(skill_name)
        if skill_folder is None:
            LOG.error("could not find skill to add to priority list")
            return False
        if not self.skills[skill_folder]["installed"]:
            LOG.debug("Adding skill to priority list, but it is not installed")
        if "priority_skills" not in self.skills_config:
            self.skills_config["priority_skills"] = []
        if skill_folder not in self.skills_config["priority_skills"]:
            self.skills_config["priority_skills"].append(skill_folder)
            LOG.info("Skill added to priority list: " + skill_folder)
            if save:
                self.update_skills_config()
        else:
            LOG.info("Skill already in priority list: " + skill_folder)
        return True

    def remove_from_blacklist(self, skill_name, save=True):
        skill_folder = self.match_name_to_folder(skill_name)
        if skill_folder is None:
            LOG.error("could not find skill to unblacklist")
            return False

        if "blacklisted_skills" not in self.skills_config:
            self.skills_config["blacklisted_skills"] = []
        if skill_folder in self.skills_config["blacklisted_skills"]:
            if not self.skills[skill_folder]["installed"]:
                LOG.debug("UnBlacklisting skill, but it is not installed")
            self.skills_config["blacklisted_skills"].remove(skill_folder)
            LOG.info("Skill UnBlacklisted: " + skill_folder)
            if save:
                self.update_skills_config()
        else:
            LOG.info("Skill is not in blacklist: " + skill_folder)
        return True

    def add_to_blacklist(self, skill_name, save=True):
        skill_folder = self.match_name_to_folder(skill_name)
        if skill_folder is None:
            LOG.error("could not find skill to blacklist")
            return False
        if not self.skills[skill_folder]["installed"]:
            LOG.debug("Blacklisting skill, but it is not installed")
        if "blacklisted_skills" not in self.skills_config:
            self.skills_config["blacklisted_skills"] = []
        if skill_folder not in self.skills_config["blacklisted_skills"]:
            self.skills_config["blacklisted_skills"].append(skill_folder)
            LOG.info("Skill Blacklisted: " + skill_folder)
            if save:
                self.update_skills_config()
        else:
            LOG.info("Skill already Blacklisted: " + skill_folder)
        return True

    def change_skills_directory(self, skills_dir, save=True):
        self.skills_config["directory"] = skills_dir
        self.skills_dir = skills_dir
        if save:
            self.update_skills_config()

    def update_skills_config(self, config=None):
        conf = LocalConf(USER_CONFIG)
        conf['skills'] = config or self.skills_config
        conf.store()

    def reload_skill(self, skill_name):
        skill_folder = self.match_name_to_folder(skill_name)
        if skill_folder is None:
            LOG.error("Could not find skill to reload: " + skill_name)
            return False
        path = self.skills[skill_folder]["path"]+"/reloading"
        with open(path, "w") as f:
            f.write(" ")
        sleep(2)
        remove(path)
        return True

    def get_installed_skills(self):
        skills = []
        for skill in self.skills:
            if self.skills[skill].get("installed"):
                skills.append(skill)
        return skills

class JarbasSkillsManager(MycroftSkillsManager):
    SKILLS_MODULES = "https://raw.githubusercontent.com/JarbasAl/jarbas_skills_repo/master/"
    SKILLS_DEFAULTS_URL = "https://raw.githubusercontent.com/JarbasAl/jarbas_skills_repo/master/DEFAULT_SKILLS"

    def __init__(self, emitter=None, skills_config=None, defaults_url=None, modules_url=None):
        self.msm = MycroftSkillsManager(emitter, skills_config)
        defaults_url = defaults_url or self.SKILLS_DEFAULTS_URL
        modules_url = modules_url or self.SKILLS_MODULES
        super(JarbasSkillsManager, self).__init__(emitter, skills_config, defaults_url, modules_url)

    @property
    def mycroft_repo_skills(self):
        """ get skills list from mycroft skills repo """
        LOG.info("scanning Mycroft skills repo")
        return self.msm.scan_skills_repo()

    def get_default_skills_list(self):
        """ get default skills list from url """
        LOG.info("retrieving default skills list")
        defaults = {}
        try:
            # get core and common skillw
            text = requests.get(self.defaults_url).text
            core = text.split("# core")[1]
            core, common = core.split("# common")
            core = [c for c in core.split("\n") if c]
            common = [c for c in common.split("\n") if c]
        except:
            core = common = []
        defaults["core"] = core
        defaults["common"] = common
        # get picroft
        try:
            text = requests.get(self.defaults_url + ".picroft").text
            picroft = text.split("# picroft")[1]
            picroft = [c for c in picroft.split("\n") if c]
        except:
            picroft = []
        defaults["picroft"] = picroft
        # get kde
        try:
            text = requests.get(self.defaults_url + ".kde").text
            kde = text.split("# desktop")[1]
            kde = [c for c in kde.split("\n") if c]
        except:
            kde = []
        defaults["desktop"] = kde
        # get mark 1
        try:
            text = requests.get(self.defaults_url + ".mycroft_mark_1").text
            mk1 = text.split("# mark 1")[1]
            mk1 = [c for c in mk1.split("\n") if c]
        except:
            mk1 = []
        defaults["mycroft_mark_1"] = mk1
        # get jarbas
        try:
            text = requests.get(self.defaults_url + ".jarbas").text
            jarbas = text.split("# jarbas")[1]
            jarbas = [c for c in jarbas.split("\n") if c]
        except:
            jarbas = []
        defaults["jarbas"] = jarbas
        # on error use hard coded defaults
        self.default_skills = defaults or self.DEFAULT_SKILLS
        LOG.info("default jarbas skills: " + str(defaults))
        return self.default_skills

    def scan_skills_repo(self):
        """ get skills list from skills repo """
        LOG.info("scanning Jarbas skills repo")
        platforms = ["core", "common", "kde", "jarbas", "desktop", "picroft",  "mycroft_mark_1"]
        scanned = []
        for platform in platforms:
            text = requests.get(self.modules_url+platform+".txt").text
            skills = text.splitlines()
            for s in skills:
                name, url = s.split(",")
                if not url:
                    url = self.msm.name_info(name).get("repo")
                    if not url:
                        continue
                scanned.append(name)
                skill_folder = url.split("/")[-1]
                skill_path = join(self.skills_dir, skill_folder)
                skill_id = hash(skill_path)
                skill_author = url.split("/")[-2]
                installed = False
                if skill_folder in self.installed_skills:
                    installed = True
                self.skills[skill_folder] = {"repo": url, "folder": skill_folder, "path": skill_path, "id": skill_id,
                                             "author": skill_author, "name": name, "installed": installed}

            LOG.info("scanned " + platform + ": " + str(skills))
        return scanned

