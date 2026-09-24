# Maps theme image files to buttons. Used to draft theme.json for imported themes.
import re

IMAGE_EXTENSIONS = {"bmp", "png", "jpg", "jpeg", "tiff", "gif"}

# Same patterns and order as ThemeManager.loadTheme in Trois, so themes that
# already load there keep the same images.
PATTERNS = [
    ("close", ["closeup", "close_up", "close up", "close button up", "close window button", "1closeup"]),
    ("closeDown", ["closedwn", "closedown", "close_down", "close down", "close button down", "close window button down", "close_dw", "1closedn"]),
    ("closeDisabled", ["closedis", "close_disable", "close disabled", "close button disabled", "close gray", "close_ds", "1closedis"]),
    ("minimize", ["minup", "min_up", "min up", "mini_up", "minim_up", "minimize_up", "minimize up", "minimize button up", "1minup"]),
    ("minimizeDown", ["mindwn", "mindown", "min_down", "min down", "min dwn", "mini_dwn", "minim_dw", "minimize_down", "minimize down", "minimize button down", "1mindn"]),
    ("minimizeDisabled", ["mindis", "min_disable", "min disabled", "min gray", "mini_dis", "minim_ds", "minimize_dis", "minimize button disabled", "1mindis"]),
    ("zoom", ["maxup", "max_up", "max up", "maxim_up", "maximize_up", "maximize up", "maximize button up", "1maxup"]),
    ("zoomDown", ["maxdwn", "maxdown", "max_down", "max down", "max dwn", "maxim_dw", "maximize_down", "maximize down", "maximize button down", "1maxdn"]),
    ("zoomDisabled", ["maxdis", "max_disable", "max disabled", "max gray", "maxim_ds", "maximize_dis", "maximize button disabled", "1maxdis"]),
    ("restore", ["resup", "restore up", "restore_up", "restore button up", "rst_up", "1resup"]),
    ("restoreDown", ["resdwn", "resdown", "restore down", "restore_down", "restore_dw", "rst_dwn", "restore button down", "1resdn"]),
    ("help", ["helpup", "help up", "help button up", "1helpup"]),
    ("helpDown", ["helpdwn", "helpdown", "help down", "help dwn", "help button down", "1helpdn"]),
]

ROLES = [key for key, _ in PATTERNS]

BUTTONS = {
    "close": "close", "min": "minimize", "mini": "minimize", "minim": "minimize", "minimize": "minimize",
    "max": "zoom", "maxim": "zoom", "maximize": "zoom", "res": "restore", "rest": "restore",
    "restore": "restore", "help": "help", "hlp": "help",
}
STATES = {
    "up": "", "u": "", "down": "Down", "dwn": "Down", "d": "Down", "dw": "Down",
    "dis": "Disabled", "disable": "Disabled", "disabled": "Disabled", "x": "Disabled", "ds": "Disabled",
}


def _split(filename):
    stem, _, ext = filename.rpartition(".")
    return stem, ext.lower()


def role(filename):
    """The button a file fills under the app's own patterns, or None."""
    stem, ext = _split(filename)
    if ext not in IMAGE_EXTENSIONS:
        return None
    name = re.sub(r"\s+", " ", stem.lower())
    for key, patterns in PATTERNS:
        if any(p in name for p in patterns):
            return key
    return None


def roles_from_tokens(filename):
    """Fallback for naming schemes the app doesn't know, e.g. Close-Up.bmp,
    close_u.bmp or close_01down.bmp. A file naming two buttons (Max-Res-Up)
    fills both."""
    stem, ext = _split(filename)
    if ext not in IMAGE_EXTENSIONS:
        return []
    # Leading digits are sequence numbers: 1u, 2d, 01down.
    tokens = [re.sub(r"^\d+", "", t) for t in re.split(r"[-_ ]+", stem.lower())]
    buttons = [BUTTONS[t] for t in tokens if t in BUTTONS]
    if not buttons:
        return []
    state = next((STATES[t] for t in tokens if t in STATES), "")
    return [b + state for b in buttons]
