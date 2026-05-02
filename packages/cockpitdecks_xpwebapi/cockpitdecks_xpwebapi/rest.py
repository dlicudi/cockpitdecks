"""X-Plane Web API access through REST API"""

import logging
import threading
import base64
from datetime import timedelta
from typing import List
from enum import Enum

import requests
from natsort import natsorted
from packaging.version import Version

from .api import CONNECTION_STATUS, DATAREF_DATATYPE, API, Dataref, DatarefMeta, Command, CommandMeta, Cache, webapi_logger, DatarefValueType, meta_queue

# local logging
logger = logging.getLogger(__name__)
# logger.setLevel(logging.DEBUG)


RUNNING_TIME = "sim/time/total_running_time_sec"
FLYING_TIME = "sim/time/total_flight_time_sec"  # Total time since the flight got reset by something

# /api/capabilities introduced in /api/v2. Here is a default one for v1.
V1_CAPABILITIES = {"api": {"versions": ["v1"]}, "x-plane": {"version": "12.1.1"}}

# When accessing API from remote host, this is the default port number for the **proxy** to X-Plane standard :8086 port.
# Can be changed when calling set_network_from_beacon_data()
PROXY_TCP_PORT = 8080


# REST KEYWORDS
class REST_KW(Enum):
    """REST requests and response JSON keywords."""

    COMMANDS = "commands"
    DATA = "data"
    DATAREFS = "datarefs"
    DESCRIPTION = "description"
    DURATION = "duration"
    ERROR_MESSAGE = "error_message"
    ERROR_CODE = "error_code"
    IDENT = "id"
    INDEX = "index"
    ISACTIVE = "is_active"
    ISWRITABLE = "is_writable"
    NAME = "name"
    PARAMS = "params"
    REQID = "req_id"
    RESULT = "result"
    SUCCESS = "success"
    TYPE = "type"
    VALUE = "value"
    VALUE_TYPE = "value_type"


# #############################################
# REST API
#
class XPRestAPI(API):
    """XPlane REST API

    Adds cache for datarefs and commands meta data.

    There is no permanent connection to REST API. When needed, connection can be probed
    with XPRestAPI.connected which is True if API is reachable. Most API call test for reachability before issuing their request(s).

    See Also:
        [X-Plane Web API — REST API](https://developer.x-plane.com/article/x-plane-web-api/#REST_API)
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 8086, api: str = "/api", api_version: str = "v1", use_cache: bool = False) -> None:
        API.__init__(self, host=host, port=port, api=api, api_version=api_version)
        self._capabilities = {}

        self._first_try = True
        self._running_time = Dataref(path=RUNNING_TIME, api=self)  # cheating, side effect, works for rest api only, do not force!

        # Caches ids for all known datarefs and commands
        self._should_use_cache = use_cache  # desired use of cache, not actual one in _use_cache
        self.all_datarefs: Cache | None = None
        self.all_commands: Cache | None = None

        self._last_updated = 0
        self._warning_count = 0
        self._unreach_count = 0
        self._dataref_by_id = {}  # {dataref-id: Dataref}

        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(pool_connections=50, pool_maxsize=100)
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)
        # Install session here:
        # examples:
        # self.session.auth = ('user', 'password')
        self.session.headers["Accept"] = "application/json"
        self.session.headers["Content-Type"] = "application/json"

    @property
    def use_cache(self) -> bool:
        """Use cache for object meta data"""
        return self._use_cache

    @use_cache.setter
    def use_cache(self, use_cache):
        self._should_use_cache = use_cache
        if use_cache:
            self.reload_caches()  # will set use_cache if caches loaded successfully

    @property
    def uptime(self) -> float:
        """Time X-Plane has been running in seconds since start

        Value is fetched from simulator dataref sim/time/total_running_time_sec
        """
        if self._running_time is not None:
            r = self._running_time.value
            if r is not None:
                return float(r)
        return 0.0

    @property
    def connected(self) -> bool:
        """Whether API is reachable

        API may not be reachable if:
         - X-Plane version before 12.1.4,
         - X-Plane is not running
        """
        return self.rest_api_reachable

    @property
    def rest_api_reachable(self) -> bool:
        """Whether API is reachable

        API may not be reachable if:
         - X-Plane version before 12.1.4,
         - X-Plane is not running
        """
        CHECK_API_URL = f"http://{self.host}:{self.port}/api/v1/datarefs/count"
        response = None
        if self._first_try:
            logger.info(f"trying to connect to {CHECK_API_URL}..")
            self._first_try = False
        try:
            # Relies on the fact that first version is always provided.
            # Later verion offer alternative ot detect API
            self.inc("get")
            response = self.session.get(CHECK_API_URL)
            webapi_logger.info(f"GET {CHECK_API_URL}: {response}")
            if response.status_code == 200:
                if self._unreach_count > 0:
                    logger.info("rest api reachable")
                    self._unreach_count = 0
                self.status = CONNECTION_STATUS.REST_API_REACHABLE
                return True
        except requests.exceptions.ConnectionError:
            if self._warning_count % 20 == 0:
                logger.warning("api unreachable, X-Plane may be not running")
                self.status = CONNECTION_STATUS.REST_API_NOT_REACHABLE
                self._warning_count = self._warning_count + 1
        return False

    @property
    def has_data(self) -> bool:
        res = ""
        d = self.all_datarefs is not None and self.all_datarefs.has_data
        if d:
            res = res + f"loaded {self.all_datarefs.count} datarefs metadata"
        c = self.all_commands is not None and self.all_commands.has_data
        if c:
            res = res + f", loaded {self.all_commands.count} commands metadata"
        logger.debug(res)
        return d and c

    @property
    def capabilities(self) -> dict:
        """Fetches API capabilties and caches it"""
        if len(self._capabilities) > 0:
            return self._capabilities
        # Use REST reachability, not XPWebsocketAPI.connected (websocket open), so we can read
        # /api/capabilities and pick v2 vs v3 before opening the WebSocket.
        if self.rest_api_reachable:
            try:
                CAPABILITIES_API_URL = f"http://{self.host}:{self.port}/api/capabilities"  # independent from version
                self.inc("get")
                response = self.session.get(CAPABILITIES_API_URL)
                webapi_logger.info(f"GET {CAPABILITIES_API_URL}: {response}")
                if response.status_code == 200:  # We have version 12.1.4 or above
                    self._capabilities = response.json()
                    logger.debug(f"capabilities: {self._capabilities}")
                    return self._capabilities
                logger.info(f"capabilities at {self.rest_url + '/capabilities'}: response={response.status_code}")
                url = self.rest_url + "/v1/datarefs/count"
                self.inc("get")
                response = self.session.get(url)
                webapi_logger.info(f"GET {url}: {response}")
                if response.status_code == 200:  # OK, /api/v1 exists, we use it, we have version 12.1.1 or above
                    self._capabilities = V1_CAPABILITIES
                    logger.debug(f"capabilities: {self._capabilities}")
                    return self._capabilities
                logger.error(f"capabilities at {self.rest_url + '/datarefs/count'}: response={response.status_code}")
            except:
                logger.error("capabilities", exc_info=True)
        else:
            logger.debug("capabilities: REST API not reachable yet")
        return self._capabilities

    @property
    def xp_version(self) -> str | None:
        """Returns reported X-Plane version from simulator"""
        a = self._capabilities.get("x-plane")
        if a is None:
            return None
        return a.get("version")

    def set_api_version(self, api_version: str | None = None):
        """Set API version

        Version is often specified with a v# short string.
        If no version is supplied, try to take the latest version available.
        Version numbering is not formally specified, ordering is performed using natural sorting.
        (See [natsort](https://github.com/SethMMorton/natsort/wiki).)
        """
        capabilities = self.capabilities
        if len(capabilities) == 0:
            logger.warning("no capabilities, cannot check API version")
            self.version = api_version
            self._api_version = f"/{api_version}"
            logger.warning("no capabilities, cannot check API version")
            logger.info(f"set api {api_version} without verification")
            return
        api_details = capabilities.get("api")
        if api_details is not None:
            api_versions = api_details.get("versions")
            if api_version is None:
                if api_versions is None:
                    logger.error("cannot determine api, api not set")
                    return
                sorted_apis = natsorted(api_versions, reverse=True)
                api_version = sorted_apis[0]  # takes the latest one, hoping it is the latest in time...
                logger.info(f"selected api {api_version} ({sorted_apis})")
            if api_version in api_versions:
                self.version = api_version
                self._api_version = f"/{api_version}"
                logger.info(f"set api {api_version}, xp {self.xp_version}")
            else:
                logger.warning(f"no api {api_version} in {api_versions}, api not set")
            return
        logger.warning(f"could not check api {api_version} in {capabilities}, api not set")

    def sync_web_api_version_with_capabilities(self) -> None:
        """Set REST/WebSocket API path to v3 on X-Plane 12.4+ when advertised.

        On 12.4+, using /api/v2 for REST combined with the v2 WebSocket can yield
        ``invalid_dataref_id`` on subscribe; v3 REST ids match the v3 WebSocket.
        """
        if not self.rest_api_reachable:
            return
        caps = self.capabilities
        if len(caps) == 0:
            return
        api_versions = (caps.get("api") or {}).get("versions")
        if not api_versions:
            return
        xp_str = self.xp_version
        if xp_str is None:
            return
        try:
            xp_base = Version(xp_str).base_version
            if Version(xp_base) >= Version("12.4") and "v3" in api_versions and self.version == "v2":
                logger.info(
                    f"Web API v3 selected for X-Plane {xp_str} (v2 WebSocket rejected dataref subscriptions on this version)"
                )
                self.set_api_version("v3")
            elif self.version == "v3" and "v3" not in api_versions:
                logger.warning("simulator does not advertise v3; falling back to v2")
                self.set_api_version("v2")
        except Exception:
            logger.debug("sync_web_api_version_with_capabilities: could not parse X-Plane version", exc_info=True)

    # Cache
    def reload_caches(self, force: bool = False, save: bool = False):
        """Reload meta data caches

        Must be performed regularly, if aircraft changed, etc.

        Later, Laminar Research has plan for a notification of additing of datarefs

        Args:
            force (bool): Force reloading (default: `False`)
            save (bool): Save raw meta data in JSON formatted files (default: `False`)
        """
        MINTIME_BETWEEN_RELOAD = 10  # seconds
        if not self.rest_api_reachable:
            thread_name = threading.current_thread().name
            log = logger.debug if thread_name.startswith("XPlane::Startup") or thread_name.startswith("XPlane::LostConnection") else logger.warning
            log("rest api unreachable, cannot reload caches")
            self.all_datarefs = None
            self.all_commands = None
            return
        if not force:
            if self._last_updated != 0:
                currtime = self._running_time.value
                if currtime is not None:
                    currtime = int(currtime)
                    difftime = currtime - self._last_updated
                    if difftime < MINTIME_BETWEEN_RELOAD:
                        logger.info(f"dataref cache not updated, updated {round(difftime, 1)} secs. ago")
                        return
                else:
                    log = logger.debug if threading.current_thread().name.startswith("XPlane::Startup") else logger.warning
                    log(f"no value for {RUNNING_TIME}")
        datarefs = Cache(self)
        datarefs.load("/datarefs")
        commands = Cache(self)
        if self.version in ("v2", "v3"):
            commands.load("/commands")
        self.all_datarefs = datarefs if datarefs.has_data else None
        self.all_commands = commands if commands.has_data else None
        if save:
            if self.all_datarefs is not None:
                self.all_datarefs.save("webapi-datarefs.json")
            if self.all_commands is not None:
                self.all_commands.save("webapi-commands.json")
        currtime = self._running_time.value
        if currtime is not None:
            self._last_updated = int(currtime)
        else:
            thread_name = threading.current_thread().name
            log = logger.debug if thread_name.startswith("XPlane::Startup") or thread_name.startswith("XPlane::LostConnection") else logger.warning
            log(f"no value for {RUNNING_TIME}")
        if (self.all_commands is not None and self.all_commands.has_data) or (self.all_datarefs is not None and self.all_datarefs.has_data):
            self._use_cache = self._should_use_cache
            if self._use_cache:
                logger.info("using caches")
        dataref_count = self.all_datarefs.count if self.all_datarefs is not None else 0
        command_count = self.all_commands.count if self.all_commands is not None else 0
        uptime = self.uptime if self.uptime is not None else 0
        logger.info(
            f"dataref cache ({dataref_count}) and command cache ({command_count}) reloaded, sim uptime {str(timedelta(seconds=int(uptime)))}"
        )

    def invalidate_caches(self):
        """Remove cache data"""
        self.all_datarefs = None
        self.all_commands = None
        # Clear per-instance cached metas so datarefs re-resolve their IDs from the
        # fresh shared cache on reconnect. X-Plane reassigns numeric IDs each session,
        # so stale _cached_meta would cause 404 errors after a disconnect/reconnect.
        for d in self._dataref_by_id.values():
            if type(d) is Dataref:
                d._cached_meta = None
                d._meta_failed = False
                d._monitored = 0
            elif type(d) is list:
                for di in d:
                    di._cached_meta = None
                    di._meta_failed = False
                    di._monitored = 0
        self._dataref_by_id.clear()
        logger.info("cache invalidated")

    def dataref_equiv(self, ident: int) -> str:
        """Return a display name for a dataref id, even while caches are unavailable."""
        return self.all_datarefs.equiv(ident=ident) if self.all_datarefs is not None else f"no dataref cache for {ident}"

    def command_equiv(self, ident: int) -> str:
        """Return a display name for a command id, even while caches are unavailable."""
        return self.all_commands.equiv(ident=ident) if self.all_commands is not None else f"no command cache for {ident}"

    def rebuild_dataref_ids(self):
        """Rebuild dataref idenfier index"""
        if len(self._dataref_by_id) > 0:
            if self.all_datarefs is not None and self.all_datarefs.has_data:
                newdict = dict()
                for d in self._dataref_by_id.values():
                    if type(d) is Dataref:
                        newdict[d.ident] = d
                    elif type(d) is list and len(d) > 0:
                        t = d[0]  # ident of first element, same for all elements in the list
                        newdict[t.ident] = d
                self._dataref_by_id = newdict
                logger.info("dataref ids rebuilt")
                return
            logger.warning("no data to rebuild dataref ids")
        else:
            logger.debug("no dataref to rebuild ids")

    def get_rest_meta(self, obj: Dataref | Command, force: bool = False) -> DatarefMeta | CommandMeta | None:
        """Get meta data from X-Plane through REST API for object.

        Fetches meta data and cache it unless force = True.

        Args:
            obj (Dataref| Command): Objet (Dataref or Command) to get the meta data for
            force (bool): Force new fetch, do not read from cache (default: `False`)

        Returns:
            DatarefMeta| CommandMeta: Meta data for object.
        """
        if not self.connected:
            logger.warning("not connected")
            return None
        if not force and obj._cached_meta is not None:
            return obj._cached_meta
        obj._cached_meta = None
        payload = f"filter[name]={obj.path}"
        obj_type = "/datarefs" if isinstance(obj, Dataref) else "/commands"
        url = self.rest_url + obj_type
        self.inc("get")
        response = self.session.get(url, params=payload)
        webapi_logger.info(f"GET {obj.path}: {url} = {response}")
        if response.status_code == 200:
            respjson = response.json()
            metadata = respjson[REST_KW.DATA.value]
            if len(metadata) > 0:
                m0 = metadata[0]
                obj._cached_meta = Cache.meta(**m0)
                return obj._cached_meta
        # The caller (MetaFetchQueue worker) may retry before giving up, so log
        # transient attempts at debug level; only the final attempt logs ERROR.
        retries = getattr(obj, "_meta_retries", 0)
        max_retries = getattr(meta_queue, "MAX_RETRIES", 0)
        log = logger.error if retries >= max_retries else logger.debug
        log(f"{obj_type} {obj.path} could not get meta data through REST API")
        return None

    def get_dataref_meta_by_name(self, path: str) -> DatarefMeta | None:
        """Get dataref meta data by dataref name"""
        return self.all_datarefs.get_by_name(path) if self.all_datarefs is not None else None

    def get_dataref_meta_by_id(self, ident: int) -> DatarefMeta | None:
        """Get dataref meta data by dataref identifier"""
        return self.all_datarefs.get_by_id(ident) if self.all_datarefs is not None else None

    def get_command_meta_by_name(self, path: str) -> CommandMeta | None:
        """Get command meta data by command path"""
        return self.all_commands.get_by_name(path) if self.all_commands is not None else None

    def get_command_meta_by_id(self, ident: int) -> CommandMeta | None:
        """Get command meta data by command identifier"""
        return self.all_commands.get_by_id(ident) if self.all_commands is not None else None

    def write_dataref(self, dataref: Dataref) -> bool | int:
        """Write single dataref value through REST API

        Returns:

        bool: success of operation
        """
        if not self.connected:
            logger.warning("not connected")
            return False
        if not dataref.valid:
            if not dataref._meta_fetching:
                if dataref._err == 0:
                    logger.error(f"dataref {dataref.path} not valid")
                dataref.add_error()
            return False
        if not dataref.is_writable:
            logger.warning(f"dataref {dataref.path} is not writable")
            return False
        value = dataref._new_value
        if value is None:  # set a default value for it
            logger.warning(f"dataref {dataref.path} has no new value")
            return False
        if dataref.value_type == DATAREF_DATATYPE.DATA.value or type(value) is bytes:
            value = dataref.b64encoded
        payload = {REST_KW.DATA.value: value}
        url = f"{self.rest_url}/datarefs/{dataref.ident}/value"
        if dataref.index is not None and dataref.value_type in [DATAREF_DATATYPE.INTARRAY.value, DATAREF_DATATYPE.FLOATARRAY.value]:
            # Update just one element of the array
            url = url + f"?index={dataref.index}"
        webapi_logger.info(f"PATCH {dataref.path}: {url}, {payload}")
        self.inc("patch")
        try:
            response = self.session.patch(url, json=payload)
        except requests.exceptions.ConnectionError:
            logger.warning(f"rest_write: connection lost writing {dataref.path}")
            return False
        if response.status_code == 200:
            data = response.json()
            logger.debug(f"result: {data}")
            return True
        webapi_logger.info(f"ERROR {dataref.path}: {response} {response.reason} {response.text}")
        logger.error(f"rest_write: {response} {response.reason} {response.text}")
        return False

    def execute_command(self, command: Command, duration: float = 0.0) -> bool | int:
        """Executes Command through REST API

        Returns:

        bool: success of operation
        """
        if not self.connected:
            logger.warning("not connected")
            return False
        if not command.valid:
            if not command._meta_fetching:
                if command._err == 0:
                    logger.error(f"command {command.path} is not valid")
                command.add_error()
            return False
        if duration == 0.0 and command.duration != 0.0:
            duration = command.duration
        payload = {REST_KW.IDENT.value: command.ident, REST_KW.DURATION.value: duration}
        url = f"{self.rest_url}/command/{command.ident}/activate"
        self.inc("post")
        try:
            response = self.session.post(url, json=payload)
        except requests.exceptions.ConnectionError:
            logger.warning(f"execute_command: connection lost executing {command.path}")
            return False
        webapi_logger.info(f"POST {command.path}: {url} {payload} {response}")
        if response.status_code == 200:
            data = response.json()
            logger.debug(f"result: {data}")
            return True
        webapi_logger.info(f"ERROR {command.path}: {response} {response.reason} {response.text}")
        logger.error(f"rest_execute: {response}")
        return False

    def dataref_value(self, dataref: Dataref, raw: bool = False, no_decode: bool = False) -> DatarefValueType | None:
        """Get dataref value through REST API

        Value is not stored or cached.
        """
        if not self.connected:
            logger.debug("not connected")
            return None
        if not dataref.valid:
            if not dataref._meta_fetching:
                if dataref._err == 0:
                    logger.error(f"dataref {dataref.path} not valid")
                dataref.add_error()
            return None
        url = f"{self.rest_url}/datarefs/{dataref.ident}/value"
        self.inc("get")
        try:
            response = self.session.get(url)
        except requests.exceptions.ConnectionError:
            logger.warning(f"dataref_value: connection lost fetching {dataref.path}")
            return None
        if response.status_code == 200:
            respjson = response.json()
            webapi_logger.info(f"GET {dataref.path}: {url} = {respjson}")
            if not raw and REST_KW.DATA.value in respjson and type(respjson[REST_KW.DATA.value]) in [bytes, str]:
                try:
                    return base64.b64decode(respjson[REST_KW.DATA.value])
                except:
                    logger.warning(f"cannot decode: {response} {response.reason} {response.text}", exc_info=True)
                return respjson[REST_KW.DATA.value]
            return respjson[REST_KW.DATA.value]
        webapi_logger.info(f"ERROR {dataref.path}: {response} {response.reason} {response.text}")
        logger.error(f"dataref_value: {response} {response.reason} {response.text}")
        return None

    def dataref_meta(self, dataref, fields: List[str] | str = "all") -> DatarefMeta | None:
        """Get dataref meta data through REST API

        @todo: dataref_meta(self, dataref, fields:List[str]|str = "all")  # fields={id, name, value_type, all}
        """
        url = f"{self.rest_url}/datarefs/filter[name]={dataref.path}"
        if fields != "all":
            url = url + f"&fields=[{','.join(fields)}]"
        self.inc("get")
        try:
            response = self.session.get(url)
        except requests.exceptions.ConnectionError:
            logger.warning(f"dataref_meta: connection lost fetching {dataref.path}")
            return None
        if response.status_code == 200:
            respjson = response.json()
            webapi_logger.info(f"GET {dataref.path}: {url} = {respjson}")
            data = respjson[REST_KW.DATA.value]
            try:
                ret = Cache.meta(**data[0]) if type(data) is list and len(data) > 0 else Cache.meta(**data)
                return ret
            except:
                logger.warning(f"dataref meta invalid {data}", exc_info=True)
            return None
        webapi_logger.info(f"ERROR {dataref.path}: {response} {response.reason} {response.text}")
        logger.error(f"dataref_meta: {response} {response.reason} {response.text}")
        return None

    # Meta data collection for one or more datarefs or commands
    #
    def datarefs_meta(self, datarefs: List[Dataref], fields: List[str] | str = "all", start: int | None = None, limit: int | None = None) -> List[DatarefMeta]:
        """Get dataref meta data through REST API for all dataref supplied

        @todo: datarefs_meta(self, dataref, fields:List[str]|str = "all", start: int|None = None, limit: int|None = None)  # fields={id, name, value_type, all}
        """
        payload = "&".join([f"filter[name]={d.path}" for d in datarefs])
        if fields != "all":
            payload = payload + f"&fields=[{fields}]"
        if start is not None:
            payload = payload + f"&start={start}"
        if limit is not None:
            payload = payload + f"&limit={limit}"
        url = f"{self.rest_url}/datarefs"
        self.inc("get")
        try:
            response = self.session.get(url, params=payload)
        except requests.exceptions.ConnectionError:
            logger.warning("datarefs_meta: connection lost")
            return []
        if response.status_code == 200:
            respjson = response.json()
            webapi_logger.info(f"GET {payload}: {url} = {respjson}")
            data = respjson[REST_KW.DATA.value]
            try:
                ret = [Cache.meta(**m) for m in data]
                return ret
            except:
                logger.warning(f"dataref meta invalid {data}", exc_info=True)
            return []
        webapi_logger.info(f"ERROR {payload}: {response} {response.reason} {response.text}")
        logger.error(f"datarefs_meta: {response} {response.reason} {response.text}")
        return []

    def commands_meta(self, commands: List[Command], fields: List[str] | str = "all", start: int | None = None, limit: int | None = None) -> List[CommandMeta]:
        """Get dataref meta data through REST API for all dataref supplied

        @todo: commands_meta(self, dataref, fields:List[str]|str = "all", start: int|None = None, limit: int|None = None)  # fields={id, name, description, all}
        """
        payload = "&".join([f"filter[name]={c.path}" for c in commands])
        if fields != "all":
            payload = payload + f"&fields=[{fields}]"
        if start is not None:
            payload = payload + f"&start={start}"
        if limit is not None:
            payload = payload + f"&limit={limit}"
        url = f"{self.rest_url}/commands"
        self.inc("get")
        try:
            response = self.session.get(url, params=payload)
        except requests.exceptions.ConnectionError:
            logger.warning("commands_meta: connection lost")
            return []
        if response.status_code == 200:
            respjson = response.json()
            webapi_logger.info(f"GET {payload}: {url} = {respjson}")
            data = respjson[REST_KW.DATA.value]
            try:
                ret = [Cache.meta(**m) for m in data]
                return ret
            except:
                logger.warning(f"command meta invalid {data}", exc_info=True)
            return []
        webapi_logger.info(f"ERROR {payload}: {response} {response.reason} {response.text}")
        logger.error(f"commands_meta: {response} {response.reason} {response.text}")
        return []

    def set_connection_from_beacon_data(self, beacon_data: "BeaconData", same_host: bool, remote_tcp_port: int = PROXY_TCP_PORT):
        API_TCP_PORT = 8086

        XP_MIN_VERSION = 121400
        XP_MIN_VERSION_STR = "12.1.4"
        XP_MAX_VERSION = 121499
        XP_MAX_VERSION_STR = "12.1.4"

        self.use_rest = self.use_rest and not same_host
        new_host = "127.0.0.1"
        new_port = API_TCP_PORT
        if not same_host:
            new_host = beacon_data.host
            new_port = PROXY_TCP_PORT
        xp_version = beacon_data.xplane_version
        if xp_version is not None:
            use_rest = ", use REST" if self.use_rest else ""
            new_apiversion = "/v1"
            if xp_version >= XP_MIN_VERSION:
                new_apiversion = "/v2"
            elif xp_version < XP_MIN_VERSION:
                new_apiversion = ""
                logger.warning(f"could not set API version from {xp_version} ({beacon_data})")
            if new_apiversion != "":
                host_or_port_changed = new_host != self.host or new_port != self.port
                # Only update network when host/port actually changed.
                # sync_web_api_version_with_capabilities (called by connection_monitor at
                # startup) may have already promoted v2→v3; re-applying the beacon's v2
                # every tick causes a v3→v2→v3 bounce that momentarily points REST at
                # the wrong endpoint and can corrupt dataref ID lookups.
                if host_or_port_changed:
                    self.set_network(host=new_host, port=new_port, api="/api", api_version=new_apiversion)
                    logger.info(f"XPlane API at {self.rest_url} from UDP beacon data{use_rest}")
                    self.sync_web_api_version_with_capabilities()
        else:
            logger.warning(f"could not get X-Plane version from beacon data {beacon_data}")
