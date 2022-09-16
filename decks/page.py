import logging

from .constant import convert_color
from .button import Button

logger = logging.getLogger("Page")


class Page:
    """
    A Page is a collection of buttons.
    """

    def __init__(self, name: str, deck: "Streamdeck"):
        self.name = name
        self.deck = deck
        self.xp = self.deck.decks.xp  # shortcut alias

        self.fill_empty = None

        self.buttons = {}
        self.datarefs = {}


    def add_button(self, idx: int, button: Button):
        if idx in self.buttons.keys():
            logger.error(f"add_button: button index {idx} already defined, ignoring {button.name}")
            return
        self.buttons[idx] = button
        # Build page dataref list, each dataref points at the button(s) that use it
        # logger.debug(f"add_button: page {self.name}: button {button.name}: datarefs: {button.dataref_values.keys()}")

        for d in button.get_datarefs():
            if d not in self.datarefs:
                ref = self.xp.get_dataref(d)
                if ref is not None:
                    self.datarefs[d] = ref
                    self.datarefs[d].add_listener(button)
                else:
                    logger.warning(f"add_button: page {self.name}: button {button.name}: failed to create dataref {d}")
        logger.debug(f"add_button: page {self.name}: button {button.name} {idx} added")

    def dataref_changed(self, dataref):
        """
        For each button on this page, notifies the button if a dataref used by that button has changed.
        """
        if dataref.path in self.datarefs.keys():
            self.datarefs[dataref].notify()
        else:
            logger.warning(f"dataref_changed: page {self.name}: dataref {dataref.path} not found")

    def activate(self, idx: int):
        if idx in self.buttons.keys():
            self.buttons[idx].activate()
        else:
            logger.error(f"activate: page {self.name}: invalid button index {idx}")

    def render(self):
        """
        Renders this page on the deck
        """
        logger.debug(f"render: page {self.name}: fill {self.fill_empty}")
        for button in self.buttons.values():
            button.render()
            # logger.debug(f"render: page {self.name}: button {button.name} rendered")
        if self.fill_empty is not None:
            icon = None
            if self.fill_empty.startswith("(") and self.fill_empty.endswith(")"):
                colors = convert_color(self.fill_empty)
                icon = self.deck.pil_helper.create_image(deck=self.deck.device, background=colors)
            elif self.fill_empty in self.deck.icons.keys():
                icon = self.deck.icons[self.fill_empty]
            if icon is not None:
                image = self.deck.pil_helper.to_native_format(self.deck.device, icon)
                for i in range(self.deck.device.key_count()):
                    if i not in self.buttons.keys():
                        self.deck.device.set_key_image(i, image)
            else:
                logger.warning(f"render: page {self.name}: fill image {self.fill_empty} not found")

    def clean(self):
        """
        Ask each button to stop rendering and clean its mess.
        """
        for button in self.buttons.values():
            button.clean()