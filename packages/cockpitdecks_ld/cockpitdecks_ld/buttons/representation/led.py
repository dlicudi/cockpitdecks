"""
Representation for ColoredLED.
"""

import logging
import colorsys

from cockpitdecks.resources.color import convert_color
from cockpitdecks import CONFIG_KW, DECK_FEEDBACK
from cockpitdecks.buttons.representation import Representation

logger = logging.getLogger(__name__)
# logger.setLevel(logging.DEBUG)


class ColoredLED(Representation):

    REPRESENTATION_NAME = "colored-led"
    REQUIRED_DECK_FEEDBACKS = DECK_FEEDBACK.COLORED_LED

    SCHEMA = {"color": {"type": "color", "meta": {"label": "Color"}}}

    def __init__(self, button: "Button"):
        self._color = button._config.get("color", button.get_attribute("cockpit-color"))
        self.color = (128, 128, 256)
        Representation.__init__(self, button=button)
        self.off_color = self.get_attribute("off-color", default=(0, 0, 0))

    def init(self):
        if type(self._color) is dict:  # @todo: does not currently work
            self.datarefs = self.button.scan_datarefs(self._color)
            if self.datarefs is not None and len(self.datarefs) > 0:
                logger.debug(f"button {self.button_name}: adding datarefs {self.datarefs} for color")
        else:
            self.color = convert_color(self._color)

    def get_color(self, base: dict | None = None):
        """
        Compute color from formula/datarefs if any.
        Static colored-led buttons should stay lit with their configured color.
        """
        if base is None:
            base = self._config
        color_str = base.get("color")
        if color_str is None:
            return self.color

        # Formula in text
        KW_FORMULA_STR = f"${{{CONFIG_KW.FORMULA.value}}}"  # "${formula}"
        hue = 0  # red
        if KW_FORMULA_STR in str(color_str):
            formula = base.get(CONFIG_KW.FORMULA.value)
            if formula is not None:
                hue = self.button.execute_formula(formula=formula)
        else:
            try:
                hue = int(color_str)
            except (ValueError, TypeError):
                return convert_color(color_str)

        color_rgb = colorsys.hsv_to_rgb((int(hue) % 360) / 360, 1, 1)
        self.color = tuple([int(255 * i) for i in color_rgb])  # type: ignore
        logger.debug(f"{color_str}, {hue}, {[(int(hue) % 360)/360,1,1]}, {color_rgb}, {self.color}")

        return self.color

    def render(self):
        color = self.get_color()
        logger.debug(f"{type(self).__name__}: {color}")
        return color

    def clean(self):
        logger.debug(f"{type(self).__name__}")
        old_value = self.button.value
        self.button.value = 0  # switch it off for the clean display
        self.button.render()
        self.button.value = old_value

    def describe(self) -> str:
        """
        Describe what the button does in plain English
        """
        a = [f"The representation turns ON or OFF a single LED light and changes the color of the LED."]
        return "\n\r".join(a)
