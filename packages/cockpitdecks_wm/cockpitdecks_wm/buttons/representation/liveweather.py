# ###########################
# Representation of a Metar in short textual summary form
#
import logging

from avwx import Taf

from cockpitdecks.buttons.representation import WeatherBaseIcon
from ...resources.weatheravwx import WeatherAVWX

logger = logging.getLogger(__name__)
# logger.setLevel(SPAM_LEVEL)
# logger.setLevel(logging.DEBUG)


class LiveWeatherIcon(WeatherBaseIcon):
    """
    Depends on avwx-engine
    """

    REPRESENTATION_NAME = "live-weather"

    def __init__(self, button: "Button"):
        WeatherBaseIcon.__init__(self, button=button)
        icao = self.weather.get("station", self.DEFAULT_STATION)
        taf = self.weather.get("taf", False)
        self.width = self.weather.get("width", 21)
        self.set_label(icao)
        self.weather_data = WeatherAVWX(icao=icao, taf=taf, client=button.name)
        self.weather_data.add_listener(self)
        self.always_render = True

    def updated(self) -> bool:
        return self.button.has_changed()  # to cycle pages

    # #############################################
    # Cockpitdecks Representation interface
    #
    def get_lines(self) -> list | None:
        # METAR
        if not self.weather_data.taf:
            return self.weather_data.weather.summary.split(",")  # ~ 6-7 short lines
        # TAF
        return self.weather_data.get_forecast_page(page=self.get_activation_count(), width=self.width)
