# Python Plugin To Save Toliss Situations on request.
# Enjoy.
#
import os
import glob
from traceback import print_exc
from datetime import datetime

import xp

# ###########################################################
# SAVE TOLISS SITUATION
#
PLUGIN_VERSION = "1.0.1"
#
# Changelog:
#
# 24-FEB-2024: 1.0.1: Change date-time format
# 31-JAN-2024: 1.0.0: Original release
#
#
SAVE_TOLISS_COMMAND = "toliss/save_situation_now"
SAVE_TOLISS_COMMAND_DESC = "Save ToLiss Airbus situation to file with a timestamp"

TOLISS_SAVE_COMMAND = "toliss_airbus/iscsinterface/save_sit"
XPLANE_FOLDER_PATH = os.getcwd()
SAVED_SITUATION_FOLDER_PATH = os.path.join("Resources", "Plugins", "ToLissData", "Situations")
DATETIME_FORMAT = "%Y%m%d%H%M%S"


class PythonInterface:
    def __init__(self):
        self.Name = "Save ToLiss Situation"
        self.Sig = "xppython3.savetoliss"
        self.Desc = SAVE_TOLISS_COMMAND_DESC + " (Rel. " + PLUGIN_VERSION + ")"
        self.Info = self.Name + f" (rel. {PLUGIN_VERSION})"
        self.enabled = False
        self.trace = True  # produces extra debugging in XPPython3.log for this class
        self.saveToLissCmdRef = None

    def XPluginStart(self):
        if self.trace:
            print(self.Info, "XPluginStart: starting..")

        self.saveToLissCmdRef = xp.createCommand(SAVE_TOLISS_COMMAND, SAVE_TOLISS_COMMAND_DESC)
        xp.registerCommandHandler(self.saveToLissCmdRef, self.saveToLiss, 1, None)

        print(self.Info, "XPluginStart: ..started.")
        return self.Name, self.Sig, self.Desc

    def XPluginStop(self):
        if self.trace:
            print(self.Info, "XPluginStop: stopping..")

        if self.saveToLissCmdRef:
            xp.unregisterCommandHandler(self.saveToLissCmdRef, self.saveToLiss, 1, None)
            self.saveToLissCmdRef = None

        print(self.Info, "XPluginStop: ..stopped.")
        return None

    def XPluginEnable(self):
        self.enabled = True
        return 1

    def XPluginDisable(self):
        self.enabled = False
        return None

    def XPluginReceiveMessage(self, inFromWho, inMessage, inParam):
        pass

    def saveToLiss(self, *args, **kwargs):
        # pylint: disable=unused-argument
        if not self.enabled:
            print(self.Info, "saveToLiss: not enabled.")
            return 0

        command_phase = 0
        if len(args) > 2:
            command_phase = args[1]
            if self.trace:
                print(self.Info, "saveToLiss: command phase", command_phase)
        else:
            print(self.Info, "saveToLiss: no command phase", len(args))

        if command_phase == 0:
            try:
                # 1. Save the situation (2 files)
                cmd_ref = xp.findCommand(TOLISS_SAVE_COMMAND)
                if cmd_ref is None:
                    if self.trace:
                        print(self.Info, f"command '{TOLISS_SAVE_COMMAND}' not found")
                    return 1

                ts = datetime.now()
                xp.commandOnce(cmd_ref)
                if self.trace:
                    print(self.Info, f"saved situation at {ts}")

                # 2. Rename the situation files with timestamp
                if self.trace:
                    print(self.Info, f"X-Plane folder path {XPLANE_FOLDER_PATH}")

                # Find all files newer than ts
                all_files = glob.glob(os.path.join(XPLANE_FOLDER_PATH, SAVED_SITUATION_FOLDER_PATH, "*.qps"))
                all_files = all_files + glob.glob(os.path.join(XPLANE_FOLDER_PATH, SAVED_SITUATION_FOLDER_PATH, "*_pilotItems.dat"))
                files = list(filter(lambda f: os.path.getctime(f) > ts.timestamp(), all_files))
                # Rename those files with <timestamp> added to name
                newname = ""
                if len(files) > 0:
                    tstr = ts.strftime(DATETIME_FORMAT)
                    for f in files:
                        fn, fext = os.path.os.path.splitext(f)
                        newname = os.path.join(fn + "-" + tstr + fext).replace("AUTO", "USER")
                        os.rename(f, newname)
                        print(self.Info, f"saved situation at {ts} in file {newname}")
                    # if self.trace:
                    #     print(self.Info, f"{len(files)} files renamed at {tstr}")
                else:
                    if self.trace:
                        print(self.Info, "no file")

                return 1
            except:
                print(self.Info, "saveToLiss: exception")
                print_exc()

        return 0