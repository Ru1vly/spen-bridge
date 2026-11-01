"""User-created profiles for behavioral tests; never shipped application defaults."""
from server.config import AppProfile


def add_example_profiles(config):
    config.profiles.update({
        "osu!": AppProfile(name="osu!", app_matches=["osu!", "osu", "osu-lazer", "osu!.exe"],
                           click_on_touch=False, button_primary="none", button_secondary="none"),
        "Krita": AppProfile(name="Krita", app_matches=["krita"], stroke_smoothing=.15),
        "Blender": AppProfile(name="Blender", app_matches=["blender"]),
    })
    return config
