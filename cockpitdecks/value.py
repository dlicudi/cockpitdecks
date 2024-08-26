from __future__ import annotations

from abc import abstractmethod
import logging
import re
from abc import ABC

import ruamel

from cockpitdecks import CONFIG_KW
from cockpitdecks.simulator import (
    Dataref,
    INTERNAL_STATE_PREFIX,
    PATTERN_DOLCB,
    PATTERN_INTSTATE,
)
from .resources.iconfonts import ICON_FONTS
from .resources.rpc import RPC
from .resources.color import convert_color

logger = logging.getLogger(__name__)
# logger.setLevel(logging.DEBUG)


class DatarefValueProvider(ABC):
    @abstractmethod
    def get_dataref_value(name: str):
        pass


class StateVariableProvider(ABC):
    @abstractmethod
    def get_state_value(name: str):
        pass


class ValueProvider(DatarefValueProvider, StateVariableProvider):
    pass


class Formula:

    def __init__(self, name: str, formula: str):
        self._formula_raw = formula
        self._formula_temp = None

    @staticmethod
    def is_formula(formula: str, strict: bool = True) -> bool:
        if strict:
            return type(formula) is str and "${" in formula  # ${..} to substitute
        if type(formula) in [int, float]:  # it is a constant
            return True
        try:
            a = float(formula)  # "123.456"
            return True
        except ValueError:
            pass
        try:
            a = int(formula)  # "123"
            return True
        except ValueError:
            pass
        return False

    @property
    def formula(self):
        return self._formula_raw if self._formula_temp is None else self._formula_temp

    def get_datarefs(self) -> set:
        datarefs = re.findall(PATTERN_DOLCB, self.formula)
        return set(filter(lambda x: Dataref.might_be_dataref(x), datarefs))

    def substitute_dataref_values(self, provider: ValueProvider, default: str = "0.0", formatting: str = None):
        """
        Replaces ${dataref} with value of dataref in labels and execution formula.
        @todo: should take into account dataref value type (Dataref.xp_data_type or Dataref.data_type).
        """
        text = self.formula
        if type(text) is int or type(text) is float:  # probably formula is a constant value
            value_str = text
            if formatting is not None:
                value_str = formatting.format(text)
                logger.debug(f"value {provider.name}:received int or float, returning as is.")
            else:
                value_str = str(text)
                logger.debug(f"value {provider.name}:received int or float, returning formatted {formatting}.")
            return value_str

        dataref_names = re.findall(PATTERN_DOLCB, text)

        if len(dataref_names) == 0:
            logger.debug(f"value {provider.name}:no dataref to substitute.")
            return text

        if formatting is not None:
            if type(formatting) is list:
                if len(dataref_names) != len(formatting):
                    logger.warning(
                        f"value {provider.name}:number of datarefs {len(dataref_names)} not equal to the number of format {len(formatting)}, cannot proceed."
                    )
                    return text
                # Else: format (to do)
            elif type(formatting) is not str:
                logger.warning(f"value {provider.name}:single format is not a string, cannot proceed.")
                return text

        retmsg = text
        cnt = 0
        for dataref_name in dataref_names:
            value = provider.get_dataref_value(dataref_name)
            value_str = ""
            if formatting is not None and value is not None:
                if type(formatting) is list:
                    value_str = formatting[cnt].format(value)
                elif formatting is not None and type(formatting) is str:
                    value_str = formatting.format(value)
            else:
                value_str = str(value) if value is not None else str(default)  # default gets converted in float sometimes!
            retmsg = retmsg.replace(f"${{{dataref_name}}}", value_str)
            cnt = cnt + 1

        more = re.findall(PATTERN_DOLCB, retmsg)  # XXXHERE
        if len(more) > 0:
            logger.warning(f"value {self.formula}:unsubstituted dataref values {more}")

        return retmsg

    def substitute_state_values(self, provider: ValueProvider, default: str = "0.0", formatting: str = None):
        txtcpy = self.formula
        more = re.findall(PATTERN_INTSTATE, txtcpy)
        for name in more:
            state_string = f"${{{INTERNAL_STATE_PREFIX}{name}}}"  # @todo: !!possible injection!!
            value = provider.get_state_value(name)
            logger.debug(f"value {state_string} = {value}")
            if value is not None:
                txtcpy = txtcpy.replace(state_string, value)
            else:
                txtcpy = txtcpy.replace(state_string, default)
        more = re.findall(PATTERN_INTSTATE, txtcpy)
        if len(more) > 0:
            logger.warning(f"formula {self.formula}:unsubstituted status values {more}")
        return txtcpy

    def substitute_button_values(self, provider: ValueProvider, default: str = "0.0", formatting=None):
        # Experimental, do not use
        txtcpy = self.formula
        more = re.findall("\\${button:([^\\}]+?)}", txtcpy)
        if len(more) > 0:
            for m in more:
                v = provider.deck.cockpit.get_button_value(m)  # starts at the top
                if v is None:
                    logger.warning(f"value {provider.name}:{m} has no value")
                    v = str(default)
                else:
                    v = str(v)  # @todo: later: use formatting
                m_str = f"${{button:{m}}}"  # "${formula}"
                txtcpy = txtcpy.replace(m_str, v)
                logger.debug(f"value {provider.name}:replaced {m_str} by {str(v)}. ({m})")
        more = re.findall("\\${button:([^\\}]+?)}", txtcpy)
        if len(more) > 0:
            logger.warning(f"value {provider.name}:unsubstituted button values {more}")
        return txtcpy

    def substitute_values(self, provider: ValueProvider, default: str = "0.0", formatting: str = None):
        text = self.formula
        logger.debug(f"substitute_values: processing '{text}'..")
        if type(text) is not str or "${" not in text:  # no ${..} to substitute
            logger.debug(f"substitute_values: value {text} has no variable, returning as it is")
            return text
        self._formula_temp = self.substitute_state_values(provider=provider, default=default, formatting=formatting)
        if text != self._formula_temp:
            logger.debug(f"substitute_values: value {provider.name}: {text} => {self._formula_temp}")
        else:
            logger.debug(f"substitute_values: has no state variable ({text})")
        # do not use
        # step1 = self._formula_temp
        # self._formula_temp = self.substitute_state_values(provider=provider, default=default, formatting=formatting)
        # step2 = self._formula_temp
        step3 = self.substitute_dataref_values(provider=provider, default=default, formatting=formatting)
        if step3 != self._formula_temp:
            logger.debug(f"substitute_values: value {provider.name}: {self._formula_temp} => {step3}")
        else:
            logger.debug(f"substitute_values: has no dataref ({step3})")
        logger.debug(f"substitute_values: ..processed '{text}' => {step3}")
        return step3

    # ##################################
    # Formula Execution
    #
    def get_value(self, button: ValueProvider, default: float = 0.0, formatting: str = None):
        """
        replace datarefs variables with their (numeric) value and execute formula.
        Returns formula result.
        """
        expr = self.substitute_values(provider=button, default=str(default), formatting=formatting)
        logger.debug(f"value {self.formula} => {expr}")
        r = RPC(expr)
        value = r.calculate()
        logger.debug(f"formula: value {self.formula} => {expr}: => {value}")
        return value


class Value:
    """Value class.

    Defines a value used by Cockpitdecks which is based on datarefs and button state variables.
    Value needs a pointer to the button to get the values of datarefs and state variables.
    Values DOES not contain the value, only its définition and methods to compute it.
    """

    def __init__(self, name: str, config: dict, button: ValueProvider):
        self._config = config
        self._button = button
        self.name = name  # for debeging and information purpose

        self._set_dataref = self._config.get(CONFIG_KW.SET_DATAREF.value)
        self._set_dref = None
        if self._set_dataref is not None:
            self._set_dref = self._button.sim.get_dataref(self._set_dataref)
            self._set_dref.set_writable()

        # Used in "value"
        self._datarefs = None
        self._string_datarefs = None
        self._statevars = {}
        self._known_extras = ()

        self.init()

    def init(self):
        self._string_datarefs = self.string_datarefs
        if type(self._string_datarefs) is str:
            if "," in self._string_datarefs:
                self._string_datarefs = self._string_datarefs.replace(" ", "").split(",")
            else:
                self._string_datarefs = [self._string_datarefs]

    def get_dataref_value(self, dataref):
        return self._button.get_dataref_value(dataref)

    def get_state_value(self, state):
        return self._button.get_state_value(state)

    @property
    def dataref(self) -> str | None:
        # Single datatef
        return self._config.get(CONFIG_KW.DATAREF.value)

    @property
    def set_dataref(self) -> str | None:
        # Single datatef
        return self._config.get(CONFIG_KW.SET_DATAREF.value)

    @property
    def string_datarefs(self) -> set:
        # List of string datarefs
        return set(self._config.get(CONFIG_KW.STRING_DATAREFS.value, set()))

    @property
    def datarefs(self) -> list:
        # List of datarefs
        return self._config.get(CONFIG_KW.MULTI_DATAREFS.value, [])

    @property
    def formula(self) -> str:
        # Formula
        return self._config.get(CONFIG_KW.FORMULA.value, "")

    def is_self_modified(self):
        # Determine of the activation of the button directly modifies
        # a dataref used in computation of the value.
        print("is_self_modified >>>", self._set_dataref in self._datarefs, self._set_dataref, self._datarefs)
        return self._set_dataref in self._datarefs

    def complement_datarefs(self, datarefs: set, reason: str | None = None):
        # Add datarefs to the value for computation purpose
        # Used by activation and representation to add to button datarefs
        if self._datarefs is None:
            self._datarefs = set()
        self._datarefs = self._datarefs | datarefs
        logger.debug(f"value {self.name}: added {len(datarefs)} datarefs ({reason})")

    def get_datarefs(self, base: dict | None = None, extra_keys: list = [CONFIG_KW.FORMULA.value]) -> set:
        """
        Returns all datarefs used by this button from label, texts, computed datarefs, and explicitely
        listed dataref and datarefs attributes.
        This can be applied to the entire button or to a subset (for annunciator parts)
        """
        if base is None:  # local, button-level ones
            if self._datarefs is not None:  # cached if globals (base is None)
                return self._datarefs
            base = self._config

        self._datarefs = self.scan_datarefs(base, extra_keys=extra_keys)
        logger.debug(f"value {self.name}: found datarefs {self._datarefs}")
        return self._datarefs

    def get_all_datarefs(self) -> list:
        return self.get_datarefs() | self._string_datarefs

    def scan_datarefs(self, base: dict, extra_keys: list = [CONFIG_KW.FORMULA.value]) -> set:
        """
        scan all datarefs in texts, computed datarefs, or explicitely listed.
        This is applied to the entire button or to a subset (for annunciator parts for example).
        String datarefs are treated separately.
        """
        r = set()

        # Direct use of datarefs:
        #
        # 1.1 Single datarefs in attributes, yes we monotor the set-dataref as well in case someone is using it.
        for attribute in [CONFIG_KW.DATAREF.value, CONFIG_KW.SET_DATAREF.value]:
            dataref = base.get(attribute)
            if dataref is not None and Dataref.might_be_dataref(dataref):
                r.add(dataref)
                logger.debug(f"value {self.name}: added single dataref {dataref}")

        # 1.2 Multiple
        datarefs = base.get(CONFIG_KW.MULTI_DATAREFS.value)
        if datarefs is not None:
            a = []
            for d in datarefs:
                if Dataref.might_be_dataref(d):
                    r.add(d)
                    a.append(d)
            logger.debug(f"value {self.name}: added multiple datarefs {a}")

        # 2. In string datarefs (formula, text, etc.)
        allways_extra = [CONFIG_KW.FORMULA.value, CONFIG_KW.VIEW_IF.value]
        self._known_extras = set(extra_keys + allways_extra)

        for key in self._known_extras:
            text = base.get(key)
            if text is None:
                continue
            if type(text) is dict:
                datarefs = self.scan_datarefs(base=text, extra_keys=extra_keys)
                if len(datarefs) > 0:
                    r = r | datarefs
                continue
            if text is not str:
                text = str(text)
            datarefs = re.findall(PATTERN_DOLCB, text)
            datarefs = set(filter(lambda x: Dataref.might_be_dataref(x), datarefs))
            if len(datarefs) > 0:
                r = r | datarefs
                logger.debug(f"value {self.name}: added datarefs found in {key}: {datarefs}")

        # Clean up
        # text: ${formula} replaces text with result of formula
        if CONFIG_KW.FORMULA.value in r:  # label or text may contain like ${{CONFIG_KW.FORMULA.value}}, but {CONFIG_KW.FORMULA.value} is not a dataref.
            r.remove(CONFIG_KW.FORMULA.value)
        if None in r:
            r.remove(None)

        return r

    def deepscan(base: dict | ruamel.yaml.comments.CommentedMap | ruamel.yaml.comments.CommentedSeq) -> set:
        # Highly ruamel.yaml specific procedure to scan
        # all dataref in yaml-loaded structure.
        # Returns a list of all ${} elements.
        #
        r = set()

        # Direct use of datarefs:
        #
        # 1.1 Single datarefs in attributes, yes we monotor the set-dataref as well in case someone is using it.
        for attribute in [CONFIG_KW.DATAREF.value, CONFIG_KW.SET_DATAREF.value]:
            dataref = base.get(attribute)
            if dataref is not None:
                r.add(dataref)

        # 1.2 List of datarefs in attributes
        for attribute in [CONFIG_KW.MULTI_DATAREFS.value, CONFIG_KW.DATAREFS.value]:
            datarefs = base.get(attribute)
            if datarefs is not None:
                r = r | set(datarefs)

        # 2. In string datarefs (formula, text, etc.)
        #    Crawl down in dict attribute values
        for key, value in base.items():
            if type(value) is str and value != "":
                r = r | set(re.findall(PATTERN_DOLCB, value))
            elif type(value) is dict:
                r = r | deepscan(value)
            elif type(value) is list:
                for v in value:
                    r = r | deepscan(v)
            elif type(value) is ruamel.yaml.comments.CommentedMap:
                t = {k: v for k, v in value.items()}
                r = r | deepscan(t)
            elif type(value) is ruamel.yaml.comments.CommentedSeq:
                for v in enumerate(value):
                    v1 = v[1]
                    if type(v1) is str and v1 != "":
                        r = r | set(re.findall(PATTERN_DOLCB, v1))
                    elif type(v1) is dict:
                        r = r | deepscan(v[1])
                    elif type(v1) is ruamel.yaml.comments.CommentedMap:
                        t = {k: v for k, v in v1.items()}
                        r = r | deepscan(t)
                    else:
                        print("unprocessed", v, type(v1), v1)

        if "formula" in r:  # label or text may contain like ${{CONFIG_KW.FORMULA.value}}, but {CONFIG_KW.FORMULA.value} is not a dataref.
            r.remove("formula")
        if None in r:
            r.remove(None)

        return r

    # ##################################
    # Formula value substitution
    #
    def get_formula(self, base: dict | None = None) -> str | None:
        if base is not None:
            formula = base.get(CONFIG_KW.FORMULA.value)
            if formula is not None and formula != "":
                return formula
        if self.formula is not None and self.formula != "":
            return self.formula
        if self._button.formula is not None and self._button.formula != "":
            return self._button.formula
        return None

    def substitute_dataref_values(self, message: str | int | float, default: str = "0.0", formatting=None):
        """
        Replaces ${dataref} with value of dataref in labels and execution formula.
        @todo: should take into account dataref value type (Dataref.xp_data_type or Dataref.data_type).
        """
        if type(message) is int or type(message) is float:  # probably formula is a constant value
            value_str = message
            if formatting is not None:
                if formatting is not None:
                    value_str = formatting.format(message)
                    logger.debug(f"value {self.name}:received int or float, returning as is.")
                else:
                    value_str = str(message)
                    logger.debug(f"value {self.name}:received int or float, returning formatted {formatting}.")
            return value_str

        dataref_names = re.findall(PATTERN_DOLCB, message)

        if len(dataref_names) == 0:
            logger.debug(f"value {self.name}:no dataref to substitute.")
            return message

        if formatting is not None:
            if type(formatting) is list:
                if len(dataref_names) != len(formatting):
                    logger.warning(
                        f"value {self.name}:number of datarefs {len(dataref_names)} not equal to the number of format {len(formatting)}, cannot proceed."
                    )
                    return message
            elif type(formatting) is not str:
                logger.warning(f"value {self.name}:single format is not a string, cannot proceed.")
                return message

        retmsg = message
        cnt = 0
        for dataref_name in dataref_names:
            value = self.get_dataref_value(dataref_name)
            value_str = ""
            if formatting is not None and value is not None:
                if type(formatting) is list:
                    value_str = formatting[cnt].format(value)
                elif formatting is not None and type(formatting) is str:
                    value_str = formatting.format(value)
            else:
                value_str = str(value) if value is not None else str(default)  # default gets converted in float sometimes!
            retmsg = retmsg.replace(f"${{{dataref_name}}}", value_str)
            cnt = cnt + 1

        more = re.findall(PATTERN_DOLCB, retmsg)  # XXXHERE
        if len(more) > 0:
            logger.warning(f"value {self.name}:unsubstituted dataref values {more}")

        return retmsg

    def substitute_state_values(self, text, default: str = "0.0", formatting=None):
        txtcpy = text
        more = re.findall(PATTERN_INTSTATE, txtcpy)
        for name in more:
            state_string = f"${{{INTERNAL_STATE_PREFIX}{name}}}"  # @todo: !!possible injection!!
            value = self._button.get_state_value(name)
            logger.debug(f"value {state_string} = {value}")
            if value is not None:
                txtcpy = txtcpy.replace(state_string, value)
            else:
                txtcpy = txtcpy.replace(state_string, default)
        more = re.findall(PATTERN_INTSTATE, txtcpy)
        if len(more) > 0:
            logger.warning(f"value {self.name}:unsubstituted status values {more}")
        return txtcpy

    # def substitute_button_values(self, text, default: str = "0.0", formatting=None):
    #     # Experimental, do not use
    #     txtcpy = text
    #     more = re.findall("\\${button:([^\\}]+?)}", txtcpy)
    #     if len(more) > 0:
    #         for m in more:
    #             v = self.deck.cockpit.get_button_value(m)  # starts at the top
    #             if v is None:
    #                 logger.warning(f"value {self.name}:{m} has no value")
    #                 v = str(default)
    #             else:
    #                 v = str(v)  # @todo: later: use formatting
    #             m_str = f"${{button:{m}}}"  # "${formula}"
    #             txtcpy = txtcpy.replace(m_str, v)
    #             logger.debug(f"value {self.name}:replaced {m_str} by {str(v)}. ({m})")
    #     more = re.findall("\\${button:([^\\}]+?)}", txtcpy)
    #     if len(more) > 0:
    #         logger.warning(f"value {self.name}:unsubstituted button values {more}")
    #     return txtcpy

    def substitute_values(self, text, default: str = "0.0", formatting=None):
        logger.debug(f"substitute_values: processing '{text}'..")
        if type(text) is not str or "$" not in text:  # no ${..} to stubstitute
            logger.debug(f"substitute_values: value {text} has no variable to substitute, returning as it is")
            return text
        step1 = self.substitute_state_values(text, default=default, formatting=formatting)
        if text != step1:
            logger.debug(f"substitute_values: state: value {self.name}: {text} => {step1}")
        else:
            logger.debug(f"substitute_values: has no state variable ({text})")
        # step2 = self.substitute_button_values(step1, default=default, formatting=formatting)
        step2 = step1
        step3 = self.substitute_dataref_values(step2, default=default, formatting=formatting)
        if step3 != step2:
            logger.debug(f"substitute_values: value {self.name}: {step2} => {step3}")
        else:
            logger.debug(f"substitute_values: has no dataref ({step3})")
        logger.debug(f"substitute_values: ..processed '{text}' => {step3}")
        return step3

    # ##################################
    # Formula Execution
    #
    def execute_formula(self, formula, default: float = 0.0):
        """
        replace datarefs variables with their (numeric) value and execute formula.
        Returns formula result.
        """
        expr = self.substitute_values(text=formula, default=str(default))
        logger.debug(f"value {self.name}: {formula} => {expr}")
        r = RPC(expr)
        value = r.calculate()
        logger.debug(
            f"execute_formula: value {self.name}: {formula} => {expr}: => {value}",
        )
        return value

    # ##################################
    # Text substitution
    #
    def get_text_detail(self, config, which_text):
        DEFAULT_VALID_TEXT_POSITION = "cm"

        text = self.get_text(config, which_text)
        text_format = config.get(f"{which_text}-format")
        page = self._button.page

        dflt_system_font = self._button.get_attribute(f"system-font")
        if dflt_system_font is None:
            logger.error(f"button {self._button.name}: no system font")

        dflt_text_font = self._button.get_attribute(f"{which_text}-font")
        if dflt_text_font is None:
            dflt_text_font = self._button.get_attribute("label-font")
            if dflt_text_font is None:
                logger.warning(f"button {self._button.name}: no default label font, using system font")
                dflt_text_font = dflt_system_font

        text_font = config.get(f"{which_text}-font", dflt_text_font)

        dflt_text_size = self._button.get_attribute(f"{which_text}-size")
        if dflt_text_size is None:
            dflt_text_size = self._button.get_attribute("label-size")
            if dflt_text_size is None:
                logger.warning(f"button {self._button.name}: no default label size, using 10")
                dflt_text_size = 16
        text_size = config.get(f"{which_text}-size", dflt_text_size)

        dflt_text_color = self._button.get_attribute(f"{which_text}-color")
        if dflt_text_color is None:
            dflt_text_color = self._button.get_attribute("label-color")
            if dflt_text_color is None:
                logger.warning(f"button {self._button.name}: no default label color, using {DEFAULT_COLOR}")
                dflt_text_color = DEFAULT_COLOR
        text_color = config.get(f"{which_text}-color", dflt_text_color)
        text_color = convert_color(text_color)

        dflt_text_position = self._button.get_attribute(f"{which_text}-position")
        if dflt_text_position is None:
            dflt_text_position = self._button.get_attribute("label-position")
            if dflt_text_position is None:
                logger.warning(f"button {self._button.name}: no default label position, using cm")
                dflt_text_position = DEFAULT_VALID_TEXT_POSITION  # middle of icon
        text_position = config.get(f"{which_text}-position", dflt_text_position)
        if text_position[0] not in "lcr":
            text_position = DEFAULT_VALID_TEXT_POSITION
            logger.warning(f"button {self._button.name}: {type(self).__name__}: invalid horizontal label position code {text_position}, using default")
        if text_position[1] not in "tmb":
            text_position = DEFAULT_VALID_TEXT_POSITION
            logger.warning(f"button {self._button.name}: {type(self).__name__}: invalid vertical label position code {text_position}, using default")

        # print(f">>>> {self._button.get_id()}:{which_text}", dflt_text_font, dflt_text_size, dflt_text_color, dflt_text_position)

        if text is not None and not isinstance(text, str):
            logger.warning(f"button {self._button.name}: converting text {text} to string (type {type(text)})")
            text = str(text)

        return text, text_format, text_font, text_color, text_size, text_position

    def get_text(self, base: dict, root: str = "label"):  # root={label|text}
        """
        Extract label or text from base and perform formula and dataref values substitution if present.
        (I.e. replaces ${formula} and ${dataref} with their values.)
        """
        text = base.get(root)
        if text is None:
            return None

        # HACK 1: Special icon font substitution
        default_font = self._button.get_attribute("label-font")
        if default_font is None:
            logger.warning("no default font")

        text_font = base.get(root + "-font", default_font)

        # Substituing icons in icon fonts
        for k, v in ICON_FONTS.items():
            if text_font.lower().startswith(v[0]):
                s = "\\${%s:([^\\}]+?)}" % (k)
                icons = re.findall(s, text)
                for i in icons:
                    if i in v[1].keys():
                        text = text.replace(f"${{{k}:{i}}}", v[1][i])
                        logger.debug(f"button {self._button.name}: substituing font icon {i}")

        # Formula in text
        # If text contains ${formula}, it is replaced by the value of the formula calculation.
        text_format = base.get(f"{root}-format")
        KW_FORMULA_STR = f"${{{CONFIG_KW.FORMULA.value}}}"  # "${formula}"
        if KW_FORMULA_STR in str(text):
            res = ""
            formula = self.get_formula(base)
            if formula is not None:
                res = self.execute_formula(formula=formula)
                if res != "":  # Format output if format present
                    if text_format is not None:
                        logger.debug(f"button {self._button.name}: {root}-format {text_format}: res {res} => {text_format.format(res)}")
                        res = text_format.format(res)
                    else:
                        res = str(res)
            else:
                logger.warning(f"button {self._button.name}: text contains {KW_FORMULA_STR} but no {CONFIG_KW.FORMULA.value} attribute found")

            text = text.replace(KW_FORMULA_STR, res)

        # Rest of text: substitution of ${}
        text = self.substitute_values(text, formatting=text_format, default="---")
        return text

    # ##################################
    # Value computation
    #
    def get_value(self):
        """ """
        # 1. If there is a formula, value comes from it
        formula = self.get_formula()
        if formula is not None and formula != "":
            ret = self.execute_formula(formula=formula)
            logger.debug(f"value {self.name}: {ret} (from formula)")
            return ret

        # 2. One dataref
        if self.dataref is not None:
            # if self._datarefs[0] in self.page.datarefs.keys():  # unnecessary check
            ret = self.get_dataref_value(self.dataref)
            logger.debug(f"value {self.name}: {ret} (from single dataref {self.dataref})")
            return ret

        # 3. Multiple datarefs
        if len(self._datarefs) > 1:
            r = {}
            for d in self.get_all_datarefs():
                v = self.get_dataref_value(d)
                r[d] = v
            logger.debug(f"value {self.name}: {r} (no formula, no dataref, returning all datarefs)")
            return r

        logger.debug(f"value {self.name}: no formula, no dataref")
        # 4. State variables?

        return None

    def save(self):
        # Writes the computed button value to set-dataref
        if self._set_dref is not None:
            new_value = self.get_value()
            self._set_dref.update_value(new_value=new_value, cascade=True)
            self._set_dref.save()
            # print(f"set-dataref>>value {self.name}: button {self._button.name}: set-dataref {self._set_dref.path} = {new_value} ({self._set_dref.value()})")
