# ###########################
# Representation of a Metar in short textual summary form
#
import logging

from cockpitdecks.buttons.representation import WeatherStationPlot
from ...resources.weatheravwx import WeatherAVWX

logger = logging.getLogger(__name__)
# logger.setLevel(SPAM_LEVEL)
# logger.setLevel(logging.DEBUG)


class LiveStationPlot(WeatherStationPlot):
    """
    Depends on avwx-engine
    """

    REPRESENTATION_NAME = "live-station-plot"

    def __init__(self, button: "Button"):
        WeatherStationPlot.__init__(self, button=button)
        icao = button._config.get(self.REPRESENTATION_NAME).get("station", self.DEFAULT_STATION)
        self.button = button
        self.weather_data = WeatherAVWX(icao=icao, client=button.name)
        self.weather_data.add_listener(self)
