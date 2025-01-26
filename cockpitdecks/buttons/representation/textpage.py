# ###########################
# Abstract Base Representation for weather icons.
# The ABC offerts basic update structures, just need
#  - A Weather data feed
#  - get_image_for_icon() to provide an iconic representation of the weather provided as above.
#
from __future__ import annotations
import logging
from functools import reduce
from textwrap import wrap
from math import ceil

from PIL import Image, ImageDraw

from cockpitdecks import ICON_SIZE
from cockpitdecks.resources.color import light_off, TRANSPARENT_PNG_COLOR
from cockpitdecks.buttons.representation.draw import DrawBase

logger = logging.getLogger(__name__)
# logger.setLevel(SPAM_LEVEL)
# logger.setLevel(logging.DEBUG)


class TextPageIcon(DrawBase):
    """Display text in pages, pressing icon flip pages
    """

    REPRESENTATION_NAME = "textpage"

    PARAMETERS = {
        "textpages": {"type": "string", "prompt": "Text pages"},
    }

    def __init__(self, button: "Button"):
        DrawBase.__init__(self, button=button)
        self.text = self._representation_config.get("text")
        self.width = self._representation_config.get("width", 20)
        self.lines = self._representation_config.get("lines", 7)
        self.pagenum = self._representation_config.get("page-number", True)

    # #############################################
    # Cockpitdecks Representation interface
    #
    def updated(self) -> bool:
        return self.button.has_changed()  # to cycle pages

    def get_lines(self, page: int = 0) -> list | None:
        text = self.text.split(".")
        all_lines = reduce(lambda x, t: x + wrap(t, width=self.width), text, [])
        npages = ceil(len(all_lines) / self.lines)
        l = (page % npages) * self.lines
        if self.pagenum:
            return [f"Page {1 + (page % npages)} / {npages}"] + all_lines[l:l+self.lines]
        else:
            return all_lines[l:l+self.lines]

    def get_image_for_icon(self):
        """
        Helper function to get button image and overlay label on top of it.
        Label may be updated at each activation since it can contain datarefs.
        Also add a little marker on placeholder/invalid buttons that will do nothing.
        """
        if not self.updated() and self._cached is not None:
            return self._cached

        # Generic display text in small font on icon
        image = Image.new(mode="RGBA", size=(ICON_SIZE, ICON_SIZE), color=TRANSPARENT_PNG_COLOR)  # annunciator text and leds , color=(0, 0, 0, 0)
        draw = ImageDraw.Draw(image)
        inside = round(0.04 * image.width + 0.5)

        page = self.button.value
        page = 0 if page is None else int(page)
        lines = self.get_lines(page=page)

        if lines is not None:
            text, text_format, text_font, text_color, text_size, text_position = self.get_text_detail(self._representation_config, "text")
            if text_font is None:
                text_font = self.label_font
            if text_size is None:
                text_size = int(image.width / 10)
            if text_color is None:
                text_color = self.label_color
            font = self.get_font(text_font, text_size)
            w = inside
            p = "l"
            a = "left"
            h = image.height / 3
            il = text_size
            for line in lines:
                draw.text(
                    (w, h),
                    text=line.strip(),
                    font=font,
                    anchor=p + "m",
                    align=a,
                    fill=text_color,
                )
                h = h + il
        else:
            logger.warning("no weather information")

        # Paste image on cockpit background and return it.
        bg = self.button.deck.get_icon_background(
            name=self.button_name(),
            width=ICON_SIZE,
            height=ICON_SIZE,
            texture_in=self.cockpit_texture,
            color_in=self.cockpit_color,
            use_texture=True,
            who="Weather",
        )
        bg.alpha_composite(image)
        self._cached = bg
        return self._cached
