# ###########################
# Representation that displays side icons.
# Vertical: present left or right vertical screens on Loupedeck Live.
# These buttons are Loupedeck Live specific.
#
import logging
import re
from PIL import ImageDraw
from cockpitdecks.pil_sync import PIL_RENDER_LOCK
from cockpitdecks.resources.color import convert_color
from cockpitdecks.buttons.representation.icon import Icon, IconBase
from cockpitdecks.buttons.representation.parameters import PARAM_LABEL, PARAM_TEXT
from cockpitdecks.strvar import TextWithVariables
from cockpitdecks.variable import Variable

# from cockpitdecks.button import Button


logger = logging.getLogger(__name__)

VAR_PATTERN = re.compile(r"\${([^}]+)}")


class IconSide(Icon):  # modified Representation IconSide class

    REPRESENTATION_NAME = "side"

    SCHEMA = {
        "centers": {"type": "list", "schema": {"type": "integer"}, "meta": {"label": "Centers"}, "minlength": 3, "maxlength": 3},
        "side": {
            "type": "list",
            "schema": {
                "text": {"type": "string", "meta": {"label": "Text"}},
                "text-font": {"type": "font", "meta": {"label": "Font"}},
                "text-size": {"type": "integer", "meta": {"label": "Size"}},
                "text-color": {"type": "string", "meta": {"label": "Color"}},
                "text-position": {"type": "choice", "meta": {"label": "Position"}, "choices": ["lt", "ct", "rt", "lm", "cm", "rm", "lb", "cb", "rb"]},
            },
            "meta": {"label": "Labels"},
        },
        "minlength": 3,
        "maxlength": 3,
    }

    def __init__(self, button: "Button"):
        button._config["icon-color"] = button._config["side"].get("icon-color", button.get_attribute("icon-color"))
        Icon.__init__(self, button=button)

        self.side = self._config.get("side")  # multi-labels
        self.centers = self.side.get("centers", [43, 150, 227])  # type: ignore
        self.labels: str | None = self.side.get("labels")  # type: ignore
        self.label_font = self.get_attribute("label-font")
        self.label_size = self.get_attribute("label-size", default=16)
        self.label_color = self.get_attribute("label-color")
        self.label_position = self._config.get("label-position", "cm")  # "centered" on middle of side image
        self.text_font = self.get_attribute("text-font")

    def get_simulator_data(self) -> set:
        datarefs = set()
        if not self.labels:
            return datarefs
        for label in self.labels:
            drefs = self.button.scan_datarefs(label)
            if len(drefs) > 0:
                datarefs = datarefs | drefs
        return datarefs

    def get_variables(self) -> set:
        datarefs = set()
        if not self.labels:
            return datarefs
        for label in self.labels:
            label_text = TextWithVariables(owner=self.button, config=label, prefix="label")
            value_text = TextWithVariables(owner=self.button, config=label, prefix="text")
            datarefs |= label_text.get_variables()
            datarefs |= value_text.get_variables()
        return datarefs

    def get_current_values(self):
        if not self.labels:
            return ()
        states = []
        for label in self.labels:
            states.append(
                {
                    "label": label.get("label", ""),
                    "value": self._resolve_side_text(label),
                }
            )
        return tuple(states)

    # get_datarefs from old IconSide
    # def get_simulator_data(self):
    #     if self.datarefs is None:
    #         self.datarefs = []
    #         if self.labels is not None:
    #             for label in self.labels:
    #                 dref = label.get(CONFIG_KW.MANAGED.value)
    #                 if dref is not None:
    #                     logger.debug(f"button {self.button_name}: added label dataref {dref}")
    #                     self.datarefs.append(dref)
    #     return self.datarefs

    def is_valid(self):
        if self.button.index not in ["left", "right"]:
            logger.debug(f"button {self.button_name}: {type(self).__name__}: not a valid index {self.button.index}")
            return False
        return super().is_valid()

    def get_image_for_icon(self):
        """
        Helper function to get button image and overlay label on top of it for SIDE keys (60x270).
        Side keys can have 3 labels placed in front of each knob.
        """
        image = super().get_image_for_icon()

        if image is None:
            return None

        if not self.labels:
            return image

        image = image.copy()
        draw = ImageDraw.Draw(image)
        inside = round(0.04 * image.width + 0.5)
        vheight = 38 - inside

        vcenter = [35, 124, 213]
        cnt = self.side.get("centers")
        if cnt is not None:
            vcenter = [round(270 * i / 100, 0) for i in convert_color(cnt)]

        for li, label in enumerate(self.labels):
            if li >= len(vcenter):
                break

            label_text = label.get("label", "")
            value_text = self._resolve_side_text(label)

            if not label_text and not value_text:
                continue

            lfont = label.get("label-font", self.label_font)
            lsize = int(label.get("label-size", self.label_size or 16))
            label_font = self.get_font(lfont, lsize)

            label_position = label.get("label-position", self.label_position)
            hpos = label_position[0] if len(label_position) > 0 else "c"
            vpos = label_position[1] if len(label_position) > 1 else "m"

            w = image.width / 2
            p = "m"
            a = "center"
            if hpos == "l":
                w = inside
                p = "l"
                a = "left"
            elif hpos == "r":
                w = image.width - inside
                p = "r"
                a = "right"

            h = vcenter[li] - lsize / 2
            if vpos == "t":
                h = vcenter[li] - vheight
            elif vpos == "b":
                h = vcenter[li] + vheight - lsize

            with PIL_RENDER_LOCK:
                draw.multiline_text(
                    (w, h),
                    text=label_text,
                    font=label_font,
                    anchor=p + "m",
                    align=a,
                    fill=label.get("label-color", self.label_color),
                )

            tsize = int(label.get("text-size", lsize))
            tfont_name = label.get("text-font", self.text_font or lfont)
            text_font = self.get_font(tfont_name, tsize)
            text_position = h + lsize + 5
            with PIL_RENDER_LOCK:
                draw.text(
                    (w, text_position),
                    text=value_text,
                    font=text_font,
                    anchor=p + "m",
                    align=a,
                    fill=label.get("text-color", self.label_color),
                )
        return image

    @staticmethod
    def _apply_text_format(value, fmt: str | None) -> str:
        """Format a formula result as a string, applying an optional Python format spec."""
        if fmt is not None:
            try:
                return fmt.format(float(value))
            except Exception:
                pass
        return str(value)

    def _resolve_side_text(self, label: dict) -> str:
        text = label.get("text", "")
        if text is None:
            return ""

        formula = label.get("formula")
        if formula is not None:
            # Old format: explicit formula: key with ${formula} placeholder in text
            if "${formula}" in str(text):
                value = self.button.execute_formula(formula=formula)
                formatted = self._apply_text_format(value, label.get("text-format"))
                text = str(text).replace("${formula}", formatted)
        elif VAR_PATTERN.search(str(text)):
            # New format: text IS the expression (dataref ref + optional RPN operators).
            # Evaluate the whole text as a formula, then apply text-format.
            value = self.button.execute_formula(formula=str(text))
            return self._apply_text_format(value, label.get("text-format"))

        def replace_var(match):
            varname = match.group(1)
            if varname == "formula":
                return ""
            if Variable.is_internal_variable(varname):
                var = self.button.sim.get_internal_variable(name=varname, is_string=True)
                value = var.value
                return "" if value is None else str(value)
            if not Variable.may_be_non_internal_variable(varname):
                return match.group(0)
            value = self.button.get_simulator_variable_value(varname, default="")
            return "" if value is None else str(value)

        return VAR_PATTERN.sub(replace_var, str(text))

    def describe(self) -> str:
        return "The representation produces an icon with optional label overlay for larger side buttons on LoupedeckLive."


class SideDisplay(IconSide):
    REPRESENTATION_NAME = "side-display"
    EDITOR_FAMILY = "Basic"
    EDITOR_LABEL = "Loupedeck Side Display"
    EDITOR_HINT = "Single-slot side panel for Loupedeck Live encoder buttons (eN index)."

    PARAMETERS = IconBase.PARAMETERS | PARAM_LABEL | PARAM_TEXT | {
        "text-format": {
            "label": "Text Format",
            "type": "string",
            "hint": "Python format string applied to evaluated text, e.g. {0:01.0f}%",
            "group": "Display",
        },
        "formula": {
            "label": "Formula",
            "type": "string",
            "hint": "Explicit formula (legacy). Use text with ${formula} placeholder, or put the expression directly in text.",
            "group": "Display",
        },
    }
