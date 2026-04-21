import logging
import re

from typing import Dict, Set

from cockpitdecks.buttons.representation.draw import DrawBase, ICON_SIZE
from cockpitdecks.strvar import TextWithVariables

# ##############################
# Toliss Airbus FMA display
FMA_DATAREFS = {
    "1w": "AirbusFBW/FMA1w",
    "1g": "AirbusFBW/FMA1g",
    "1b": "AirbusFBW/FMA1b",
    "2w": "AirbusFBW/FMA2w",
    "2b": "AirbusFBW/FMA2b",
    "2m": "AirbusFBW/FMA2m",
    "3w": "AirbusFBW/FMA3w",
    "3b": "AirbusFBW/FMA3b",
    "3a": "AirbusFBW/FMA3a",
}
FMA_BOXES = [
    "AirbusFBW/FMAAPFDboxing",
    "AirbusFBW/FMAAPLeftArmedBox",
    "AirbusFBW/FMAAPLeftModeBox",
    "AirbusFBW/FMAAPRightArmedBox",
    "AirbusFBW/FMAAPRightModeBox",
    "AirbusFBW/FMAATHRModeBox",
    "AirbusFBW/FMAATHRboxing",
    "AirbusFBW/FMATHRWarning",
    "AirbusFBW/AutoBrkLo",
    "AirbusFBW/AutoBrkMed",
]
FMA_A339_DATAREFS = [
    #    "AirbusFBW/AltitudeTargetIsFL",
    "toliss_airbus/init/cruise_alt",
    "toliss_airbus/pfdoutputs/general/ap_altitude_reference",
]
# Reproduction on Streamdeck touchscreen colors is difficult.
FMA_COLORS = {
    "b": "#00EEFF",
    "w": "white",
    "g": "#00FF00",
    "m": "#FF00FF",
    "a": "#A04000",
}

FMA_LABELS = {
    "ATHR": "Auto Thrust",
    "VNAV": "Vertical Navigation",
    "LNAV": "Horizontal Navigation",
    "APPR": "Approach",
    "AP": "Auto Pilot",
}

FMA_LABELS_ALT = {
    "ATHR": "Autothrust Mode",
    "VNAV": "Vertical Mode",
    "LNAV": "Horizontal Mode",
    "APPR": "Approach",
    "AP": "Autopilot Mode",
}

# More or less ok for A320 series
FMA_MESSAGES = [
    "1TOGA",  # FMA 1 (THR)
    "1FLX ([0-9]+) MCT",
    "CLB",
    "1IDLE ASYM",
    "1A. FLOOR",
    "1TOGA LK",
    "1THR LK",
    "1MAN TOGA",
    "1MAN FLEX",
    "1MAN MCT",
    "1THR MCT",
    "1THR CLB",
    "1THR LVR",
    "1THR SPEED",
    "1THR IDLE",
    "1THR DES",  # A339
    "1SPEED",
    "1MACH",
    "1LVR CLB",
    "1LVR MCT",
    "1LVR ASYM",
    "2SRS",  # FMA 2 (VNAV)
    "2BRK LO",
    "2BRK MED",
    "2ALT",
    "2ALT*",
    "2ALT CRZ",
    "2ALT CST",
    "2V/S",
    "2CLB",
    "2DES",
    "2OP CLB",
    "2EXP CLB",
    "2EXP DES",
    "2OP DES",
    "2G/S",
    "2FINAL",
    "2V/S ± ([0-9]+)",
    "2FPA ± ([0-9]+).([0-9]+)",
    "3RWY",  # FMA 3 (LNAV)
    "3RWY TRK",
    "3GA TRK",
    "3TRACK",
    "3HDG",
    "3NAV",
    "3LOC",
    "3LOC*",
    "3APP NAV",
    "4CAT 1",  # FMA 4 (APPCH)
    "4CAT 2",
    "4CAT 3",
    "4SINGLE",
    "4CAT 3",
    "4DUAL",
    "4DH ([0-9]+)",
    "4MDA ([0-9]+)",
    "5AP 1",  # FMA 5 (MODE)
    "5AP 2",
    "5AP 1+2",
    "5AP1",  # same, no space
    "5AP2",
    "5AP1+2",
    "5-FD-",  # completely off
    "51FD2",
    "51FD",
    "5FD2",
    "51FD1",
    "52FD2",
    "52FD",
    "5FD1",
    "5A/THR",
    "CLAND",  # COMBINED MODES
    "CFLARE",
    "CROLL",
    "COUT",
    "CFINAL",
    "CAPP",
    "MUSE MAN PITCH TRIM",  # FMA MESSAGES
    "MMAN PITCH TRIM ONLY",
    "MDECELERATE",
    "MMORE DRAG",
    "MVERTICAL DISCON AHEAD",
    "MCHECK APP SEL",
    "MSET GREEN DOT SPD",
    "MSET HOLD SPEED",
    "MMACH SEL .([0-9]+)",
    "MSPEED SEL ([0-9]+)",
]

FMA_LABEL_MODE = 3  # 0 (None), 1 (keys), or 2 (values), or 3 alternates

FMA_COUNT = len(FMA_LABELS.keys())
FMA_LINES = len(set([c[0] for c in FMA_DATAREFS]))
# FMA_COLUMNS = [[0, 7], [7, 15], [15, 21], [21, 28], [28, 37]]
FMA_COLUMNS = [[0, 7], [7, 15], [15, 21], [21, 30], [30, 37]]
FMA_LINE_LENGTH = FMA_COLUMNS[-1][-1]
FMA_EMPTY_LINE = " " * FMA_LINE_LENGTH
COMBINED = "combined"
WARNING = "warn"

GLOBAL_SUBSTITUTES = {"THRIDLE": "THR IDLE", "FNL": "FINAL", "1FD": "1 FD", "FD2": "FD 2"}

logger = logging.getLogger(__file__)
# logger.setLevel(logging.DEBUG)
# logger.setLevel(15)


class FMAIcon(DrawBase):
    """Displays Toliss Airbus Flight Mode Annunciators on Streamdeck Plus touchscreen"""

    REPRESENTATION_NAME = "fma"

    SCHEMA = {
        "text-font": {"type": "font", "meta": {"label": "Font"}},
        "text-size": {"type": "integer", "meta": {"label": "Size"}},
        "text-color": {"type": "color", "meta": {"label": "Color"}},
        "value-font": {"type": "font", "meta": {"label": "Font"}},
        "label-mode": {"type": "integer", "meta": {"label": "FMA Label mode"}},
    }

    def __init__(self, button: "Button"):
        DrawBase.__init__(self, button=button)

        self.fmaconfig = button._config.get("fma", {})  # should not be none, empty at most...
        self.fma_label_mode = self.fmaconfig.get("label-mode", FMA_LABEL_MODE)
        self.icon_color = (20, 20, 20)
        self.text = {k: FMA_EMPTY_LINE for k in FMA_DATAREFS}
        self.previous_text: Dict[str, str] = {}
        self.boxed: Set[str] = []
        self._auto_brake = "00"
        self._cached = None  # cached icon
        self._datarefs: set | None = None
        self._icao = ""  # from which aircraft do we have the set?

        # style
        self._text = TextWithVariables(owner=button, config=self.fmaconfig, prefix="text")

        # get mandatory index
        self.all_in_one = False
        fma = self.fmaconfig.get("index")
        if fma is None:
            logger.info(f"button {button.name}: no FMA index, assuming all-in-one")
            self.all_in_one = True
            fma = 1
        fma = int(fma)
        if fma < 1:
            logger.warning(f"button {button.name}: FMA index must be in 1..{FMA_COUNT} range")
            fma = 1
        if fma > FMA_COUNT:
            logger.warning(f"button {button.name}: FMA index must be in 1..{FMA_COUNT} range")
            fma = FMA_COUNT
        self.fma_idx = fma - 1

    @property
    def aircraft_icao(self):
        return self.button.cockpit.get_aircraft_icao()

    @property
    def combined(self) -> bool:
        """FMA vertical and lateral combined into one"""
        return COMBINED in self.boxed

    def describe(self) -> str:
        return "The representation is specific to Toliss Airbus and display the Flight Mode Annunciators (FMA)."

    def get_variables(self) -> set:
        if self._datarefs is not None:
            return self._datarefs

        self._datarefs = set(FMA_BOXES) | set(FMA_DATAREFS.values())
        if self.aircraft_icao == "A339":
            self._datarefs = self._datarefs | set(FMA_A339_DATAREFS)
        self._icao = self.aircraft_icao
        return self._datarefs

    def is_master_fma(self) -> bool:
        return self.all_in_one or self.fma_idx == 1

    def get_master_fma(self):
        """Among all FMA icon buttons on the same page, tries to find the master one,
        i;e. the one that holds the datarefs.
        """
        if self.is_master_fma():
            return self
        candidates = list(
            filter(
                lambda m: isinstance(m._representation, FMAIcon) and m._representation.is_master_fma(),
                self.button.page.buttons.values(),
            )
        )
        if len(candidates) == 1:
            logger.debug(f"button {self.button.name}: master FMA is {candidates[0].name}, fma={candidates[0]._representation.fma_idx}")
            return candidates[0]._representation
        if len(candidates) == 0:
            logger.warning(f"button {self.button.name}: no master FMA found")
        else:
            logger.warning(f"button {self.button.name}: too many master FMA")
        return None

    def is_updated(self) -> bool:
        oldboxed = self.boxed
        self.check_boxed()
        if self.boxed != oldboxed:
            logger.debug(f"boxed changed {self.boxed}/{oldboxed}")
            return True
        auto_brake = self.auto_brake()
        if self._auto_brake != auto_brake:
            logger.debug(f"auto_brake changed {self._auto_brake}/{auto_brake}")
            self._auto_brake = auto_brake
            return True
        self.previous_text = self.text
        self.text = {k: self.button.get_simulator_variable_value(v, default=FMA_EMPTY_LINE) for k, v in FMA_DATAREFS.items()}
        return self.text != self.previous_text

    def is_fma_message(self, message: str, column: int = 0) -> bool:
        # search with column
        message = message.strip()
        test = message
        if 1 <= column <= 5:  # annunciators 1-5
            test = f"{column}{message}"
        elif column == 6:  # combined
            test = f"C{message}"
        elif column == 7:  # messages
            test = f"M{message}"
        if test in FMA_MESSAGES:
            logger.debug(f"found {test}")
            return True
        # search making abstraction of spaces, sometimes AP1 is "AP 1".
        # Note: in this case, the vesrion to display might be nicer with space around...
        for m in FMA_MESSAGES:
            if test.replace(" ", "") == m.replace(" ", ""):
                logger.debug(f"found {test} (no space)")
                return True
        # search without column
        msgs = [m[1:] for m in FMA_MESSAGES]
        if message in msgs:
            logger.debug(f"found {message} ({column})")
            return True
        for test in filter(lambda m: "(" in m, FMA_MESSAGES):
            pattern = re.compile(test)
            if pattern.match(message):
                logger.debug(f"{message} matches {test}")
                return True
        logger.debug(f"{message} ({column}) not in FMA message list")
        return False

    def check_boxed(self):
        """Check "boxed" datarefs to determine which texts are boxed/framed.
        They are listed as FMA#-LINE# pairs of digit. Special keyword WARNING if warning enabled.
        """
        boxed = []
        if self.button.get_simulator_variable_value("AirbusFBW/FMAAPLeftArmedBox") == 1:
            boxed.append("22")
        if self.button.get_simulator_variable_value("AirbusFBW/FMAAPLeftModeBox") == 1:
            boxed.append("21")
        if self.button.get_simulator_variable_value("AirbusFBW/FMAAPRightArmedBox") == 1:
            boxed.append("32")
        if self.button.get_simulator_variable_value("AirbusFBW/FMAAPRightModeBox") == 1:
            boxed.append("31")
        if self.button.get_simulator_variable_value("AirbusFBW/FMAATHRModeBox") == 1:
            boxed.append("11")
        if self.button.get_simulator_variable_value("AirbusFBW/FMAATHRboxing") == 1:
            boxed.append("12")
        if self.button.get_simulator_variable_value("AirbusFBW/FMAATHRboxing") == 2:
            boxed.append("11")
            boxed.append("12")
        if self.button.get_simulator_variable_value("AirbusFBW/FMATHRWarning") == 1:
            boxed.append(WARNING)
        # big mess:
        boxcode = self.button.get_simulator_variable_value("AirbusFBW/FMAAPFDboxing")
        if boxcode is not None:  # can be 0-7, is it a set of binary flags?
            boxcode = int(boxcode)
            if boxcode & 1 == 1:
                boxed.append("51")
            if boxcode & 2 == 2:
                boxed.append("52")
            if boxcode & 4 == 4:
                boxed.append("53")
            if boxcode & 8 == 8:
                boxed.append(COMBINED)
            if boxcode & 9 == 9:
                boxed.append("21")
            # etc.
        self.boxed = set(boxed)
        logger.debug(f"boxed: {boxcode}, {self.boxed}")

    def auto_brake(self):
        auto_brake = "00"
        if self.aircraft_icao != "A339":
            return auto_brake
        brk_lo = self.button.get_simulator_variable_value("AirbusFBW/AutoBrkLo", default=-1)
        if brk_lo == 1:
            auto_brake = "10"
        else:
            brk_md = self.button.get_simulator_variable_value("AirbusFBW/AutoBrkMed", default=-1)
            if brk_md == 1:
                auto_brake = "01"
        return auto_brake

    def adjust_fma_texts(self):
        if self.aircraft_icao != "A339":
            return
        # 1
        init_alt = self.button.get_simulator_variable_value("toliss_airbus/init/cruise_alt", default=-1)
        fcu_alt = self.button.get_simulator_variable_value("toliss_airbus/pfdoutputs/general/ap_altitude_reference", default=-2)
        if init_alt == fcu_alt:
            for line in ["1w", "2b"]:
                text = self.text.get(line, "")
                before = text
                if text.strip() == "ALT":
                    text = text.replace("ALT    ", "ALT CRZ")
                    self.text[line] = text
                    logger.debug(f"fma text modified: {line}: {before} -> {text}")
        # 2
        auto_brake = self.auto_brake()
        if auto_brake == "10":
            self.text["2b"] = "BRK LO"
        elif auto_brake == "01":
            self.text["2b"] = "BRK MED"
        self.text["2b"] = self.text["2b"] + " " * (FMA_LINE_LENGTH - len(self.text["2b"]))

    def get_fma_lines(self, idx: int = -1):
        if not self.is_master_fma():
            master_fma = self.get_master_fma()
            if master_fma is not None:
                return master_fma.get_fma_lines(idx=self.fma_idx)
            logger.warning(f"button {self.button.name}: fma has no master, no lines")
            return []

        if idx == -1:
            idx = self.fma_idx
        s = FMA_COLUMNS[idx][0]  # idx * self.text_length
        e = FMA_COLUMNS[idx][1]  # s + self.text_length
        l = e - s
        c = "1w"
        empty = c + " " * l
        if self.combined and idx == 1:
            s = FMA_COLUMNS[idx][0]
            e = FMA_COLUMNS[idx + 1][1]
            l = e - s
            c = "1w"
            empty = c + " " * l
        elif self.combined and idx == 2:
            return set()
        lines = []
        for li in range(1, 4):  # Loop on lines
            good = empty
            for k, v in self.text.items():
                raws = {k: v for k, v in self.text.items() if int(k[0]) == li}
                for k, v in raws.items():
                    if type(v) is float:
                        # logger.warning(f"{k}={v} is float ({raws})")
                        continue
                    # normalize
                    if len(v) < FMA_LINE_LENGTH:
                        v = v + " " * (FMA_LINE_LENGTH - len(v))
                    if len(v) > FMA_LINE_LENGTH:
                        v = v[:FMA_LINE_LENGTH]
                    # extract
                    m = v[s:e]
                    if len(m) != l:
                        logger.warning(f"string '{m}' len {len(m)} has wrong size (should be {l})")
                    if (c + m) != empty:  # if good == empty and
                        good = str(li) + k[1] + m
                        lines.append(good)
        self.adjust_fma_texts()
        return set(lines)

    def get_image_for_icon_alt(self):
        """
        Displays one FMA on one key icon, 5 keys are required for 5 FMA... (or one touchscreen, see below.)
        """
        if not self.is_updated() and self._cached is not None:
            return self._cached

        image, draw = self.double_icon(width=ICON_SIZE, height=ICON_SIZE)  # annunciator text and leds , color=(0, 0, 0, 0)
        inside = round(0.04 * image.width + 0.5)

        # pylint: disable=W0612
        lines = self.get_fma_lines()
        logger.debug(f"button {self.button.name}: {lines}")

        font = self.get_font(self._text.font, self._text.size)
        w = image.width / 2
        p = "m"
        a = "center"
        idx = -1
        for text in lines:
            idx = int(text[0]) - 1  # idx + 1
            if text[2:] == (" " * (len(text) - 1)):
                continue
            h = image.height / 2
            if idx == 0:
                h = inside + self._text.size
            elif idx == 2:
                h = image.height - inside - self._text.size
            # logger.debug(f"position {(w, h)}")
            color = FMA_COLORS[text[1]]
            draw.text((w, h), text=text[2:], font=font, anchor=p + "m", align=a, fill=color)
            ref = f"{self.fma_idx+1}{idx+1}"
            if ref in self.boxed:
                draw.rectangle(
                    (
                        2 * inside,
                        h - self._text.size / 2,
                        ICON_SIZE - 2 * inside,
                        h + self._text.size / 2 + 4,
                    ),
                    outline="white",
                    width=3,
                )

        # Paste image on cockpit background and return it.
        bg = self.button.deck.get_icon_background(
            name=self.button_name,
            width=ICON_SIZE,
            height=ICON_SIZE,
            texture_in=None,
            color_in=self.icon_color,
            use_texture=False,
            who="FMA",
        )
        bg.alpha_composite(image)
        self._cached = bg
        return self._cached

    def get_image_for_icon(self):
        """
        Helper function to get button image and overlay label on top of it.
        Label may be updated at each activation since it can contain datarefs.
        Also add a little marker on placeholder/invalid buttons that will do nothing.
        (This is currently more or less hardcoded for Elgato Streamdeck Plus touchscreen.)
        """
        if not self.all_in_one:
            return self.get_image_for_icon_alt()

        if not self.is_updated() and self._cached is not None:
            logger.debug(f"button {self.button.name}: returning cached")
            return self._cached

        # print(">>>" + "0" * 10 + "1" * 10 + "2" * 10 + "3" * 10)
        # print(">>>" + "0123456789" * 4)
        # print("\n".join([f"{k}:{v}:{len(v)}" for k, v in self.text.items()]))
        # print(">>>" + "0123456789" * 4)

        image, draw = self.double_icon(width=8 * ICON_SIZE, height=ICON_SIZE)

        inside = round(0.04 * image.height + 0.5)

        # pylint: disable=W0612
        logger.debug(f"button {self.button.name}: is FMA master")

        # replaces a few bizarre strings...
        text = self.fmaconfig.get("text")
        if text is not None:
            text = text.replace("THRIDLE", "THR IDLE")  # ?
            text = text.replace("FNL", "FINAL")  # ?

        icon_width = int(8 * ICON_SIZE / 5)
        loffset = 0
        lthinkness = 3
        has_line = False
        for i in range(FMA_COUNT - 1):
            loffset = loffset + icon_width
            if i == 1:  # second line skipped
                continue
            draw.line(((loffset, 0), (loffset, ICON_SIZE)), fill="white", width=lthinkness)
        if self.fma_label_mode > 0:
            ls = 20
            font = self.get_font(self._text.font, ls)
            offs = icon_width / 2
            h = inside + ls / 2
            lbl = list(FMA_LABELS.keys())
            if self.fma_label_mode == 2:
                lbl = list(FMA_LABELS.values())
            if self.fma_label_mode == 3:
                lbl = list(FMA_LABELS_ALT.values())
            for i in range(FMA_COUNT):
                draw.text(
                    (offs, h),
                    text=lbl[i],
                    font=font,
                    anchor="ms",
                    align="center",
                    fill="white",
                )
                offs = offs + icon_width

        if not self.button.sim.connected:
            logger.debug("not connected")
            if not self.combined:
                draw.line(
                    ((2 * icon_width, 0), (2 * icon_width, int(2 * ICON_SIZE / 3))),
                    fill="white",
                    width=lthinkness,
                )
            bg = self.button.deck.get_icon_background(
                name=self.button_name,
                width=8 * ICON_SIZE,
                height=ICON_SIZE,
                texture_in=None,
                color_in=self.icon_color,
                use_texture=False,
                who="FMA",
            )
            bg.alpha_composite(image)
            self._cached = bg
            self.previous_text = self.text
            logger.debug("texts updated")
            return self._cached

        loffset = 0
        for i in range(FMA_COUNT):
            if i == 2 and self.combined:  # skip it
                loffset = loffset + icon_width
                continue
            lines = self.get_fma_lines(idx=i)
            logger.debug(f"button {self.button.name}: FMA {i+1}: {lines}")
            font = self.get_font(self._text.font, self._text.size)
            w = int(4 * ICON_SIZE / 5)
            p = "m"
            a = "center"
            idx = -1
            for text in lines:
                idx = int(text[0]) - 1  # idx + 1
                if text[2:] == (" " * (len(text) - 2)):
                    continue
                h = image.height / 2
                if idx == 0:
                    h = inside + self._text.size / 2
                elif idx == 2:
                    h = image.height - inside - self._text.size / 2
                    #
                    # special treatment of warning amber messages, centered across FMA 2-3, 3rd line, amber
                    # (yes, I know, they blink 5 times then stay fixed. may be one day.)
                    #
                    currline = text[:2]
                    if (i == 1 or i == 2) and currline in ["3a", "3w"]:
                        wmsg = self.text[currline][FMA_COLUMNS[1][0] : FMA_COLUMNS[2][1]].strip()
                        if i == 1:
                            if not self.is_fma_message(wmsg, 6):
                                logger.warning(f">>{self.text[currline]}")

                            logger.debug(f"combined message '{wmsg}'")
                        else:
                            if not self.is_fma_message(wmsg, 7):
                                logger.warning(f">>{self.text[currline]}")
                            logger.debug(f"message '{wmsg}'")
                        draw.line(
                            (
                                (2 * icon_width, 0),
                                (2 * icon_width, int(2 * ICON_SIZE / 3)),
                            ),
                            fill="white",
                            width=lthinkness,
                        )
                        draw.text(
                            (2 * icon_width, h),
                            text=wmsg,
                            font=font,
                            anchor=p + "m",
                            align=a,
                            fill=FMA_COLORS[text[1]],
                        )
                        has_line = True
                        continue
                    #
                    #
                color = FMA_COLORS[text[1]]
                # logger.debug(f"added {text[2:]} @ {loffset + w}, {h}, {color}")
                lat = loffset + w
                if i == 1 and self.combined:
                    lat = lat + w
                if not self.is_fma_message(text[2:], i + 1):
                    logger.warning(f">>{text}")

                for k, v in GLOBAL_SUBSTITUTES.items():
                    text = text.replace(k, v)

                draw.text(
                    (lat, h),
                    text=text[2:],
                    font=font,
                    anchor=p + "m",
                    align=a,
                    fill=color,
                )
                ref = f"{i+1}{idx+1}"
                # logger.debug(ref, text)
                if ref in self.boxed:
                    if WARNING in self.boxed:
                        color = "orange"
                    else:
                        color = "white"
                    if ref == "21" and self.combined:  # frame around combined text (LAND, FLARE, ROLL OUT...)
                        draw.rectangle(
                            (
                                int(loffset + icon_width / 4 + 2 * inside),
                                h - self._text.size / 2,
                                int(loffset + icon_width + 3 * icon_width / 4 - 2 * inside),
                                h + self._text.size / 2 + 4,
                            ),
                            outline=color,
                            width=3,
                        )
                    else:
                        draw.rectangle(
                            (
                                loffset + 2 * inside,
                                h - self._text.size / 2,
                                loffset + icon_width - 2 * inside,
                                h + self._text.size / 2 + 4,
                            ),
                            outline=color,
                            width=3,
                        )
            loffset = loffset + icon_width

        if not has_line and not self.combined:
            draw.line(
                ((2 * icon_width, 0), (2 * icon_width, ICON_SIZE)),
                fill="white",
                width=lthinkness,
            )

        # Paste image on cockpit background and return it.
        bg = self.button.deck.get_icon_background(
            name=self.button_name,
            width=8 * ICON_SIZE,
            height=ICON_SIZE,
            texture_in=None,
            color_in=self.icon_color,
            use_texture=False,
            who="FMA",
        )
        bg.alpha_composite(image)
        self._cached = bg
        self.previous_text = self.text
        logger.debug("texts updated")

        # with open("fma_lines.png", "wb") as im:
        #     image.save(im, format="PNG")
        #     logger.debug(f"button {self.button.name}: saved")

        return self._cached

    def make_lines(self) -> list:
        """Returns array of lines, each line is array of tuple (character, color).
        [[("a", "g"), ("b", "w"), ...], [...]]
        """
        all_lines = []
        for linenum in range(3):
            line = {k: v for k, v in self.text.items() if int(k[0]) == (linenum + 1)}
            thisline = []
            for i in range(FMA_LINE_LENGTH):
                car = None
                color = None
                carline = None
                for k, l in line.items():
                    l = l.ljust(FMA_LINE_LENGTH)
                    c = l[i]
                    if c != " ":
                        if car is not None and car != " ":
                            logger.warning(f"several lines with different characters ({i}, {car}, {color} vs {c} {k[1]}) / {carline} {l}")
                        else:
                            car = c
                            color = k[1]
                            carline = l
                    else:
                        if car is None:
                            car = c
                thisline.append((car, color))
            all_lines.append(thisline)
        return all_lines
