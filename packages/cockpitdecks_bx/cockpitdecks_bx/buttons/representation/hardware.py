"""
Special represenations for web decks, to draw a "hardware" button
"""

import logging
import math

from PIL import Image, ImageDraw

from cockpitdecks.buttons.representation.hardware import VirtualLED, VirtualEncoder, NO_ICON
from XTouchMini.Devices.xtouchmini import LED_MODE

logger = logging.getLogger(__name__)
# logger.setLevel(logging.DEBUG)

NO_ICON = "no-icon"


class VirtualXTMLED(VirtualLED):
    """Uniform color or texture icon, arbitrary size

    Attributes:
        REPRESENTATION_NAME: "virtual-xtm-led"
    """

    REPRESENTATION_NAME = "virtual-xtm-led"

    def __init__(self, button: "Button"):
        VirtualLED.__init__(self, button=button)

        self.color = self.hardware.get("color", (207, 229, 149))
        self.off_color = self.hardware.get("off-color", (150, 150, 150))

    def describe(self) -> str:
        return "The representation places a uniform color icon for X-Touch Mini buttons."


class VirtualXTMMCLED(VirtualLED):
    """Uniform color or texture icon, arbitrary size

    Attributes:
        REPRESENTATION_NAME: "virtual-xtm-mcled"
    """

    REPRESENTATION_NAME = "virtual-xtm-mcled"

    def __init__(self, button: "Button"):
        VirtualLED.__init__(self, button=button)

        self.color = self.hardware.get("color", "gold")
        self.off_color = self.hardware.get("off-color", (30, 30, 30))

    def describe(self) -> str:
        return "The representation places a specific Mackie Mode led for X-Touch Mini encoders."


class VirtualXTMEncoderLED(VirtualEncoder):
    """Uniform color or texture icon, no square!

    Attributes:
        REPRESENTATION_NAME: "virtual-xtm-encoderled"
    """

    REPRESENTATION_NAME = "virtual-xtm-encoderled"

    def __init__(self, button: "Button"):
        VirtualEncoder.__init__(self, button=button)

        self.width = 2 * self.radius  # final dimension, 2 x radius of circle
        self.height = self.width  # force final image to be a square icon with. circle in it

        self.ltot = int(self.ICON_SIZE / 2)  # button will be created in self.ICON_SIZE x self.ICON_SIZE
        self.lext = 120
        self.lint = 84
        self.lstart = -130  # angles
        self.lend = -self.lstart
        self.lwidth = 12  # led
        self.lheight = 20
        self.rounded_corder = int(self.lwidth / 2)

        self.color = self.hardware.get("color", "gold")
        self.off_color = self.hardware.get("off-color", (30, 30, 30))

        self.led_count = 13
        self.mackie = True  # cannot change it for xtouchmini package (does not work otherwise)

    def is_on(self, led, value, mode) -> bool:
        # class LED_MODE(Enum):
        #     SINGLE = 0
        #     TRIM = 1
        #     FAN = 2
        #     SPREAD = 3
        led_count1 = self.led_count - 1
        led_limit = led_count1 - 1 if self.mackie else led_count1  # last led to turn on

        if self.mackie and led in [0, led_count1]:  # LED 0 and 12 never used in Mackie mode...
            return False

        if value <= 0:
            return False

        if value > led_limit:
            value = led_limit

        if mode == LED_MODE.SINGLE:
            return led == value
        if mode == LED_MODE.FAN:
            return led <= value
        middle = math.floor(self.led_count / 2)
        if mode == LED_MODE.SPREAD:
            if value > middle:
                value = middle
            value = value - 1
            return middle - value <= led <= middle + value
        # LED_MODE.TRIM
        if led <= middle:
            return value <= led <= middle
        return middle <= led <= value

    def get_image(self):
        value, mode = self.button.get_representation()
        center = (self.ltot, self.ltot)

        tl = (self.ltot - self.lwidth / 2, self.ltot - self.lext)
        br = (self.ltot + self.lwidth / 2, self.ltot - self.lint)
        image = Image.new(mode="RGBA", size=(self.ICON_SIZE, self.ICON_SIZE), color=self.TRANSPARENT_PNG_COLOR)

        # Add surrounding leds
        image_on = Image.new(mode="RGBA", size=(self.ICON_SIZE, self.ICON_SIZE), color=self.TRANSPARENT_PNG_COLOR)
        one_mark_on = ImageDraw.Draw(image_on)
        one_mark_on.rounded_rectangle(tl + br, radius=self.rounded_corder, fill=self.color, outline=self.off_color, width=1)

        # Add bleed
        # s = 2
        # tl = [x-s for x in tl]
        # br = [x+s for x in br]
        image_off = Image.new(mode="RGBA", size=(self.ICON_SIZE, self.ICON_SIZE), color=self.TRANSPARENT_PNG_COLOR)
        one_mark_off = ImageDraw.Draw(image_off)
        one_mark_off.rounded_rectangle(tl + br, radius=self.rounded_corder, fill=self.off_color, outline=self.off_color, width=1)

        step_angle = (self.lend - self.lstart) / (self.led_count - 1)
        angle = self.lend
        for i in range(self.led_count):
            this_led = image_on.copy() if self.is_on(led=i, value=value, mode=mode) else image_off.copy()
            this_led = this_led.rotate(angle, center=center)
            angle = angle - step_angle
            image.alpha_composite(this_led)

        # Resize
        image = image.resize((self.width, self.height))
        # paste encoder in middle
        self.radius = 27
        encoder = super().get_image()  # paste in center
        image.alpha_composite(encoder, (int(image.width / 2 - encoder.width / 2), int(image.height / 2 - encoder.height / 2)))
        return image

    def describe(self) -> str:
        return "The representation places a uniform color icon for X-Touch Mini Mackie mode."
