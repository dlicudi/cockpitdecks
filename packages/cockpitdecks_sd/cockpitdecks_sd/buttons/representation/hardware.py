"""
Special represenations for web decks, to draw a "hardware" button
"""

import logging

from cockpitdecks.buttons.representation.hardware import VirtualLED

logger = logging.getLogger(__name__)
# logger.setLevel(logging.DEBUG)


class VirtualSDNeoLED(VirtualLED):
    """Uniform color or texture icon, arbitrary size

    Attributes:
        REPRESENTATION_NAME: "virtual-xtm-mcled"
    """

    REPRESENTATION_NAME = "virtual-sd-neoled"

    SCHEMA = {
        "color": {"type": "color", "meta": {"label": "Color"}},
    }

    def __init__(self, button: "Button"):
        VirtualLED.__init__(self, button=button)

        self.color = self._representation_config.get("color", "lime")  # Led can change color...
        self.off_color = self.hardware.get("off-color", "silver")

    def describe(self) -> str:
        return "The representation places a specific led for Stream Deck Neo."
