"""Main startup script for Cockpitdecks

Starts up Cockpitdecks. Process command line arguments, load Cockpitdecks with proper simulator.
Starts listening to events from both simulator and decks connected to the computer.
Starts web server to serve web decks, designer, and button editor.
Starts WebSocket listener to collect events from web decks.

Press CTRL-C ** once ** to gracefully stop Cockpitdecks. Be patient.
"""

import sys
import os
import logging
import time
import itertools
import threading
import json
import urllib.parse
import argparse
import subprocess
import shutil
import webbrowser
from pathlib import Path

import socket
import ipaddress

from enum import Enum

from cockpitdecks import constant
from flask import Flask, render_template, send_from_directory, send_file, request, abort
from simple_websocket import Server, ConnectionClosed

import ruamel
from ruamel.yaml import YAML

from cockpitdecks import __NAME__, __version__, __COPYRIGHT__, __DESCRIPTION__, Config, LOGFILE, FORMAT
from cockpitdecks.constant import ENVIRON_KW, CONFIG_KW, DECK_KW, CONFIG_FOLDER, DECKS_FOLDER, DECK_TYPES, TEMPLATE_FOLDER, ASSET_FOLDER, AUTOSAVE_FILE
from cockpitdecks.cockpit import Cockpit
from cockpitdecks.aircraft import DECK_TYPE_DESCRIPTION
from cockpitdecks.webcontrol import install_recent_log_handler, register_web_control


ruamel.yaml.representer.RoundTripRepresenter.ignore_aliases = lambda x, y: True
yaml = YAML(typ="safe", pure=True)
yaml.default_flow_style = False

logging.basicConfig(level=logging.INFO, format=FORMAT, datefmt="%H:%M:%S")

logger = logging.getLogger(__name__)
if LOGFILE is not None:
    formatter = logging.Formatter(FORMAT)
    handler = logging.FileHandler(LOGFILE, mode="a")
    handler.setFormatter(formatter)
    logger.addHandler(handler)

startup_logger = logging.getLogger("Cockpitdecks startup")
PROCESS_START_TS = time.time()
runtime_state_lock = threading.Lock()
runtime_state = {
    "status": "starting",
    "message": "Starting web control server..",
    "error": None,
}
_recent_log_handler = install_recent_log_handler(FORMAT)


def set_runtime_state(status: str, message: str, error: str | None = None) -> None:
    with runtime_state_lock:
        runtime_state["status"] = status
        runtime_state["message"] = message
        runtime_state["error"] = error


def get_runtime_state() -> dict:
    with runtime_state_lock:
        return dict(runtime_state)


class CD_MODE(Enum):
    NORMAL = 0
    DEMO = 1
    FIXED = 2


#
# Utility functions
def my_ip() -> str | set:
    x = set([address[4][0] for address in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)])
    return list(x)[0] if len(x) == 1 else x


def get_ip(s) -> str:
    c = s[0]
    if c in "0123456789":
        return ipaddress.ip_address(s)
    else:
        return ipaddress.ip_address(socket.gethostbyname(s))


def which(program):
    def is_exe(fpath):
        return os.path.isfile(fpath) and os.access(fpath, os.X_OK)

    fpath, fname = os.path.split(program)
    if fpath:
        if is_exe(program):
            return program
    else:
        for path in os.environ.get("PATH", "").split(os.pathsep):
            exe_file = os.path.join(path, program)
            if is_exe(exe_file):
                return exe_file

    return None




def add_env(env, paths):
    return ":".join(set(env.split(":") + paths)).strip(":")


def cockpitdecks_config_dir() -> Path:
    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "Cockpitdecks"
    if sys.platform == "win32":
        local_appdata = os.environ.get("LOCALAPPDATA")
        base = Path(local_appdata) if local_appdata else home / "AppData" / "Local"
        return base / "Cockpitdecks"
    return home / ".config" / "cockpitdecks"


def cockpitdecks_config_file(explicit_path: str | None = None) -> Path:
    if explicit_path:
        return Path(explicit_path).expanduser()
    return cockpitdecks_config_dir() / "config.yaml"


def load_runtime_config(explicit_path: str | None = None) -> tuple[dict, Path]:
    path = cockpitdecks_config_file(explicit_path)
    if explicit_path and not path.exists():
        startup_logger.error(f"config file not found: {path}")
        sys.exit(1)
    if not path.exists():
        startup_logger.debug(f"no runtime config file at {path}")
        return {}, path
    try:
        with open(path, "r", encoding="utf-8") as fp:
            data = yaml.load(fp) or {}
        if not isinstance(data, dict):
            startup_logger.error(f"invalid config file {path}: top-level YAML object must be a mapping")
            sys.exit(1)
        startup_logger.info(f"loaded runtime config from {path}")
        return data, path
    except Exception:
        startup_logger.error(f"failed to load runtime config from {path}", exc_info=True)
        sys.exit(1)


def runtime_config_defaults() -> dict:
    return {
        "deck_paths": [],
        "target": None,
        "xplane_api": {"host": "127.0.0.1", "port": 8086},
        "cockpitdecks_server": {"host": "127.0.0.1", "port": 7777},
        "simulator_host": None,
        "launch_log": None,
        "logging": {"console": True, "log_level_filter": "DEBUG"},
    }


RUNTIME_CONFIG_KEYS = {
    "deck_paths",
    "target",
    "xplane_api",
    "cockpitdecks_server",
    "simulator_host",
    "launch_log",
    "logging",
}


def merge_runtime_config(data: dict | None) -> dict:
    merged = runtime_config_defaults()
    if not isinstance(data, dict):
        return merged
    for key in ("deck_paths", "target", "simulator_host", "launch_log"):
        if key in data:
            merged[key] = data.get(key)
    for key in ("xplane_api", "cockpitdecks_server", "logging"):
        section = data.get(key)
        if isinstance(section, dict):
            merged[key].update(section)
    return merged


def save_runtime_config(path: Path, data: dict, existing: dict | None = None) -> dict:
    merged = dict(existing) if isinstance(existing, dict) else {}
    for key in RUNTIME_CONFIG_KEYS:
        if key in data:
            merged[key] = data[key]
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup_path = path.with_suffix(path.suffix + ".bak")
        shutil.copy2(path, backup_path)
    with open(path, "w", encoding="utf-8") as fp:
        yaml.dump(merged, fp)
    return merged


def configure_runtime_logging(data: dict) -> None:
    root_logger = logging.getLogger()
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    # Engine mode: launched by cockpitdecks-desktop as a managed subprocess.
    # Stream output to stdout so the desktop app can capture and filter it.
    # COCKPITDECKS_LOG_LEVEL controls verbosity (default INFO).
    if os.environ.get("COCKPITDECKS_ENGINE"):
        level_name = os.environ.get("COCKPITDECKS_LOG_LEVEL", "INFO").upper()
        level = getattr(logging, level_name, logging.INFO)
        root_logger.setLevel(level)
        # Remove any existing console handlers to avoid duplicate output.
        for h in list(root_logger.handlers):
            if h is _recent_log_handler:
                continue
            if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler):
                root_logger.removeHandler(h)
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level)
        handler.setFormatter(logging.Formatter(FORMAT))
        root_logger.addHandler(handler)
        return
    logging_cfg = config_section(data.get("logging"), "logging")
    console_enabled = logging_cfg.get("console", True)
    if isinstance(console_enabled, str):
        console_enabled = console_enabled.strip().lower() not in {"0", "false", "no", "off"}
    if console_enabled:
        return
    for handler in list(root_logger.handlers):
        if handler is _recent_log_handler:
            continue
        if isinstance(handler, logging.StreamHandler):
            root_logger.removeHandler(handler)


def suppress_console_logging() -> None:
    if os.environ.get("COCKPITDECKS_ENGINE"):
        return
    root_logger = logging.getLogger()
    for handler in list(root_logger.handlers):
        if handler is _recent_log_handler:
            continue
        if isinstance(handler, logging.StreamHandler):
            root_logger.removeHandler(handler)


def config_path_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.split(":") if part.strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(part).strip() for part in value if str(part).strip()]
    startup_logger.warning(f"invalid deck_paths={value!r}, expected list or colon-separated string")
    return []


def config_section(value, name: str) -> dict:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    startup_logger.warning(f"invalid {name}={value!r}, expected mapping")
    return {}


def config_port(value, default: int, name: str) -> int:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        startup_logger.warning(f"invalid {name}={value!r}, using default {default}")
        return default


# ######################################################################################################
# COCKPITDECKS STARTS HERE
#
# DESC = "Elgato Stream Decks, Loupedeck decks, Berhinger X-Touch Mini, and web decks to X-Plane 12.1+"
DESC = __DESCRIPTION__

# Default values for demo
DEMO_HOME = os.path.join(os.path.dirname(__file__), "resources", "demo")
AIRCRAFT_HOME = DEMO_HOME
AIRCRAFT_DESC = "Cockpitdecks Demo"

# Used values for startup
SIMULATOR_NAME = None
SIMULATOR_HOST = None

# Command-line arguments
#
parser = argparse.ArgumentParser(description="Start Cockpitdecks")
parser.add_argument("--version", action="store_true", help="show version information and exit")
parser.add_argument("-v", "--verbose", action="store_true", help="show startup information")
parser.add_argument("-d", "--demo", action="store_true", help="start demo mode")
parser.add_argument("-f", "--fixed", action="store_true", help="does not automatically switch aircraft")
parser.add_argument("-w", "--web", action="store_true", help="open web application in new browser window")
parser.add_argument("-p", "--packages", nargs="+", help="lookup and load additional packages")
parser.add_argument(
    "--template", metavar="aircraft folder", type=str, nargs=1, help="create deckconfig and add template files to start in supplied aircraft folder"
)
parser.add_argument("--designer", action="store_true", help="start designer")
parser.add_argument("--config", metavar="config.yaml", type=str, help="load runtime config from supplied file")
# parser.add_argument("--install-plugin", action="store_true", help="install Cockpitdecks plugin in X-Plane/XPPython3")
parser.add_argument("aircraft_folder", metavar="aircraft_folder", type=str, nargs="?", help="aircraft folder for non automatic start")

early_args, _ = parser.parse_known_args()
_early_runtime_config, _ = load_runtime_config(early_args.config)
_early_runtime_config = merge_runtime_config(_early_runtime_config)
configure_runtime_logging(_early_runtime_config)

args = parser.parse_args()

if args.verbose:
    startup_logger.setLevel(logging.DEBUG)
    startup_logger.debug(f"{os.path.basename(sys.argv[0])} {__version__} configuring startup..")
    # startup_logger.debug(args)
else:
    startup_logger.info(f"python {sys.version[0:sys.version.index(' ')]}, {os.path.basename(sys.argv[0])} {__version__}")

# Run git if available to collect info
#
last_commit = ""
project_url = ""
last_commit_hash = ""
git = which("git")
if os.path.exists(".git") and git is not None:
    process = subprocess.Popen([git, "show", "-s", "--format=%ci"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = process.communicate()
    last_commit = "." + stdout.decode("utf-8")[:10].replace("-", "")
    process = subprocess.Popen([git, "remote", "get-url", "origin"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = process.communicate()
    project_url = stdout.decode("utf-8")[:-1]
    process = subprocess.Popen([git, "log", "-n", "1", '--pretty=format:"%H"'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = process.communicate()
    last_commit_hash = stdout.decode("utf-8")[1:8]

# #########################################@
# Show version (and exits)
#
if args.version:
    if git is not None:
        # copyrights = f"{__NAME__.title()} {__version__}{last_commit} {project_url}\n{__COPYRIGHT__}\n{DESC}\n"
        version = f"{os.path.basename(sys.argv[0])} ({project_url}) version {__version__} ({last_commit_hash})"
        startup_logger.info(version)
    else:
        startup_logger.warning("git not available")
    sys.exit(0)

# #########################################@
# Copy template files (and exits)
#
if args.template:
    tmpl_dir = args.template[0]
    tmpl_dest = os.path.join(tmpl_dir, CONFIG_FOLDER)
    tmpl_src = DEMO_HOME

    if not os.path.exists(tmpl_src):
        startup_logger.warning(f"could not locate templates in {tmpl_src}")
        sys.exit(1)
    if os.path.exists(tmpl_dest):
        startup_logger.warning(f"{tmpl_dir} already contains a {CONFIG_FOLDER}, cannot install templates")
        sys.exit(1)
    else:
        shutil.copytree(tmpl_src, tmpl_dest, dirs_exist_ok=False)
        startup_logger.info(f"templates installed in {tmpl_dest}")
    sys.exit(0)

# #########################################@
# Load Environment File if any, tries default one as well.
# Loads environment to know which flight simulator and where to locate it.
#
environment = Config(filename=None)  # create default env to host values
runtime_config_raw, _runtime_config_path = load_runtime_config(args.config)
runtime_config = merge_runtime_config(runtime_config_raw)
RUNTIME_CONFIG_PATH = _runtime_config_path
configure_runtime_logging(runtime_config)

# Debug
#
debug_mode = environment.get(ENVIRON_KW.DEBUG.value, "info").lower()
if debug_mode == "debug":
    logging.basicConfig(level=logging.DEBUG)
elif debug_mode == "warning":
    logging.basicConfig(level=logging.WARNING)
elif debug_mode != "info":
    debug_mode = "info"
    startup_logger.warning(f"invalid debug mode {debug_mode}, using info")
startup_logger.debug(f"Cockpitdecks debug set to {debug_mode}")

environment.verbose = args.verbose
environment.debug = debug_mode

# Demo
#
if args.demo:
    startup_logger.info("Cockpitdecks starting for demo")
    environment[ENVIRON_KW.SIMULATOR_NAME.value] = "NoSimulator"
    environment[ENVIRON_KW.APP_HOST.value] = ["127.0.0.1", 7777]

# #########################################@
# Simulator
#
SIMULATOR_NAME = "NoSimulator" if args.demo else "X-Plane"
environment[ENVIRON_KW.SIMULATOR_NAME.value] = SIMULATOR_NAME
startup_logger.debug(f"Simulator is {SIMULATOR_NAME}")

SIMULATOR_HOST = runtime_config.get("simulator_host")
if SIMULATOR_HOST in ("", "null"):
    SIMULATOR_HOST = None
if SIMULATOR_HOST is None:
    SIMULATOR_HOST = os.getenv(ENVIRON_KW.SIMULATOR_HOST.value) or environment.get(ENVIRON_KW.SIMULATOR_HOST.value)
if SIMULATOR_HOST is not None:
    startup_logger.debug(f"remote simulator at {ENVIRON_KW.SIMULATOR_HOST.value}={SIMULATOR_HOST}")
    environment[ENVIRON_KW.SIMULATOR_HOST.value] = SIMULATOR_HOST

# Extension packages
if args.packages is not None:
    if ENVIRON_KW.COCKPITDECKS_EXTENSION_PATH.value not in environment:
        environment[ENVIRON_KW.COCKPITDECKS_EXTENSION_PATH.value] = args.packages
    else:
        environment[ENVIRON_KW.COCKPITDECKS_EXTENSION_PATH.value] = environment[ENVIRON_KW.COCKPITDECKS_EXTENSION_PATH.value] + args.packages
    startup_logger.info(f"added packages {", ".join(args.packages)}")

# COCKPITDECKS_PATH
#
runtime_deck_paths = config_path_list(runtime_config.get("deck_paths"))
COCKPITDECKS_PATH = ":".join(runtime_deck_paths)
if COCKPITDECKS_PATH == "":
    COCKPITDECKS_PATH = os.getenv(ENVIRON_KW.COCKPITDECKS_PATH.value, "")

# Append from environment file
ENV_PATH = environment.get(ENVIRON_KW.COCKPITDECKS_PATH.value)
if ENV_PATH is not None:
    COCKPITDECKS_PATH = add_env(COCKPITDECKS_PATH, ENV_PATH)

environment[ENVIRON_KW.COCKPITDECKS_PATH.value] = COCKPITDECKS_PATH

startup_logger.debug(f"{ENVIRON_KW.COCKPITDECKS_PATH.value}={COCKPITDECKS_PATH}")

# X-Plane Web API connection
#
xplane_api = config_section(runtime_config.get("xplane_api"), "xplane_api")
api_host_env = os.getenv(ENVIRON_KW.API_HOST.value) or environment.get(ENVIRON_KW.API_HOST.value)
api_port_env = os.getenv(ENVIRON_KW.API_PORT.value) or environment.get(ENVIRON_KW.API_PORT.value)
if os.getenv("COCKPITDECKS_ENGINE"):
    api_host = api_host_env or xplane_api.get("host") or "127.0.0.1"
    api_port = config_port(api_port_env, default=xplane_api.get("port", 8086), name=ENVIRON_KW.API_PORT.value)
else:
    api_host = xplane_api.get("host")
    if not api_host:
        api_host = api_host_env or "127.0.0.1"
    api_port = config_port(xplane_api.get("port"), default=8086, name="xplane_api.port")
    if "port" not in xplane_api:
        api_port = config_port(api_port_env, default=8086, name=ENVIRON_KW.API_PORT.value)
environment[ENVIRON_KW.API_HOST.value] = str(api_host)
environment[ENVIRON_KW.API_PORT.value] = int(api_port)
startup_logger.debug(f"X-Plane API at {api_host}:{api_port}")

# Application environment variables
#
cockpitdecks_server = config_section(runtime_config.get("cockpitdecks_server"), "cockpitdecks_server")
app_bind_host = str(cockpitdecks_server.get("host") or "").strip()
if app_bind_host == "":
    app_host_env = os.getenv(ENVIRON_KW.APP_HOST.value)  # !! should only return a hostname
    if app_host_env is not None:
        app_bind_host = app_host_env
    else:
        configured_app_host = environment.get(ENVIRON_KW.APP_HOST.value, ["127.0.0.1", 7777])
        if isinstance(configured_app_host, (list, tuple)) and len(configured_app_host) >= 2:
            app_bind_host = str(configured_app_host[0])
        else:
            startup_logger.warning(f"invalid {ENVIRON_KW.APP_HOST.value}={configured_app_host}, using default 127.0.0.1:7777")
            app_bind_host = "127.0.0.1"

app_bind_port = config_port(cockpitdecks_server.get("port"), default=7777, name="cockpitdecks_server.port")
if "port" not in cockpitdecks_server:
    app_port_env = os.getenv(ENVIRON_KW.APP_PORT.value)
    if app_port_env is not None:
        app_bind_port = config_port(app_port_env, default=7777, name=ENVIRON_KW.APP_PORT.value)
    else:
        configured_app_host = environment.get(ENVIRON_KW.APP_HOST.value, ["127.0.0.1", 7777])
        if isinstance(configured_app_host, (list, tuple)) and len(configured_app_host) >= 2:
            app_bind_port = config_port(configured_app_host[1], default=7777, name=ENVIRON_KW.APP_PORT.value)

APP_HOST = [app_bind_host, app_bind_port]
environment[ENVIRON_KW.APP_HOST.value] = APP_HOST
environment[ENVIRON_KW.APP_PORT.value] = app_bind_port

startup_logger.debug(f"Cockpitdecks application server at {APP_HOST}")


# Start-up Mode
#
mode = CD_MODE.DEMO if args.demo else CD_MODE.NORMAL
environment[ENVIRON_KW.MODE.value] = mode

ac = args.aircraft_folder or runtime_config.get("target")

if not args.demo:
    if ac is not None:
        target_dir = os.path.abspath(os.path.expanduser(os.path.join(os.getcwd(), ac)))
        if not os.path.exists(target_dir) or not os.path.isdir(target_dir):
            startup_logger.error(f"{target_dir} directory not found")
            sys.exit(1)
        test_dir = os.path.join(target_dir, CONFIG_FOLDER)
        if not os.path.exists(test_dir) or not os.path.isdir(test_dir):
            startup_logger.error(f"{target_dir} directory does not contain {CONFIG_FOLDER} directory")
            sys.exit(1)
        AIRCRAFT_HOME = target_dir
        AIRCRAFT_DESC = os.path.basename(ac)
        mode = CD_MODE.FIXED if args.fixed else CD_MODE.NORMAL
        startup_logger.debug(f"starting aircraft folder {AIRCRAFT_HOME}, {'fixed' if mode.value > 0 else 'dynamically adjusted to aircraft'}")
    elif ac is None:
        if args.fixed:
            startup_logger.error("non demo and fixed mode but no aircraft path")
            sys.exit(1)
        elif len(COCKPITDECKS_PATH) == 0:
            mode = CD_MODE.DEMO
            startup_logger.debug(f"no aircraft path and COCKPITDECKS_PATH not defined: starting in demonstration mode")

startup_logger.debug(f"environment: {environment.store}")
startup_logger.debug(f"cockpitdecks {mode}")
startup_logger.debug(f"..Cockpitdecks configured startup. Let's {'try' if args.fixed else 'fly'}...\n")
#
# COCKPITDECKS STARTS HERE, REALLY
#
copyrights = f"{__NAME__.title()} {__version__}{last_commit} {__COPYRIGHT__}\n{DESC}\n"
print(copyrights)
cockpit = None


# ######################################################################################################
# Flask Web Server (& WebSocket Server)
#
# Serves decks and their assets.
# Proxy WebSockets to TCP Sockets
#
# Local key words and defaults
#
CODE = "code"
WEBDECK_DEFAULTS = "presentation-default"
WEBDECK_WSURL = "ws_url"


# Flask Web Server (& WebSocket Server)
#
app = Flask(__NAME__, template_folder=TEMPLATE_FOLDER)
def persist_runtime_config(updated: dict) -> dict:
    global runtime_config, runtime_config_raw
    runtime_config = updated
    runtime_config_raw = save_runtime_config(RUNTIME_CONFIG_PATH, runtime_config, runtime_config_raw)
    return runtime_config


def get_aircraft_home():
    aircraft = getattr(cockpit, "aircraft", None) if cockpit is not None else None
    acpath = getattr(aircraft, "acpath", None)
    return acpath if acpath is not None else AIRCRAFT_HOME


def get_aircraft_asset_folder():
    return os.path.join(get_aircraft_home(), CONFIG_FOLDER, RESOURCES_FOLDER)


def get_aircraft_deck_types_folder():
    return os.path.join(get_aircraft_asset_folder(), DECKS_FOLDER, DECK_TYPES)


register_web_control(
    app,
    recent_log_handler=_recent_log_handler,
    get_cockpit=lambda: cockpit,
    get_runtime_state=get_runtime_state,
    get_runtime_config=lambda: runtime_config,
    persist_runtime_config=persist_runtime_config,
    runtime_config_path=RUNTIME_CONFIG_PATH,
    environment=environment,
    environ_kw=ENVIRON_KW,
    config_path_list=config_path_list,
    merge_runtime_config=merge_runtime_config,
    process_start_ts=PROCESS_START_TS,
)


def start_cockpit_runtime() -> None:
    global cockpit
    try:
        set_runtime_state("starting", "Initializing Cockpitdecks..")
        logger.info("Initializing Cockpitdecks..")
        cockpit = Cockpit(environ=environment)
        logger.info("..initialized\n")

        start_acpath = AIRCRAFT_HOME
        start_desc = AIRCRAFT_DESC
        if ac is None and mode == CD_MODE.NORMAL:
            start_acpath = None
            start_desc = __NAME__.title()

        set_runtime_state("starting", f"Starting {start_desc}..")
        logger.info(f"Starting {start_desc}..")
        if start_acpath is None:
            logger.info(
                f"(starting without a preloaded aircraft; will load aircraft if {SIMULATOR_NAME} is running and aircraft with Cockpitdecks {CONFIG_FOLDER} loaded)"
            )
        release_to_startup = args.designer or mode == CD_MODE.NORMAL
        cockpit.start_aircraft(acpath=start_acpath, release=release_to_startup, mode=mode.value)
        logger.info(f"..{start_desc} running..")
        set_runtime_state("running", f"{start_desc} running")
        base_url = f"http://{APP_HOST[0]}:{APP_HOST[1]}"
        if cockpit is not None and cockpit.virtual_decks:
            logger.info(f"web decks available at {base_url}:")
            print(f"Web decks available:")
            for deck_name in cockpit.virtual_decks:
                url = f"{base_url}/deck/{deck_name}"
                logger.info(f"  {deck_name}: {url}")
                print(f"  {deck_name}: {url}")
    except Exception as exc:
        logger.exception("Cockpitdecks startup failed")
        set_runtime_state("failed", "Startup failed", error=str(exc))


@app.route("/")
def index():
    virtual_decks = cockpit.virtual_decks if cockpit is not None else {}
    return render_template("index.j2", virtual_decks=virtual_decks, copyrights={"copyrights": copyrights.replace("\n", "<br/>")})


@app.route("/favicon.ico")
def send_favicon():
    return send_from_directory(TEMPLATE_FOLDER, "favicon.ico")


@app.route("/assets/<path:path>")
def send_asset(path):
    return send_from_directory(ASSET_FOLDER, path)


@app.route("/aircraft/<path:path>")
def send_aircraft_asset(path):
    return send_from_directory(get_aircraft_asset_folder(), path)


# Designers
#
def legacy_designer_removed():
    return {
        "error": "legacy web designer removed",
        "message": "Use cockpitdecks-editor for button and deck editing.",
    }, 410


@app.route("/designer")
def designer():
    return legacy_designer_removed()


# Button designer
#
@app.route("/button-designer", methods=("GET", "POST"))
def button_designer():
    return legacy_designer_removed()


@app.route("/deck-indices", methods=("GET", "POST"))
def deck_indices():
    return legacy_designer_removed()


@app.route("/button-details", methods=("GET", "POST"))
def button_details():
    return legacy_designer_removed()


@app.route("/activation", methods=("GET", "POST"))
def activation_details():
    return legacy_designer_removed()


@app.route("/representation", methods=("GET", "POST"))
def representation_details():
    return legacy_designer_removed()


@app.route("/load-button", methods=("GET", "POST"))
def button_definition():
    return legacy_designer_removed()


# Button designer - SVELTE
#
@app.route("/aircraft-list", methods=("GET", "POST"))
def aircraft_list():
    return legacy_designer_removed()


@app.route("/capabilities", methods=("GET", "POST"))
def capabilities():
    return legacy_designer_removed()


@app.route("/preview", methods=("GET", "POST"))  # alias to button-designer
def preview():
    return legacy_designer_removed()


# Deck designer
#
@app.route("/deck-designer")
def deck_designer():
    return legacy_designer_removed()


@app.route("/deck-designer-io", methods=("GET", "POST"))
def button_designer_io():
    return legacy_designer_removed()


# Deck runner
#
@app.route("/deck/<name>")
def deck(name: str):
    if cockpit is None:
        abort(503, description="Cockpitdecks is still starting up")
    uname = urllib.parse.unquote(name)
    app.logger.debug(f"Starting deck {uname}")
    deck_desc = cockpit.get_virtual_deck_description(uname)
    # Inject our contact address:
    if type(deck_desc) is dict:
        ws_host = request.host
        deck_desc[WEBDECK_WSURL] = f"ws://{ws_host}/cockpit"
        deck_desc[WEBDECK_DEFAULTS] = cockpit.get_virtual_deck_defaults()
        deck_desc["dark_mode"] = cockpit.sim.is_night()
    else:
        app.logger.debug(f"deck desc is not a dict {deck_desc}")
    return render_template("deck.j2", deck=deck_desc)


@app.route("/deck-bg/<name>", defaults={"alternate": None})
@app.route("/deck-bg/<name>/alternate/<alternate>")
def deck_bg(name: str, alternate: str | None = None):
    if cockpit is None:
        abort(503, description="Cockpitdecks is still starting up")
    if name is None or name == "":
        app.logger.debug(f"no deck name")
        abort(404)
    uname = urllib.parse.unquote(name)
    deck_desc = cockpit.get_virtual_deck_description(uname)
    if deck_desc is None:
        app.logger.debug(f"no description")
        abort(404)
    deck_flat = deck_desc.get(DECK_TYPE_DESCRIPTION)
    if deck_flat is None:
        app.logger.debug(f"no {DECK_TYPE_DESCRIPTION} in description")
        abort(404)
    if alternate is not None:
        deck_img = deck_flat.get(DECK_KW.BACKGROUND_IMAGE_ALTERNATE_PATH.value)  # can be "background-image": None
        if deck_img is None:
            app.logger.debug(f"no {DECK_KW.BACKGROUND_IMAGE_ALTERNATE_PATH.value} in {DECK_TYPE_DESCRIPTION}")
            abort(404)
        if deck_img == "":
            app.logger.debug(f"no alternate background image for {uname}")
            abort(404)
        if not os.path.exists(deck_img):
            app.logger.debug(f"alternate background image not found {deck_img}")
            abort(404)
        return send_file(deck_img, mimetype="image/png")

    deck_img = deck_flat.get(DECK_KW.BACKGROUND_IMAGE_PATH.value)  # can be "background-image": None
    if deck_img is None:
        app.logger.debug(f"no {DECK_KW.BACKGROUND_IMAGE_PATH.value} in {DECK_TYPE_DESCRIPTION}")
        abort(404)
    if deck_img == "":
        app.logger.debug(f"no background image for {uname}")
        abort(404)
        deck_img = deck_flat.get(DECK_KW.BACKGROUND_IMAGE_ALTERNATE_PATH.value)  # can be "background-image": None
    if not os.path.exists(deck_img):
        app.logger.debug(f"background image not found {deck_img}")
        abort(404)
    return send_file(deck_img, mimetype="image/png")


@app.route("/cockpit", websocket=True)  # How convenient...
def cockpit_wshandler():
    ws = Server.accept(request.environ)
    try:
        while True:
            data = ws.receive()
            app.logger.debug(f"received {data}")
            if data is None:
                app.logger.debug("websocket closed by client")
                break

            if cockpit is None:
                app.logger.warning("cockpit not initialized, ignoring message")
                continue

            data = json.loads(data)
            code = data.get(CODE)
            if code == 1:
                deck = data.get("deck")
                cockpit.register_deck(deck, ws)
                # app.logger.info(f"registered deck {deck}")
                cockpit.handle_code(code, deck)
                app.logger.debug(f"handled deck={deck}, code={code}")
            elif code == 0 or code == 99:  # 99 is replay
                deck = data.get("deck")
                if deck is None:  # sim event
                    cockpit.replay_sim_event(data=data)
                    # app.logger.info(f"event processed, data={data}")
                else:
                    key = data.get("key")
                    event = data.get("event")
                    payload = data.get("data")
                    cockpit.process_event(deck_name=deck, key=key, event=event, data=payload, replay=code == 99)
                # app.logger.info(f"event processed deck={deck}, event={event} data={payload}")
    except ConnectionClosed:
        app.logger.debug("connection closed")
        if cockpit is not None:
            cockpit.remove_client(ws)
            app.logger.debug("client removed")
    return ""


# ##################################
# MAIN
#
# Wrapped in main function to make it accessible
# from builder/installer
#
def main():
    try:
        suppress_console_logging()
        print(f"Cockpitdecks control available at http://{APP_HOST[0]}:{APP_HOST[1]}/control")
        logger.info("starting application server..")
        startup_thread = threading.Thread(target=start_cockpit_runtime, name="CockpitStartup", daemon=True)
        startup_thread.start()
        if args.web:
            url = f"http://{APP_HOST[0]}:{APP_HOST[1]}"
            logger.info(f"..opening browser window ({url})..")
            webbrowser.open(url)
        app.run(host="0.0.0.0", port=APP_HOST[1])

        # If single CTRL-C pressed, will terminate from here
        # logger.info("terminating (please wait)..")
        print("")  # to highlight CTRL-C in log window
        logger.info("..application server terminated")
        if cockpit is not None:
            cockpit.terminate_all(threads=1)  # [MainThread]
            logger.info(f"..{cockpit.get_aircraft_name()} terminated")
        # os._exit(0)

    except KeyboardInterrupt:

        def spin():
            spinners = ["|", "/", "-", "\\"]
            for c in itertools.cycle(spinners):
                print(f"\r{c}", end="")
                time.sleep(0.1)

        logger.info("terminating (please wait)..")
        thread = threading.Thread(target=spin, name="spinner", daemon=True)
        thread.start()

        if cockpit is not None:
            cockpit.terminate_all(threads=1)
        logger.info(f"..{AIRCRAFT_DESC} terminated.")


# Run if unwrapped
if __name__ == "__main__":
    main()
