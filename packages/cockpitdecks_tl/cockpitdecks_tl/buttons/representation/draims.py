"""Digital Radio and Audio Integrating Management System"""

import logging

from typing import Set


from cockpitdecks.variable import VariableListener

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


DRAIMS_COLORS = {
    "a": "#FD8008",  # BF521A , amber, dark yellow
    "b": "#2FAFDB",
    "g": "#63E224",
    "m": "#DE50DC",
    "s": "#FFFFFF",  # special characters, not a color
    "w": "#DDDDDD",
    "y": "#EEEE00",
}

DRAIMS_UNIT = "draims-unit"

DRAIMS_DATAREFS = [
    # VHF
    "AirbusFBW/RMP1Freq",
    "AirbusFBW/RMP1StbyFreq",
    "AirbusFBW/RMP2Freq",
    "AirbusFBW/RMP2StbyFreq",
    "AirbusFBW/RMP3/ActiveWindowString",
    "AirbusFBW/RMP3/StandbyWindowString",
    # ATC
    "AirbusFBW/XPDRPower",
    "AirbusFBW/XPDRAltitude",
    "AirbusFBW/XPDRString",
    "AirbusFBW/XPDRTCASMode",  # 0, 1, 2
    "AirbusFBW/XPDRSystem",  # 1 or 2
    "AirbusFBW/XPDR3",
    "AirbusFBW/XPDRTCASAltSelect",
]

DRAIMS_ACTIVITIES = [
    "AirbusFBW/DRAIMS1/PageSelVHF",
    "AirbusFBW/DRAIMS1/PageSelHF",
    "AirbusFBW/DRAIMS1/PageSelTEL",
    "AirbusFBW/DRAIMS1/PageSelATC",
    "AirbusFBW/DRAIMS1/PageSelMENU",
    "AirbusFBW/DRAIMS1/PageSelNAV",
]


class DRAIMS(VariableListener):

    def __init__(self) -> None:
        VariableListener.__init__(self, name="DRAIMS")
        self.variables = None
        self.datarefs = {}
        self.activities = []
        self.lines = {}
        self.page = "vhf"
        self._first = True

    def init(self, simulator):
        for varname in self.get_variables():
            var = simulator.get_variable(name=varname)
            var.add_listener(self)
            self.datarefs[varname] = var
        logger.info(f"DRAIMS requests {len(self.variables)} variables")

    def get_variables(self) -> set:
        if self.variables is not None:
            return self.variables
        variables = set(DRAIMS_DATAREFS)
        self.variables = variables
        return variables

    def get_activities(self) -> Set:
        return set(ACTIVITIES)

    def completed(self) -> bool:
        return len(self.variables) == len(self.datarefs)

    def variable_changed(self, variable):
        if not variable.has_changed():
            return

    def activity_received(self, activity):
        if activity.name.startswith("AirbusFBW/DRAIMS1/PageSel"):
            self.page = activity.name.replace("AirbusFBW/DRAIMS1/PageSel", "").lower()
            print(">>> page changed", self.page)
