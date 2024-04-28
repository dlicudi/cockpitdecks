# Base class for all decks
#
import os
import logging
import pickle

from typing import Dict, List, Any
from abc import ABC, abstractmethod
from functools import reduce

from PIL import Image

from cockpitdecks import CONFIG_FOLDER, CONFIG_FILE, DECK_FEEDBACK, RESOURCES_FOLDER, ICONS_FOLDER
from cockpitdecks import ID_SEP, KW, DEFAULT_LAYOUT
from cockpitdecks import Config
from cockpitdecks.resources.color import convert_color

from .page import Page
from .button import Button
from cockpitdecks.event import DeckEvent, PushEvent
from cockpitdecks.decks.resources import DeckType

logger = logging.getLogger(__name__)
# logger.setLevel(logging.DEBUG)

DECKS_FOLDER = "decks"


class Deck(ABC):
    """
    Loads the configuration of a Deck.
    A Deck has a collection of Pages, and knows which one is currently being displayed.
    """

    def __init__(self, name: str, config: dict, cockpit: "Cockpit", device=None):
        self._config = config
        self.name = name
        self.cockpit = cockpit
        self.device = device
        self.deck_type: DeckType = {}

        self.cockpit.set_logging_level(__name__)

        self._layout_config: Dict[str, str | int | float | bool | Dict] = {}
        self.pages: Dict[str, Page] = {}
        self.home_page: Page | None = None
        self.current_page: Page | None = None
        self.previous_page: Page | None = None
        self.page_history: List[str] = []

        self.valid = False
        self.running = False

        self.previous_key_values: Dict[str, Any] = {}
        self.current_key_values: Dict[str, Any] = {}

        if "serial" in config:
            self.serial = config["serial"]
        else:
            self.valid = False
            logger.error(f"{self.name}: has no serial number, cannot use")

        self.brightness = 100
        if "brightness" in config:
            self.brightness = int(config["brightness"])
            if self.device is not None:
                self.device.set_brightness(self.brightness)

        self.layout = config.get(KW.LAYOUT.value)
        # if self.layout is None:
        #     self.layout = DEFAULT_LAYOUT
        #     logger.warning(f"deck has no layout, using default")

        self.home_page_name = config.get("home-page-name", self.get_attribute("default-home-page-name"))
        self.logo = config.get("logo", self.get_attribute("default-logo"))
        self.wallpaper = config.get("wallpaper", self.get_attribute("default-wallpaper"))

        self.valid = True

    # #######################################
    # Deck Common Functions
    #
    def init(self):
        if not self.valid:
            logger.warning(f"deck {self.name}: is invalid")
            return
        self.set_deck_type()
        self.load()  # will load default page if no page found
        self.start()  # Some system may need to start before we can load a page

    def get_id(self):
        l = self.layout if self.layout is not None else "-nolayout-"
        return ID_SEP.join([self.cockpit.get_id(), self.name, l])

    def get_deck_button_definition(self, idx):
        return self.deck_type.get_button_definition(idx)

    def set_deck_type(self):
        deck_type = self._config.get(KW.TYPE.value)
        self.deck_type = self.cockpit.get_deck_type_description(deck_type)
        if self.deck_type is None:
            logger.error(f"no deck definition for {deck_type}")

    def get_deck_type_description(self):
        return self.deck_type

    def get_attribute(self, attribute: str, silence: bool = False):
        val = self._config.get(attribute)
        if val is not None:
            return val
        val = self._layout_config.get(attribute)
        if val is not None:
            return val
        ATTRNAME = "_defaults"
        val = None
        if hasattr(self, ATTRNAME):
            ld = getattr(self, ATTRNAME)
            if isinstance(ld, dict):
                val = ld.get(attribute)
        return val if val is not None else self.cockpit.get_attribute(attribute, silence=silence)

    def get_button_value(self, name):
        a = name.split(ID_SEP)
        if len(a) > 0:
            if a[0] == self.name:
                if a[1] in self.pages.keys():
                    return self.pages[a[1]].get_button_value(ID_SEP.join(a[1:]))
                else:
                    logger.warning(f"so such page {a[1]}")
            else:
                logger.warning(f"not my deck {a[0]} ({self.name})")
        return None

    def inspect(self, what: str | None = None):
        """
        This function is called on all pages of this Deck.
        """
        logger.info(f"*" * 60)
        logger.info(f"Deck {self.name} -- {what}")
        for v in self.pages.values():
            v.inspect(what)

    def load(self):
        """
        Loads Streamdeck pages during configuration
        """
        if self.layout is None:
            self.make_default_page()
            return

        dn = os.path.join(self.cockpit.acpath, CONFIG_FOLDER, self.layout)
        if not os.path.exists(dn):
            logger.warning(f"deck has no layout folder '{self.layout}', loading default page")
            self.make_default_page()
            return

        pages = os.listdir(dn)
        if CONFIG_FILE in pages:  # first load config
            self._layout_config = Config(os.path.join(dn, CONFIG_FILE))
            if not self._layout_config.is_valid():
                logger.debug(f"no layout config file")

        for p in pages:
            if p == CONFIG_FILE:
                continue
            elif not (p.lower().endswith(".yaml") or p.lower().endswith(".yml")):  # not a yaml file
                logger.debug(f"{dn}: ignoring file {p}")
                continue

            fn = os.path.join(dn, p)
            # if os.path.exists(fn):  # we know the file should exists...
            page_config = Config(fn)
            if not page_config.is_valid():
                logger.warning(f"file {p} not found")
                continue

            page_name = ".".join(p.split(".")[:-1])  # build default page name, remove extension ".yaml" or ".yml" from filename
            if KW.NAME.value in page_config:
                page_name = page_config[KW.NAME.value]

            if page_name in self.pages.keys():
                logger.warning(f"page {page_name}: duplicate name, ignored")
                continue

            if not KW.BUTTONS.value in page_config:
                logger.error(f"{page_name} has no button definition '{KW.BUTTONS.value}', ignoring")
                continue

            display_fn = fn.replace(os.path.join(self.cockpit.acpath, CONFIG_FOLDER + os.sep), "..")
            logger.debug(f"loading page {page_name} (from file {display_fn})..")

            this_page = Page(page_name, page_config.store, self)
            self.pages[page_name] = this_page

            # Page buttons
            this_page.load_buttons(page_config[KW.BUTTONS.value])

            # Page includes
            if KW.INCLUDES.value in page_config:
                includes = page_config[KW.INCLUDES.value]
                if type(page_config[KW.INCLUDES.value]) == str:  # just one file
                    includes = includes.split(",")
                logger.debug(f"deck {self.name}: page {page_name} includes {includes}..")
                ipb = 0
                for inc in includes:
                    fni = os.path.join(dn, inc + ".yaml")
                    inc_config = Config(fni)
                    if inc_config.is_valid():
                        this_page.merge_attributes(inc_config.store)  # merges attributes first since can have things for buttons....
                        if KW.BUTTONS.value in inc_config:
                            before = len(this_page.buttons)
                            this_page.load_buttons(inc_config[KW.BUTTONS.value])
                            ipb = len(this_page.buttons) - before
                        del inc_config.store[KW.BUTTONS.value]
                    else:
                        logger.warning(f"includes: {inc}: file {fni} not found")
                display_fni = fni.replace(
                    os.path.join(self.cockpit.acpath, CONFIG_FOLDER + os.sep),
                    "..",
                )
                logger.info(f"deck {self.name}: page {page_name} includes {inc} (from file {display_fni}), include contains {ipb} buttons")
                logger.debug(f"includes: ..included")

            logger.info(f"deck {self.name}: page {page_name} loaded (from file {display_fn}), contains {len(this_page.buttons)} buttons")

        if not len(self.pages) > 0:
            self.valid = False
            logger.error(f"{self.name}: has no page, ignoring")
            # self.load_default_page()
        else:
            self.set_home_page()
            logger.info(f"deck {self.name}: loaded {len(self.pages)} pages from layout {self.layout}")

    def change_page(self, page: str | None = None):
        """
        Returns the currently loaded page name

        :param    page:  The page
        :type      page:  str
        """
        if page is None:
            logger.debug(f"deck {self.name} loading home page")
            self.load_home_page()
            return
        if page == KW.BACKPAGE.value:
            if len(self.page_history) > 1:
                page = self.page_history.pop()  # this page
                page = self.page_history.pop()  # previous one
            else:
                if self.home_page is not None:
                    page = self.home_page.name
            logger.debug(f"deck {self.name} back page to {page}..")
        logger.debug(f"deck {self.name} changing page to {page}..")
        if page in self.pages.keys():
            if self.current_page is not None:
                logger.debug(f"deck {self.name} unloading page {self.current_page.name}..")
                logger.debug(f"..unloading datarefs..")
                self.cockpit.sim.remove_datarefs_to_monitor(self.current_page.datarefs)
                self.cockpit.sim.remove_collections_to_monitor(self.current_page.dataref_collections)
                logger.debug(f"..cleaning page..")
                self.current_page.clean()
            logger.debug(f"deck {self.name} ..installing new page {page}..")
            self.previous_page = self.current_page
            self.current_page = self.pages[page]
            self.page_history.append(self.current_page.name)
            logger.debug(f"..reset device {self.name}..")
            self.device.reset()
            logger.debug(f"..loading datarefs..")
            self.cockpit.sim.add_datarefs_to_monitor(self.current_page.datarefs)  # set which datarefs to monitor
            self.cockpit.sim.add_collections_to_monitor(self.current_page.dataref_collections)
            logger.debug(f"..rendering page..")
            self.current_page.render()
            logger.debug(f"deck {self.name} ..done")
            logger.info(f"deck {self.name} changed page to {page}")
            return self.current_page.name
        else:
            logger.warning(f"deck {self.name}: ..page {page} not found")
            if self.current_page is not None:
                return self.current_page.name
        return None

    def reload_page(self):
        self.change_page(self.current_page.name)

    def set_home_page(self):
        if not len(self.pages) > 0:
            self.valid = False
            logger.error(f"deck {self.name} has no page, ignoring")
        else:
            if self.home_page_name in self.pages.keys():
                self.home_page = self.pages[self.home_page_name]
            else:
                logger.debug(f"deck {self.name}: no home page named {self.home_page_name}")
                self.home_page = self.pages[list(self.pages.keys())[0]]  # first page
            logger.debug(f"deck {self.name}: home page {self.home_page.name}")

    def load_home_page(self):
        """
        Connects to device and send initial keys.
        """
        if self.home_page is not None:
            self.change_page(self.home_page.name)
            logger.debug(f"deck {self.name}, home page {self.home_page.name} loaded")
        else:
            logger.debug(f"deck {self.name} has no home page")

    @abstractmethod
    def make_default_page(self, b: str | None = None):
        """
        Connects to device and send initial keys.
        """
        pass

    # #######################################
    # Deck Specific Functions : Description (capabilities)
    #
    def get_index_prefix(self, index):
        return self.deck_type.get_index_prefix(index=index)

    def get_index_numeric(self, index):
        # Useful to just get the int value of index
        return self.deck_type.get_index_numeric(index=index)

    def valid_indices(self, with_icon: bool = False):
        return self.deck_type.valid_indices(with_icon=with_icon)

    def valid_activations(self, index=None):
        return self.deck_type.valid_activations(index=index)

    def valid_representations(self, index=None):
        return self.deck_type.valid_representations(index=index)

    # #######################################
    # Deck Specific Functions : Activation
    #
    def key_change_processing(self, event: DeckEvent):
        """
        For those that did not process the event, this does the work.
        Mainly, mostly, it enqueues the event for execution.
        Sometimes, this is done right away from the Deck driver.
        But if it not the case, this function does it.
        """
        event.run()

    # #######################################
    # Deck Specific Functions : Representation
    #
    def print_page(self, page: Page):
        pass

    def fill_empty(self, key):
        pass

    def clean_empty(self, key):
        pass

    @abstractmethod
    def render(self, button: Button):
        pass

    # #######################################
    # Deck Specific Functions : Device
    #
    @abstractmethod
    def start(self):
        pass

    def terminate(self):
        for p in self.pages.values():
            p.terminate()
        self.pages = {}


class DeckWithIcons(Deck):
    """
    This type of deck is a variant of the above for decks with LCD capabilites,
    LCD being individual key display (like streamdecks) or a larger LCD with areas
    of interaction, like LoupedeckLive.
    This class complement the generic deck with image display function
    and utilities for image transformation.
    """

    def __init__(self, name: str, config: dict, cockpit: "Cockpit", device=None):
        Deck.__init__(self, name=name, config=config, cockpit=cockpit, device=device)

        self.pil_helper = None
        self.icons: Dict[str, "PIL.Image"] = {}  # icons ready for this deck

    # #######################################
    # Deck Specific Functions
    #
    # #######################################
    # Deck Specific Functions : Installation
    #
    def init(self):
        if not self.valid:
            logger.warning(f"deck {self.name}: is invalid")
            return
        self.set_deck_type()
        self.load_icons()
        self.load()  # will load default page if no page found
        self.start()  # Some system may need to start before we can load a page

    def get_display_for_pil(self, b: str | None = None):
        """
        Return device or device element to use for PIL.
        """
        return self.device

    def get_index_image_size(self, index):
        b = self._buttons.get(index)
        if b is not None:
            return b.get(KW.IMAGE.value)
        logger.warning(f"deck {self.name}: no button index {index}")
        return None

    def load_icons(self):
        """
        Each device model requires a different icon format (size).
        We could build a set per deck model rather than deck instance...
        """
        cache_icon = self.get_attribute("cache-icon")
        logger.info(f"deck {self.name}: use cache {cache_icon}")
        dn = self.cockpit.icon_folder
        if dn is not None:
            cache = os.path.join(dn, f"{self.name}_icon_cache.pickle")
            if os.path.exists(cache) and cache_icon:
                with open(cache, "rb") as fp:
                    icons_temp = pickle.load(fp)
                    self.icons.update(icons_temp)
                logger.info(f"deck {self.name}: {len(self.icons)} icons loaded from cache")
                return

        if self.device is not None:
            for k, v in self.cockpit.icons.items():
                self.icons[k] = self.pil_helper.create_scaled_image(self.device, v, margins=[0, 0, 0, 0])
            if dn is not None:
                cache = os.path.join(dn, f"{self.name}_icon_cache.pickle")
                if cache_icon:
                    with open(cache, "wb") as fp:
                        pickle.dump(self.icons, fp)
                    logger.info(f"deck {self.name}: {len(self.icons)} icons cached")
                else:
                    logger.info(f"deck {self.name}: {len(self.icons)} icons loaded")
        else:
            logger.warning(f"deck {self.name} has no device")

    def get_icon_background(
        self,
        name: str,
        width: int,
        height: int,
        texture_in,
        color_in,
        use_texture=True,
        who: str = "Deck",
    ):
        """
        Returns a **Pillow Image** of size width x height with either the file specified by texture or a uniform color
        """

        def get_texture():
            tarr = []
            if texture_in is not None:
                tarr.append(texture_in)
            default_icon_texture = self.get_attribute("default-icon-texture")
            if default_icon_texture is not None:
                tarr.append(default_icon_texture)
            cockpit_texture = self.get_attribute("cockpit-texture")
            if cockpit_texture is not None:
                tarr.append(cockpit_texture)

            dirs = []
            dirs.append(os.path.join(os.path.dirname(__file__), RESOURCES_FOLDER))
            dirs.append(os.path.join(os.path.dirname(__file__), RESOURCES_FOLDER, ICONS_FOLDER))
            if self.cockpit.acpath is not None:  # add to search path
                dirs.append(os.path.join(self.cockpit.acpath, CONFIG_FOLDER, RESOURCES_FOLDER))
                dirs.append(
                    os.path.join(
                        self.cockpit.acpath,
                        CONFIG_FOLDER,
                        RESOURCES_FOLDER,
                        ICONS_FOLDER,
                    )
                )

            for dn in dirs:
                for texture in tarr:
                    fn = os.path.join(dn, texture)
                    if os.path.exists(fn):
                        return fn
            return None

        def get_color():
            for t in [
                color_in,
                self.get_attribute("default-icon-color"),
                self.get_attribute("cockpit-color"),
            ]:
                if t is not None:
                    return convert_color(t)
            return convert_color(self.get_attribute("cockpit-color"))

        image = None

        texture = get_texture()
        if use_texture and texture is not None:
            texture = os.path.normpath(texture)
            if texture in self.cockpit.icons.keys():
                image = self.cockpit.icons[texture]
            else:
                image = Image.open(texture)  # @todo: what is texture file not found?
                self.cockpit.icons[texture] = image
            # logger.debug(f"{who}: texture {texture_in} in {texture}")

        if image is not None:  # found a texture as requested
            logger.debug(f"{who}: use texture {texture}")
            image = image.resize((width, height))
            return image

        if use_texture and texture is None:
            logger.debug(f"{who}: should use texture but no texture found, using uniform color")

        color = get_color()
        image = Image.new(mode="RGBA", size=(width, height), color=color)
        logger.debug(f"{who}: uniform color {color} (color_in={color_in})")
        return image

    def create_icon_for_key(self, index, colors, texture, name: str | None = None):
        # Abstact
        return None

    def scale_icon_for_key(self, index, image, name: str | None = None):
        # Abstact
        return None

    def get_image_size(self, index):
        # Abstact
        return (0, 0)

    def fill_empty(self, key, clean: bool = False):
        icon = None
        if self.current_page is not None:
            icon = self.create_icon_for_key(
                key,
                colors=convert_color(self.current_page.get_attribute("cockpit-color")),
                texture=self.current_page.get_attribute("cockpit-texture"),
                name=f"{self.name}:{self.current_page.name}:{key}",
            )
        else:
            icon = self.create_icon_for_key(
                key,
                colors=self.get_attribute("cockpit-color"),
                texture=self.get_attribute("cockpit-texture"),
                name=f"{self.name}:{key}",
            )
        if icon is not None:
            self._send_key_image_to_device(key, icon)
        else:
            logger.warning(f"deck {self.name}: {key}: no fill icon{' cleaning' if clean else ''}")

    def clean_empty(self, key):
        self.fill_empty(key, clean=True)

    # #######################################
    # Deck Specific Functions : Rendering
    #
    def _send_key_image_to_device(self, key, image):
        pass
