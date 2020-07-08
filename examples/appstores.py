from msm.appstores import pling, mycroft_marketplace
from msm import appstores
from msm import MycroftSkillsManager

msm = MycroftSkillsManager()


print("Searching pling appstore for hivemind")
for s in pling.search("hivemind", msm=msm):
    print(s.name)  # pling appstore only

print("Searching mycroft marketplace for jokes")
for s in mycroft_marketplace.search("jokes", msm=msm):
    print(s.name)  # mycroft appstore only

print("Searching everywhere for node red")
for s in appstores.search("node red", min_conf=0.4, msm=msm):
    print(s.name)  # All appstores

print("Listing pling appstore skills")
for s in pling.list_skills(msm=msm):
    print(s.name)

print("Listing mycroft marketplace skills")
for s in mycroft_marketplace.list_skills(msm=msm):
    print(s.name)
