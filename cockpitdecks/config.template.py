# User settable variables
import os

# #############################@
# NETWORK SETTING
#
# Where X-Plane runs
XP_HOST = "127.0.0.1"
XP_HOME = os.path.join(os.sep, "X-Plane 12")
# XP_HOME = None  # Uncomment this line if X-Plane runs on a remote machine
API_PORT = "8086"
API_PATH = "/api/v1"  # no default, Laminar provides it

# Where cockpitdecks runs
APP_HOST = "127.0.0.1"
# Where to search for aircrafts
COCKPITDECKS_PATH = ":".join([
    os.path.join(XP_HOME, "Aircraft", "Extra Aircraft"),
    os.path.join(XP_HOME, "Aircraft", "Laminar Research")
])

# #############################@
# DATAREFS
#
# if no frequency is supplied (or forced to None), this is used
DEFAULT_REQ_FREQUENCY = 1
