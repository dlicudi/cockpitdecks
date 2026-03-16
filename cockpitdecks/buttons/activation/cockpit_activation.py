"""
Button action and activation abstraction
"""

import logging
import os
import random
import subprocess

from cockpitdecks.event import EncoderEvent, PushEvent
from cockpitdecks import DECK_ACTIONS, CONFIG_KW, ID_SEP, ENVIRON_KW
from cockpitdecks.resources.intvariables import COCKPITDECKS_INTVAR
from .activation import Activation
from .deck_activation import EncoderProperties

# from ...cockpit import CockpitInstruction

logger = logging.getLogger(__name__)
# from cockpitdecks import SPAM
# logger.setLevel(SPAM_LEVEL)
# logger.setLevel(logging.DEBUG)

INSTRUCTION_PREFIX = "cockpitdecks-"


class CockpitActivation(Activation):
    """
    Base class for all deck activations.
    """

    ACTIVATION_NAME = "cockpit"

    PARAMETERS = Activation.PARAMETERS

    def __init__(self, button: "Button"):
        Activation.__init__(self, button=button)


class LoadPage(Activation):
    """
    Defines a Page change activation.
    """

    ACTIVATION_NAME = "page"
    REQUIRED_DECK_ACTIONS = [DECK_ACTIONS.PRESS, DECK_ACTIONS.LONGPRESS, DECK_ACTIONS.PUSH]

    KW_BACKPAGE = "back"

    PARAMETERS = {
        "page": {"type": "string", "prompt": "Page", "default-value": "back", "mandatory": True},
        "deck": {"type": "string", "prompt": "Remote deck"},
    }
    SKIP_OLD_PAGE_RENDER = True

    def __init__(self, button: "Button"):
        Activation.__init__(self, button=button)

        # Activation arguments
        self.page = self._config.get("page", LoadPage.KW_BACKPAGE)  # default is to go to previously loaded page, if any
        self.remote_deck = self._config.get("deck")
        self.instruction = self.cockpit.instruction_factory(
            name=INSTRUCTION_PREFIX + "page",
            instruction_block={"page": self.page, "deck": self.remote_deck if self.remote_deck is not None else self.button.deck.name},
        )

    def is_valid(self):
        if self.page is None:
            logger.warning(f"button {self.button_name}: {type(self).__name__} has no page")
            return False
        return super().is_valid()

    def activate(self, event: PushEvent) -> bool:
        if not self.can_handle(event):
            return False
        if not super().activate(event):
            return False
        if event.pressed:
            self.instruction.execute()
        return True  # Normal termination

    def describe(self) -> str:
        """
        Describe what the button does in plain English
        """
        deck = f"deck {self.remote_deck}" if self.remote_deck is not None else "the current deck"
        return "\n\r".join([f"The button loads page {self.page} on {deck}."])


class LoadPageCycle(Activation, EncoderProperties):
    """
    Defines a Page cycle activation for encoders.
    Rotating the encoder cycles through a defined list of pages.
    Pushing the encoder loads the first page in the list (home).
    """

    ACTIVATION_NAME = "page-cycle"
    REQUIRED_DECK_ACTIONS = [DECK_ACTIONS.ENCODER, DECK_ACTIONS.PRESS, DECK_ACTIONS.LONGPRESS, DECK_ACTIONS.PUSH]

    PARAMETERS = {
        "pages": {"type": "list", "prompt": "Pages to cycle through", "mandatory": True},
        "deck": {"type": "string", "prompt": "Remote deck"},
    }
    SKIP_OLD_PAGE_RENDER = True

    def __init__(self, button: "Button"):
        Activation.__init__(self, button=button)
        EncoderProperties.__init__(self, button=button)

        self.pages = self._config.get("pages", [])
        self.remote_deck = self._config.get("deck")
        self._page_index = 0

    @property
    def deck_name(self):
        return self.remote_deck if self.remote_deck is not None else self.button.deck.name

    def _make_page_instruction(self, page: str):
        return self.cockpit.instruction_factory(
            name=INSTRUCTION_PREFIX + "page",
            instruction_block={"page": page, "deck": self.deck_name},
        )

    def _current_page_index(self) -> int:
        """Find current page in cycle list, defaulting to 0."""
        deck = self.cockpit.decks.get(self.deck_name)
        if deck is not None and deck.current_page is not None:
            current = deck.current_page.name
            if current in self.pages:
                return self.pages.index(current)
        return self._page_index

    def is_valid(self):
        if not self.pages or len(self.pages) < 2:
            logger.warning(f"button {self.button_name}: {type(self).__name__} needs at least 2 pages")
            return False
        return super().is_valid()

    def activate(self, event) -> bool:
        if not self.can_handle(event):
            return False
        if not super().activate(event):
            return False

        if isinstance(event, EncoderEvent):
            idx = self._current_page_index()
            if event.turned_clockwise:
                idx = (idx + 1) % len(self.pages)
                self.inc(COCKPITDECKS_INTVAR.ENCODER_TURNS.value, 1)
                self.inc(COCKPITDECKS_INTVAR.ENCODER_CLOCKWISE.value)
            elif event.turned_counter_clockwise:
                idx = (idx - 1) % len(self.pages)
                self.inc(COCKPITDECKS_INTVAR.ENCODER_TURNS.value, -1)
                self.inc(COCKPITDECKS_INTVAR.ENCODER_COUNTER_CLOCKWISE.value)
            self._page_index = idx
            self._make_page_instruction(self.pages[idx]).execute()

        elif isinstance(event, PushEvent):
            if event.pressed:
                self._page_index = 0
                self._make_page_instruction(self.pages[0]).execute()

        return True

    def get_activation_value(self):
        return self._turns

    def get_state_variables(self) -> dict:
        a = {
            COCKPITDECKS_INTVAR.ENCODER_CLOCKWISE.value: self._cw,
            COCKPITDECKS_INTVAR.ENCODER_COUNTER_CLOCKWISE.value: self._ccw,
            COCKPITDECKS_INTVAR.ENCODER_TURNS.value: self._turns,
            "page_index": self._page_index,
        }
        return a | super().get_state_variables()

    def describe(self) -> str:
        deck = f"deck {self.remote_deck}" if self.remote_deck is not None else "the current deck"
        return "\n\r".join([
            f"This encoder cycles through pages {', '.join(self.pages)} on {deck}.",
            f"Pushing the encoder loads the first page ({self.pages[0] if self.pages else 'none'}).",
        ])


class Reload(Activation):
    """
    Reloads all decks.
    """

    ACTIVATION_NAME = "reload"
    REQUIRED_DECK_ACTIONS = [DECK_ACTIONS.PRESS, DECK_ACTIONS.LONGPRESS, DECK_ACTIONS.PUSH]

    PARAMETERS = {
        "deck": {
            "type": "string",
            "prompt": "Deck",
        }
    }

    def __init__(self, button: "Button"):
        Activation.__init__(self, button=button)
        self.deck = self._config.get("deck")
        self.instruction = None
        if self.deck is None:
            self.instruction = self.cockpit.instruction_factory(name=INSTRUCTION_PREFIX + "reload", instruction_block={})
        else:
            self.instruction = self.cockpit.instruction_factory(name=INSTRUCTION_PREFIX + "reload1", instruction_block={"deck": self.deck})

    def activate(self, event) -> bool:
        if not self.can_handle(event):
            return False
        if not event.pressed:  # trigger on button "release"
            self.instruction.execute()
            # if self.deck is not None:
            #     self.button.deck.cockpit.reload_deck(deck_name=self.deck)
            # else:
            #     self.button.deck.cockpit.reload_decks()
        return True

    def describe(self) -> str:
        """
        Describe what the button does in plain English
        """
        return "\n\r".join(["The button reloads all decks and tries to reload the page that was displayed."])


class ChangeTheme(Activation):
    """
    Reloads all decks.
    """

    ACTIVATION_NAME = "theme"
    REQUIRED_DECK_ACTIONS = [DECK_ACTIONS.PRESS, DECK_ACTIONS.LONGPRESS, DECK_ACTIONS.PUSH]

    PARAMETERS = {
        "theme": {
            "type": "string",
            "prompt": "Theme",
        }
    }

    def __init__(self, button: "Button"):
        Activation.__init__(self, button=button)

        # Activation arguments
        self.theme = self._config.get("theme")
        self.instruction = self.cockpit.instruction_factory(name=INSTRUCTION_PREFIX + "theme", instruction_block={"theme": self.theme})

    def is_valid(self):
        if self.theme is None:
            logger.warning(f"button {self.button_name}: {type(self).__name__} has no theme")
            return False
        return super().is_valid()

    def activate(self, event) -> bool:
        if not self.can_handle(event):
            return False
        if not self.is_valid():
            return False
        if not event.pressed:  # trigger on button "release"
            self.instruction.execute()
        return True  # normal termination

    def describe(self) -> str:
        """
        Describe what the button does in plain English
        """
        return "\n\r".join([f"The button switches between dark and light (night and day) themes and reload pages."])


class Inspect(Activation):
    """
    Inspect all decks.
    """

    ACTIVATION_NAME = "inspect"
    REQUIRED_DECK_ACTIONS = [DECK_ACTIONS.PRESS, DECK_ACTIONS.LONGPRESS, DECK_ACTIONS.PUSH]

    PARAMETERS = {
        "what": {
            "type": "string",
            "prompt": "What to inspect",
            "default-value": "status",
            "lov": ["thread", "datarefs", "monitored", "print", "invalid", "status", "config", "valid", "desc", "dataref", "desc"],
        }
    }

    def __init__(self, button: "Button"):
        Activation.__init__(self, button=button)

        # Activation arguments
        self.what = self._config.get("what", "status")

    def activate(self, event) -> bool:
        if not self.can_handle(event):
            return False
        if event.pressed:
            self.button.deck.cockpit.inspect(self.what)
        return True  # normal termination

    def get_state_variables(self) -> dict:
        s = super().get_state_variables()
        if s is None:
            s = {}
        s = s | {"what": self.what}
        return s

    def describe(self) -> str:
        """
        Describe what the button does in plain English
        """
        return "\n\r".join([f"The button displays '{self.what}' information about each cockpit, deck, page and/or button."])


class Stop(Activation):
    """
    Stops all decks.
    """

    ACTIVATION_NAME = "stop"
    REQUIRED_DECK_ACTIONS = [DECK_ACTIONS.PRESS, DECK_ACTIONS.LONGPRESS, DECK_ACTIONS.PUSH]

    PARAMETERS = {}

    def __init__(self, button: "Button"):
        Activation.__init__(self, button=button)
        self.instruction = self.cockpit.instruction_factory(name=INSTRUCTION_PREFIX + self.ACTIVATION_NAME, instruction_block={})

    def activate(self, event) -> bool:
        if not self.can_handle(event):
            return False

        # Guard handling
        if not super().activate(event):
            return False

        if not self.is_guarded():
            if not event.pressed:  # trigger on button "release"
                self.instruction.execute()
        return True  # normal termination

    def describe(self) -> str:
        """
        Describe what the button does in plain English
        """
        return "\n\r".join(["The button stops Cockpitdecks and terminates gracefully."])


class StartSimulator(Activation):
    """
    Starts local copy of simulator software if not running.
    Currently only works on MacOS.
    """

    ACTIVATION_NAME = "simulator"
    REQUIRED_DECK_ACTIONS = [DECK_ACTIONS.PRESS, DECK_ACTIONS.LONGPRESS, DECK_ACTIONS.PUSH]

    PARAMETERS = {}

    def __init__(self, button: "Button"):
        Activation.__init__(self, button=button)

    def activate(self, event) -> bool:
        if not self.can_handle(event):
            return False

        # Guard handling
        if not super().activate(event):
            return False

        if not self.is_guarded():
            if not event.pressed:  # os dependent
                # 1. Should check it is already running, may be remote?
                # 2. Start it locally at least:
                # 2.a: build path from environ (SIMULATOR_HOME) and exe name
                sim_home = self.cockpit._environ.get(ENVIRON_KW.SIMULATOR_HOME.value)
                if sim_home is None:
                    sim_home = os.environ.get(ENVIRON_KW.SIMULATOR_HOME.value)
                if sim_home is None:
                    logger.error("cannot start simulator: SIMULATOR_HOME not set in environ")
                    return False
                p = subprocess.Popen(["open", sim_home])

        return True  # normal termination

    def describe(self) -> str:
        """
        Describe what the button does in plain English
        """
        return "\n\r".join(["The button stops Cockpitdecks and terminates gracefully."])


class Obs(Activation):
    """
    Execute observable instruction (to enable, disable)
    """

    ACTIVATION_NAME = "obs"
    REQUIRED_DECK_ACTIONS = [DECK_ACTIONS.PRESS, DECK_ACTIONS.LONGPRESS, DECK_ACTIONS.PUSH]

    PARAMETERS = {
        "observable": {
            "type": "string",
            "prompt": "Observable",
        },
        "action": {
            "type": "string",
            "prompt": "Action",
            "default-value": "toggle",
            "lov": ["toggle", "enable", "disable"],
        },
    }

    def __init__(self, button: "Button"):
        Activation.__init__(self, button=button)
        self.observable = self._config.get(CONFIG_KW.OBSERVABLE.value)
        self.instruction = self.cockpit.instruction_factory(
            name=INSTRUCTION_PREFIX + "obs", instruction_block={"observable": self.observable, "action": self._config.get(CONFIG_KW.ACTION.value, "toggle")}
        )

    def get_variables(self) -> set:
        if self.observable is not None:
            return {ID_SEP.join([CONFIG_KW.OBSERVABLE.value, self.observable])}
        return set()

    def activate(self, event) -> bool:
        if not self.can_handle(event):
            return False

        # Guard handling
        if not super().activate(event):
            return False

        if not self.is_guarded():
            if not event.pressed:  # trigger on button "release"
                self.instruction.execute()
        return True  # normal termination

    def describe(self) -> str:
        """
        Describe what the button does in plain English
        """
        return "\n\r".join(["The button enable, disable, or toggle (enable/disable) an observable."])


# class Random(Activation):
#     """
#     Set the value of the button to a float random number between 0 and 1..
#     """

#     ACTIVATION_NAME = "random"
#     REQUIRED_DECK_ACTIONS = [DECK_ACTIONS.PRESS, DECK_ACTIONS.LONGPRESS, DECK_ACTIONS.PUSH, DECK_ACTIONS.ENCODER]

#     PARAMETERS = {}

#     def __init__(self, button: "Button"):
#         Activation.__init__(self, button=button)

#         # Activation arguments
#         self.random_value = 0.0

#     def activate(self, event) -> bool:
#         if not self.can_handle(event):
#             return False
#         if event.pressed:
#             self.random_value = random.random()
#         return True  # normal termination

#     def get_state_variables(self) -> dict:
#         s = super().get_state_variables()
#         if s is None:
#             s = {}
#         s = s | {"random": self.random_value}
#         return s

#     def describe(self) -> str:
#         """
#         Describe what the button does in plain English
#         """
#         return "\n\r".join(["The button stops Cockpitdecks and terminates gracefully."])
