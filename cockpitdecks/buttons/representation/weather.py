# ###########################
# Abstract Base Representation for weather icons.
# The ABC offerts basic update structures, just need
#  - A Weather data feed
#  - get_image_for_icon() to provide an iconic representation of the weather provided as above.
#
from __future__ import annotations
import logging
from datetime import datetime, timedelta
from threading import Lock
from typing import Tuple

from PIL import Image, ImageDraw

from cockpitdecks import ICON_SIZE
from cockpitdecks.resources.iconfonts import WEATHER_ICON_FONT
from cockpitdecks.resources.color import light_off, TRANSPARENT_PNG_COLOR
from cockpitdecks.resources.weather import WeatherData, WeatherDataListener
from cockpitdecks.buttons.representation.draw_animation import DrawAnimation
from cockpitdecks.simulator import SimulatorVariable, SimulatorVariableListener

logger = logging.getLogger(__name__)
# logger.setLevel(SPAM_LEVEL)
logger.setLevel(logging.DEBUG)


class WeatherBaseIcon(DrawAnimation, WeatherDataListener, SimulatorVariableListener):
    """Base class for all weather iconic representations.
    Subclasses produce different iconic representations: Simple text, pages of text, station plot...
    This base class proposes a simple textual display of lines returned by the get_lines() function.
    Internally, the weather-type class is responsible for fetching weather data
    """

    REPRESENTATION_NAME = "weather-icon-base"

    DEFAULT_STATION = "EBBR"  # LFBO for Airbus?

    PARAMETERS = {
        "speed": {"type": "integer", "prompt": "Refresh weather (seconds)"},
        "Refresh location": {"type": "integer", "prompt": "Refresh location (seconds)"},
    }

    def __init__(self, button: "Button"):
        self.weather = button._config.get(self.REPRESENTATION_NAME)  # Weather specific config
        if self.weather is not None and isinstance(self.weather, dict):  # Add animation parameters for automatic update
            button._config["animation"] = button._config.get(self.REPRESENTATION_NAME)
        else:
            button._config["animation"] = {}
            self.weather = {}

        # Working variables
        self._weather_data: WeatherData
        self._last_updated = datetime.now().astimezone() - timedelta(seconds=3600)

        # Weather image management
        self.protection = Lock()

        # Following parameters are overwritten by config
        self.icao_dataref_path = button._config.get("string-dataref")
        self.icao_dataref = None

        DrawAnimation.__init__(self, button=button)

        icao = self.weather.get("station", self.DEFAULT_STATION)
        self.set_label(icao)

        # "Animation" (refresh) rate
        speed = self.weather.get("refresh", 10)  # minutes, should be ~30 minutes
        self.speed = int(speed) * 60  # minutes

        # This is for the weather icon in the background
        self.icon_color = self.weather.get("icon-color", self.get_attribute("text-color"))

    def init(self):
        if self._inited:
            return
        if self.icao_dataref_path is not None:
            # toliss_airbus/flightplan/departure_icao
            # toliss_airbus/flightplan/destination_icao
            self.icao_dataref = self.button.sim.get_variable(self.icao_dataref_path, is_string=True)
            self.icao_dataref.add_listener(self)  # the representation gets notified directly.
            self.simulator_variable_changed(self.icao_dataref)
            self._inited = True
            logger.debug(f"initialized, waiting for dataref {self.icao_dataref.name}")
        self._inited = True

    def get_variables(self) -> set:
        ret = set()
        if self.icao_dataref_path is not None:
            ret.add(self.icao_dataref_path)
        return ret

    # #############################################
    # Weather data interface
    #
    @property
    def weather_data(self) -> WeatherData:
        return self._weather_data

    @weather_data.setter
    def weather_data(self, weather_data: WeatherData):
        self._weather_data = weather_data
        self.weather_changed()

    def weather_changed(self):
        self.set_label(self.weather_data.label)
        self.button.render()

    def has_weather(self) -> bool:
        return getattr(self, "weather_data", None) is not None

    # #############################################
    # Cockpitdecks Representation interface
    #
    def should_run(self) -> bool:
        """
        Check conditions to animate the icon.
        In this case, always runs
        """
        return self._inited and self.button.on_current_page()

    def anim_start(self):
        super().anim_start()
        if self.has_weather():
            logger.info("starting weather surveillance")
            self.weather_data.start()
        else:
            logger.info(f"no weather surveillance {self.button.button_name()}")

    def anim_stop(self):
        super().anim_stop()
        if self.weather_data is not None:
            logger.info("stopping weather surveillance")
            self.weather_data.stop()
        else:
            logger.info("no weather surveillance")

    def animate(self):
        if self.has_weather():
            if not self.weather_data.is_running:
                self.weather_data.start()
        else:
            logger.info(f"no weather surveillance {self.button.button_name()}")

    def updated(self) -> bool:
        """Determine if cached icon reflects weather data or needs redoing"""
        if self.weather_data.last_updated is None:
            return False
        return self.weather_data.last_updated > self._last_updated

    def set_label(self, label: str = "Weather"):
        self.button._config["label"] = label if label is not None else "Weather"

    def get_image_for_icon(self):
        """
        Helper function to get button image and overlay label on top of it.
        Label may be updated at each activation since it can contain datarefs.
        Also add a little marker on placeholder/invalid buttons that will do nothing.
        """
        with self.protection:
            if self.updated() or self._cached is None:
                self.make_weather_image()

        return self._cached

    def simulator_variable_changed(self, data: SimulatorVariable):
        # what if Dataref.internal_variableref_path("weather:*") change?
        if data.name != self.icao_dataref_path:
            return
        icao = data.value()
        if icao is None or icao == "":  # no new station, stick or current
            return
        self.weather_data.set_station(station=icao)

    # #############################################
    # Cockpitdecks Representation interface
    #
    def get_lines(self) -> list | None:
        return None

    def make_weather_image(self):
        # Generic display text in small font on icon
        image = Image.new(mode="RGBA", size=(ICON_SIZE, ICON_SIZE), color=TRANSPARENT_PNG_COLOR)  # annunciator text and leds , color=(0, 0, 0, 0)
        draw = ImageDraw.Draw(image)
        inside = round(0.04 * image.width + 0.5)

        # Weather Icon in the background
        icon_font = self._config.get("icon-font", WEATHER_ICON_FONT)
        icon_size = int(image.width / 2)
        icon_color = self.icon_color
        font = self.get_font(icon_font, icon_size)
        inside = round(0.04 * image.width + 0.5)
        w = image.width / 2
        h = image.height / 2
        weather_icon, icon_text = self.weather_data.get_icon()
        if weather_icon is not None:
            logger.debug(f"weather icon: {weather_icon}")
            draw.text(
                (w, h),
                text=icon_text,
                font=font,
                anchor="mm",
                align="center",
                fill=light_off(icon_color, 0.8),
            )
        else:
            logger.debug("no weather icon")

        # Weather Data
        lines = self.get_lines()

        if lines is not None:
            text, text_format, text_font, text_color, text_size, text_position = self.get_text_detail(self._representation_config, "weather")
            if text_font is None:
                text_font = self.label_font
            if text_size is None:
                text_size = int(image.width / 10)
            if text_color is None:
                text_color = self.label_color
            font = self.get_font(text_font, text_size)
            w = inside
            p = "l"
            a = "left"
            h = image.height / 3
            il = text_size
            for line in lines:
                draw.text(
                    (w, h),
                    text=line.strip(),
                    font=font,
                    anchor=p + "m",
                    align=a,
                    fill=text_color,
                )
                h = h + il
        else:
            logger.warning("no weather information")

        # Paste image on cockpit background and return it.
        bg = self.button.deck.get_icon_background(
            name=self.button_name(),
            width=ICON_SIZE,
            height=ICON_SIZE,
            texture_in=self.cockpit_texture,
            color_in=self.cockpit_color,
            use_texture=True,
            who="Weather",
        )
        bg.alpha_composite(image)
        self._last_updated = datetime.now().astimezone()
        self._cached = bg