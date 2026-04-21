"""MCDU"""

import logging
import re

from cockpitdecks.variable import VariableListener

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


MCDU_ROOT = "AirbusFBW/MCDU"
MCDU_COLORS = {
    "a": "#FD8008",  # BF521A , amber, dark yellow
    "b": "#2FAFDB",
    "g": "#63E224",
    "m": "#DE50DC",
    "s": "#FFFFFF",  # special characters, not a color
    "w": "#DDDDDD",
    "y": "#EEEE00",
    "Lw": "#FFFFFF",  # bold white, bright white
    "Lg": "#00FF00",  # bold white, bright green
}
SLEW_KEYS = "VertSlewKeys"

MCDU_UNIT = "mucdu-unit"

MCDU_DISPLAY_DATA = r"AirbusFBW/MCDU(?P<unit>[1-3])(?P<name>(title|stitle|sp|label|cont|scont))(?P<line>[1-6]?)(?P<color>(Lw|Lg|[abgmswy]))"


class MCDU(VariableListener):

    def __init__(self) -> None:
        VariableListener.__init__(self, name="MCDU")
        self.variables = None
        self.datarefs = {}
        self.lines = {}
        self._first = True
        self.mcdu_units = [1, 2]

    def init(self, simulator):
        for varname in self.get_variables():
            var = simulator.get_variable(name=varname)
            var.add_listener(self)
            # self.datarefs[varname] = var
        logger.info(f"MCDU requests {len(self.variables)} variables")

    def get_variables(self) -> set:
        if self.variables is not None:
            return self.variables
        variables = set()
        for mcdu_unit in range(1, 2):
            variables.add(f"{MCDU_ROOT}{mcdu_unit}{SLEW_KEYS}")
            variables = variables | self.get_variables1unit(mcdu_unit=mcdu_unit)
        self.variables = variables
        return variables

    def completed(self) -> bool:
        # if len(self.datarefs) > (len(self.variables) - 10):
        #     logger.debug("MCDU waiting for data")
        #     print([d for d in self.variables if d not in self.datarefs])
        return len(self.variables) == len(self.datarefs)

    def get_variables1unit(self, mcdu_unit: int = 1) -> set:
        variables = set()
        # title
        for color in "bgswy":
            variables.add(f"{MCDU_ROOT}{mcdu_unit}title{color}")

        for color in "bgwy":
            variables.add(f"{MCDU_ROOT}{mcdu_unit}stitle{color}")
        # scratchpad
        code = "sp"
        for color in "aw":
            variables.add(f"{MCDU_ROOT}{mcdu_unit}{code}{color}")
        # label and content
        for line in range(1, 7):
            for code in ["label", "cont", "scont"]:  # cont = content, scont = content with special characters
                for color in MCDU_COLORS:
                    if code.endswith("cont") and color.startswith("L"):
                        continue  # skip
                    variables.add(f"{MCDU_ROOT}{mcdu_unit}{code}{line}{color}")
        return variables

    def get_mcdu_unit(self, dataref) -> int:
        mcdu_unit = -1
        if dataref == "AirbusFBW/DUBrightness[6]":  # MCDU screen brightness unit 1
            return 1
        elif dataref == "AirbusFBW/DUBrightness[7]":  # MCDU screen brightness unit 2
            return 2
        try:
            m = None
            if "VertSlewKeys" in dataref:
                m = re.match("AirbusFBW/MCDU(?P<unit>[1-3])VertSlewKeys", dataref)
            else:
                m = re.match(MCDU_DISPLAY_DATA, dataref)
            if m is None:
                logger.warning(f"not a display dataref {dataref}")
                return -1
            mcdu_unit = int(m["unit"])
        except:
            logger.warning(f"error invalid MCDU unit for {dataref}")
            return -1
        return mcdu_unit

    def variable_changed(self, variable):
        dataref = variable.name
        value = variable.value
        self.datarefs[dataref] = value
        mcdu_unit = self.get_mcdu_unit(dataref)

        if mcdu_unit not in self.mcdu_units:
            logger.warning(f"invalid MCDU unit {mcdu_unit} ({self.mcdu_units})")
            return

        if dataref not in self.variables:
            logger.debug(f"not a display dataref {dataref}")
            return

        m = re.match(MCDU_DISPLAY_DATA, dataref)
        if m is None:
            return
        colors = "".join([c for c in MCDU_COLORS.keys() if not c.startswith("L")])
        line = -1
        what = m.group("name")
        if what.endswith("title"):  # stitle, title
            colors = "bgwys"
        elif what == "sp":
            colors = "aw"
        else:  # label, scont, cont
            line = int(m.group("line"))
        self.update_line(mcdu_unit=mcdu_unit, line=line, what=what, colors=colors)

    def update_line(self, mcdu_unit: int, line: int, what: str, colors):
        """Line is 24 characters, 1 character is (<char>, <color>, <small>)."""
        line_str = "" if line == -1 else str(line)
        this_line = []
        for c in range(24):
            has_char = []
            size = 1 if what in ["stitle", "scont", "label"] else 0
            for color in colors:
                if what.endswith("cont") and color.startswith("L"):
                    continue
                if size == 1 and color.startswith("L"):  # small becomes large
                    size = 0
                name = f"AirbusFBW/MCDU{mcdu_unit}{what}{line_str}{color}"
                v = self.datarefs.get(name)
                if v is None:
                    # logger.debug(f"no value for dataref {name}")
                    continue
                if c < len(v):
                    if v[c] != " ":
                        if color.startswith("L") and len(color) == 2:  # maps Lg, Lw to g, w.
                            color = color[1]  # prevents "invalid color" further on
                        if color in MCDU_COLORS:
                            has_char.append((v[c], color, size))
                        else:
                            has_char.append((v[c], color, size))
            if len(has_char) == 1:
                this_line = this_line + has_char
            else:
                # if len(has_char) > 1:
                #     logger.debug(f"mutiple char {what}, {c}: {has_char}")
                this_line.append((" ", "w", size))
        self.lines[f"AirbusFBW/MCDU{mcdu_unit}{what}{line_str}"] = this_line

    def draw_text(self, mcdu_unit: int, draw, fonts, left_offset: int, char_delta: int, line_bases: list, font_sizes: list) -> bool:
        """Returns success"""

        def combine(lr, sm):
            return [sm[i] if lr[i][0] == " " else lr[i] for i in range(24)]

        def show_line(line, y) -> bool:
            if line is None:
                logger.debug(f"no line {src}")
                return False
            x = left_offset
            for c in line:
                if len(c) != 3:
                    logger.warning(f"invalid character {c}, replaced by white space")
                    c = (" ", COLORS.WHITE, 0)
                size = c[2]  # !!! Until now, c[2] = 0 (Large), 1 (small)
                font = fonts[0] if size > 0 else fonts[1]
                c = (c[0], c[1], font)  # !!! From now on, c[2] = LARGE font or small font
                if c[1] == "s":  # "special" characters (rev. eng.)
                    font_alt = fonts[2] if size > 0 else fonts[3]  # special font too...
                    if c[0] == "0":
                        c = ("←", "b", font)
                    elif c[0] == "1":
                        c = ("↑", "w", font)
                    elif c[0] == "2":
                        c = ("←", "w", font)
                    elif c[0] == "3":
                        c = ("→", "w", font)
                    elif c[0] == "4":
                        c = ("↓", "w", font)
                    elif c[0] == "A":
                        c = ("[", "b", font_alt)
                    elif c[0] == "B":
                        c = ("]", "b", font_alt)
                    elif c[0] == "E":
                        c = ("☐", "a", font_alt)  # in searh of larger rectangular box...
                        color = MCDU_COLORS.get(c[1], "white")  # if color is wrong, default to white
                        # draw.rectangle(((x - int(font_sizes[1]/2), y - font_sizes[1] + 2), (x + int(font_sizes[1]/6), y + 1)), outline=color, width=1)
                        bbox = draw.textbbox((x, y), text="I", font=c[2], anchor="ms")
                        # (left, top, right, bottom), taller, narrower
                        sd = 2
                        bbox = ((bbox[0] + sd, bbox[1] + sd), (bbox[2] - sd, bbox[3] + sd))
                        draw.rectangle(bbox, outline=color, width=1)
                        # print((bbox[2] - bbox[0], bbox[3]-bbox[1]), ( int(font_sizes[1]/2) + int(font_sizes[1]/6), font_sizes[1] + 2 + 1) )
                if c[0] == "`":  # does not print on terminal
                    c = ("°", c[1], font)
                if c[0] != "☐":
                    color = MCDU_COLORS.get(c[1], "white")  # if color is wrong, default to white
                    draw.text((x, y), text=c[0], font=c[2], anchor="ms", fill=color)
                x = x + char_delta
            return True

        if not self.completed():  # if got all data
            # logger.debug("MCDU waiting for data")
            return False

        line = combine(self.lines.get(f"AirbusFBW/MCDU{mcdu_unit}title"), self.lines.get(f"AirbusFBW/MCDU{mcdu_unit}stitle"))
        show_line(line, y=line_bases[0])
        for l in range(1, 7):
            show_line(self.lines.get(f"AirbusFBW/MCDU{mcdu_unit}label{l}"), y=line_bases[2 * l - 1])
            line = combine(self.lines.get(f"AirbusFBW/MCDU{mcdu_unit}cont{l}"), self.lines.get(f"AirbusFBW/MCDU{mcdu_unit}scont{l}"))
            show_line(line, y=line_bases[2 * l])
        show_line(self.lines.get(f"AirbusFBW/MCDU{mcdu_unit}sp"), y=line_bases[-1])

        # TO DO
        # # Additional, non printed keys in lower right corner of display
        # vertslew_dref = self.set_mcdu_unit(str_in="AirbusFBW/MCDU1VertSlewKeys", mcdu_unit=mcdu_unit)
        # vertslew_key = self.datarefs.get(self.set_mcdu_unit(str_in="AirbusFBW/MCDU1VertSlewKeys", mcdu_unit=mcdu_unit))
        # if vertslew_key == 1 or vertslew_key == 2:
        #     c = (PAGE_CHARS_PER_LINE - 2) * PAGE_BYTES_PER_CHAR
        #     page[PAGE_LINES - 1][c] = COLORS.WHITE
        #     page[PAGE_LINES - 1][c + 1] = False
        #     page[PAGE_LINES - 1][c + 2] = chr(SPECIAL_CHARACTERS.ARROW_UP.value)
        # if vertslew_key == 1 or vertslew_key == 3:
        #     c = (PAGE_CHARS_PER_LINE - 1) * PAGE_BYTES_PER_CHAR
        #     page[PAGE_LINES - 1][c] = COLORS.WHITE
        #     page[PAGE_LINES - 1][c + 1] = False
        #     page[PAGE_LINES - 1][c + 2] = chr(SPECIAL_CHARACTERS.ARROW_DOWN.value)

        return True
