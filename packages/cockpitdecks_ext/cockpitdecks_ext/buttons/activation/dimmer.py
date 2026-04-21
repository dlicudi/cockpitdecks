# ###########################
#
import logging

from cockpitdecks import DECK_ACTIONS
from cockpitdecks.buttons.activation import Sweep

logger = logging.getLogger(__name__)
# logger.setLevel(logging.DEBUG)


class LightDimmer(Sweep):
    """Customized class to dim deck back lights according to up-down switch value"""

    ACTIVATION_NAME = "dimmer"

    REQUIRED_DECK_ACTIONS = [DECK_ACTIONS.PRESS, DECK_ACTIONS.LONGPRESS, DECK_ACTIONS.PUSH]

    _DIMMER_DEF = {"dimmer": {"type": "list", "schema": {"type": "integer"}, "meta": {"label": "Dataref"}}}
    PARAMETERS = getattr(Sweep, "PARAMETERS", {}) | _DIMMER_DEF
    SCHEMA = getattr(Sweep, "SCHEMA", {}) | _DIMMER_DEF

    def __init__(self, button: "Button"):
        Sweep.__init__(self, button=button)
        self.dimmer = self._config.get("dimmer", [10, 90])
        self.deck_alt = self._config.get("deck")
        self.adjust_cockpit = self._config.get("adjust-cockpit", True)

    def activate(self, event):
        currval = self.stop_current
        if currval is not None and 0 <= currval < len(self.dimmer):
            deck = self.button.deck
            if self.deck_alt is not None:
                deck = self.button.deck.cockpit.decks.get(self.deck_alt)
                if deck is None:
                    logger.warning(f"target deck {self.deck_alt} not found")
                    return
            deck.set_brightness(self.dimmer[currval])
            # do it globally as well
            if self.adjust_cockpit:
                self.button.deck.cockpit.adjust_light(brightness=int(self.dimmer[currval]) / 100)
        super().activate(event)
