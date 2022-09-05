import os
import logging
from time import sleep

from streamdecks import Streamdecks, XPlaneUDP

# logging.basicConfig(level=logging.DEBUG, filename="streamdecks.log", filemode='a')
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("streamdecks")

s = None
try:
    s = Streamdecks(None, XPlaneUDP)
    s.load(os.path.join(os.path.dirname(__file__), "A321"))
except KeyboardInterrupt:
    if s is not None:
        s.terminate_all()