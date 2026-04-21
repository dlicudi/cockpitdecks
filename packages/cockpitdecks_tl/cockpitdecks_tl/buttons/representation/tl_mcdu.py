import logging

from cockpitdecks.buttons.representation.hardware import HardwareRepresentation

from .mcdu import MCDU

logger = logging.getLogger(__file__)
# logger.setLevel(logging.DEBUG)
# logger.setLevel(15)


class MCDUScreen(HardwareRepresentation):
    """Displays Toliss Airbus MCDU screen on web deck"""

    REPRESENTATION_NAME = "mcdu"

    SCHEMA = HardwareRepresentation.SCHEMA | {"unit": {"type": "integer"}}

    def __init__(self, button: "Button"):
        self._inited = False
        self.sizes = button._definition.display_size() if button._definition is not None else [500, 400]
        self.inside = None
        self.font = None
        self.fontsm = None
        self.altfont = None
        self.altfontsm = None
        self.side_margin = None
        self.linebases = []

        HardwareRepresentation.__init__(self, button=button)

        self.mcduconfig = button._config.get("mcdu", {})  # should not be none, empty at most...
        self.mcdu_unit = self.mcduconfig.get("unit", 1)
        self._datarefs = None
        self.mcdu = MCDU()
        self.mcdu.init(simulator=button.sim)

    def init(self):
        super().init()

        self.inside = round(0.04 * self.sizes[1] + 0.5)

        # 520x400
        self.font_lg = 19
        self.font_sm = 18
        spc_il = 2  # space between label and content line
        spc_bl = 3  # space between 2 pairs of (label, content)
        block = spc_bl + self.font_lg + spc_il + self.font_sm
        linebases = [self.font_lg]  # title
        for i in range(6):
            linebases.append(linebases[0] + spc_bl + self.font_sm + i * block)  # label
            linebases.append(linebases[1] + spc_il + self.font_lg + i * block)  # content
        linebases.append(linebases[-1] + spc_bl + self.font_lg)  # scratchpad
        self.linebases = linebases

        self.side_margin = int(self.sizes[0] * 0.02)
        self.xd = int((self.sizes[0] - (2 * self.side_margin)) / 24)  # 24 chars per line

        # Draw
        self.font = self.get_font("HoneywellMCDU.ttf", self.font_lg)
        self.fontsm = self.get_font("HoneywellMCDUSmall.ttf", self.font_sm)
        # alternate font for special character, not present in above (arrows, brackets, etc.)
        self.altfont = self.get_font("D-DIN.otf", self.font_lg)
        self.altfontsm = self.get_font("D-DIN.otf", self.font_sm)

        self._inited = True

    def describe(self) -> str:
        return "The representation is specific to Toliss Airbus and display the MCDU screen."

    def get_variables(self) -> set:
        return self.mcdu.get_variables()

    def is_updated(self) -> bool:
        return True

    def get_image_for_icon(self):
        """ """
        image, draw = self.double_icon(width=self.sizes[0], height=self.sizes[1])

        if not self.mcdu.draw_text(
            mcdu_unit=self.mcdu_unit,
            draw=draw,
            fonts=[self.fontsm, self.font, self.altfontsm, self.altfont],
            left_offset=self.side_margin + self.xd,  # int(self.xd / 2),
            char_delta=self.xd,
            line_bases=self.linebases,
            font_sizes=[self.font_lg, self.font_sm],
        ):
            draw.text(
                (int(image.width / 2), self.inside + int(image.height / 4)),
                text="WAITING FOR DATA",
                font=self.fontsm,
                anchor="ms",
                align="center",
                fill="#FD8008",
            )

        # Paste image on cockpit background and return it.
        bg = self.button.deck.get_icon_background(
            name=self.button_name,
            width=image.width,
            height=image.height,
            texture_in=None,
            color_in="black",
            use_texture=False,
            who="MCDU",
        )
        bg.alpha_composite(image)
        return bg
