from msm.appstores import pling, mycroft_marketplace


def search(*args, **kwargs):
    for skill in mycroft_marketplace.search(*args, **kwargs):
        yield skill
    for skill in pling.search(*args, **kwargs):
        yield skill
