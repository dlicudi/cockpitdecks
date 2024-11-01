# Main container for all decks
#
from __future__ import annotations
import sys
import os
import io
import glob
import base64
import threading
import logging
import pickle
import json
import importlib
import pkgutil
from typing import Dict
import pkg_resources

from datetime import datetime
from queue import Queue

from PIL import Image, ImageFont

# from cairosvg import svg2png

from cockpitdecks import __version__, LOGFILE, FORMAT
from cockpitdecks import (
    AIRCRAFT_ASSET_PATH,
    AIRCRAFT_CHANGE_MONITORING_DATAREF,
    ASSETS_FOLDER,
    COCKPITDECKS_ASSET_PATH,
    COCKPITDECKS_DEFAULT_VALUES,
    CONFIG_FILE,
    CONFIG_FILENAME,
    CONFIG_FOLDER,
    CONFIG_KW,
    DECK_ACTIONS,
    DECK_FEEDBACK,
    DECK_IMAGES,
    DECK_KW,
    DECK_TYPES,
    DECKS_FOLDER,
    DEFAULT_ATTRIBUTE_PREFIX,
    COCKPITDECKS_INTERNAL_EXTENSIONS,
    DEFAULT_FREQUENCY,
    DEFAULT_LAYOUT,
    ENVIRON_KW,
    EXCLUDE_DECKS,
    FONTS_FOLDER,
    ICONS_FOLDER,
    ID_SEP,
    NAMED_COLORS,
    OBSERVABLES_FILE,
    RESOURCES_FOLDER,
    ROOT_DEBUG,
    SECRET_FILE,
    SOUNDS_FOLDER,
    SPAM,
    SPAM_LEVEL,
    VIRTUAL_DECK_DRIVER,
    Config,
    yaml,
)
from cockpitdecks.constant import TYPES_FOLDER
from cockpitdecks.resources.color import convert_color, has_ext, add_ext
from cockpitdecks.resources.intdatarefs import INTERNAL_DATAREF
from cockpitdecks.simulator import Simulator, SimulatorData, SimulatorDataListener, SimulatorEvent
from cockpitdecks.instruction import Instruction
from cockpitdecks.observable import Observables

# from cockpitdecks.simulators.xplane import DatarefEvent

# imports all known decks, if deck driver not available, ignore it
import cockpitdecks.decks

# @todo later: put custom decks outside of cockpitdecks for flexibility
# same for simulator
from cockpitdecks.deck import Deck
from cockpitdecks.decks.resources import DeckType
from cockpitdecks.buttons.activation import Activation
from cockpitdecks.buttons.representation import Representation, HardwareRepresentation

# #################################
#
# Logging
#
logging.addLevelName(SPAM_LEVEL, SPAM)
logger = logging.getLogger(__name__)
# logger.setLevel(logging.DEBUG)

if LOGFILE is not None:
    formatter = logging.Formatter(FORMAT)
    handler = logging.FileHandler(LOGFILE, mode="a")
    handler.setFormatter(formatter)
    logger.addHandler(handler)

EVENTLOGFILE = "events.json"
event_logger = logging.getLogger("events")
if EVENTLOGFILE is not None:
    formatter = logging.Formatter('{"ts": "%(asctime)s", "event": %(message)s}')
    handler = logging.FileHandler(EVENTLOGFILE, mode="w")
    handler.setFormatter(formatter)
    event_logger.addHandler(handler)
    event_logger.propagate = False
LOG_DATAREF_EVENTS = False  # Do not log dataref events (numerous, can grow quite large, especialy for long sessions)


class CockpitdecksInstruction(Instruction):
    """
    An Instruction to be performed by Cockpitdekcs itself like:
    - Change page
    - Reload decks
    - Stop
    ...
    Instruction is not sent to simulator.
    """

    def __init__(self, name: str, cockpit: Cockpit, delay: float = 0.0, condition: str | None = None) -> None:
        Instruction.__init__(self, name=name, delay=delay, condition=condition)
        self._cockpit = cockpit

    # @classmethod
    # def new(cls, name: str, simulator: XPlane, **kwargs):
    #     if "cockpit" in kwargs:
    #         cockpit = kwargs.get("cockpit")
    #         if type(cmdargs) is str:
    #             return CockpitdecksInstruction(
    #                 name=name,
    #                 cockpit=cockpit,
    #                 delay=kwargs.get("delay"),
    #                 condition=kwargs.get("condition"),
    #             )
    #     else:
    #         if not kwargs.get("silence", False):
    #             logger.warning(f"Instruction {name}: invalid argument {kwargs}")
    #     return None

    @property
    def cockpit(self):
        return self._cockpit

    @cockpit.setter
    def cockpit(self, cockpit):
        self._cockpit = cockpit

    def _execute(self):
        if instruction.name == "reload":
            self.cockpit.reload_decks()
        if instruction.name == "stop":
            self.cockpit.terminate_all()
        else:
            logger.warning(f"invalid instruction {self.name}")


# #################################
#
# Global constants
#
# IMPORTANT: These are rendez-vous point for JavaScript code
# If changed here, please adjust JavaScript Code too.
#
DECK_TYPE_ORIGINAL = "deck-type-desc"
DECK_TYPE_DESCRIPTION = "deck-type-flat"

# Aircraft change detection
# Why livery? because this dataref is an o.s. PATH! So it contains not only the livery
# (you may want to change your cockpit texture to a pinky one for this Barbie Livery)
# but also the aircraft. So in 1 dataref, 2 informations: aircraft and livery!
RELOAD_ON_LIVERY_CHANGE = False
AIRCRAFT = "_livery"  # dataref name is data:_livery


class CockpitBase:
    """As used in Simulator"""

    def __init__(self):
        self._debug = ROOT_DEBUG.split(",")  # comma separated list of module names like cockpitdecks.page or cockpitdeck.button_ext
        pass

    def set_logging_level(self, name):
        if name in self._debug:
            l = logging.getLogger(name)
            if l is not None:
                l.setLevel(logging.DEBUG)
                l.info(f"set_logging_level: {name} set to debug")
            else:
                logger.warning(f"logger {name} not found")

    def reload_pages(self):
        pass


class Cockpit(SimulatorDataListener, CockpitBase):
    """
    Contains all deck configurations for a given aircraft.
    Is started when aicraft is loaded and aircraft contains CONFIG_FOLDER folder.
    """

    def __init__(self, environ: Config | dict):
        self._startup_time = datetime.now()

        CockpitBase.__init__(self)
        SimulatorDataListener.__init__(self)

        # Defaults and config
        self._environ = environ

        self.extension_paths = environ.get(ENVIRON_KW.COCKPITDECKS_EXTENSION_PATH.value, set())
        if type(self.extension_paths) is str:
            if ":" in self.extension_paths:
                self.extension_paths = self.extension_paths.split(":")
            else:
                self.extension_paths = {self.extension_paths}
        self.extension_paths = set(self.extension_paths)

        self.all_extensions = environ.get(ENVIRON_KW.COCKPITDECKS_EXTENSION_NAME.value, set())
        if type(self.all_extensions) is str:
            self.all_extensions = {self.all_extensions}
        self.all_extensions = set(self.all_extensions)
        self.all_extensions.update(COCKPITDECKS_INTERNAL_EXTENSIONS)

        self.cockpitdecks_path = environ.get(ENVIRON_KW.COCKPITDECKS_PATH.value)

        self._defaults = COCKPITDECKS_DEFAULT_VALUES
        self._resources_config = {}  # content of resources/config.yaml
        self._config = {}  # content of aircraft/deckconfig/config.yaml
        self._secret = {}  # content of aircraft/deckconfig/secret.yaml
        self._reqdfts = set()

        # What's available
        self.all_simulators: Dict[str, Simulator] = {}
        self.all_activations: Dict[str, Activation] = {}
        self.all_representations: Dict[str, Representation] = {}
        self.all_hardware_representations: Dict[str, Representation] = {}
        self.all_deck_drivers = {}  # Dict[str, Device], one day

        # "Aircraft" name or model...
        self._acpath = None
        self.name = "Cockpitdecks"
        self.icao = "ZZZZ"

        # Decks
        self.cockpit = {}  # all decks: { deckname: deck }
        self.deck_types = {}
        self.deck_types_new = {}
        self.virtual_deck_types = {}
        self.virtual_deck_list = {}
        self.virtual_decks_added = False

        self.devices = []

        self.vd_ws_conn = {}
        self.vd_errs = []

        # Content
        self.fonts = {}
        self.sounds = {}

        self.icon_folder = None
        self.icons = {}

        # Main event look
        self.event_loop_run = False
        self.event_loop_thread = None
        self.event_queue = Queue()

        # Simulator
        self._simulator_name = environ.get(ENVIRON_KW.SIMULATOR_NAME.value)
        self._simulator = None
        self.sim = None

        # Internal variables
        self.named_colors = NAMED_COLORS
        self.observables = []
        self.ac_observables = []
        self.busy_reloading = False
        self.disabled = False
        self.default_pages = None  # current pages on decks when reloading
        self.theme = None
        self.mode = 0
        self._dark = False
        self._livery_dataref = None  # self.sim.get_internal_dataref(AIRCRAFT, is_string=True)
        self._acname = ""
        self._livery_path = ""
        self._monitored_strings = [AIRCRAFT_CHANGE_MONITORING_DATAREF]

        #
        # Global parameters that affect colors
        # and deck LCD backlight
        self.global_luminosity = 1.0
        self.global_brightness = 1.0

        self.init()  # this will install all available simulators

    @property
    def acpath(self):
        return self._acpath

    @acpath.setter
    def acpath(self, acpath: str | None):
        if acpath is not None:
            logger.info(f"aircraft path set to {self._acpath}")
        self._acpath = acpath

    def init(self):
        """
        Loads extensions, then build lists of available resources (simulators, decks, etc.)
        """
        self.add_extensions(trace_ext_loading=self._environ.verbose)

        self.all_simulators = {s.name: s for s in self.all_subclasses(Simulator)}
        logger.info(f"available simulators: {", ".join(self.all_simulators.keys())}")

        self.all_deck_drivers = {s.DECK_NAME: [s, s.DEVICE_MANAGER] for s in self.all_subclasses(Deck) if s.DECK_NAME != "none"}
        logger.info(f"available deck drivers: {", ".join(self.all_deck_drivers.keys())}")

        self.all_activations = {s.name(): s for s in self.all_subclasses(Activation)} | {DECK_ACTIONS.NONE.value: Activation}
        logger.debug(f"available activations: {", ".join(sorted(self.all_activations.keys()))}")

        self.all_representations = {s.name(): s for s in self.all_subclasses(Representation)} | {DECK_FEEDBACK.NONE.value: Representation}
        logger.debug(f"available representations: {", ".join(sorted(self.all_representations.keys()))}")

        self.all_hardware_representations = {s.name(): s for s in self.all_subclasses(HardwareRepresentation)}
        logger.debug(f"available hardware representations: {", ".join(self.all_hardware_representations.keys())}")

        if not self.init_simulator():  # this will start the requested one
            logger.info("..initialized with error, cannot continue\n")
            sys.exit(1)

        self.load_deck_types()
        self.scan_devices()

    def init_simulator(self) -> bool:
        if self._simulator_name is None and len(self.all_simulators) != 1:
            logger.error("no simulator")
            return False
        if self._simulator_name is None:
            self._simulator_name = list(self.all_simulators.keys())[0]
            logger.info(f"simulator set to {self._simulator_name}")
        self._simulator = self.all_simulators[self._simulator_name]
        self.sim = self._simulator(self, self._environ)
        self._livery_dataref = self.sim.get_internal_dataref(AIRCRAFT, is_string=True)
        self._livery_dataref.update_value(new_value=None, cascade=False)  # init
        if self.cockpitdecks_path is not None:
            logger.info(f"COCKPITDECKS_PATH={self.cockpitdecks_path}")
        return True

    def get_id(self):
        return self.name

    def inc(self, name: str, amount: float = 1.0, cascade: bool = False):
        # Here, it is purely statistics
        if self.sim is not None:
            self.sim.inc_internal_dataref(path=ID_SEP.join([self.get_id(), name]), amount=amount, cascade=cascade)

    def set_default(self, dflt, value):
        if not dflt.startswith(DEFAULT_ATTRIBUTE_PREFIX):
            logger.warning(f"default variable {dflt} does not start with {DEFAULT_ATTRIBUTE_PREFIX}")
        ATTRNAME = "_defaults"
        if not hasattr(self, ATTRNAME):
            setattr(self, ATTRNAME, dict())
        ld = getattr(self, ATTRNAME)
        if isinstance(ld, dict):
            ld[dflt] = value
        logger.debug(f"set default {dflt} to {value}")

    def adjust_light(self, luminosity: float = 1.0, brightness: float = 1.0):
        self.global_luminosity = luminosity
        self.global_brightness = brightness

    def all_subclasses(self, cls) -> list:
        """Returns the list of all subclasses.

        Recurses through all sub-sub classes

        Returns:
            [list]: list of all subclasses

        Raises:
            ValueError: If invalid class found in recursion (types, etc.)
        """
        if cls is type:
            raise ValueError("Invalid class - 'type' is not a class")
        subclasses = set()
        stack = []
        try:
            stack.extend(cls.__subclasses__())
        except (TypeError, AttributeError) as ex:
            raise ValueError("Invalid class" + repr(cls)) from ex
        while stack:
            sub = stack.pop()
            subclasses.add(sub)
            try:
                stack.extend(s for s in sub.__subclasses__() if s not in subclasses)
            except (TypeError, AttributeError):
                continue
        return list(subclasses)

    def add_extensions(self, trace_ext_loading: bool = False):
        # https://stackoverflow.com/questions/3365740/how-to-import-all-submodules
        def import_submodules(package, recursive=True):
            """Import all submodules of a module, recursively, including subpackages

            :param package: package (name or actual module)
            :type package: str | module
            :rtype: dict[str, types.ModuleType]
            """
            if isinstance(package, str):
                try:
                    if trace_ext_loading:
                        logger.info(f"loading package {package}")
                    package = importlib.import_module(package)
                except ModuleNotFoundError:
                    logger.warning(f"package {package} not found, ignored")
                    return {}

            results = {}
            for loader, name, is_pkg in pkgutil.walk_packages(package.__path__):
                full_name = package.__name__ + "." + name
                try:
                    results[full_name] = importlib.import_module(full_name)
                    if trace_ext_loading:
                        logger.info(f"loading module {full_name}")
                except ModuleNotFoundError:
                    logger.warning(f"module {full_name} not found, ignored")
                    continue
                except:
                    logger.warning(f"module {full_name}: error", exc_info=True)
                    continue
                if recursive and is_pkg:
                    results.update(import_submodules(full_name))
            return results

        if self.extension_paths is not None:
            for path in self.extension_paths:
                pythonpath = os.path.abspath(path)
                if os.path.exists(pythonpath) and os.path.isdir(pythonpath):
                    if pythonpath not in sys.path:
                        sys.path.append(pythonpath)
                        arr = os.path.split(pythonpath)
                        self.all_extensions.add(arr[1])
                        if trace_ext_loading:
                            logger.info(f"added extension path {pythonpath} to sys.path")

        logger.info(f"loading extensions {", ".join(self.all_extensions)}..")
        for package in self.all_extensions:
            test = import_submodules(package)
            if len(test) > 0:
                logger.info(f"loaded package {package} (recursively)")
        logger.debug(f"..loaded")

    def get_activations_for(self, action: DECK_ACTIONS) -> list:
        return [a for a in self.all_activations.values() if action in a.get_required_capability()]

    def get_representations_for(self, feedback: DECK_FEEDBACK):
        return [a for a in self.all_representations.values() if feedback in a.get_required_capability()]

    def defaults_prefix(self):
        return "dark-" + DEFAULT_ATTRIBUTE_PREFIX if self._dark else DEFAULT_ATTRIBUTE_PREFIX

    def get_attribute(self, attribute: str, default=None, silence: bool = True):
        # Attempts to provide a dark/light theme alternative, fall back on light(=normal)
        def is_color_attribute(a):
            return "color" in a

        def theme_only(a: str) -> bool:
            # Returns whether an attribute can be themed
            # Currently, only color, texture, and fonts
            return a.endswith("color") or a.endswith("texture") or "font" in a

        self._reqdfts.add(attribute)  # internal stats

        if attribute.startswith(DEFAULT_ATTRIBUTE_PREFIX) or attribute.startswith("cockpit-"):
            theme_prefix = self._config.get("cockpit-theme", "")  # prefix = "dark", or nothing
            if theme_prefix is not None and theme_prefix not in ["", "default", "cockpit"] and not attribute.startswith(theme_prefix):
                newattr = "-".join([theme_prefix, attribute])  # dark-default-color
                value = self.get_attribute(attribute=newattr, default=default, silence=silence)

                if value is not None:  # found!
                    if silence:
                        logger.debug(f"cockpit returning {attribute}={value} (from {newattr})")
                    else:
                        logger.info(f"cockpit returning {attribute}={value} (from {newattr})")
                    return convert_color(value) if is_color_attribute(attribute) else value

                if theme_only(attribute):  # a theme exist, do not try without theme
                    if not silence:
                        logger.info(f"cockpit themed attribute {newattr} not found, cannot try without theme {theme_prefix}, returning default ({default})")
                    return convert_color(default) if is_color_attribute(attribute) else default

        value = self._config.get(attribute)
        if value is not None:
            if silence:
                logger.debug(f"cockpit returning {attribute}={value} (from config)")
            else:
                logger.info(f"cockpit returning {attribute}={value} (from config)")
            return convert_color(value) if is_color_attribute(attribute) else value

        value = self._resources_config.get(attribute)
        if value is not None:
            if silence:
                logger.debug(f"cockpit returning {attribute}={value} (from resources)")
            else:
                logger.info(f"cockpit returning {attribute}={value} (from resources)")
            return convert_color(value) if is_color_attribute(attribute) else value

        ATTRNAME = "_defaults"
        if hasattr(self, ATTRNAME):
            ld = getattr(self, ATTRNAME)
            if isinstance(ld, dict):
                value = ld.get(attribute)
                if value is not None:
                    if silence:
                        logger.debug(f"cockpit returning {attribute}={value} (from internal default)")
                    else:
                        logger.info(f"cockpit returning {attribute}={value} (from internal default)")
                    return convert_color(value) if is_color_attribute(attribute) else value

        if not silence and "-" in attribute and attribute.split("-")[-1] not in ["font", "size", "color", "position", "texture"]:
            logger.warning(f"no attribute {attribute}")

        if not silence:
            logger.info(f"cockpit attribute {attribute} not found, returning default ({default})")

        if not attribute.startswith(DEFAULT_ATTRIBUTE_PREFIX):
            # we did not search for a default-*, now we do:
            default_attribute = DEFAULT_ATTRIBUTE_PREFIX + attribute
            return self.get_attribute(attribute=default_attribute, default=default, silence=silence)

        return default

    def is_dark(self):
        # Could also determine this from simulator time...
        # Always evaluates cockpit attribute since its value can be updated
        # by page changes
        #
        # Note: Theming could be extended to any "string" like:
        #
        # cockpit-theme: barbie
        #
        # and defaults as
        #
        # barbie-default-label-color: pink
        #
        val = self.get_attribute("cockpit-theme")
        self._dark = val is not None and val in ["dark", "night"]
        return self._dark

    def get_button_value(self, name):
        a = name.split(ID_SEP)
        if len(a) > 0:
            if a[0] == self.name:
                if a[1] in self.cockpit.keys():
                    return self.cockpit[a[1]].get_button_value(ID_SEP.join(a[1:]))
                else:
                    logger.warning(f"so such deck {a[1]}")
            else:
                logger.warning(f"no such cockpit {a[0]}")
        else:
            logger.warning(f"invalid name {name}")
        return None

    def inspect(self, what: str | None = None):
        """
        This function is called on all instances of Deck.
        """
        logger.info(f"Cockpitdecks Rel. {__version__} -- {what}")

        if what is not None and "thread" in what:
            logger.info(f"{[(t.name,t.isDaemon(),t.is_alive()) for t in threading.enumerate()]}")
        elif what is not None and what.startswith("datarefs"):
            self.inspect_datarefs(what)
        elif what == "monitored":
            self.inspect_monitored(what)
        else:
            for v in self.cockpit.values():
                v.inspect(what)

    def inspect_datarefs(self, what: str | None = None):
        if what is not None and what.startswith("datarefs"):
            for dref in self.sim.all_simulator_data.values():
                logger.info(f"{dref.name} = {dref.value()} ({len(dref.listeners)} lsnrs)")
                if what.endswith("listener"):
                    for l in dref.listeners:
                        logger.info(f"  {l.name}")
        else:
            logger.info("to do")

    def inspect_monitored(self, what: str | None = None):
        for dref in self.sim.simulator_data.values():
            logger.info(f"{dref}")

    def scan_devices(self):
        """Scan for hardware devices"""
        if len(self.all_deck_drivers) == 0:
            logger.error("no driver")
            return
        driver_info = []
        for deck_driver in self.all_deck_drivers:
            desc = f"{deck_driver} (included)"
            try:
                desc = f"{deck_driver} {pkg_resources.get_distribution(deck_driver).version}"
            except:
                pass
            driver_info.append(desc)
        if len(driver_info) == 0:
            logger.warning("no device driver for physical decks")
            return
        logger.info(f"device drivers installed for {', '.join(driver_info)}; scanning for decks and initializing them (this may take a few seconds)..")
        dependencies = []
        for deck_driver in self.all_deck_drivers.items():
            dep = ""
            try:
                dep = f"{deck_driver[0].DRIVER_NAME}>={deck_driver[0].MIN_DRIVER_VERSION}"
            except:
                pass
            if dep != "":
                dependencies.append(dep)
        logger.debug(f"dependencies: {dependencies}")
        pkg_resources.require(dependencies)

        # If there are already some devices, we need to terminate/kill them first
        if len(self.devices) > 0:
            logger.info("new scan for devices, terminating devices..")
            self.terminate_devices()
            logger.info("..terminated")

        self.devices = []
        for deck_driver, builder in self.all_deck_drivers.items():
            if deck_driver == VIRTUAL_DECK_DRIVER:
                # will be added later, when we have acpath set, in add virtual_decks()
                continue
            decks = builder[1]().enumerate()
            logger.info(f"found {len(decks)} {deck_driver}")  # " ({deck_driver} {pkg_resources.get_distribution(deck_driver).version})")
            for name, device in enumerate(decks):
                device.open()
                serial = device.get_serial_number()
                device.close()
                if serial in EXCLUDE_DECKS:
                    logger.warning(f"deck {serial} excluded")
                    del decks[name]
                logger.debug(f"added {type(device).__name__} (driver {deck_driver}, serial {serial[:3]}{'*'*max(1,len(serial))})")
                self.devices.append(
                    {
                        CONFIG_KW.DRIVER.value: deck_driver,
                        CONFIG_KW.DEVICE.value: device,
                        CONFIG_KW.SERIAL.value: serial,
                    }
                )
            logger.debug(f"using {len(decks)} {deck_driver}")
        logger.debug(f"..scanned")

    def get_device(self, req_driver: str, req_serial: str | None):
        """
        Get a hardware device for the supplied serial number.
        If found, the device is opened and reset and returned open.

        :param    req_serial:  The request serial
        :type      req_serial:  str
        """
        # No serial, return deck if only one deck of that type
        if req_serial is None:
            i = 0
            good = None
            for deck in self.devices:
                if deck[CONFIG_KW.DRIVER.value] == req_driver:
                    good = deck
                    i = i + 1
            if i == 1 and good is not None:
                logger.debug(f"only one deck of type {req_driver}, returning it")
                device = good[CONFIG_KW.DEVICE.value]
                device.open()
                device.reset()
                return device
            else:
                if i > 1:
                    logger.warning(f"more than one deck of type {req_driver}, no serial to disambiguate")
                    deckdr = filter(
                        lambda d: d[CONFIG_KW.DRIVER.value] == req_driver and d[CONFIG_KW.SERIAL.value] is None,
                        self.devices,
                    )
                    logger.warning(f"driver: {req_driver}, decks with no serial: {[d[CONFIG_KW.DEVICE.value].name for d in deckdr]}")
            return None
        ## Got serial, search for it
        for deck in self.devices:
            if deck[CONFIG_KW.SERIAL.value] == req_serial:
                device = deck[CONFIG_KW.DEVICE.value]
                device.open()
                device.reset()
                return device
        logger.warning(f"deck {req_serial} not found")
        return None

    def start_aircraft(self, acpath: str, release: bool = False, mode: int = 0):
        """
        Loads decks for aircraft in supplied path and start listening for key presses.
        """
        self.mode = mode
        self.load_aircraft(acpath)
        self.run(release)

    def load_aircraft(self, acpath: str):
        """
        Loads decks for aircraft in supplied path.
        """
        if self.disabled:
            logger.warning("Cockpitdecks is disabled")
            return
        # Reset, if new aircraft
        if len(self.cockpit) > 0:
            self.terminate_aircraft()
            # self.sim.clean_datarefs_to_monitor()
            logger.info(f"{os.path.basename(self.acpath)} unloaded")

        if self.sim is None:
            logger.info("..starting simulator..")
            self.sim = self._simulator(self, self._environ)
        else:
            logger.debug("simulator already running")

        logger.info(f"starting {os.path.basename(acpath)} " + "=" * 50)

        self.cockpit = {}
        self.icons = {}
        # self.fonts = {}
        self.acpath = None

        self.load_defaults()

        if acpath is not None and os.path.exists(os.path.join(acpath, CONFIG_FOLDER)):
            self.acpath = acpath

            self.load_aircraft_deck_types()
            self.scan_web_decks()

            if len(self.devices) == 0:
                logger.warning(f"no device")
                return

            self.load_icons()
            self.load_fonts()
            self.load_sounds()
            self.create_decks()
            self.load_pages()
            self.load_observables()
        else:
            if acpath is None:
                logger.error(f"no aircraft folder")
            elif not os.path.exists(acpath):
                logger.error(f"no aircraft folder {acpath}")
            else:
                logger.error(f"no Cockpitdecks folder '{CONFIG_FOLDER}' in aircraft folder {acpath}")
            self.create_default_decks()

    def load_pages(self):
        if self.default_pages is not None:
            logger.debug(f"default_pages {self.default_pages.keys()}")
            for name, deck in self.cockpit.items():
                if name in self.default_pages.keys():
                    if self.default_pages[name] in deck.pages.keys() and deck.home_page is not None:  # do not refresh if no home page loaded...
                        deck.change_page(self.default_pages[name])
                    else:
                        deck.change_page()
            self.default_pages = None
        else:
            for deck in self.cockpit.values():
                deck.change_page()

    def reload_pages(self):
        self.inc(INTERNAL_DATAREF.COCKPITDECK_RELOADS.value)
        for name, deck in self.cockpit.items():
            deck.reload_page()

    def load_defaults(self):
        """
        Loads default values for font, icon, etc. They will be used if no layout is found.
        """

        def locate_font(fontname: str) -> str | None:
            if fontname in self.fonts.keys():
                logger.debug(f"font {fontname} already loaded")
                return fontname

            # 1. Try "system" font
            try:
                test = ImageFont.truetype(fontname, self.get_attribute("label-size"))
                logger.debug(f"font {fontname} found in computer system fonts")
                return fontname
            except:
                logger.debug(f"font {fontname} not found in computer system fonts")

            # 2. Try font in resources folder
            fn = None
            try:
                fn = os.path.join(os.path.dirname(__file__), RESOURCES_FOLDER, fontname)
                test = ImageFont.truetype(fn, self.get_attribute("label-size"))
                logger.debug(f"font {fontname} found locally ({RESOURCES_FOLDER} folder)")
                return fn
            except:
                logger.debug(f"font {fontname} not found locally ({RESOURCES_FOLDER} folder)")

            # 3. Try font in resources/fonts folder
            fn = None
            try:
                fn = os.path.join(os.path.dirname(__file__), RESOURCES_FOLDER, FONTS_FOLDER, fontname)
                test = ImageFont.truetype(fn, self.get_attribute("label-size"))
                logger.debug(f"font {fontname} found locally ({FONTS_FOLDER} folder)")
                return fn
            except:
                logger.debug(f"font {fontname} not found locally ({FONTS_FOLDER} folder)")

            logger.debug(f"font {fontname} not found")
            return None

        # 0. Some variables defaults
        fn = os.path.join(os.path.dirname(__file__), RESOURCES_FOLDER, CONFIG_FILE)
        self._resources_config = Config(fn)

        # Load global defaults from resources/config.yaml file or use application default
        self._debug = self._resources_config.get("debug", ",".join(self._debug)).split(",")
        self.set_logging_level(__name__)

        if self.sim is not None:
            self.sim.set_simulator_data_roundings(self._resources_config.get("dataref-roundings", {}))
            self.sim.set_simulator_data_frequencies(simulator_data_frequencies=self._resources_config.get("dataref-fetch-frequencies", {}))

        # 1. Load global icons
        #   (They are never cached when loaded without aircraft.)
        rf = os.path.join(os.path.dirname(__file__), RESOURCES_FOLDER, ICONS_FOLDER)
        if os.path.exists(rf):
            icons = os.listdir(rf)
            for i in icons:
                if has_ext(i, "png"):  # later, might load JPG as well.
                    fn = os.path.join(rf, i)
                    image = Image.open(fn)
                    self.icons[i] = image

        # 1.2 Do we have a default icon with proper name?
        dftname = self.get_attribute("icon-name")
        if dftname in self.icons.keys():
            logger.debug(f"default icon name {dftname} found")
        else:
            logger.warning(f"default icon name {dftname} not found")

        # 2. Finding a default font for Pillow
        #   WE MUST find a default, system font at least

        # 2.1 We try the requested "default label font"
        default_label_font = self.get_attribute("label-font")
        if default_label_font is not None and default_label_font not in self.fonts.keys():
            f = locate_font(default_label_font)
            if f is not None:  # found one, perfect
                self.fonts[default_label_font] = f
                self.set_default("default-font", default_label_font)
                logger.debug(f"default font set to {default_label_font}")
                logger.debug(f"default label font set to {default_label_font}")

        # 2.3 We try the "default system font"
        default_system_font = self.get_attribute("system-font")
        if default_system_font is not None:
            f = locate_font(default_system_font)
            if f is not None:  # found it, perfect, keep it as default font for all purposes
                self.fonts[default_system_font] = f
                self.set_default("default-font", default_system_font)
                logger.debug(f"default font set to {default_system_font}")
                if default_label_font is None:  # additionnally, if we don't have a default label font, use it
                    self.set_default("default-label-font", default_system_font)
                    logger.debug(f"default label font set to {default_system_font}")

        if default_label_font is None and len(self.fonts) > 0:
            first_one = list(self.fonts.keys())[0]
            self.set_default("default-label-font", first_one)
            self.set_default("default-font", first_one)
            logger.debug(f"no default font found, using first available font ({first_one})")

        if default_label_font is None:
            logger.error(f"no default font")

        # 4. report summary if debugging
        logger.debug(
            f"default fonts {self.fonts.keys()}, default={self.get_attribute('default-font')}, default label={self.get_attribute('default-label-font')}"
        )

    def scan_web_decks(self):
        """Virtual decks are declared in the cockpit configuration
        Therefore it is necessary to have an aircraft folder.

        [description]
        """
        if self.acpath is None:
            logger.warning(f"no aircraft folder, cannot load virtual decks")
            return
        if self.virtual_decks_added:
            logger.info(f"virtual decks already added")
            return
        cnt = 0
        virtual_deck_types = {d.name: d for d in filter(lambda d: d.is_virtual_deck(), self.deck_types.values())}
        builder = self.all_deck_drivers.get(VIRTUAL_DECK_DRIVER)
        decks = builder[1]().enumerate(acpath=self.acpath, virtual_deck_types=virtual_deck_types)
        logger.info(f"found {len(decks)} virtual deck(s)")
        for name, device in decks.items():
            serial = device.get_serial_number()
            if serial in EXCLUDE_DECKS:
                logger.warning(f"deck {serial} excluded")
                del decks[name]
            logger.info(f"added virtual deck {name}, type {device.virtual_deck_config.get('type', 'type-not-found')}, serial {serial})")
            self.devices.append(
                {
                    CONFIG_KW.DRIVER.value: VIRTUAL_DECK_DRIVER,
                    CONFIG_KW.DEVICE.value: device,
                    CONFIG_KW.SERIAL.value: serial,
                }
            )
            cnt = cnt + 1
        self.virtual_decks_added = True
        logger.debug(f"added {cnt} virtual decks")

    def remove_web_decks(self):
        if not self.virtual_decks_added:
            logger.info(f"virtual decks not added")
            return
        to_remove = []
        for device in self.devices:
            if device.get(CONFIG_KW.DRIVER.value) == VIRTUAL_DECK_DRIVER:
                to_remove.append(device)
        for device in to_remove:
            self.devices.remove(device)
        self.virtual_decks_added = False
        logger.info(f"removed {len(to_remove)} virtual decks")

    def create_decks(self):
        fn = os.path.join(self.acpath, CONFIG_FOLDER, CONFIG_FILE)
        self._config = Config(fn)
        if not self._config.is_valid():
            logger.warning(f"no config file {fn}")
            return
        self.named_colors.update(self._config.get(CONFIG_KW.NAMED_COLORS.value, {}))
        if len(self.named_colors) > 0:
            logger.info(f"named colors {', '.join(self.named_colors)}")
        sn = os.path.join(self.acpath, CONFIG_FOLDER, SECRET_FILE)
        serial_numbers = Config(sn)
        self._secret = serial_numbers

        # 1. Adjust some settings in global config file.
        if self.sim is not None:
            self.sim.set_simulator_data_roundings(self._config.get("dataref-roundings", {}))
            self.sim.set_simulator_data_frequencies(simulator_data_frequencies=self._config.get("dataref-fetch-frequencies", {}))
            self.sim.DEFAULT_REQ_FREQUENCY = self._config.get("dataref-fetch-frequency", DEFAULT_FREQUENCY)

        # 2. Create decks
        decks = self._config.get(CONFIG_KW.DECKS.value)
        if decks is None:
            logger.warning(f"no deck in config file {fn}")
            return

        logger.info(f"cockpit is {'dark' if self.is_dark() else 'light'}, theme is {self.get_attribute('cockpit-theme')}")  # debug?

        # init
        deck_count_by_type = {ty.get(CONFIG_KW.NAME.value): 0 for ty in self.deck_types.values()}
        # tally
        for deck in decks:
            ty = deck.get(CONFIG_KW.TYPE.value)
            if ty in deck_count_by_type:
                deck_count_by_type[ty] = deck_count_by_type[ty] + 1
            else:
                deck_count_by_type[ty] = 1

        cnt = 0
        self.virtual_deck_list = {}

        for deck_config in decks:
            name = deck_config.get(CONFIG_KW.NAME.value, f"Deck {cnt}")

            disabled = deck_config.get(CONFIG_KW.DISABLED.value)
            if type(disabled) is not bool:
                if type(disabled) is str:
                    disabled = disabled.upper() in ["YES", "TRUE"]
                elif type(disabled) in [int, float]:
                    disabled = int(disabled) != 0
            if disabled:
                logger.info(f"deck {name} disabled, ignoring")
                continue

            deck_type = deck_config.get(CONFIG_KW.TYPE.value)
            if deck_type not in self.deck_types.keys():
                logger.warning(f"invalid deck type {deck_type}, ignoring")
                continue

            deck_driver = self.deck_types[deck_type].get(CONFIG_KW.DRIVER.value)
            if deck_driver not in self.all_deck_drivers.keys():
                logger.warning(f"invalid deck driver {deck_driver}, ignoring")
                continue

            serial = deck_config.get(CONFIG_KW.SERIAL.value)
            if serial is None:  # get it from the secret file
                serial = serial_numbers.get(name)

            # if serial is not None:
            device = self.get_device(req_driver=deck_driver, req_serial=serial)
            if device is not None:
                #
                if serial is None:
                    if deck_count_by_type[deck_type] > 1:
                        logger.warning(
                            f"only one deck of that type but more than one configuration in config.yaml for decks of that type and no serial number, ignoring"
                        )
                        continue
                    deck_config[CONFIG_KW.SERIAL.value] = device.get_serial_number()  # issue: might return None?
                    logger.info(f"deck {deck_type} {name} has serial {deck_config[CONFIG_KW.SERIAL.value]}")
                else:
                    deck_config[CONFIG_KW.SERIAL.value] = serial
                if name not in self.cockpit.keys():
                    self.cockpit[name] = self.all_deck_drivers[deck_driver][0](name=name, config=deck_config, cockpit=self, device=device)
                    if deck_driver == VIRTUAL_DECK_DRIVER:
                        deck_flat = self.deck_types.get(deck_type).desc()
                        if DECK_KW.BACKGROUND.value in deck_flat and DECK_KW.IMAGE.value in deck_flat[DECK_KW.BACKGROUND.value]:
                            background = deck_flat[DECK_KW.BACKGROUND.value]
                            fn = background[DECK_KW.IMAGE.value]
                            if self.deck_types.get(deck_type)._aircraft:
                                if not fn.startswith(AIRCRAFT_ASSET_PATH):
                                    background[DECK_KW.IMAGE.value] = AIRCRAFT_ASSET_PATH + fn
                            else:
                                if not fn.startswith(COCKPITDECKS_ASSET_PATH):
                                    background[DECK_KW.IMAGE.value] = COCKPITDECKS_ASSET_PATH + fn
                        self.virtual_deck_list[name] = deck_config | {
                            DECK_TYPE_ORIGINAL: self.deck_types.get(deck_type).store,
                            DECK_TYPE_DESCRIPTION: deck_flat,
                        }
                    cnt = cnt + 1
                    deck_layout = deck_config.get(DECK_KW.LAYOUT.value, DEFAULT_LAYOUT)
                    logger.info(f"deck {name} added ({deck_type}, driver {deck_driver}, layout {deck_layout})")
                else:
                    logger.warning(f"deck {name} already exist, ignoring")
            else:
                logger.error(f"deck {deck_type} {name} has no device, ignoring")

    def convert_color(self, instr):
        """Adds an extra layer of possibilities to define our own color names
        for styling purposes.
        """
        if instr in self.named_colors:
            return self.named_colors.get(instr)
        return convert_color(instr=instr)

    def create_default_decks(self):
        """
        When no deck definition is found in the aicraft folder, Cockpit loads
        a default X-Plane logo on all deck devices. The only active button is index 0,
        which toggle X-Plane map on/off.
        """
        self.acpath = None

        # {
        #    CONFIG_KW.TYPE.value: decktype,
        #    CONFIG_KW.DEVICE.value: device,
        #    CONFIG_KW.SERIAL.value: serial
        # }
        for deck in self.devices:
            deckdriver = deck.get(CONFIG_KW.DRIVER.value)
            if deckdriver not in self.all_deck_drivers.keys():
                logger.warning(f"invalid deck driver {deckdriver}, ignoring")
                continue
            device = deck[CONFIG_KW.DEVICE.value]
            device.open()
            device.reset()
            name = device.id()
            config = {
                CONFIG_KW.NAME.value: name,
                CONFIG_KW.TYPE.value: device.deck_type(),
                CONFIG_KW.SERIAL.value: device.get_serial_number(),
                CONFIG_KW.LAYOUT.value: None,  # Streamdeck will detect None layout and present default deck
                "brightness": 75,  # Note: layout=None is not the same as no layout attribute (attribute missing)
            }
            self.cockpit[name] = self.all_deck_drivers[deckdriver][0](name, config, self, device)

    def load_observables(self):
        fn = os.path.abspath(os.path.join(os.path.dirname(__file__), RESOURCES_FOLDER, OBSERVABLES_FILE))
        if os.path.exists(fn):
            config = {}
            with open(fn, "r") as fp:
                config = yaml.load(fp)
            self.observables = Observables(config=config, simulator=self.sim)
            logger.info(f"loaded {len(self.observables.observables)} observables")

        fn = os.path.abspath(os.path.join(self.acpath, CONFIG_FOLDER, RESOURCES_FOLDER, OBSERVABLES_FILE))
        if os.path.exists(fn):
            config = {}
            with open(fn, "r") as fp:
                config = yaml.load(fp)
            self.ac_observables = Observables(config=config, simulator=self.sim)
            logger.info(f"loaded {len(self.ac_observables.observables)} aircraft observables")

    # #########################################################
    # Cockpit data caches
    #
    def load_deck_types(self):
        # 1. "System" types
        for deck_type in DeckType.list():
            data = DeckType(deck_type)
            self.deck_types[data.name] = data
            if data.is_virtual_deck():
                self.virtual_deck_types[data.name] = data.get_virtual_deck_layout()
        # 2. Deck types in extension folder(s)
        if self.extension_paths is not None:
            for path in self.extension_paths:
                ext_path = os.path.join(path, DECKS_FOLDER, RESOURCES_FOLDER, TYPES_FOLDER)
                for deck_type in DeckType.list(ext_path):
                    data = DeckType(deck_type)
                    self.deck_types[data.name] = data
                    if data.is_virtual_deck():
                        self.virtual_deck_types[data.name] = data.get_virtual_deck_layout()

        # 3. Deck types in extension modules:
        for package in self.all_extensions:
            for deck_type in DeckType.list(path=None, module=package + ".decks.resources.types"):
                if deck_type not in self.deck_types:
                    data = DeckType(deck_type)
                    self.deck_types[data.name] = data
                    if data.is_virtual_deck():
                        self.virtual_deck_types[data.name] = data.get_virtual_deck_layout()
                    logger.debug(f"package {package}: decktype {deck_type} loaded")
                else:
                    logger.warning(f"package {package}: decktype {deck_type} already loaded")

        logger.info(f"loaded {len(self.deck_types)} deck types ({', '.join(self.deck_types.keys())}), {len(self.virtual_deck_types)} are virtual deck types")

    def load_aircraft_deck_types(self):
        aircraft_deck_types = os.path.abspath(os.path.join(self.acpath, CONFIG_FOLDER, RESOURCES_FOLDER, DECKS_FOLDER, DECK_TYPES))
        added = []
        for deck_type in DeckType.list(aircraft_deck_types):
            b = os.path.basename(deck_type)
            if b in [CONFIG_FILE, "designer.yaml"]:
                continue
            data = DeckType(deck_type)
            data._aircraft = True  # mark as non-system deck type
            self.deck_types[data.name] = data
            if data.is_virtual_deck():
                self.virtual_deck_types[data.name] = data.get_virtual_deck_layout()
            added.append(data.name)
        logger.info(f"added {len(added)} aircraft deck types ({', '.join(added)})")

    def get_deck_type(self, name: str):
        return self.deck_types.get(name)

    def load_icons(self):
        # Loading icons
        #
        cache_icon = self.get_attribute("cache-icon")
        dn = os.path.join(self.acpath, CONFIG_FOLDER, RESOURCES_FOLDER, ICONS_FOLDER)
        if os.path.exists(dn):
            self.icon_folder = dn
            cache = os.path.join(dn, "_icon_cache.pickle")
            if os.path.exists(cache) and cache_icon:
                with open(cache, "rb") as fp:
                    self.icons = pickle.load(fp)
                logger.info(f"{len(self.icons)} icons loaded from cache")
            else:
                # # Global, resource folder icons
                # #                                   # #
                # # THEY ARE NOW LOADED IN LOAD_DEFAULTS # #
                # #                                   # #
                # rf = os.path.join(os.path.dirname(__file__), RESOURCES_FOLDER, ICONS_FOLDER)
                # if os.path.exists(rf):
                #    icons = os.listdir(rf)
                #    for i in icons:
                #        if has_ext(i, "png"):  # later, might load JPG as well.
                #            fn = os.path.join(rf, i)
                #            image = Image.open(fn)
                #            self.icons[i] = image

                # Aircraft specific folder icons
                icons = os.listdir(dn)
                for i in icons:
                    if has_ext(i, "png"):  # later, might load JPG as well.
                        fn = os.path.join(dn, i)
                        image = Image.open(fn)
                        self.icons[i] = image
                    elif has_ext(i, "svg"):  # Wow.
                        try:
                            fn = os.path.join(dn, i)
                            fout = fn.replace(".svg", ".png")
                            svg2png(url=fn, write_to=fout)
                            image = Image.open(fout)
                            self.icons[i] = image
                        except:
                            logger.warning(f"could not load icon {fn}")
                            pass  # no cairosvg

                if cache_icon:  # we cache both folders of icons
                    with open(cache, "wb") as fp:
                        pickle.dump(self.icons, fp)
                    logger.info(f"{len(self.icons)} icons cached")
                else:
                    logger.info(f"{len(self.icons)} icons loaded")

    def get_icon(self, candidate_icon):
        for ext in ["", ".png", ".jpg", ".jpeg"]:
            fn = add_ext(candidate_icon, ext)
            if fn in self.icons.keys():
                logger.debug(f"Cockpit: icon {fn} found")
                return fn
        logger.warning(f"Cockpit: icon not found {candidate_icon}")  # , available={self.icons.keys()}
        return None

    def get_icon_image(self, icon):
        return self.icons.get(icon)

    def load_fonts(self):
        # Loading fonts.
        # For custom fonts (fonts found in the fonts config folder),
        # we supply the full path for font definition to ImageFont.
        # For other fonts, we assume ImageFont will search at OS dependent folders or directories.
        # If the font is not found by ImageFont, we ignore it.
        # So self.icons is a list of properly located usable fonts.
        #
        # 1. Load fonts supplied by Cockpitdeck in its resource folder
        rn = os.path.join(os.path.dirname(__file__), RESOURCES_FOLDER, FONTS_FOLDER)
        if os.path.exists(rn):
            fonts = os.listdir(rn)
            for i in fonts:
                if has_ext(i, ".ttf") or has_ext(i, ".otf"):
                    if i not in self.fonts.keys():
                        fn = os.path.join(rn, i)
                        try:
                            test = ImageFont.truetype(fn, self.get_attribute("label-size"))
                            self.fonts[i] = fn
                        except:
                            logger.warning(f"default font file {fn} not loaded")
                    else:
                        logger.debug(f"font {i} already loaded")

        # 2. Load fonts supplied by the user in the configuration
        dn = os.path.join(self.acpath, CONFIG_FOLDER, RESOURCES_FOLDER, FONTS_FOLDER)
        if os.path.exists(dn):
            fonts = os.listdir(dn)
            for i in fonts:
                if has_ext(i, ".ttf") or has_ext(i, ".otf"):
                    if i not in self.fonts.keys():
                        fn = os.path.join(dn, i)
                        try:
                            test = ImageFont.truetype(fn, self.get_attribute("label-size"))
                            self.fonts[i] = fn
                        except:
                            logger.warning(f"custom font file {fn} not loaded")
                    else:
                        logger.debug(f"font {i} already loaded")

        # 3. DEFAULT_LABEL_FONT and DEFAULT_SYSTEM_FONT loaded in load_defaults()
        logger.info(
            f"{len(self.fonts)} fonts loaded, default font={self.get_attribute('default-font')}, default label font={self.get_attribute('default-label-font')}"
        )

    def load_sounds(self):
        # Loading sounds.
        #
        # 1. Load sounds supplied by Cockpitdeck in its resource folder
        rn = os.path.join(os.path.dirname(__file__), RESOURCES_FOLDER, SOUNDS_FOLDER)
        if os.path.exists(rn):
            sounds = os.listdir(rn)
            for i in sounds:
                if has_ext(i, ".wav") or has_ext(i, ".mp3"):
                    if i not in self.sounds.keys():
                        fn = os.path.join(rn, i)
                        try:
                            with open(fn, mode="rb") as file:  # b is important -> binary
                                self.sounds[i] = file.read()
                        except:
                            logger.warning(f"default sound file {fn} not loaded")
                    else:
                        logger.debug(f"sound {i} already loaded")

        # 2. Load fonts supplied by the user in the configuration
        dn = os.path.join(self.acpath, CONFIG_FOLDER, RESOURCES_FOLDER, SOUNDS_FOLDER)
        if os.path.exists(dn):
            sounds = os.listdir(dn)
            for i in sounds:
                if has_ext(i, ".wav") or has_ext(i, ".mp3"):
                    if i not in self.sounds.keys():
                        fn = os.path.join(dn, i)
                        try:
                            with open(fn, mode="rb") as file:  # b is important -> binary
                                self.sounds[i] = file.read()
                        except:
                            logger.warning(f"custom sound file {fn} not loaded")
                    else:
                        logger.debug(f"sound {i} already loaded")

        logger.info(f"{len(self.sounds)} sounds loaded")

    # #########################################################
    # Cockpit start/stop/event/reload procedures
    #
    # Note: Reloading the deck is done from a separate (dedicated) thread through a queue.
    #
    # The reason is that the reload is provoked by a keypress which is handled in a callback
    # from a deck thread. On reload, the deck will be stopped, initialized, and restarted
    # leading somehow in the destruction of the objects that had created the thread.
    # When pressing a new button, callback would terminate Cockpitdeck.
    # To prevent that, the callback just enqueue a request to perform a reload and exits right away.
    # We do the reload from another thread, external to the callback,
    # that cleanly stops, initializes, and restarts the deck.
    #
    def start_event_loop(self):
        if not self.event_loop_run:
            self.event_loop_thread = threading.Thread(target=self.event_loop, name="Cockpit::event_loop")
            self.event_loop_run = True
            self.event_loop_thread.start()
            logger.debug("started")
        else:
            logger.warning("already running")

    def event_loop(self):
        logger.debug("starting event loop..")

        while self.event_loop_run:
            e = self.event_queue.get()  # blocks infinitely here

            if type(e) is str:
                if e == "terminate":
                    self.stop_event_loop()
                elif e == "reload":
                    self.reload_decks(just_do_it=True)
                elif e == "stop":
                    self.stop_decks(just_do_it=True)
                self.inc("event_count_" + e)
                continue

            try:
                logger.debug(f"doing {e}..")
                self.inc("event_count_" + type(e).__name__)
                if EVENTLOGFILE is not None and (LOG_DATAREF_EVENTS or not isinstance(e, SimulatorEvent)) and not e.is_replay():
                    # we do not enqueue events that are replayed
                    event_logger.info(e.to_json())
                e.run(just_do_it=True)
                logger.debug("..done without error")
            except:
                logger.warning("..done with error", exc_info=True)

        logger.debug(".. event loop ended")

    def stop_event_loop(self):
        if self.event_loop_run:
            self.event_loop_run = False
            self.event_queue.put("terminate")  # to unblock the Queue.get()
            # self.event_loop_thread.join()
            logger.debug("stopped")
        else:
            logger.warning("not running")

    # #########################################################
    # Cockpit start/stop/handle procedures for virtual decks
    #
    def has_web_decks(self) -> bool:
        for device in self.devices:
            if device.get(CONFIG_KW.DRIVER.value) == VIRTUAL_DECK_DRIVER:
                return True
        return False

    def get_web_decks(self):
        return self.virtual_deck_list

    def get_virtual_deck_description(self, deck):
        return self.virtual_deck_list.get(deck)

    def get_virtual_deck_defaults(self):
        return self.get_attribute("web-deck-defaults")

    def handle_code(self, code: int, name: str):
        logger.debug(f"received code {name}:{code}")
        if code == 1:
            deck = self.cockpit.get(name)
            if deck is None:
                logger.warning(f"handle code: deck {name} not found (code {code})")
                return
            deck.add_client()
            logger.debug(f"{name} opened")
            deck.reload_page()
            logger.debug(f"{name} reloaded")
        if code == 2:
            deck = self.cockpit.get(name)
            if deck is None:
                logger.warning(f"handle code: deck {name} not found (code {code})")
                return
            deck.remove_client()
            logger.debug(f"{name} closed")
        elif code in [4, 5]:
            payload = {
                "code": code,
                "deck": name,
                "meta": {"ts": datetime.now().timestamp()},
            }
            self.send(deck=self.name, payload=payload)

    def process_event(self, deck_name, key, event, data, replay: bool = False):
        deck = self.cockpit.get(deck_name)
        logger.debug(f"received {deck_name}: key={key}, event={event}")
        if deck is None:
            logger.warning(f"handle event: deck {deck_name} not found")
            return
        if not replay:
            if deck.deck_type.is_virtual_deck():
                deck.key_change_callback(key=key, state=event, data=data)
            else:
                deck.key_change_callback(deck=deck.device, key=key, state=event)
            return
        deck.replay(key=key, state=event, data=data)

    def replay_sim_event(self, data: dict):
        path = data.get("path")
        if path is not None:
            if not self.sim.is_internal_simulator_data(path):
                e = self.sim.create_replay_event(name=path, value=data.get("value"))
                e._replay = True
                e.run()  # enqueue after setting the reply flag
        else:
            logger.warning(f"path not found")

    # #########################################################
    # Other
    #
    def reload_decks(self, just_do_it: bool = False):
        """
        Development function to reload page yaml without leaving the page
        Should not be used in production...
        """
        # A security... if we get called we must ensure reloader is running...
        if just_do_it:
            logger.info("reloading decks..")
            self.busy_reloading = True
            self.default_pages = {}  # {deck_name: currently_loaded_page_name}
            for name, deck in self.cockpit.items():
                if deck.current_page is not None:
                    self.default_pages[name] = deck.current_page.name
            self.load_aircraft(self.acpath)  # will terminate it before loading again
            self.busy_reloading = False
            logger.info("..done")
        else:
            self.event_queue.put("reload")
            logger.debug("enqueued")

    def stop_decks(self, just_do_it: bool = False):
        """
        Stop decks gracefully. Since it also terminates self.event_loop_thread we cannot wait for it
        since we are called from it ... So we just tell it to terminate.
        """
        if just_do_it:
            logger.info("stopping decks..")
            self.terminate_all()
        else:
            self.event_queue.put("stop")
            logger.debug("enqueued")

    def get_livery(self, path: str) -> str:
        return os.path.basename(os.path.normpath(path))

    def get_aircraft_home(self, path: str) -> str:
        return os.path.normpath(os.path.join(path, "..", ".."))

    def get_aircraft(self, path: str) -> str:
        # Path is like Aircraft/Extra Aircraft/ToLiss A321/liveries/F Airways (OO-PMA)/
        return os.path.split(os.path.normpath(os.path.join(path, "..", "..")))[1]

    def get_aircraft_path(self, aircraft) -> str | None:
        for base in self.cockpitdecks_path.split(":"):
            ac = os.path.join(base, aircraft)
            if os.path.exists(ac) and os.path.isdir(ac):
                ac_cfg = os.path.join(ac, CONFIG_FOLDER)
                if os.path.exists(ac_cfg) and os.path.isdir(ac_cfg):
                    logger.info(f"aircraft path found in COCKPITDECKS_PATH: {ac}, with deckconfig")
                    return ac
        logger.info(f"aircraft {aircraft} not found in COCKPITDECKS_PATH={self.cockpitdecks_path}")
        return None

    def simulator_data_changed(self, data: SimulatorData):
        """
        This gets called when dataref AIRCRAFT_CHANGE_MONITORING_DATAREF is changed, hence a new aircraft has been loaded.
        """
        if not isinstance(data, SimulatorData) or data.name not in self._monitored_strings:
            logger.warning(f"unhandled {data.name}={data.value()}")
            return

        if data.name != AIRCRAFT_CHANGE_MONITORING_DATAREF:
            logger.info(f"{data.name}={data.value()}")
            return

        value = data.value()
        if value is not None and self._livery_path == value:
            logger.info(f"livery path unchanged {self._livery_path}")
            return
        if value is None or type(value) is not str:
            logger.warning(f"livery path invalid value {value}, ignoring")
            return

        self._livery_path = value
        acname = self.get_aircraft(value)
        if self._acname != acname:
            self._acname = acname
            logger.info(f"aircraft name set to {self._acname}")

        new_livery = self.get_livery(value)

        # Automatic reloading of aircraft
        if self.mode > 0:
            logger.info("Cockpitdecks in demontration mode or aircraft fixed, aircraft not adjusted")
        else:
            new_ac = self.get_aircraft_path(self._acname)
            if new_ac != None and self.acpath != new_ac:
                logger.debug(f"aircraft path: current {self.acpath}, new {new_ac}")
                logger.info(f"livery changed to {new_livery}, aircraft changed to {new_ac}, loading new aircraft")
                self.load_aircraft(acpath=new_ac)
                return  # no additional processing
            else:
                logger.info("aircraft path not found, aircraft not adjusted")

        # Adjustment of livery
        old_livery = self._livery_dataref.value()
        if old_livery is None:
            self._livery_dataref.update_value(new_value=new_livery, cascade=True)
            logger.info(f"initial aircraft livery set to {new_livery}")
        elif old_livery != new_livery:
            self._livery_dataref.update_value(new_value=new_livery, cascade=True)
            logger.info(f"new aircraft livery {new_livery} (former was {old_livery})")
            if RELOAD_ON_LIVERY_CHANGE:
                self.reload_decks()

    def terminate_aircraft(self):
        logger.info("terminating..")
        drefs = {d.name: d.value() for d in self.sim.all_simulator_data.values()}  #  if d.is_internal
        with open("datarefs-log.yaml", "w") as fp:
            yaml.dump(drefs, fp)
        for deck in self.cockpit.values():
            deck.terminate()
        self.remove_web_decks()
        self.cockpit = {}
        nt = len(threading.enumerate())
        if nt > 1:
            logger.info(f"{nt} threads")
            logger.info(f"{[t.name for t in threading.enumerate()]}")
        logger.info("..done")
        logger.info(f"{os.path.basename(self.acpath)} terminated " + "=" * 50)

    def terminate_devices(self):
        for deck in self.devices:
            deck_driver = deck.get(CONFIG_KW.DRIVER.value)
            if deck_driver not in self.all_deck_drivers.keys():
                logger.warning(f"invalid deck type {deck_driver}, ignoring")
                continue
            device = deck[CONFIG_KW.DEVICE.value]
            self.all_deck_drivers[deck_driver][0].terminate_device(device, deck[CONFIG_KW.SERIAL.value])

    def terminate_all(self, threads: int = 1):
        logger.info("terminating..")
        # Stop processing events
        if self.event_loop_run:
            self.stop_event_loop()
            logger.info("..event loop stopped..")
        # Terminate decks
        self.terminate_aircraft()
        logger.info("..aircraft terminated..")
        # Terminate dataref collection
        if self.sim is not None:
            logger.info("..terminating connection to simulator..")
            self.sim.terminate()
            logger.debug("..deleting connection to simulator..")
            del self.sim
            self.sim = None
            logger.debug("..connection to simulator deleted..")
        logger.info("..terminating devices..")
        self.terminate_devices()
        logger.info("..done")
        left = len(threading.enumerate())
        if left > threads:  # [MainThread and spinner]
            logger.error(f"{left} threads remaining")
            logger.error(f"{[t.name for t in threading.enumerate()]}")
        # logger.info(self._reqdfts)

    def run(self, release: bool = False):
        if len(self.cockpit) > 0:
            # Each deck should have been started
            # Start reload loop
            logger.info("starting..")
            self.sim.connect()
            logger.info("..connect to simulator loop started..")
            self.start_event_loop()
            logger.info("..event loop started..")
            if self.has_web_decks():
                self.handle_code(code=4, name="init")  # wake up proxy
            logger.info(f"{len(threading.enumerate())} threads")
            logger.info(f"{[t.name for t in threading.enumerate()]}")
            logger.info("(note: threads named 'Thread-? (_read)' are Elgato Stream Deck serial port readers)")
            logger.info("..started")
            if not release or not self.has_web_decks():
                logger.info(f"serving {self.name}")
                for t in threading.enumerate():
                    try:
                        t.join()
                    except RuntimeError:
                        pass
                logger.info("terminated")
            logger.info(f"serving {self.name} (released)")
        else:
            logger.warning("no deck")
            if self.acpath is not None:
                self.terminate_all()

    def err_clear(self):
        self.vd_errs = []

    def register_deck(self, deck: str, websocket):
        if deck not in self.vd_ws_conn:
            self.vd_ws_conn[deck] = []
            logger.debug(f"{deck}: new registration")
        self.vd_ws_conn[deck].append(websocket)
        logger.debug(f"{deck}: registration added ({len(self.vd_ws_conn[deck])})")
        logger.info(f"registered deck {deck}")

    def is_closed(self, ws):
        return ws.__dict__.get("environ").get("werkzeug.socket").fileno() < 0  # there must be a better way to do this...

    def remove(self, websocket):
        # we unfortunately have to scan all decks to find the ws to remove
        #
        for deck in self.vd_ws_conn:
            remove = []
            for ws in self.vd_ws_conn[deck]:
                if ws == websocket:
                    remove.append(websocket)
            for ws in remove:
                self.vd_ws_conn[deck].remove(ws)
        remove = []
        for deck in self.vd_ws_conn:
            if len(self.vd_ws_conn[deck]) == 0:
                self.handle_code(code=2, name=deck)
                remove.append(deck)
                logger.info(f"unregistered deck {deck}")
        for deck in remove:
            del self.vd_ws_conn[deck]

    def send(self, deck, payload) -> bool:
        sent = False
        client_list = self.vd_ws_conn.get(deck)
        closed_ws = []
        if client_list is not None:
            for ws in client_list:  # send to each instance of this deck connected to this websocket server
                if self.is_closed(ws):
                    closed_ws.append(ws)
                    continue
                ws.send(json.dumps(payload))
                logger.debug(f"sent for {deck}")
                sent = True
            if len(closed_ws) > 0:
                for ws in closed_ws:
                    client_list.remove(ws)
        else:
            if deck not in self.vd_errs:
                logger.warning(f"no client for {deck}")
                self.vd_errs.append(deck)
        return sent

    def probe(self, deck):
        return self.send(
            deck=deck,
            payload={
                "code": 99,
                "deck": deck,
                "meta": {"ts": datetime.now().timestamp()},
            },
        )

    # ###############################################################
    # Button designer
    #
    #
    def get_assets(self):
        """Collects all assets for button designer

        Returns:
            dict: Assets
        """
        decks = [{"name": k, "type": v.deck_type.name} for k, v in self.cockpit.items()]
        return {
            "decks": decks,
            "fonts": list(self.fonts.keys()),
            "icons": list(self.icons.keys()),
            "activations": list(self.all_activations.keys()),
            "representations": list(self.all_representations.keys()),
        }

    def get_deck_indices(self, name):
        deck = self.cockpit.get(name)
        if deck is None:
            return {"index": []}
        return {"indices": deck.deck_type.valid_indices(with_icon=True)}

    def get_button_details(self, deck, index):
        deck = self.cockpit.get(deck)
        if deck is None:
            return {}
        return {
            "deck": deck.name,
            "deck_type": deck.deck_type.name,
            "index": index,
            "activations": list(deck.deck_type.valid_activations(index, source=self)),
            "representations": list(deck.deck_type.valid_representations(index, source=self)),
        }

    def get_activation_parameters(self, name, index=None):
        return self.all_activations.get(name).parameters()

    def get_representation_parameters(self, name, index=None):
        return self.all_representations.get(name).parameters()

    def save_deck(self, deck):
        fn = os.path.join(self.acpath, CONFIG_FOLDER, CONFIG_FILE)
        current_config = Config(fn)
        decks = current_config[CONFIG_KW.DECKS.value]
        found = False
        i = 0
        while not found and i < len(decks):
            found = decks[i][CONFIG_KW.NAME.value] == deck
            i = i + 1
        if not found:
            # create it, save it
            decks.append({"name": deck, "type": deck})  # default layout will be 'default'
            with open(fn, "w") as fp:
                if CONFIG_FILENAME in current_config.store:
                    del current_config.store[CONFIG_FILENAME]
                yaml.dump(current_config.store, fp)
                logger.info(f"added deck {deck} to config file")
            # create/save serial as well
            sn = os.path.join(self.acpath, CONFIG_FOLDER, SECRET_FILE)
            serial_numbers = Config(sn)
            if not deck in serial_numbers.store:
                serial_numbers.store[deck] = deck
            with open(sn, "w") as fp:
                if CONFIG_FILENAME in serial_numbers.store:
                    del serial_numbers.store[CONFIG_FILENAME]
                yaml.dump(serial_numbers.store, fp)
                logger.info(f"added deck {deck} to secret file")

            if self.event_loop_run:
                logger.info(f"reloading decks..")
                self.reload_decks()
            else:
                logger.info(f"starting..")
                self.start_aircraft(self.acpath)
                self.refresh_all_decks()
        else:
            logger.debug(f"deck {deck} already exists in config file")

    def save_button(self, data):
        acpath = self.acpath
        if acpath is None:
            acpath = "output"  # will save in current dir

        deck = data.get("deck", "")
        # if deck != "":
        #     self.save_deck(deck)

        layout = data.get("layout", "")
        if layout == "":
            layout = "default"
        dn = os.path.join(acpath, CONFIG_FOLDER, layout)
        if not os.path.exists(dn):
            os.makedirs(dn, exist_ok=True)

        page = data.get("page", "")
        if page == "":
            page = "index.yaml"
        if not page.endswith(".yaml"):
            page = page + ".yaml"
        fn = os.path.join(dn, page)

        page_config = None
        button_config = yaml.load(data["code"])
        if os.path.exists(fn):
            with open(fn, "r") as fp:
                page_config = yaml.load(fp)
                if page_config is not None:
                    if "buttons" in page_config:
                        page_config["buttons"] = list(
                            filter(
                                lambda b: b["index"] != button_config["index"],
                                page_config["buttons"],
                            )
                        )
                    else:
                        page_config["buttons"] = []
        if page_config is None:
            page_config = {"buttons": [button_config]}
        else:
            page_config["buttons"].append(button_config)
        with open(fn, "w") as fp:
            yaml.dump(page_config, fp)
            logger.info(f"button saved ({fn})")

    def load_button(self, deck, layout, page, index):
        deck_name = self.cockpit.get(deck)
        if deck_name is None or deck_name == "":
            return {"code": "", "meta": {"error": f"no deck {deck}"}}

        if layout == "":
            layout = "default"
        dn = os.path.join(self.acpath, CONFIG_FOLDER, layout)
        if not os.path.exists(dn):
            return {"code": "", "meta": {"error": f"no layout {layout}"}}

        if page == "":  # page name cannot be in name: attribute0
            page = "index"
        fn = os.path.join(dn, page + ".yaml")
        if not os.path.exists(dn):
            return {"code": "", "meta": {"error": f"no page {page}"}}

        this_page = Config(fn)
        if CONFIG_KW.BUTTONS.value not in this_page.store:
            return {"code": "", "meta": {"error": f"no buttons in {page}"}}

        this_button = None
        for b in this_page.store.get(CONFIG_KW.BUTTONS.value):
            idx = b.get(CONFIG_KW.INDEX.value)
            if idx is not None and ((idx == index) or (str(idx) == str(index))):
                buf = io.BytesIO()
                yaml.dump(b, buf)
                ret = buf.getvalue().decode("utf-8")
                return {
                    "code": ret,
                    "meta": {"error": f"no buttons in {page}"},
                }  # there might be yaml parser garbage in b
        return {"code": "", "meta": {"error": f"no button index {index}"}}

    def render_button(self, data):
        # testing. returns random icon
        action = data.get("action")
        if action is not None and action == "save":
            self.save_button(data)
        deck_name = data.get("deck")
        if deck_name is None or deck_name == "":
            return {"image": "", "meta": {"error": "no deck name"}}
        deck = self.cockpit.get(deck_name)
        if deck is None:
            return {"image": "", "meta": {"error": f"deck {deck_name} not found"}}
        config = yaml.load(data["code"])
        if config is None or len(config) == 0:
            return {"image": "", "meta": {"error": "no button configuration"}}
        button = None
        image = None
        try:
            button = deck.make_button(config=config)
            if button is None:
                return {"image": "", "meta": {"error": "button not created"}}
            image = button.get_representation()
        except:
            logger.warning(
                f"error generating button or image\ndata: {data}\nconfig: {json.dumps(config, indent=2)}",
                exc_info=True,
            )
        if button is None:
            return {"image": "", "meta": {"error": "no button"}}
        if image is None:
            return {"image": "", "meta": {"error": "no image"}}
        width, height = image.size
        img_byte_arr = io.BytesIO()
        image.save(img_byte_arr, format="PNG")
        content = img_byte_arr.getvalue()
        meta = {  # later: return also is_valid() and errors
            "error": "ok",
            "activation-valid": button._activation.is_valid(),
            "representation-valid": button._representation.is_valid(),
            "activation-desc": button._activation.describe(),
            "representation-desc": button._representation.describe(),
        }
        payload = {"image": base64.encodebytes(content).decode("ascii"), "meta": meta}
        return payload

    def get_deck_background_images(self):
        # Located either in cockpitdecks/decks/resources/assets/decks/images
        # or <aircraft>/deckconfig/resources/decks/images.
        ASSET_FOLDER = os.path.abspath(os.path.join("cockpitdecks", DECKS_FOLDER, RESOURCES_FOLDER, ASSETS_FOLDER))
        AIRCRAFT_ASSET_FOLDER = os.path.abspath(os.path.join(self.acpath, CONFIG_FOLDER, RESOURCES_FOLDER))
        INTERNAL_DESIGN = False
        folders = [AIRCRAFT_ASSET_FOLDER]
        if INTERNAL_DESIGN:
            folders.append(ASSET_FOLDER)
        deckimages = {}
        for base in folders:
            dn = os.path.join(base, DECKS_FOLDER, DECK_IMAGES)
            if os.path.isdir(dn):
                files = []
                for ext in ["png", "jpg"]:
                    files = files + glob.glob(os.path.join(dn, f"*.{ext}"))
                for f in files:
                    fn = os.path.basename(f)
                    if fn in deckimages:
                        logger.warning(f"duplicate deck background image {fn}, ignoring {f}")
                    else:
                        if fn.startswith("/"):
                            fn = fn[1:]
                        if base == AIRCRAFT_ASSET_FOLDER:
                            deckimages[fn] = AIRCRAFT_ASSET_PATH + fn
                        else:
                            deckimages[fn] = COCKPITDECKS_ASSET_PATH + fn
        return deckimages

    def refresh_deck(self, deck):
        payload = {"code": 1, "deck": name, "meta": {"ts": datetime.now().timestamp()}}
        self.send(deck=name, payload=payload)

    def refresh_all_decks(self):
        for name in self.get_web_decks():
            payload = {
                "code": 1,
                "deck": name,
                "meta": {"ts": datetime.now().timestamp()},
            }
            self.send(deck=name, payload=payload)

    def locate_image(self, filename):
        if filename is None:
            return None
        places = [
            os.path.join(os.path.abspath(self.acpath), CONFIG_FOLDER, RESOURCES_FOLDER),
            os.path.join(os.path.abspath(self.acpath), CONFIG_FOLDER, RESOURCES_FOLDER, ICONS_FOLDER),
            os.path.join(os.path.abspath(self.acpath), CONFIG_FOLDER, RESOURCES_FOLDER, DECKS_FOLDER),
            os.path.join(os.path.abspath(self.acpath), CONFIG_FOLDER, RESOURCES_FOLDER, DECKS_FOLDER, "images"),
            os.path.abspath(os.path.join("cockpitdecks", RESOURCES_FOLDER)),
            os.path.abspath(os.path.join("cockpitdecks", RESOURCES_FOLDER, ICONS_FOLDER)),
        ]
        for directory in places:
            fn = os.path.abspath(os.path.join(directory, filename))
            logger.debug(f"trying {fn}")
            if os.path.exists(fn):
                logger.debug(f"file {filename} in {fn}")
                return fn
        logger.warning(f"file {filename} not found")
        return None

    def execute(self, instruction: CockpitdecksInstruction):
        if not isinstance(instruction, CockpitdecksInstruction):
            logger.warning(f"invalid instruction {instruction.name}")
            return
        instruction._execute()

    def instruction_factory(self, name: str, delay: float = 0.0, condition: str | None = None):
        return CockpitdecksInstruction(name=name, cockpit=self, condition=condition, delay=delay)
