"""
Different button classes for different purpose.
Button base class does not perform any action, it mainly is an ABC.

Buttons do
1. Execute zero or more X-Plane command
2. Optionally update their representation to confirm the action

"""
import os
import re
import logging

from math import floor

from PIL import Image, ImageDraw, ImageFont, ImageOps
from StreamDeck.ImageHelpers import PILHelper

from .constant import add_ext, CONFIG_DIR, ICONS_FOLDER, FONTS_FOLDER, convert_color
from .rpc import RPC

logger = logging.getLogger("Button")


class Button:

    def __init__(self, config: dict, deck: "Streamdeck"):
        self.deck = deck
        self.xp = self.deck.decks.xp  # shortcut alias
        self.pressed_count = 0
        self.inited = False
        self.bounce_arr = None
        self.bounce_idx = 0

        self.name = config.get("name", f"bnt-{config['index']}")
        self.index = config.get("index")

        self.label = config.get("label")
        self.label_format = config.get("label-format")
        self.label_font = config.get("label-font", deck.default_label_font)
        self.label_size = int(config.get("label-size", deck.default_label_size))
        self.label_color = config.get("label-color", deck.default_label_color)
        self.label_color = convert_color(self.label_color)
        self.label_position = config.get("label-position", "cm")
        self.icon_color = config.get("icon-color")

        self.command = config.get("command")
        self.commands = config.get("commands")

        self.dataref = config.get("dataref")
        self.datarefs = config.get("multi-datarefs")
        self.dataref_rpn = config.get("dataref-rpn")
        self.dataref_values = dict( [ (d, None) for d in self.get_datarefs() ] )

        if len(self.dataref_values) > 1:
            logger.debug(f"__init__: button {self.name}: using datarefs {self.dataref_values.keys()}")

        old = ""
        new = config.get("options", "counter")
        while len(old) != len(new):
            old = new
            new = old.strip().replace(" =", "=").replace("= ", "=").replace(" ,", ",").replace(", ", ",")
        self.options = [a.strip() for a in new.split(",")]

        self.icon = config.get("icon")
        if self.icon is not None:
            self.icon = add_ext(self.icon, ".png")
            if self.icon not in self.deck.icons.keys():
                logger.warning(f"__init__: button {self.name}: icon not found {self.icon}")
        elif self.icon_color is not None:  # create one
            self.icon_color = convert_color(self.icon_color)
            logger.debug(f"__init__: button {self.name}: creating icon with color {self.icon_color}")
            self.default_icon_image = PILHelper.create_image(deck=self.deck.device, background=self.icon_color)
            self.default_icon = "_default_button_icon_" + self.name + ".png"
            # register it globally
            self.deck.decks.icons[self.default_icon] = self.default_icon_image
            # add it to icon for this deck too
            self.deck.icons[self.default_icon] = self.default_icon_image
            self.icon = self.default_icon
        else:
            self.icon = add_ext(deck.default_icon_name, ".png")
            if self.icon not in self.deck.icons.keys():
                logger.warning(f"__init__: button {self.name}: icon not found {self.icon}")

        self.multi_icons = config.get("multi-icons")
        if self.multi_icons is not None:
            for i in range(len(self.multi_icons)):
                self.multi_icons[i] = add_ext(self.multi_icons[i], ".png")
                if self.multi_icons[i] not in self.deck.icons.keys():
                    logger.warning(f"__init__: button {self.name}: icon not found {self.multi_icons[i]}")

        self.key_icon = self.icon  # Working icon that will be displayed, default to self.icon
                                   # If key icon should come from icons, will be selected later
        if self.label_position[0] not in "lcr" or self.label_position[1] not in "tmb":
            logger.warning(f"__init__: button {self.name}: invalid label position code {self.label_position}, using default")
            self.label_position = "cm"

        # working variables
        self.previous_value = None
        self.current_value = None

        self.init()

    @classmethod
    def new(cls, config: dict, deck: "Streamdeck"):
        return cls(config=config, deck=deck)

    def init(self):
        """
        Install button
        """
        if self.has_option("bounce") and self.multi_icons is not None and len(self.multi_icons) > 0:
            stops = self.option_value(option="stops", default=len(self.multi_icons))
            self.bounce_arr = self.make_bounce_array(stops)

    def is_valid(self) -> bool:
        """
        Validate button data once and for all
        """
        r = (self.deck is not None) and (self.index is not None)
        if not r:
            logger.warning(f"is_valid: button {self.name} is invalid")
        return r

    def has_option(self, option):
        for opt in self.options:
            opt = opt.split("=")
            name = opt[0]
            name = name.strip()
            return name == option
        return False

    def option_value(self, option, default = None):
        for opt in self.options:
            opt = opt.split("=")
            name = opt[0]
            if name == option:
                if len(opt) > 1:
                    return opt[1]
                else:  # found just the name, so it may be a boolean, True if present
                    return True
        return default

    def make_bounce_array(self, stops: int):
        if stops > 1:
            af = list(range(stops - 1))
            ab = af.copy()
            ab.reverse()
            return af + [stops-1] + ab[:-1]
        return [0]

    def get_datarefs(self):
        """
        Returns all datarefs used by this button
        """
        r = []
        if self.dataref is not None:
            r.append(self.dataref)
            # logger.debug(f"get_datarefs: button {self.name}: added single dataref {self.dataref}")
        if self.datarefs is not None:
            r = r + self.datarefs
            # logger.debug(f"get_datarefs: button {self.name}: added multiple datarefs {self.datarefs}")
        # logger.debug(f"get_datarefs: button {self.name}: {r}, {self.datarefs}")
        # Use of datarefs in label:
        if self.label is not None:
            datarefs = re.findall("\\${(.+?)}", self.label)
            if len(datarefs) > 0:
                r = r + datarefs
                # logger.debug(f"get_datarefs: button {self.name}: added label datarefs {datarefs}")
        # Use of datarefs in formulae:
        if self.dataref_rpn is not None:
            datarefs = re.findall("\\${(.+?)}", self.dataref_rpn)
            if len(datarefs) > 0:
                r = r + datarefs
                # logger.debug(f"get_datarefs: button {self.name}: added formulae datarefs {datarefs}")

        return set(r)  # removes deplicates

    def get_font(self):
        """
        Helper function to get valid font, depending on button or global preferences
        """
        fonts_available = self.deck.decks.fonts.keys()
        # 1. Tries button specific font
        if self.label_font is not None:
            if self.label_font in fonts_available:
                return self.deck.decks.fonts[self.label_font]
            else:
                logger.warning(f"get_font: button label font '{self.label_font}' not found")
        # 2. Tries deck default font
        if self.deck.default_label_font is not None and self.deck.default_label_font in fonts_available:
            logger.info(f"get_font: using deck default font '{self.deck.default_label_font}'")
            return self.deck.decks.fonts[self.deck.default_label_font]
        else:
            logger.warning(f"get_font: deck default label font '{self.label_font}' not found")
        # 3. Tries streamdecks default font
        if self.deck.decks.default_label_font is not None and self.deck.decks.default_label_font in fonts_available:
            logger.info(f"get_font: using streamdecks default font '{self.deck.decks.default_label_font}'")
            return self.deck.decks.fonts[self.deck.decks.default_label_font]
        logger.error(f"get_font: streamdecks default label font not found, tried {self.label_font}, {self.deck.default_label_font}, {self.deck.decks.default_label_font}")
        return None

    def get_label(self):
        if self.label is not None:
            if self.label.startswith("${") and self.label.endswith("}"):  # ${dataref-name}
                dataref = self.label[2:-1]
                if dataref in self.dataref_values.keys():
                    value = self.dataref_values[dataref]
                    if value is not None and self.label_format is not None:
                        label = self.label_format.format(value)
                        return label
                    else:
                        return value
                else:
                    logger.warning(f"get_label: button {self.name}: dataref in label not found")
                    return None
            else:
                return self.label
        return None

    def get_image(self):
        """
        Helper function to get button image and overlay label on top of it.
        Label may be updated at each activation.
        """
        if self.key_icon in self.deck.icons.keys():
            image = self.deck.icons[self.key_icon]
            # Add label if any
            label = self.get_label()
            if label is not None:
                fontname = self.get_font()
                if fontname is None:
                    logger.warning(f"get_image: no font, cannot overlay label")
                else:
                    # logger.debug(f"get_image: font {fontname}")
                    image = image.copy()  # we will add text over it
                    draw = ImageDraw.Draw(image)
                    font = ImageFont.truetype(fontname, self.label_size)
                    inside = round(0.04 * image.width + 0.5)
                    w = image.width / 2
                    p = "m"
                    a = "center"
                    if self.label_position[0] == "l":
                        w = inside
                        p = "l"
                        a = "left"
                    elif self.label_position[0] == "r":
                        w = image.width - inside
                        p = "r"
                        a = "right"
                    h = image.height / 2
                    if self.label_position[1] == "t":
                        h = inside + self.label_size / 2
                    elif self.label_position[1] == "r":
                        h = image.height - inside - self.label_size / 2
                    # logger.debug(f"get_image: position {(w, h)}")
                    draw.multiline_text((w, h),  # (image.width / 2, 15)
                              text=label,
                              font=font,
                              anchor=p+"m",
                              align=a,
                              fill=self.label_color)
            return image
        else:
            logger.warning(f"get_image: button {self.name}: icon {self.key_icon} not found")
            # logger.debug(f"{self.deck.icons.keys()}")
        return None

    def execute_formula(self):
        if self.dataref_rpn is not None:
            expr = self.dataref_rpn
            nice = self.dataref_rpn
            for dataref, value in self.dataref_values.items():
                expr = expr.replace(f"${{{dataref}}}", str(value) if value is not None else "0.0")
                nice = nice.replace(f"${{{dataref}}}", str(round(value, 4)) if value is not None else "0.0")
            r = RPC(expr)
            r1 = r.calculate()
            # logger.debug(f"execute_formula: button {self.name}: {dataref}: {expr} = {r1}")
            logger.debug(f"execute_formula: button {self.name}: {self.dataref_rpn} => {nice}:  => {r1}")
            return r1
        return value

    def button_value(self):
        """
        Button ultimately returns one value that is either directly extracted from a single dataref,
        or computed from several dataref values (later).
        """
        # 1. Unique dataref
        if self.dataref is not None and self.dataref in self.dataref_values.keys() and len(self.dataref_values.keys()) == 1:
            if self.dataref_rpn is None:
                return self.dataref_values[self.dataref]
            else:
                return self.execute_formula()
        # 2. Multiple datarefs
        elif len(self.dataref_values.keys()) > 1:
            return self.execute_formula()
        elif "counter" in self.options or "bounce" in self.options:
            # logger.debug(f"get_image: button {self.name} get cycle icon")
            return self.pressed_count
        return None

    def dataref_changed(self, dataref, value):
        """
        One of its dataref has changed, records its value and provoke an update of its representation.
        """
        if dataref in self.dataref_values:
            if self.dataref_values[dataref] != value:
                self.dataref_values[dataref] = value
        else:
            logger.warning(f"dataref_changed: {dataref} not registered")
            self.dataref_values[dataref] = value

        self.previous_value = self.current_value
        self.current_value = self.button_value()

        self.render()

    def activate(self, state: bool):
        """
        Function that is executed when a button is pressed (state=True) or released (state=False) on the Stream Deck device
        """
        if state:
            self.pressed_count = self.pressed_count + 1
        # logger.debug(f"activate: button {self.name} activated ({state}, {self.pressed_count})")

    def render(self):
        if self.deck is not None:
            self.deck.set_key_image(self)
        # logger.debug(f"render: button {self.name} rendered")


class ButtonPage(Button):
    """
    When pressed, activation change to selected page.
    If new page is not found, issues a warning and remain on current page.
    """
    def __init__(self, config: dict, deck: "Streamdeck"):
        Button.__init__(self, config=config, deck=deck)
        if self.name is None:
            logger.error(f"__init__: page button has no name")
        # We cannot change page validity because target page might not already be loaded.

    def is_valid(self):
        return super().is_valid() and self.name is not None and self.name in self.deck.pages.keys()

    def activate(self, state: bool):
        super().activate(state)
        if state:
            if self.name in self.deck.pages.keys():
                logger.debug(f"activate: button {self.name} change page to {self.name}")
                self.deck.change_page(self.name)
                self.previous_value = self.current_value
                self.current_value = self.name
            else:
                logger.warning(f"activate: button {self.name}: page not found {self.name}")


class ButtonReload(Button):
    """
    Execute command while the key is pressed.
    Pressing starts the command, releasing stops it.
    """

    def __init__(self, config: dict, deck: "Streamdeck"):
        Button.__init__(self, config=config, deck=deck)

    def is_valid(self):
        return super().is_valid()

    def activate(self, state: bool):
        if state:
            if self.is_valid():
                self.deck.decks.reload_decks()


# ###########################@
#
#
class ButtonPush(Button):
    """
    Execute command once when key pressed
    """
    def __init__(self, config: dict, deck: "Streamdeck"):
        Button.__init__(self, config=config, deck=deck)

    def is_valid(self):
        return super().is_valid() and ((self.command is not None) or self.has_option("counter"))

    def get_image(self):
        """
        If button has more icons, select one from button current value
        """
        if self.multi_icons is not None and len(self.multi_icons) > 1:
            num_icons = len(self.multi_icons)
            value = self.current_value
            if value is None:
                logger.debug(f"get_image: button {self.name}: current value is null, default to 0")
                value = 0
            else:
                value = int(value)
            # logger.debug(f"get_image: button {self.name}: value={value}")
            if "counter" in self.options and num_icons > 0:  # modulo: 0-1-2-0-1-2...
                value = value % num_icons

            elif "bounce" in self.options and num_icons > 0:  # "bounce": 0-1-2-1-0-1-2-1-0-1-2-1-0
                value = self.bounce_arr[value % len(self.bounce_arr)]

            if value < 0 or value >= num_icons:
                logger.debug(f"get_image: button {self.name} invalid icon key {value} not in [0,{len(self.multi_icons)}], default to 0")
                value = 0

            self.key_icon = self.multi_icons[value]
        else:
            self.key_icon = self.icon
        return super().get_image()

    def activate(self, state: bool):
        super().activate(state)
        if state:
            if self.is_valid():
                if self.command is not None:
                    self.xp.commandOnce(self.command)
                self.render()


class ButtonDual(Button):
    """
    Execute command while the key is pressed.
    Pressing starts the command, releasing stops it.
    """

    def __init__(self, config: dict, deck: "Streamdeck"):
        Button.__init__(self, config=config, deck=deck)

    def is_valid(self):
        return super().is_valid() and (self.commands is not None) and (len(self.commands) > 1)

    def activate(self, state: bool):
        if state:
            if self.is_valid():
                self.xp.commandBegin(self.commands[0])
        else:
            if self.is_valid():
                self.xp.commandEnd(self.commands[1])
        self.render()

# ###########################@
#
class ButtonUpDown(ButtonPush):


    def __init__(self, config: dict, deck: "Streamdeck"):
        ButtonPush.__init__(self, config=config, deck=deck)
        self.stops = self.option_value("stops", len(self.multi_icons))
        self.bounce_arr = self.make_bounce_array(self.stops)
        self.start_value = 0

    def is_valid(self):
        return (self.commands is not None) and (len(self.commands) > 1)

    def activate(self, state: bool):
        super().activate(state)
        # if self.start_value is None:
        #     if self.current_value is not None:
        #         self.start_value = int(self.current_value)
        #     else:
        #         self.start_value = 0
        if state:
            value = self.bounce_arr[(self.start_value + self.pressed_count) % len(self.bounce_arr)]
            print(f">>>>>>>>>>  counter={self.start_value + self.pressed_count} = start={self.start_value} + press={self.pressed_count} curr={self.current_value} last={self.bounce_idx} value={value} arr={self.bounce_arr} dir={value > self.bounce_idx}")
            if self.is_valid():
                if value > self.bounce_idx:
                    self.xp.commandOnce(self.commands[0])  # up
                else:
                    self.xp.commandOnce(self.commands[1])  # down
                self.bounce_idx = value
            else:
                logger.warning(f"activate: button {self.name}: invalid {self.commands}")
        self.render()


# ###########################@
# Mapping butween button types and classes
#
BUTTON_TYPES = {
    "none": Button,
    "page": ButtonPage,
    "push": ButtonPush,
    "dual": ButtonDual,
    "updown": ButtonUpDown,
    "animate": None,  # loaded from xplaneudp/xplanesdk depending on integration
    "reload": ButtonReload
}
