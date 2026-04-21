import logging

from cockpitdecks.resources.iconfonts import get_special_character
from cockpitdecks.buttons.representation.hardware import HardwareRepresentation

from .draims import DRAIMS

logger = logging.getLogger(__file__)
# logger.setLevel(logging.DEBUG)
# logger.setLevel(15)


class DRAIMSScreen(HardwareRepresentation):
    """Displays Toliss Airbus DRAIMS screen on web deck"""

    REPRESENTATION_NAME = "draims"

    SCHEMA = HardwareRepresentation.SCHEMA | {"unit": {"type": "integer"}}

    def __init__(self, button: "Button"):
        self._inited = False
        self.sizes = button._definition.display_size() if button._definition is not None else [500, 400]
        self.inside = None
        self.font = None
        self.fontlg = None
        self.fontsm = None
        self.interline = None
        self.side_margin = None
        self.line_offsets = None

        HardwareRepresentation.__init__(self, button=button)

        self.draimsconfig = button._config.get("draims", {})  # should not be none, empty at most...
        self.draims_unit = self.draimsconfig.get("unit", 1)
        self._datarefs = None
        self.draims = DRAIMS()
        self.draims.init(simulator=button.sim)

    def init(self):
        super().init()

        self.inside = round(0.04 * self.sizes[1] + 0.5)

        self.font_nr = int(self.sizes[1] / 12)
        self.font_lg = int(self.sizes[1] / 8)
        self.font_sm = int(self.sizes[1] / 20)
        fontname = "Roboto-Regular.ttf"
        self.font = self.get_font(fontname, self.font_nr)
        self.fontlg = self.get_font(fontname, self.font_lg)
        self.fontsm = self.get_font(fontname, self.font_sm)

        # 450x277: [28, -7, 17, 398]
        #
        self.line_offsets = [
            self.font_lg + 2,
            -int(self.font_sm / 3),
            self.font_lg - int(self.font_sm / 3),
            self.sizes[1] - 2,
        ]  # baseline for title, 6 x (small, large), scratchpad

        self.side_margin = int(self.sizes[0] * 0.02)
        self.xd = int((self.sizes[0] - (2 * self.side_margin)) / 24)  # 24 chars per line

        # Draw
        self._inited = True

        # print(">>>", self.sizes, self.inside, self.side_margin, self.xd, self.font_lg, self.font_sm, self.interline, self.line_offsets)

    def describe(self) -> str:
        return "The representation is specific to Toliss Airbus and display the DRAIMS screen."

    def get_variables(self) -> set:
        return self.draims.get_variables()

    def is_updated(self) -> bool:
        return True

    def get_image_for_icon(self):
        """ """
        image, draw = self.double_icon(width=self.sizes[0], height=self.sizes[1])
        self.inside = round(0.04 * self.sizes[1] + 0.5)
        i2 = int(self.inside / 2)

        def draw_lines(add_split: bool):
            # draw horizontal and vertical spit bars
            d = int(image.height / 4)
            for i in range(1, 4):
                draw.line(((i2, i * d), (image.width - i2, i * d)), fill="white", width=2)
            d = 3 * d
            p = [18, 44, 57]
            for i in range(3):
                s = int(p[i] * image.width / 80)
                if i > 0 and add_split:
                    draw.line(((s, d), (s, self.height - self.inside)), fill="white", width=2)

        page = "vhf"

        # draw.rectangle(((0,0), (image.width-1, image.height-1)), outline="cyan", width=1)
        if page != "menu":
            draw_lines(add_split=page != "nav")

        # development

        if page == "vhf":
            self.page_vhf(image, draw)
        elif page == "hf":
            self.page_hf(image, draw)
        elif page == "tel":
            self.page_tel(image, draw)
        elif page == "atc":
            self.page_atc(image, draw)
        elif page == "menu":
            self.page_menu(image, draw)
        elif page == "nav":
            self.page_nav(image, draw)

        # Paste image on cockpit background and return it.
        bg = self.button.deck.get_icon_background(
            name=self.button_name,
            width=image.width,
            height=image.height,
            texture_in=None,
            color_in="black",
            use_texture=False,
            who="DRAIMS",
        )
        bg.alpha_composite(image)
        return bg

    def draw_icon(self, draw, name: str, x: int, y: int, size: int, color: str = "white"):
        if not name.startswith("fa:"):
            name = "fa:" + name
        icon_font_name, icon_text = get_special_character(name)
        icon_font = self.get_font(icon_font_name, size)
        draw.text(
            (x, y),
            text=icon_text,
            font=icon_font,
            anchor="ms",
            align="center",
            fill=color,
        )

    def page_vhf(self, image, draw):
        i2 = int(self.inside / 2)
        boxw = 0  # computed later
        boxh = int(0.20 * image.height)

        # Active
        ybase = [0, int(image.height / 4), int(image.height / 2), int(3 * image.height / 4)]
        for currbox in range(1, 4):
            ox = int(0.2 * image.width)
            oy = ybase[currbox] - self.font_lg
            draw.text(
                (ox, oy),
                text="119.500",  # self.draims.datarefs.get(f"AirbusFBW/RMP{currbox}StbyFreq")
                font=self.fontlg,
                anchor="ms",
                align="center",
                fill="white",
            )

        # Middle labels
        sound_on = True
        sound_off = True
        ybase = [0, int(image.height / 4), int(image.height / 2), int(3 * image.height / 4)]
        for currbox in range(1, 4):
            ox = int(0.5 * image.width)
            oy = ybase[currbox - 1] + boxh - self.font_nr
            draw.text(
                (ox, oy),
                text=f"VHF{currbox}",  # self.draims.datarefs.get(f"AirbusFBW/RMP{currbox}StbyFreq")
                font=self.font,
                anchor="ms",
                align="center",
                fill="white",
            )
            if currbox < 3:
                if sound_on:
                    self.draw_icon(draw, "volume-off", ox, ybase[currbox] - i2, self.font_nr)
                    if sound_off:
                        self.draw_icon(draw, "xmark", ox, ybase[currbox] - 2, self.font_lg, "red")

        # Stand-by
        # Focus box, can move in Y
        focus = 1
        for currbox in range(1, 4):
            if currbox == focus:
                ox = int(0.650 * image.width)
                oy = ybase[currbox - 1] + i2
                boxw = image.width - self.inside - ox
                draw.rectangle(((ox, oy), (ox + boxw, oy + boxh)), outline="cyan", width=1)

                ox = int(0.650 * image.width) + int(boxw / 2)
                oy = ybase[currbox - 1] + boxh
                draw.text(
                    (ox, oy),
                    text="STBY",
                    font=self.fontsm,
                    anchor="ms",
                    align="center",
                    fill="white",
                )

            ox = int(0.650 * image.width) + int(boxw / 2)
            oy = ybase[currbox - 1] + boxh - self.font_nr
            if currbox < 3:
                draw.text(
                    (ox, oy),
                    text="118.030",  # self.draims.datarefs.get(f"AirbusFBW/RMP{currbox}StbyFreq")
                    font=self.font,
                    anchor="ms",
                    align="center",
                    fill="white",
                )
            else:
                draw.text(
                    (ox, oy),
                    text="DATA",  # self.draims.datarefs.get(f"AirbusFBW/RMP{currbox}StbyFreq")
                    font=self.font,
                    anchor="ms",
                    align="center",
                    fill="white",
                )

            ox = int(9 * image.width / 80)
            oy = int(image.height - 2 * self.inside)
            draw.text(
                (ox, oy - self.font_nr),
                text="STBY",  # self.draims.datarefs.get(f"AirbusFBW/RMP{currbox}StbyFreq")
                font=self.fontsm,
                anchor="ms",
                align="center",
                fill="white",
            )
            draw.text(
                (ox, oy),
                text="2000",  # self.draims.datarefs.get(f"AirbusFBW/RMP{currbox}StbyFreq")
                font=self.font,
                anchor="ms",
                align="center",
                fill="cyan",
            )
            ox = int(60 * image.width / 80)
            oy = image.height - self.inside
            # "↑↓"
            # self.draw_icon(draw, "arrow-up", ox, oy - self.font_lg, self.font_nr)
            arrow_font = self.get_font("B612-Bold.otf", self.font_lg)
            draw.text(
                (ox, oy - self.font_lg + int(self.inside / 2)),
                text="↑",  # self.draims.datarefs.get(f"AirbusFBW/RMP{currbox}StbyFreq")
                font=arrow_font,
                anchor="ms",
                align="center",
                fill="white",
            )
            # self.draw_icon(draw, "arrow-down", ox, oy, self.font_nr)
            draw.text(
                (ox, oy),
                text="↓",  # self.draims.datarefs.get(f"AirbusFBW/RMP{currbox}StbyFreq")
                font=arrow_font,
                anchor="ms",
                align="center",
                fill="white",
            )
