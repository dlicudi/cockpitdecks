# Class for interface with X-Plane using UDP protocol.
#
import os
import socket
import struct
import binascii
import platform
import threading
import logging
import time
import json
from datetime import datetime, timedelta, timezone

from cockpitdecks import SPAM_LEVEL, AIRCRAFT_CHANGE_MONITORING_DATAREF
from cockpitdecks.simulator import Simulator, Dataref, Command, DatarefEvent
from cockpitdecks.resources.intdatarefs import INTERNAL_DATAREF

logger = logging.getLogger(__name__)
# logger.setLevel(SPAM_LEVEL)  # To see which dataref are requested
# logger.setLevel(logging.DEBUG)

# Data too delicate to be put in constant.py
# !! adjust with care !!
# UDP sends at most ~40 to ~50 dataref values per packet.
LOOP_ALIVE = 100  # report loop activity every 1000 executions on DEBUG, set to None to suppress output
RECONNECT_TIMEOUT = 10  # seconds
SOCKET_TIMEOUT = 5  # seconds
MAX_TIMEOUT_COUNT = 5  # after x timeouts, assumes connection lost, disconnect, and restart later
MAX_DREF_COUNT = 80  # Maximum number of dataref that can be requested to X-Plane, CTD around ~100 datarefs

# String dataref listener
ANY = "0.0.0.0"
SDL_MCAST_PORT = 49505
SDL_MCAST_GRP = "239.255.1.1"

SDL_UPDATE_FREQ = 5.0  # same starting value as PI_string_datarefs_udp.FREQUENCY  (= 5.0 default)
SDL_SOCKET_TIMEOUT = SDL_UPDATE_FREQ + 1.0  # should be larger or equal to PI_string_datarefs_udp.FREQUENCY

XP_MIN_VERSION = 121100

# When this dataref changes, the loaded aircraft has changed
#
DATETIME_DATAREFS = [
    "sim/time/local_date_days",
    "sim/time/local_time_sec",
    "sim/time/zulu_time_sec",
    "sim/time/use_system_time",
]
REPLAY_DATAREFS = [
    "sim/time/is_in_replay",
    "sim/time/sim_speed",
    "sim/time/sim_speed_actual",
]


INTDREF_CONNECTION_STATUS = "_connection_status"
# Status value:
# 0: Nothing running
# 1: Connection monitor running
# 2: Connection to X-Plane but no more
# 3: UDP listener running (no timeout)
# 4: Event forwarder running


# XPlaneBeacon
# Beacon-specific error classes
class XPlaneIpNotFound(Exception):
    args = "Could not find any running XPlane instance in network."


class XPlaneVersionNotSupported(Exception):
    args = "XPlane version not supported."


class XPlaneBeacon:
    """
    Get data from XPlane via network.
    Use a class to implement RAI Pattern for the UDP socket.
    """

    # constants
    MCAST_GRP = "239.255.1.1"
    MCAST_PORT = 49707  # (MCAST_PORT was 49000 for XPlane10)
    BEACON_TIMEOUT = 3.0  # seconds

    def __init__(self):
        # Open a UDP Socket to receive on Port 49000
        self.socket = None

        hostname = socket.gethostname()
        self.local_ip = socket.gethostbyname(hostname)

        self.beacon_data = {}

        self.should_not_connect = None  # threading.Event()
        self.connect_thread = None  # threading.Thread()

    @property
    def connected(self):
        return "IP" in self.beacon_data.keys()

    def FindIp(self):
        """
        Find the IP of XPlane Host in Network.
        It takes the first one it can find.
        """
        if self.socket is not None:
            self.socket.close()
            self.socket = None
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        self.beacon_data = {}

        # open socket for multicast group.
        # this socker is for getting the beacon, it can be closed when beacon is found.
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)  # SO_REUSEPORT?
        if platform.system() == "Windows":
            sock.bind(("", self.MCAST_PORT))
        else:
            sock.bind((self.MCAST_GRP, self.MCAST_PORT))
        mreq = struct.pack("=4sl", socket.inet_aton(self.MCAST_GRP), socket.INADDR_ANY)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        sock.settimeout(XPlaneBeacon.BEACON_TIMEOUT)

        # receive data
        try:
            packet, sender = sock.recvfrom(1472)
            logger.debug(f"XPlane Beacon: {packet.hex()}")
            self.inc(INTERNAL_DATAREF.UDP_BEACON_RCV.value)

            # decode data
            # * Header
            header = packet[0:5]
            if header != b"BECN\x00":
                logger.warning(f"Unknown packet from {sender[0]}, {str(len(packet))} bytes:")
                logger.warning(packet)
                logger.warning(binascii.hexlify(packet))

            else:
                # * Data
                data = packet[5:21]
                # struct becn_struct
                # {
                #   uchar beacon_major_version;     // 1 at the time of X-Plane 10.40
                #   uchar beacon_minor_version;     // 1 at the time of X-Plane 10.40
                #   xint application_host_id;       // 1 for X-Plane, 2 for PlaneMaker
                #   xint version_number;            // 104014 for X-Plane 10.40b14
                #   uint role;                      // 1 for master, 2 for extern visual, 3 for IOS
                #   ushort port;                    // port number X-Plane is listening on
                #   xchr    computer_name[strDIM];  // the hostname of the computer
                # };
                beacon_major_version = 0
                beacon_minor_version = 0
                application_host_id = 0
                xplane_version_number = 0
                role = 0
                port = 0
                (
                    beacon_major_version,  # 1 at the time of X-Plane 10.40
                    beacon_minor_version,  # 1 at the time of X-Plane 10.40
                    application_host_id,  # 1 for X-Plane, 2 for PlaneMaker
                    xplane_version_number,  # 104014 for X-Plane 10.40b14
                    role,  # 1 for master, 2 for extern visual, 3 for IOS
                    port,  # port number X-Plane is listening on
                ) = struct.unpack("<BBiiIH", data)
                hostname = packet[21:-1]  # the hostname of the computer
                hostname = hostname[0 : hostname.find(0)]
                if beacon_major_version == 1 and beacon_minor_version <= 2 and application_host_id == 1:
                    self.beacon_data["IP"] = sender[0]
                    self.beacon_data["Port"] = port
                    self.beacon_data["hostname"] = hostname.decode()
                    self.beacon_data["XPlaneVersion"] = xplane_version_number
                    self.beacon_data["role"] = role
                    logger.info(f"XPlane Beacon Version: {beacon_major_version}.{beacon_minor_version}.{application_host_id}")
                    #
                    s = "does not appear"
                    if self.runs_locally():
                        s = "appears"
                        if self.xp_home is not None and os.path.isdir(self.xp_home):
                            logger.info(f"XPlane home directory {self.xp_home}")
                    logger.info(f"XPlane {s} to run locally ({self.local_ip}/{self.beacon_data['IP']})")
                    if self.runs_locally() and self.xp_home is not None and os.path.isdir(self.xp_home):
                        logger.info(f"XPlane home directory {self.xp_home}")
                    #
                else:
                    logger.warning(f"XPlane Beacon Version not supported: {beacon_major_version}.{beacon_minor_version}.{application_host_id}")
                    raise XPlaneVersionNotSupported()

        except socket.timeout:
            logger.debug("XPlane IP not found.")
            self.inc(INTERNAL_DATAREF.UDP_BEACON_TIMEOUT.value)
            raise XPlaneIpNotFound()
        finally:
            sock.close()

        return self.beacon_data

    def start(self):
        logger.warning("nothing to start")

    def stop(self):
        logger.warning("nothing to stop")

    def cleanup(self):
        logger.warning("nothing to clean up")

    def connect_loop(self):
        """
        Trys to connect to X-Plane indefinitely until self.should_not_connect is set.
        If a connection fails, drops, disappears, will try periodically to restore it.
        """
        logger.debug("starting..")
        WARN_FREQ = 10
        cnt = 0
        while self.should_not_connect is not None and not self.should_not_connect.is_set():
            if not self.connected:
                try:
                    self.FindIp()
                    if self.connected:
                        logger.info(f"beacon: {self.beacon_data}")
                        if "XPlaneVersion" in self.beacon_data:
                            curr = self.beacon_data["XPlaneVersion"]
                            if curr < XP_MIN_VERSION:
                                logger.warning(f"X-Plane version {curr} detected, minimal version is {XP_MIN_VERSION}")
                                logger.warning(f"Some features in Cockpitdecks may not work properly")
                            else:
                                logger.info(f"X-Plane version {curr} meets minima (>={XP_MIN_VERSION})")
                        logger.debug("..connected, starting dataref listener..")
                        self.start()
                        self.inc(INTERNAL_DATAREF.STARTS.value)
                        logger.info("..dataref listener started..")
                except XPlaneVersionNotSupported:
                    self.beacon_data = {}
                    logger.error("..X-Plane Version not supported..")
                except XPlaneIpNotFound:
                    self.beacon_data = {}
                    if cnt % WARN_FREQ == 0:
                        logger.error(f"..X-Plane instance not found on local network.. ({datetime.now().strftime('%H:%M:%S')})")
                    cnt = cnt + 1
                if not self.connected:
                    self.should_not_connect.wait(RECONNECT_TIMEOUT)
                    logger.debug("..trying..")
            else:
                self.should_not_connect.wait(RECONNECT_TIMEOUT)  # could be n * RECONNECT_TIMEOUT
                logger.debug("..monitoring connection..")
        logger.debug("..ended")

    # ################################
    # Interface
    #
    def connect(self):
        """
        Starts connect loop.
        """
        if self.should_not_connect is None:
            self.should_not_connect = threading.Event()
            self.connect_thread = threading.Thread(target=self.connect_loop, name="XPlaneBeacon::connect_loop")
            self.connect_thread.start()
            logger.debug("connect_loop started")
        else:
            logger.debug("connect_loop already started")

    def disconnect(self):
        """
        End connect loop and disconnect
        """
        if self.should_not_connect is not None:
            logger.debug("disconnecting..")
            self.cleanup()
            self.beacon_data = {}
            self.should_not_connect.set()
            wait = RECONNECT_TIMEOUT
            logger.debug(f"..asked to stop connect_loop.. (this may last {wait} secs.)")
            self.connect_thread.join(timeout=wait)
            if self.connect_thread.is_alive():
                logger.warning(f"..thread may hang..")
            self.should_not_connect = None
            logger.debug("..disconnected")
        else:
            if self.connected:
                self.beacon_data = {}
                logger.debug("..connect_loop not running..disconnected")
            else:
                logger.debug("..not connected")


class XPlane(Simulator, XPlaneBeacon):
    """
    Get data from XPlane via network.
    Use a class to implement RAI Pattern for the UDP socket.
    """

    # constants
    MCAST_GRP = "239.255.1.1"
    MCAST_PORT = 49707  # (MCAST_PORT was 49000 for XPlane10)
    BEACON_TIMEOUT = 3.0  # seconds
    TERMINATE_QUEUE = "quit"

    def __init__(self, cockpit, environ):
        # list of requested datarefs with index number
        self.datarefidx = 0
        self.datarefs = {}  # key = idx, value = dataref path
        self._max_monitored = 0

        self.udp_event = None  # thread to read X-Plane UDP port for datarefs
        self.udp_thread = None
        self._dref_cache = {}

        self.dref_event = None  # thread to read XPPython3 PI_string_datarefs_udp alternate UDP port for string datarefs
        self.dref_thread = None
        self._strdref_cache = {}

        self.xp_home = environ.get("XP_HOME")
        self.api_host = environ.get("API_HOST")
        self.api_port = environ.get("API_PORT")
        self.api_path = environ.get("API_PATH")

        Simulator.__init__(self, cockpit=cockpit, environ=environ)
        self.cockpit.set_logging_level(__name__)

        XPlaneBeacon.__init__(self)

        self.socket_strdref = None

        self.init()

    def init(self):
        if self._inited:
            return

        # Register special datarefs for internal monitoring
        dref = self.get_dataref(AIRCRAFT_CHANGE_MONITORING_DATAREF, is_string=True)
        dref.add_listener(self.cockpit)  # Wow wow wow
        logger.info(f"aircraft dataref is {AIRCRAFT_CHANGE_MONITORING_DATAREF}")

        self.add_datetime_datarefs()

        self.set_internal_dataref(path=INTDREF_CONNECTION_STATUS, value=0, cascade=True)

        # Setup socket reception for string-datarefs
        self.socket_strdref = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        # Allow multiple sockets to use the same PORT number
        self.socket_strdref.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)  # SO_REUSEPORT

        self.socket_strdref.bind((ANY, SDL_MCAST_PORT))
        # Tell the kernel that we want to add ourselves to a multicast group
        # The address for the multicast group is the third param
        status = self.socket_strdref.setsockopt(
            socket.IPPROTO_IP,
            socket.IP_ADD_MEMBERSHIP,
            socket.inet_aton(SDL_MCAST_GRP) + socket.inet_aton(ANY),
        )

        self._inited = True

    def __del__(self):
        if not self._inited:
            return
        for i in range(len(self.datarefs)):
            self.add_dataref_to_monitor(next(iter(self.datarefs.values())), freq=0)
        self.disconnect()

    @property
    def api_url(self):
        if self.connected:
            host = self.api_host
            if host is None:
                host = self.beacon_data["IP"]
            return f"http://{host}:{self.api_port}/{self.api_path}"
        return None

    def runs_locally(self) -> bool:
        if self.connected:
            logger.debug(f"local ip {self.local_ip} vs beacon {self.beacon_data['IP']}")
        else:
            logger.debug(f"local ip {self.local_ip} but not connected to X-Plane")
        return False if not self.connected else self.local_ip == self.beacon_data["IP"]

    #
    # Datarefs
    def add_datetime_datarefs(self):
        dtdrefs = {}
        for d in DATETIME_DATAREFS:
            dtdrefs[d] = self.get_dataref(d)
        self.add_datarefs_to_monitor(dtdrefs)
        logger.info("monitoring simulator date/time datarefs")

    def datetime(self, zulu: bool = False, system: bool = False) -> datetime:
        """Returns the simulator date and time"""
        if not DATETIME_DATAREFS[0] in self.all_datarefs.keys():  # hack, means dref not created yet
            return super().datetime(zulu=zulu, system=system)
        now = datetime.now().astimezone()
        days = self.get_dataref_value("sim/time/local_date_days")
        secs = self.get_dataref_value("sim/time/local_date_sec")
        if not system and days is not None and secs is not None:
            simnow = datetime(year=now.year, month=1, day=1, hour=0, minute=0, second=0, microsecond=0).astimezone()
            simnow = simnow + timedelta(days=days) + timedelta(days=secs)
            return simnow
        return now

    def get_dataref(self, path: str, is_string: bool = False):
        if path in self.all_datarefs.keys():
            return self.all_datarefs[path]
        return self.register(dataref=Dataref(path, is_string=is_string))

    # Shortcuts
    def get_internal_dataref(self, path: str, is_string: bool = False):
        if not Dataref.is_internal_dataref(path):  # prevent duplicate prepend
            path = Dataref.mk_internal_dataref(path)
        return self.get_dataref(path=path, is_string=is_string)

    def set_internal_dataref(self, path: str, value: float, cascade: bool):
        int_path = Dataref.mk_internal_dataref(path)
        if cascade:
            e = DatarefEvent(sim=self, dataref=int_path, value=value, cascade=cascade)
        else:  # just save the value, do not cascade
            dref = self.get_dataref(path=int_path)
            dref.update_value(new_value=value, cascade=cascade)

    def inc_internal_dataref(self, path: str, amount: float, cascade: bool = False):
        dref = self.get_internal_dataref(path=path)
        curr = dref.value()
        if curr is None:
            curr = 0
        newvalue = curr + amount
        self.set_internal_dataref(path=path, value=newvalue, cascade=cascade)

    def inc(self, path: str, amount: float = 1.0, cascade: bool = False):
        # shortcut alias
        self.inc_internal_dataref(path=path, amount=amount, cascade=cascade)

    #
    # Commands
    def execute_command(self, command: Command):
        if command is None:
            logger.warning(f"no command")
            return
        elif not command.is_valid():
            logger.warning(f"command '{command}' not sent (command placeholder, no command, do nothing)")
            return
        if not self.connected:
            logger.warning(f"no connection ({command})")
            return
        if command.path is not None:
            message = "CMND0" + command.path
            self.socket.sendto(message.encode(), (self.beacon_data["IP"], self.beacon_data["Port"]))
            logger.log(SPAM_LEVEL, f"execute_command: executed {command}")
        else:
            logger.warning("execute_command: no command")

    def write_dataref(self, dataref: str, value: float | int | bool, vtype: str = "float") -> bool:
        """
        Write Dataref to XPlane
        DREF0+(4byte byte value)+dref_path+0+spaces to complete the whole message to 509 bytes
        DREF0+(4byte byte value of 1)+ sim/cockpit/switches/anti_ice_surf_heat_left+0+spaces to complete to 509 bytes
        """
        path = dataref
        if Dataref.is_internal_dataref(path):
            d = self.get_dataref(path)
            d.update_value(new_value=value, cascade=True)
            logger.debug(f"written local dataref ({path}={value})")
            return False

        if not self.connected:
            logger.warning(f"no connection ({path}={value})")
            return False

        cmd = b"DREF\x00"
        path = path + "\x00"
        string = path.ljust(500).encode()
        message = "".encode()
        if vtype == "float":
            message = struct.pack("<5sf500s", cmd, value, string)
        elif vtype == "int":
            message = struct.pack("<5si500s", cmd, value, string)
        elif vtype == "bool":
            message = struct.pack("<5sI500s", cmd, int(value), string)

        assert len(message) == 509
        logger.debug(f"sending ({self.beacon_data['IP']}, {self.beacon_data['Port']}): {path}={value} ..")
        logger.log(SPAM_LEVEL, f"write_dataref: {path}={value}")
        self.socket.sendto(message, (self.beacon_data["IP"], self.beacon_data["Port"]))
        logger.debug(".. sent")
        return True

    def add_dataref_to_monitor(self, path, freq=None):
        """
        Configure XPlane to send the dataref with a certain frequency.
        You can disable a dataref by setting freq to 0.
        """
        if Dataref.is_internal_dataref(path):
            logger.debug(f"{path} is local and does not need X-Plane monitoring")
            return False

        if not self.connected:
            logger.warning(f"no connection ({path}, {freq})")
            return False

        idx = -9999
        if freq is None:
            freq = self.DEFAULT_REQ_FREQUENCY

        if path in self.datarefs.values():
            idx = list(self.datarefs.keys())[list(self.datarefs.values()).index(path)]
            if freq == 0 and idx in self.datarefs.keys():
                # logger.debug(f">>>>>>>>>>>>>> {path} DELETING INDEX {idx}")
                del self.datarefs[idx]
        else:
            if freq != 0 and len(self.datarefs) > MAX_DREF_COUNT:
                # logger.warning(f"requesting too many datarefs ({len(self.datarefs)})")
                return False

            idx = self.datarefidx
            self.datarefs[self.datarefidx] = path
            self.datarefidx += 1

        self._max_monitored = max(self._max_monitored, len(self.datarefs))

        cmd = b"RREF\x00"
        string = path.encode()
        message = struct.pack("<5sii400s", cmd, freq, idx, string)
        assert len(message) == 413
        self.socket.sendto(message, (self.beacon_data["IP"], self.beacon_data["Port"]))
        if self.datarefidx % LOOP_ALIVE == 0:
            time.sleep(0.2)
        return True

    def remove_dataref_from_monitor(self, path):
        return self.add_dataref_to_monitor(path, freq=0)

    def udp_enqueue(self):
        """Read and decode socket messages and enqueue dataref values

        Terminates after 5 timeouts.
        """
        logger.debug("starting dataref listener..")
        number_of_timeouts = 0
        total_reads = 0
        total_values = 0
        last_read_ts = datetime.now()
        total_read_time = 0.0
        self.set_internal_dataref(path=INTDREF_CONNECTION_STATUS, value=3, cascade=True)
        while self.udp_event is not None and not self.udp_event.is_set():
            if len(self.datarefs) > 0:
                try:
                    # Receive packet
                    self.socket.settimeout(SOCKET_TIMEOUT)
                    data, addr = self.socket.recvfrom(1472)  # maximum bytes of an RREF answer X-Plane will send (Ethernet MTU - IP hdr - UDP hdr)
                    # Decode Packet
                    self.set_internal_dataref(path=INTDREF_CONNECTION_STATUS, value=4, cascade=True)
                    self.inc(INTERNAL_DATAREF.UDP_READS.value)
                    # Read the Header "RREF,".
                    number_of_timeouts = 0
                    total_reads = total_reads + 1
                    now = datetime.now()
                    delta = now - last_read_ts
                    self.set_internal_dataref(
                        path=INTERNAL_DATAREF.LAST_READ.value,
                        value=delta.microseconds,
                        cascade=True,
                    )
                    total_read_time = total_read_time + delta.microseconds / 1000000
                    last_read_ts = now
                    header = data[0:5]
                    if header == b"RREF,":  # (was b"RREFO" for XPlane10)
                        # We get 8 bytes for every dataref sent:
                        # An integer for idx and the float value.
                        values = data[5:]
                        lenvalue = 8
                        numvalues = int(len(values) / lenvalue)
                        self.inc(INTERNAL_DATAREF.VALUES.value, amount=numvalues)
                        total_values = total_values + numvalues
                        for i in range(0, numvalues):
                            singledata = data[(5 + lenvalue * i) : (5 + lenvalue * (i + 1))]
                            (idx, value) = struct.unpack("<if", singledata)

                            d = self.datarefs.get(idx)
                            if d is not None:
                                # Should cache with roundings applied
                                if value < 0.0 and value > -0.001:  # convert -0.0 values to positive 0.0
                                    value = 0.0
                                v = value
                                if d == DATETIME_DATAREFS[2]:  # zulu secs
                                    now = datetime.now().astimezone(tz=timezone.utc)
                                    seconds_since_midnight = (now - now.replace(hour=0, minute=0, second=0, microsecond=0)).total_seconds()
                                    diff = v - seconds_since_midnight
                                    self.set_internal_dataref(
                                        path=INTERNAL_DATAREF.ZULU_DIFFERENCE.value,
                                        value=diff,
                                        cascade=(total_reads % 2 == 0),
                                    )
                                r = self.get_rounding(dataref_path=d)
                                if r is not None and value is not None:
                                    v = round(value, r)
                                if d not in self._dref_cache or (d in self._dref_cache and self._dref_cache[d] != v):
                                    e = DatarefEvent(
                                        sim=self,
                                        dataref=d,
                                        value=value,
                                        cascade=d in self.datarefs_to_monitor.keys(),
                                    )
                                    self.inc(INTERNAL_DATAREF.UPDATE_ENQUEUED.value)
                                    self._dref_cache[d] = v
                            else:
                                logger.debug(f"no dataref ({values}), probably no longer monitored")
                    else:
                        logger.warning(f"{binascii.hexlify(data)}")
                    if total_reads % 10 == 0:
                        logger.debug(
                            f"average socket time between reads {round(total_read_time / total_reads, 3)} ({total_reads} reads; {total_values} values sent)"
                        )  # ignore
                except:  # socket timeout
                    number_of_timeouts = number_of_timeouts + 1
                    logger.info(f"socket timeout received ({number_of_timeouts}/{MAX_TIMEOUT_COUNT})")  # ignore
                    self.set_internal_dataref(path=INTDREF_CONNECTION_STATUS, value=2, cascade=True)
                    if number_of_timeouts >= MAX_TIMEOUT_COUNT:  # attemps to reconnect
                        logger.warning("too many times out, disconnecting, udp_enqueue terminated")  # ignore
                        self.beacon_data = {}
                        if self.udp_event is not None and not self.udp_event.is_set():
                            self.udp_event.set()
                        self.set_internal_dataref(path=INTDREF_CONNECTION_STATUS, value=1, cascade=True)
                        self.inc(INTERNAL_DATAREF.STOPS.value)
        self.udp_event = None
        self.set_internal_dataref(path=INTDREF_CONNECTION_STATUS, value=2, cascade=True)
        logger.debug("..dataref listener terminated")

    def strdref_enqueue(self):
        logger.info("starting string dataref listener..")
        frequency = max(SDL_SOCKET_TIMEOUT, SDL_UPDATE_FREQ)
        total_to = 0
        tot_items = 0
        total_reads = 0
        last_read_ts = datetime.now()
        total_read_time = 0.0
        src_last_ts = 0
        src_cnt = 0
        src_tot = 0

        while self.dref_event is not None and not self.dref_event.is_set():
            try:
                self.socket_strdref.settimeout(frequency)
                data, addr = self.socket_strdref.recvfrom(1024)
                self.set_internal_dataref(path=INTDREF_CONNECTION_STATUS, value=4, cascade=True)
                total_to = 0
                total_reads = total_reads + 1
                now = datetime.now()
                delta = now - last_read_ts
                total_read_time = total_read_time + delta.microseconds / 1000000
                last_read_ts = now
                logger.debug("string dataref listener: got data")  # \n({json.dumps(json.loads(data.decode('utf-8')), indent=2)})
                data = json.loads(data.decode("utf-8"))

                meta = data  # older version carried meta data directly in message
                if "meta" in data:  # some meta data in string values message
                    meta = data["meta"]
                    del data["meta"]

                ts = 0
                if "ts" in meta:
                    ts = meta["ts"]
                    del meta["ts"]
                    if src_last_ts > 0:
                        src_tot = src_tot + (ts - src_last_ts)
                        src_cnt = src_cnt + 1
                        self.collector_avgtime = src_tot / src_cnt
                        if src_cnt % 100 == 0:
                            logger.info(
                                f"string dataref listener: average time between reads {round(self.collector_avgtime, 4)} ({round(tot_items/total_reads,0)})"
                            )
                    src_last_ts = ts

                freq = None
                oldf = frequency
                if "f" in meta:
                    freq = meta["f"]
                    del meta["f"]
                    if freq is not None and (oldf != (freq + 1)):
                        frequency = freq + 1
                        logger.info(f"string dataref listener: {len(data)} strings, adjusted frequency to {frequency} secs")
                for k, v in data.items():  # simple cache mechanism
                    tot_items = tot_items + 1
                    if k not in self._strdref_cache or (k in self._strdref_cache and self._strdref_cache[k] != v):
                        e = DatarefEvent(sim=self, dataref=k, value=v, cascade=True)
                        self._strdref_cache[k] = v
            except:
                total_to = total_to + 1
                logger.debug(
                    f"string dataref listener: socket timeout ({frequency} secs.) received ({total_to})",
                    exc_info=(logger.level == logging.DEBUG),
                )
                self.set_internal_dataref(path=INTDREF_CONNECTION_STATUS, value=2, cascade=True)
                frequency = frequency + 1

        self.dref_event = None
        # Bind to the port that we know will receive multicast data
        # self.socket_strdref.shutdown()
        # self.socket_strdref.close()
        # logger.info("..strdref socket closed..")
        self.set_internal_dataref(path=INTDREF_CONNECTION_STATUS, value=3, cascade=True)
        logger.debug("..string dataref listener terminated")

    # ################################
    # X-Plane Interface
    #
    def command_once(self, command: Command):
        self.execute_command(command)

    def command_begin(self, command: Command):
        if command.path is not None:
            self.execute_command(Command(command.path + "/begin"))
        else:
            logger.warning(f"no command")

    def command_end(self, command: Command):
        if command.path is not None:
            self.execute_command(Command(command.path + "/end"))
        else:
            logger.warning(f"no command")

    def remove_local_datarefs(self, datarefs) -> list:
        return list(filter(lambda d: not Dataref.is_internal_dataref(d), datarefs))

    def clean_datarefs_to_monitor(self):
        if not self.connected:
            logger.warning("no connection")
            return
        for i in range(len(self.datarefs)):
            self.add_dataref_to_monitor(next(iter(self.datarefs.values())), freq=0)
        super().clean_datarefs_to_monitor()
        self._strdref_cache = {}
        self._dref_cache = {}
        logger.debug("done")

    def add_datarefs_to_monitor(self, datarefs):
        if not self.connected:
            logger.warning("no connection")
            logger.debug(f"would add {self.remove_local_datarefs(datarefs.keys())}")
            return
        # Add those to monitor
        super().add_datarefs_to_monitor(datarefs)
        prnt = []
        for d in datarefs.values():
            if d.is_internal:
                logger.debug(f"local dataref {d.path} is not monitored")
                continue
            if d.is_string:
                logger.debug(f"string dataref {d.path} is not monitored")
                continue
            if self.add_dataref_to_monitor(d.path, freq=d.update_frequency):
                prnt.append(d.path)

        # Add aircraft
        dref_ipc = self.get_dataref(AIRCRAFT_CHANGE_MONITORING_DATAREF)
        if self.add_dataref_to_monitor(dref_ipc.path, freq=dref_ipc.update_frequency):
            prnt.append(dref_ipc.path)
            super().add_datarefs_to_monitor({dref_ipc.path: dref_ipc})

        logger.log(SPAM_LEVEL, f"add_datarefs_to_monitor: added {prnt}")
        logger.info(f">>>>> monitoring++{len(datarefs)}/{len(self.datarefs)}/{self._max_monitored}")

    def remove_datarefs_to_monitor(self, datarefs):
        if not self.connected and len(self.datarefs_to_monitor) > 0:
            logger.warning("no connection")
            logger.debug(f"would remove {datarefs.keys()}/{self._max_monitored}")
            return
        # Add those to monitor
        prnt = []
        for d in datarefs.values():
            if d.is_internal:
                logger.debug(f"local dataref {d.path} is not monitored")
                continue
            if d.path in self.datarefs_to_monitor.keys():
                if self.datarefs_to_monitor[d.path] == 1:  # will be decreased by 1 in super().remove_datarefs_to_monitor()
                    if self.add_dataref_to_monitor(d.path, freq=0):
                        prnt.append(d.path)
                else:
                    logger.debug(f"{d.path} monitored {self.datarefs_to_monitor[d.path]} times")
            else:
                logger.debug(f"no need to remove {d.path}")

        # Add aircraft path
        dref_ipc = self.get_dataref(AIRCRAFT_CHANGE_MONITORING_DATAREF)
        if self.add_dataref_to_monitor(dref_ipc.path, freq=0):
            prnt.append(dref_ipc.path)
            super().remove_datarefs_to_monitor({dref_ipc.path: dref_ipc})

        logger.debug(f"removed {prnt}")
        super().remove_datarefs_to_monitor(datarefs)
        logger.info(f">>>>> monitoring--{len(datarefs)}/{len(self.datarefs)}/{self._max_monitored}")

    def remove_all_datarefs(self):
        if not self.connected and len(self.all_datarefs) > 0:
            logger.warning("no connection")
            logger.debug(f"would remove {self.all_datarefs.keys()}")
            return
        # Not necessary:
        # self.remove_datarefs_to_monitor(self.all_datarefs)
        super().remove_all_datarefs()

    def add_all_datarefs_to_monitor(self):
        if not self.connected:
            logger.warning("no connection")
            return
        # Add always monitored drefs
        self.add_datetime_datarefs()
        # Add those to monitor
        prnt = []
        for path in self.datarefs_to_monitor.keys():
            d = self.all_datarefs.get(path)
            if d is not None and not d.is_string:
                if self.add_dataref_to_monitor(d.path, freq=d.update_frequency):
                    prnt.append(d.path)
                else:
                    logger.warning(f"no dataref {path}")
        logger.log(SPAM_LEVEL, f"added {prnt}")

        # Add collector ticker
        # self.collector.add_ticker()
        # logger.info("..dataref sets collector ticking..")

    def cleanup(self):
        """
        Called when before disconnecting.
        Just before disconnecting, we try to cancel dataref UDP reporting in X-Plane
        """
        self.clean_datarefs_to_monitor()

    def start(self):
        if not self.connected:
            logger.warning("no IP address. could not start.")
            return

        if self.udp_event is None:  # Thread for X-Plane datarefs
            self.udp_event = threading.Event()
            self.udp_thread = threading.Thread(target=self.udp_enqueue, name="XPlaneUDP::udp_enqueue")
            self.udp_thread.start()
            logger.info("dataref listener started")
        else:
            logger.info("dataref listener already running.")

        if self.dref_thread is None:  # Thread for string datarefs
            self.dref_event = threading.Event()
            self.dref_thread = threading.Thread(target=self.strdref_enqueue, name="XPlaneUDP::strdref_enqueue")
            self.dref_thread.start()
            logger.info("string dataref listener started")
        else:
            logger.info("string dataref listener running.")

        # When restarted after network failure, should clean all datarefs
        # then reload datarefs from current page of each deck
        self.clean_datarefs_to_monitor()
        self.add_all_datarefs_to_monitor()
        logger.info("reloading pages")
        self.cockpit.reload_pages()  # to take into account updated values
        # this is a test, ignore
        self.get_init_datarefs()

    def get_init_datarefs(self):
        # Test function for hastily get some dataref values
        # through the XP 12.1.1 Web REST API
        #
        dref = self.get_dataref(AIRCRAFT_CHANGE_MONITORING_DATAREF, is_string=True)
        logger.info(f"{dref.path}={dref.get_value(self)}")

    def stop(self):
        if self.udp_event is not None:
            self.udp_event.set()
            logger.debug("stopping dataref listener..")
            wait = SOCKET_TIMEOUT
            logger.debug(f"..asked to stop dataref listener (this may last {wait} secs. for UDP socket to timeout)..")
            self.udp_thread.join(wait)
            if self.udp_thread.is_alive():
                logger.warning("..thread may hang in socket.recvfrom()..")
            self.udp_event = None
            logger.debug("..dataref listener stopped")
        else:
            logger.debug("dataref listener not running")

        if self.dref_event is not None and self.dref_thread is not None:
            self.dref_event.set()
            logger.debug("stopping string dataref listener..")
            timeout = max(SDL_SOCKET_TIMEOUT, SDL_UPDATE_FREQ)
            logger.debug(f"..asked to stop string dataref listener (this may last {timeout} secs. for UDP socket to timeout)..")
            self.dref_thread.join(timeout)
            if self.dref_thread.is_alive():
                logger.warning("..thread may hang in socket.recvfrom()..")
            else:
                self.dref_event = None
            logger.debug("..string dataref listener stopped")
        else:
            logger.debug("string dataref listener not running")

    # ################################
    # Cockpit interface
    #
    def terminate(self):
        logger.debug(f"currently {'not ' if self.udp_event is None else ''}running. terminating..")
        self.clean_datarefs_to_monitor()  # stop monitoring all datarefs
        self.remove_all_datarefs()
        logger.info("terminating..disconnecting..")
        self.disconnect()
        logger.info("..stopping..")
        self.stop()
        logger.info("..terminated")
