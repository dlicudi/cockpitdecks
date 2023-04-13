import os
import logging
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from cockpitdecks import Cockpit
from cockpitdecks import __NAME__, __version__, __COPYRIGHT__
from cockpitdecks.xplaneudp import XPlaneUDP

# logging.basicConfig(level=logging.DEBUG, filename="streamdecks.log", filemode='a')
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__NAME__.title())

ac = sys.argv[1] if len(sys.argv) > 1 else "AIRCRAFT"
s = None

try:
    logger.info(f"{__version__} {__COPYRIGHT__}")
    logger.info(f"Starting for {ac}..")
    logger.info(f"..searching for decks and initializing them (this may take a few seconds)..")
    # if len(sys.argv) > 2 and sys.argv[2] == "d":
    #     logging.basicConfig(level=logging.DEBUG)
    #     logger.info(f"..debug..")
    s = Cockpit(XPlaneUDP)
    s.start_aircraft(os.path.join(os.path.dirname(__file__), ac))
    logger.info(f"..{ac} terminated.")
except KeyboardInterrupt:
    if s is not None:
        s.terminate_all()
    logger.info(f"..{ac} terminated.")