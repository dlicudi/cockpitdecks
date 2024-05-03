"""
Little plugin that reads string-type datarefs and multicast them at regular interval.
(I use it to fetch Toliss Airbus FMA text lines. But can be used to multicast any string-typed dataref.)
Return value is JSON {dataref-path: dataref-value} dictionary.
Return value must be smaller than 1472 bytes.
"""

import os
import socket
import time
import json
import ruamel
from ruamel.yaml import YAML
from traceback import print_exc
from threading import RLock

from XPPython3 import xp

ruamel.yaml.representer.RoundTripRepresenter.ignore_aliases = lambda x, y: True
yaml = YAML(typ="safe", pure=True)

RELEASE = "2.0.5"

# Changelog:
#
# 02-MAY-2024: 2.0.5: Now changing dataref set in one operation to minimize impact on flightloop
# 23-APR-2024: 2.0.4: Now reading from config.yaml for aircraft.
# 22-DEC-2023: 1.0.0: Initial version.
#

MCAST_GRP = "239.255.1.1"  # same as X-Plane 12
MCAST_PORT = 49505  # 49707 for XPlane12
MULTICAST_TTL = 2
FREQUENCY = 5.0  # will run every FREQUENCY seconds at most, never faster

CONFIG_DIR = "deckconfig"
CONFIG_FILE = "config.yaml"

DEFAULT_STRING_DATAREFS = [  # default is to return these, for Toliss Airbusses
    "AirbusFBW/FMA1w",
    "AirbusFBW/FMA1g",
    "AirbusFBW/FMA1b",
    "AirbusFBW/FMA2w",
    "AirbusFBW/FMA2b",
    "AirbusFBW/FMA2m",
    "AirbusFBW/FMA3w",
    "AirbusFBW/FMA3b",
    "AirbusFBW/FMA3a",
]


class PythonInterface:
    def __init__(self):
        self.Name = "String datarefs multicast"
        self.Sig = "xppython3.strdrefmcast"
        self.Desc = f"Fetches string-type datarefs at regular intervals and UPD multicast their values (Rel. {RELEASE})"
        self.Info = self.Name + f" (rel. {RELEASE})"
        self.enabled = False
        self.trace = True  # produces extra print/debugging in XPPython3.log for this class
        self.datarefs = {}
        self.use_defaults = False
        self.run_count = 0
        self.frequency = FREQUENCY

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, MULTICAST_TTL)
        self.RLock = RLock()

    def XPluginStart(self):
        if self.trace:
            print(self.Info, "started")

        return self.Name, self.Sig, self.Desc

    def XPluginStop(self):
        if self.trace:
            print(self.Info, "stopped")

    def XPluginEnable(self):
        xp.registerFlightLoopCallback(self.FlightLoopCallback, 1.0, 0)
        if self.trace:
            print(self.Info, "PI::XPluginEnable: flight loop registered")
        try:
            ac = xp.getNthAircraftModel(0)  # ('Cessna_172SP.acf', '/Volumns/SSD1/X-Plane/Aircraft/Laminar Research/Cessna 172SP/Cessna_172SP.acf')
            if len(ac) == 2:
                acpath = os.path.split(ac[1])  # ('/Volumns/SSD1/X-Plane/Aircraft/Laminar Research/Cessna 172SP', 'Cessna_172SP.acf')
                print(self.Info, "PI::XPluginEnable: trying " + acpath[0] + " ..")
                self.load(acpath=acpath[0])
                print(self.Info, "PI::XPluginEnable: " + acpath[0] + " done.")
                self.enabled = True
                if self.trace:
                    print(self.Info, "enabled")
                return 1
            print(self.Info, "PI::XPluginEnable: getNthAircraftModel: aircraft not found.")
            return 1
        except:
            if self.trace:
                print(self.Info, "PI::XPluginEnable: exception.")
            print_exc()
            self.enabled = False
            if self.trace:
                print(self.Info, "not enabled")
        return 0

    def XPluginDisable(self):
        xp.unregisterFlightLoopCallback(self.FlightLoopCallback, 0)
        if self.trace:
            print(self.Info, "PI::XPluginDisable: flight loop unregistered")
        self.enabled = False
        if self.trace:
            print(self.Info, "disabled")

    def XPluginReceiveMessage(self, inFromWho, inMessage, inParam):
        """
        When we receive a message that an aircraft was loaded, if it is the user aircraft,
        we try to load the aicraft deskconfig.
        If it does not exist, we default to a screen saver type of screen for the deck.
        """
        if inMessage == xp.MSG_PLANE_LOADED and inParam == 0:  # 0 is for the user aircraft, greater than zero will be for AI aircraft.
            print(self.Info, "PI::XPluginReceiveMessage: user aircraft received")
            try:
                ac = xp.getNthAircraftModel(0)  # ('Cessna_172SP.acf', '/Volumns/SSD1/X-Plane/Aircraft/Laminar Research/Cessna 172SP/Cessna_172SP.acf')
                if len(ac) == 2:
                    acpath = os.path.split(ac[1])  # ('/Volumns/SSD1/X-Plane/Aircraft/Laminar Research/Cessna 172SP', 'Cessna_172SP.acf')
                    if self.trace:
                        print(
                            self.Info,
                            "PI::XPluginReceiveMessage: trying " + acpath[0] + "..",
                        )
                    self.load(acpath=acpath[0])
                    if self.trace:
                        print(
                            self.Info,
                            "PI::XPluginReceiveMessage: .. " + acpath[0] + " done.",
                        )
                    return None
                print(
                    self.Info,
                    "PI::XPluginReceiveMessage: getNthAircraftModel: aircraft not found.",
                )
            except:
                if self.trace:
                    print(self.Info, "PI::XPluginReceiveMessage: exception.")
                print_exc()
                self.enabled = False
        return None

    def FlightLoopCallback(self, elapsedMe, elapsedSim, counter, refcon):
        if not self.enabled:
            return 0
        if self.run_count % 100 == 0:
            print(self.Info, f"PI::FlightLoopCallback: is alive ({self.run_count})")
        self.run_count = self.run_count + 1
        with self.RLock:
            drefvalues = {"ts": time.time()} | {d: xp.getDatas(self.datarefs[d]) for d in self.datarefs}
        fma_bytes = bytes(json.dumps(drefvalues), "utf-8")  # no time to think. serialize as json
        # if self.trace:
        #     print(self.Info, fma_bytes.decode("utf-8"))
        if len(fma_bytes) > 1472:
            print(
                self.Info,
                f"PI::FlightLoopCallback: returned value too large ({len(fma_bytes)}/1472)",
            )
        else:
            self.sock.sendto(fma_bytes, (MCAST_GRP, MCAST_PORT))
        return self.frequency

    def load(self, acpath):
        # Unload previous aircraft's command set.
        # Load current aircraft command set.
        #
        # remove previous command set
        new_dataref_set = {}

        # install this aircraft's set
        datarefs = self.get_string_datarefs(acpath)

        if len(datarefs) == 0:
            print(self.Info, f"PI::load: no string datarefs")
            if self.use_defaults:
                datarefs = DEFAULT_STRING_DATAREFS
                print(self.Info, f"PI::load: using defaults")

        # Find the data refs we want to record.
        for dataref in datarefs:
            dref = xp.findDataRef(dataref)
            if dref is not None:
                new_dataref_set[dataref] = dref
                if self.trace:
                    print(self.Info, f"PI::load: added string dataref {dataref}")
            else:
                print(self.Info, f"PI::load: dataref {dataref} not found")

        if len(new_dataref_set) > 0:
            with self.RLock:
                self.datarefs = new_dataref_set
            if self.trace:
                print(self.Info, f"PI::load: new dataref set installed {', '.join(new_dataref_set.keys())}")
            # adjust frequency since operation is expensive
            self.frequency = max(len(self.datarefs), FREQUENCY)
            if self.trace:
                print(self.Info, f"PI::load: frequency adjusted to {self.frequency}")

    def get_string_datarefs(self, acpath):
        # Scans an aircraft deckconfig and collects long press commands.
        #
        # Internal constants (keywords in yaml file)
        #
        DEBUG = False
        config_file = os.path.join(acpath, CONFIG_DIR, CONFIG_FILE)
        if not os.path.exists(config_file):
            print(
                self.Info,
                f"PI::get_string_datarefs: Cockpitdecks config file '{config_file}' not found",
            )
            return []
        with open(config_file, "r", encoding="utf-8") as config_fp:
            config = yaml.load(config_fp)
            self.use_defaults = config.get("use-default-string-datarefs", False)
            ret = config.get("string-datarefs", [])
            if self.trace:
                print(
                    self.Info,
                    f"PI::get_string_datarefs: Cockpitdecks config file '{config_file}' loaded, config length={len(ret)}, use default={self.use_defaults}.",
                )
            return ret


# #####################################################@
# Multicast client
# Adapted from: http://chaos.weblogs.us/archives/164

# import socket

# ANY = "0.0.0.0"

# MCAST_GRP = "239.255.1.1"
# MCAST_PORT = 49505  # (MCAST_PORT is 49707 for XPlane12)

# # Create a UDP socket
# sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)

# # Allow multiple sockets to use the same PORT number
# sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)

# # Bind to the port that we know will receive multicast data
# sock.bind((ANY, MCAST_PORT))

# # Tell the kernel that we want to add ourselves to a multicast group
# # The address for the multicast group is the third param
# status = sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, socket.inet_aton(MCAST_GRP) + socket.inet_aton(ANY))

# # setblocking(False) is equiv to settimeout(0.0) which means we poll the socket.
# # But this will raise an error if recv() or send() can't immediately find or send data.
# sock.setblocking(False)

# while 1:
#     try:
#         data, addr = sock.recvfrom(1024)
#     except socket.error as e:
#         pass
#     else:
#         print("From: ", addr)
#         print("Data: ", data)
