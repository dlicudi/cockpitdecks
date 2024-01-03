# ##########################################################################
#
# C O C K P I T D E C K S
#
# Elgato Stream Decks, Loupedeck LoupedeckLive, and Berhinger X-Touch Mini to X-Plane Cockpit.
#
#
import os
import logging
from collections.abc import MutableMapping
from enum import Enum
from datetime import datetime
import ruamel
from ruamel.yaml import YAML

__NAME__ = "cockpitdecks"
__DESCRIPTION__ = "Elgato Stream Decks, Loupedeck LoupedeckLive, and Berhinger X-Touch Mini to X-Plane Cockpit"
__LICENSE__ = "MIT"
__LICENSEURL__ = "https://mit-license.org"
__COPYRIGHT__ = f"© 2022-{datetime.now().strftime('%Y')} Pierre M <pierre@devleaks.be>"
__version__ = "7.15.1"
__version_info__ = tuple(map(int, __version__.split(".")))
__version_name__ = "production"
__authorurl__ = "https://github.com/devleaks/cockpitdecks"
#
#
# ##########################################################################

# Prevent aliasing
# https://stackoverflow.com/questions/64716894/ruamel-yaml-disabling-alias-for-dumping
ruamel.yaml.representer.RoundTripRepresenter.ignore_aliases = lambda x, y: True
yaml = YAML(typ="safe", pure=True)

SPAM_LEVEL = 15
SPAM = "SPAM"
LOGFILE = "cockpitdecks.log"
FORMAT = "[%(asctime)s] %(levelname)s %(threadName)s %(filename)s:%(funcName)s:%(lineno)d: %(message)s"
# logging.basicConfig(level=logging.INFO, format=FORMAT)
init_logger = logging.getLogger(__name__)
# init_logger.setLevel(logging.DEBUG)
# if LOGFILE is not None:
#     formatter = logging.Formatter(FORMAT)
#     handler = logging.FileHandler(
#         LOGFILE, mode="a"
#     )
#     handler.setFormatter(formatter)
#     logger.addHandler(handler)


# ##############################################################
# Utility functions
# (mainly unit conversion functions)
#
def now():
    return datetime.now().astimezone()


def to_fl(m, r: int = 10):
    # Convert meters to flight level (1 FL = 100 ft). Round flight level to r if provided, typically rounded to 10, at Patm = 1013 mbar
    fl = m / 30.48
    if r is not None and r > 0:
        fl = r * int(fl / r)
    return fl


def to_m(fl):
    # Convert flight level to meters, at Patm = 1013 mbar
    return round(fl * 30.48)


# ##############################################################
# A few constants and default values
# Adjust with care...
#
# ROOT_DEBUG = "cockpitdecks.xplaneudp,cockpitdecks.xplane,cockpitdecks.button"
ROOT_DEBUG = ""
EXCLUDE_DECKS = []  # list serial numbers of deck not usable by Streadecks

# Files
CONFIG_FOLDER = "deckconfig"
CONFIG_FILE = "config.yaml"
SECRET_FILE = "secret.yaml"

DEFAULT_LAYOUT = "default"
DEFAULT_PAGE_NAME = "X-Plane"

RESOURCES_FOLDER = "resources"
FONTS_FOLDER = "fonts"
ICONS_FOLDER = "icons"

ICON_SIZE = 256  # px


class ANNUNCIATOR_STYLES(Enum):
    KORRY = "k"  # k(orry): backlit, glowing
    VIVISUN = "v"  # v(ivisun): bright, sharp.


GLOBAL_DEFAULTS = {
    "default-logo": "logo.png",
    "default-wallpaper": "wallpaper.png",
    "default-label-font": "DIN.ttf",
    "default-label-size": 10,
    "default-label-color": "white",
    "default-label-position": "ct",
    "default-text-position": "cm",
    "default-system-font": "Monaco.ttf",
    "cache-icon": True,
    "default-icon-texture": None,
    "default-icon-color": (0, 0, 100),
    "default-icon-name": "_default_icon.png",
    "default-annunciator-texture": None,
    "default-annunciator-color": (0, 0, 0),
    "default-annunciator-color-fg": (128, 128, 128),
    "default-annunciator-style": ANNUNCIATOR_STYLES.VIVISUN,
    "cockpit-texture": None,
    "cockpit-color": (94, 111, 130),
    "default-home-page-name": "index",
    "default-light-off-intensity": 10,
}

# internals
ID_SEP = "/"


# deckconfig attribute keywords
class KW(Enum):
    ACTION = "action"
    ACTIVATIONS = "activations"
    ANNUNCIATOR_MODEL = "model"
    BACKPAGE = "back"
    BUTTONS = "buttons"
    COLORED_LED = "colored-led"
    DATAREF = "dataref"
    DEVICE = "device"
    DISABLED = "disabled"
    DRIVER = "driver"
    ENABLED = "enabled"
    FORMULA = "formula"
    FRAME = "frame"
    GUARD = "guard"
    IMAGE = "image"
    INCLUDES = "includes"
    INDEX = "index"
    INDEX_NUMERIC = "_index"
    LAYOUT = "layout"
    MANAGED = "managed"
    MODEL = "model"
    NAME = "name"
    NONE = "none"
    PREFIX = "prefix"
    REPEAT = "repeat"
    REPRESENTATIONS = "representations"
    SERIAL = "serial"
    TYPE = "type"
    VIEW = "view"


class Config(MutableMapping):
    """
    A dictionary that loads from a yaml config file.
    """

    def __init__(self, filename: str):
        self.store = dict()
        if os.path.exists(filename):
            with open(filename, "r") as fp:
                self.store = yaml.load(fp)
                self.store["__filename__"] = filename
                init_logger.debug(f"loaded config from {filename}")
        else:
            init_logger.debug(f"no file {filename}")

    def __getitem__(self, key):
        return self.store[self._keytransform(key)]

    def __setitem__(self, key, value):
        self.store[self._keytransform(key)] = value

    def __delitem__(self, key):
        del self.store[self._keytransform(key)]

    def __iter__(self):
        return iter(self.store)

    def __len__(self):
        return len(self.store)

    def _keytransform(self, key):
        return key

    def is_valid(self):
        return self.store is not None and len(self.store) > 1


from .cockpit import Cockpit, CockpitBase
from .simulators.xplane import XPlane
