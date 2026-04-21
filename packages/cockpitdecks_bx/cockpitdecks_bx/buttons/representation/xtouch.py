"""
Button display and rendering abstraction.
All representations are listed at the end of this file.
"""

import logging

from XTouchMini.Devices.xtouchmini import LED_MODE

from cockpitdecks.resources.color import is_integer
from cockpitdecks import DECK_FEEDBACK
from cockpitdecks.buttons.representation import Representation

logger = logging.getLogger(__name__)
# logger.setLevel(logging.DEBUG)


class EncoderLEDs(Representation):
    """
    Ring of 13 LEDs surrounding X-Touch Mini encoders
    """

    REPRESENTATION_NAME = "encoder-leds"
    REQUIRED_DECK_FEEDBACKS = DECK_FEEDBACK.ENCODER_LEDS

    SCHEMA = {
        "encoder-leds": {"type": "integer", "meta": {"label": "Encoding Mode"}},
    }

    def __init__(self, button: "Button"):
        Representation.__init__(self, button=button)

        mode = self._config.get("encoder-leds", LED_MODE.SINGLE.name)

        self.mode = LED_MODE.SINGLE
        if is_integer(mode) and int(mode) in [l.value for l in LED_MODE]:
            self.mode = LED_MODE(mode)
        elif type(mode) is str and mode.upper() in [l.name for l in LED_MODE]:
            mode = mode.upper()
            self.mode = LED_MODE[mode]
        else:
            logger.warning(f"{type(self).__name__}: invalid mode {mode}")

    def is_valid(self):
        maxval = 7 if self.mode == LED_MODE.SPREAD else 11
        value = self.get_rescaled_value(range_min=0, range_max=maxval, steps=maxval)
        if value is None:
            value = 0
        if value >= maxval:
            logger.warning(f"button {self.button_name}: {type(self).__name__}: value {value} too large for mode {self.mode}")
        return super().is_valid()

    def render(self):
        maxval = 7 if self.mode == LED_MODE.SPREAD else 11
        value = self.get_rescaled_value(range_min=0, range_max=maxval, steps=maxval)
        logger.debug(f"rescaled {self.button_name}: {self.get_button_value()} -> {value}")
        if value is None:
            value = 0
        v = min(int(value), maxval)
        return (v, self.mode)

    def clean(self):
        old_value = self.button.value
        self.button.value = 0
        self.button.render()
        self.button.value = old_value

    def describe(self) -> str:
        """
        Describe what the button does in plain English
        """
        a = ["The representation turns multiple LED ON or OFF around X-Touch Mini encoders"]
        return "\n\r".join(a)
