"""
Button action and activation abstraction
"""

import logging
import threading

from cockpitdecks.constant import ID_SEP
from cockpitdecks.event import EncoderEvent, PushEvent, SwipeEvent, TouchEvent
from cockpitdecks.resources.color import is_integer
from cockpitdecks import CONFIG_KW, DECK_KW, DECK_ACTIONS
from cockpitdecks.resources.intvariables import COCKPITDECKS_INTVAR
from .activation import Activation

from .parameters import PARAM_DECK, PARAM_INITIAL_VALUE, PARAM_PUSH_AUTOREPEAT, PARAM_COMMAND_BLOCK, PARAM_SETVALUE_BLOCK

logger = logging.getLogger(__name__)
# from cockpitdecks import SPAM
# logger.setLevel(SPAM_LEVEL)
# logger.setLevel(logging.DEBUG)


class DeckActivation(Activation):
    """
    Base class for all deck activations.
    """

    ACTIVATION_NAME = "deck"

    PARAMETERS = Activation.PARAMETERS | PARAM_DECK

    def __init__(self, button: "Button"):
        Activation.__init__(self, button=button)


#
# ###############################
# PUSH-BUTTON TYPE ACTIVATIONS
#
#
class Push(DeckActivation):
    """
    Defines a Push activation.
    The supplied command is executed each time a button is pressed.
    """

    ACTIVATION_NAME = "push"
    EDITOR_FAMILY = "Push Button"
    EDITOR_LABEL = "Momentary Command"
    REQUIRED_DECK_ACTIONS = [DECK_ACTIONS.PRESS, DECK_ACTIONS.LONGPRESS, DECK_ACTIONS.PUSH]

    PARAMETERS = DeckActivation.PARAMETERS | PARAM_PUSH_AUTOREPEAT | PARAM_INITIAL_VALUE | {
        "commands": {"type": "sub", "list": {
            "press": {"type": "string", "label": "Press Command"},
            "long-press": {"type": "string", "label": "Long Press Command"},
        }},
    }

    # Default values
    AUTO_REPEAT_DELAY = 1  # seconds
    AUTO_REPEAT_SPEED = 0.2  # seconds

    def __init__(self, button: "Button"):
        DeckActivation.__init__(self, button=button)

        # Activation arguments
        # Command — read from commands.press
        commands = button._config.get("commands", {}) or {}
        cmd = commands.get("press")
        if cmd is not None:
            cmdname = ":".join([self.button.get_id(), type(self).__name__])
            if type(cmd) is str:
                cmd = {CONFIG_KW.COMMAND.value: cmd}
            self._command = self.sim.instruction_factory(name=cmdname, instruction_block=cmd)

        # Working variables
        self.pressed = False  # True while the button is pressed, False when released

        # Auto-repeat
        self.auto_repeat = self.button.has_option("auto-repeat")
        self.auto_repeat_delay = Push.AUTO_REPEAT_DELAY
        self.auto_repeat_speed = Push.AUTO_REPEAT_SPEED
        self.exit = None
        self.set_auto_repeat()

        self.onoff_current_value = None
        self.initial_value = button._config.get("initial-value")
        if self.initial_value is not None:
            if type(self.initial_value) is bool:
                self.onoff_current_value = self.initial_value
            else:
                self.onoff_current_value = self.initial_value != 0

    def __str__(self):  # print its status
        return str(super()) + "\n" + ", ".join([f"command: {self._command}", f"is_valid: {self.is_valid()}"])

    def set_auto_repeat(self):
        if not self.auto_repeat:
            return

        value = self.button.option_value("auto-repeat")
        if type(value) is bool:  # options: auto-repeat; uses default
            return
        elif "/" in str(value):  # options: auto-repeat=1/0.2; set both
            arr = value.split("/")
            if len(arr) > 1:
                self.auto_repeat_delay = float(arr[0])
                if self.auto_repeat_delay <= 0:
                    self.auto_repeat_delay = Push.AUTO_REPEAT_DELAY
                self.auto_repeat_speed = float(arr[1])
                if self.auto_repeat_speed <= 0:
                    self.auto_repeat_speed = Push.AUTO_REPEAT_SPEED
            elif len(arr) > 0:
                self.auto_repeat_speed = float(arr[0])
                if self.auto_repeat_speed <= 0:
                    self.auto_repeat_speed = Push.AUTO_REPEAT_SPEED
        else:  # options: auto-repeat=1; set speed only, default delay
            self.auto_repeat_speed = float(value)
            if self.auto_repeat_speed <= 0:
                self.auto_repeat_speed = Push.AUTO_REPEAT_SPEED
        logger.debug(f"{self.auto_repeat_delay}, {self.auto_repeat_speed}")

    def is_on(self):
        value = self.button.value
        if value is not None:
            if type(value) in [dict, tuple]:  # gets its value from internal state
                self.onoff_current_value = not self.onoff_current_value if self.onoff_current_value is not None else False
            elif type(value) is bool:  # expect bool or number... (no check for number)
                self.onoff_current_value = value
            else:
                self.onoff_current_value = self.initial_value != 0  # @todo: fails if not number...
            logger.debug(f"button {self.button_name} is {self.onoff_current_value}")
        else:
            self.onoff_current_value = self.activation_count % 2 == 1
            logger.debug(f"button {self.button_name} is {self.onoff_current_value} from internal state")

        return self.onoff_current_value

    def is_off(self):
        return not self.is_on()

    def is_valid(self):
        if self._command is None:
            logger.warning(f"button {self.button_name}: {type(self).__name__} has no command")
            return False
        return super().is_valid()

    def activate(self, event) -> bool:
        if not self.can_handle(event):
            return False
        if not super().activate(event):
            return False
        if event.pressed:
            if not (self.has_long_press() or self.has_beginend_command()):  # we don't have to wait for the release to trigger the command
                self._command.execute()
            if self.auto_repeat and self.exit is None:
                self.auto_repeat_start()
        else:
            if self.button.is_guarded():
                return False

            if (self.has_long_press() and not self.long_pressed()) and not self.has_beginend_command():
                self._command.execute()
            if self.auto_repeat:
                self.auto_repeat_stop()
        return True  # normal termination

    # Auto repeat
    def auto_repeat_loop(self):
        self.exit.wait(self.auto_repeat_delay)
        while not self.exit.is_set():
            self._command.execute()
            self.exit.wait(self.auto_repeat_speed)
        logger.debug("exited")

    def auto_repeat_start(self):
        """
        Starts auto_repeat
        """
        if self.exit is None:
            self.exit = threading.Event()
            self.thread = threading.Thread(target=self.auto_repeat_loop, name=f"Activation::auto_repeat({self.button_name})")
            self.thread.start()
        else:
            logger.warning(f"button {self.button_name}: already started")

    def auto_repeat_stop(self):
        """
        Stops auto_repeat
        """
        if self.exit is not None:
            self.exit.set()
            self.thread.join(timeout=2 * self.auto_repeat_speed)
            if self.thread.is_alive():
                logger.warning("..thread may hang..")
            else:
                self.exit = None
        else:
            logger.debug(f"button {self.button_name}: already stopped")

    def describe(self) -> str:
        """
        Describe what the button does in plain English
        """
        return "\n\r".join(
            [
                f"The button executes {self._command} when it is activated (pressed).",
                "The button does nothing when it is de-activated (released).",
            ]
        )


class BeginEndPress(Push):
    """
    Execute beginCommand while the key is pressed and endCommand when the key is released.
    """

    ACTIVATION_NAME = "begin-end-command"
    EDITOR_FAMILY = "Push Button"
    EDITOR_LABEL = "Begin / End Command"
    REQUIRED_DECK_ACTIONS = [DECK_ACTIONS.PRESS, DECK_ACTIONS.LONGPRESS, DECK_ACTIONS.PUSH]

    PARAMETERS = {"commands": {"type": "sub", "list": {
        "press": {"type": "string", "label": "Command (begin/end)", "mandatory": True},
    }}}

    def __init__(self, button: "Button"):
        Push.__init__(self, button=button)

        # Command — begin/end wraps commands.press
        if self._command is not None:
            del self._command
        self._command = None
        cmd = (button._config.get("commands", {}) or {}).get("press")
        if cmd is not None:
            cmdname = ":".join([self.button.get_id(), type(self).__name__])
            self._command = self.sim.instruction_factory(name=cmdname, instruction_block={CONFIG_KW.BEGIN_END.value: cmd})

    def is_valid(self):
        # if type(self._command).__name__ != "BeginEndCommand":
        #     logger.warning(f"{self.button.get_id()}: {type(self)}: command is not BeginEndCommand: {type(self._command)}")
        #     return False
        return super().is_valid()

    def activate(self, event) -> bool:
        if not self.can_handle(event):
            return False
        if not super().activate(event):
            return False
        if event.pressed:
            self._command.execute()
            self.skip_view = True
        else:
            self._command.execute()
        return True  # normal termination

    def inspect(self, what: str | None = None):
        if what is not None and "activation" in what:
            super().inspect(what=what)

    def describe(self) -> str:
        """
        Describe what the button does in plain English
        """
        return "\n\r".join(
            [
                f"The button begins command {self._command} when it is activated (pressed).",
                f"The button ends command {self._command} when it is de-activated (released).",
                f"(Begin and end command is a special terminology (phase of execution of a command) of X-Plane.)",
            ]
        )


class Sweep(Activation):
    EDITOR_FAMILY = "Push Button"
    EDITOR_LABEL = "Sweep"
    """
    N-stop activation: each press advances to the next stop and fires the command at that stop.
    With 2 stops (default) this is equivalent to a simple toggle.
    Behaviour is 'bounce' (0→1→2→1→0) by default, or 'cycle' (0→1→2→0→1→2).
    commands list is positional: commands[i] fires when arriving at stop i.
    On touch surfaces, a tap advances and a swipe moves directionally (up/right = forward,
    down/left = backward). Use swipe-invert: true to reverse the swipe direction.
    """

    ACTIVATION_NAME = "sweep"
    REQUIRED_DECK_ACTIONS = [DECK_ACTIONS.PRESS, DECK_ACTIONS.LONGPRESS, DECK_ACTIONS.PUSH, DECK_ACTIONS.SWIPE, DECK_ACTIONS.ENCODER]

    SWIPE_MIN_DISTANCE = 10  # pixels below which a touch is treated as a tap

    PARAMETERS = PARAM_INITIAL_VALUE | {
        "positions": {"type": "list", "list": "string", "label": "Position Commands", "hint": "Ordered list of command strings for each switch position"},
        "stops": {"type": "integer", "label": "Number of stops (when no positions)", "default-value": 2},
        "behaviour": {"type": "lov", "label": "Sweep Behaviour", "lov": ["bounce", "cycle"], "default-value": "bounce"},
        "swipe-invert": {"type": "boolean", "label": "Invert Swipe", "hint": "Reverse swipe direction (down/left becomes forward)", "default-value": False},
        "scroll-invert": {"type": "boolean", "label": "Invert Scroll", "hint": "Reverse scroll wheel direction (scroll down becomes forward)", "default-value": False},
        "swipe-minimum-distance": {"type": "float", "label": "Swipe Min Distance (px)", "hint": "Minimum pixel distance to treat a touch as a swipe rather than a tap", "default-value": SWIPE_MIN_DISTANCE},
    }

    def __init__(self, button: "Button"):
        Activation.__init__(self, button=button)

        cmdname = ":".join([self.button.get_id(), type(self).__name__])
        # positions: list of command strings
        positions = button._config.get("positions") or []
        self._sweep_commands = [
            self.sim.instruction_factory(name=cmdname, instruction_block={CONFIG_KW.COMMAND.value: pos})
            for pos in positions
        ]
        self.sweep_behaviour = button._config.get("behaviour", "bounce")
        self.swipe_invert = bool(button._config.get("swipe-invert", False))
        self.scroll_invert = bool(button._config.get("scroll-invert", False))
        self.swipe_minimum_distance = float(button._config.get("swipe-minimum-distance", Sweep.SWIPE_MIN_DISTANCE))

        # Internal state
        self.stop_current = 0
        self.go_forward = True
        self._init_deferred()

    def _init_deferred(self):
        if self._inited:
            return
        if self.initial_value is not None:
            if is_integer(self.initial_value):
                value = abs(int(self.initial_value))
                n = self.num_stops
                if value > n - 1:
                    logger.warning(f"button {self.button_name} initial value {value} too large. Set to {n - 1}.")
                    value = n - 1
                if self.initial_value < 0:
                    self.go_forward = False
                self.stop_current = value
            logger.debug(f"button {self.button_name} initialized stop at {self.stop_current} from initial-value")
        if self.stop_current == 0:
            self.go_forward = True
        elif self.stop_current == self.num_stops - 1:
            self.go_forward = False
        self._inited = True

    @property
    def num_stops(self):
        if self._sweep_commands:
            return len(self._sweep_commands)
        # Derive from ticks list in circular-switch representation
        cs = self.button._config.get("circular-switch")
        if isinstance(cs, dict):
            ticks = cs.get("ticks", [])
            if isinstance(ticks, list) and ticks:
                return len(ticks)
        return int(self.button._config.get("stops", 2))

    def num_commands(self) -> int:
        return len(self._sweep_commands)

    def is_on(self):
        return self.stop_current > 0

    def is_off(self):
        return self.stop_current == 0

    def _advance(self):
        """Advance to the next stop and return the new stop index."""
        n = self.num_stops
        if self.sweep_behaviour == "cycle":
            self.stop_current = (self.stop_current + 1) % n
        else:  # bounce
            if self.go_forward:
                self.stop_current = min(self.stop_current + 1, n - 1)
                if self.stop_current >= n - 1:
                    self.go_forward = False
            else:
                self.stop_current = max(self.stop_current - 1, 0)
                if self.stop_current <= 0:
                    self.go_forward = True
        return self.stop_current

    def _step(self, forward: bool) -> int:
        """Move exactly one stop in the given direction regardless of bounce state."""
        n = self.num_stops
        if self.sweep_behaviour == "cycle":
            self.stop_current = (self.stop_current + 1) % n if forward else (self.stop_current - 1) % n
        else:
            self.stop_current = min(self.stop_current + 1, n - 1) if forward else max(self.stop_current - 1, 0)
        # Keep go_forward consistent so a subsequent push bounce continues naturally
        if self.stop_current >= n - 1:
            self.go_forward = False
        elif self.stop_current <= 0:
            self.go_forward = True
        return self.stop_current

    def _swipe_direction(self, dx: float, dy: float) -> bool:
        """Return True (forward) for up/right swipes, False (backward) for down/left.
        Primary axis is whichever delta is larger. Respects swipe-invert setting."""
        if abs(dy) >= abs(dx):
            forward = dy < 0  # swipe up = forward
        else:
            forward = dx > 0  # swipe right = forward
        return (not forward) if self.swipe_invert else forward

    def __str__(self):
        return (
            super().__str__()
            + "\n"
            + ", ".join(
                [
                    f"stops: {self.num_stops}",
                    f"current: {self.stop_current}",
                    f"behaviour: {self.sweep_behaviour}",
                    f"is_valid: {self.is_valid()}",
                ]
            )
        )

    def is_valid(self):
        if 0 < self.num_commands() < 2:
            logger.error(f"button {self.button_name}: {type(self).__name__} must have at least 2 commands or none")
            return False
        if not self._sweep_commands and self._set_sim_data is None:
            logger.error(f"button {self.button_name}: {type(self).__name__} must have commands or a dataref to write to")
            return False
        return super().is_valid()

    def activate(self, event) -> bool:
        if not self.can_handle(event):
            return False
        if not super().activate(event):
            return False

        next_stop = None
        if isinstance(event, EncoderEvent):
            forward = event.clockwise if not self.scroll_invert else not event.clockwise
            next_stop = self._step(forward)
            logger.debug(f"button {self.button_name}: scroll {'forward' if forward else 'backward'} → stop {next_stop}")
        elif isinstance(event, TouchEvent):
            # Only act on the touch-end event (start is not None)
            if event.start is None:
                return True
            swipe = event.swipe(autorun=False)
            if swipe is None or swipe.swipe_distance < self.swipe_minimum_distance:
                next_stop = self._advance()  # tap = advance (toggle behaviour preserved)
            else:
                forward = self._swipe_direction(
                    swipe.end_pos_x - swipe.start_pos_x,
                    swipe.end_pos_y - swipe.start_pos_y,
                )
                next_stop = self._step(forward)
                logger.debug(f"button {self.button_name}: swipe {'forward' if forward else 'backward'} → stop {next_stop}")
        elif isinstance(event, SwipeEvent):
            forward = self._swipe_direction(
                event.end_pos_x - event.start_pos_x,
                event.end_pos_y - event.start_pos_y,
            )
            next_stop = self._step(forward)
            logger.debug(f"button {self.button_name}: swipe {'forward' if forward else 'backward'} → stop {next_stop}")
        elif event.pressed:
            next_stop = self._advance()

        if next_stop is not None and self._sweep_commands and next_stop < len(self._sweep_commands):
            self._sweep_commands[next_stop].execute()
        return True

    def get_activation_value(self):
        return self.stop_current

    def get_state_variables(self) -> dict:
        s = super().get_state_variables() or {}
        return s | {
            "stop": self.stop_current,
            "go_forward": self.go_forward,
            "num_stops": self.num_stops,
            COCKPITDECKS_INTVAR.ACTIVATION_ON.value: self.is_on(),
        }

    def describe(self) -> str:
        a = [f"Sweep activation with {self.num_stops} stops ({self.sweep_behaviour} behaviour)."]
        for i, cmd in enumerate(self._sweep_commands):
            a.append(f"  Stop {i}: fires {cmd}")
        a.append("The button does nothing when it is de-activated (released).")
        if self._set_sim_data is not None:
            a.append(f"The button writes its value in dataref {self._set_sim_data.name}.")
        a.append(f"Current stop: {self.stop_current}.")
        return "\n\r".join(a)


class ShortOrLongpress(Activation):
    EDITOR_FAMILY = "Push Button"
    EDITOR_LABEL = "Short / Long Press"
    """
    Execute beginCommand while the key is pressed and endCommand when the key is released.
    """

    ACTIVATION_NAME = "short-or-long-press"
    REQUIRED_DECK_ACTIONS = [DECK_ACTIONS.PRESS, DECK_ACTIONS.LONGPRESS, DECK_ACTIONS.PUSH]

    PARAMETERS = {
        "commands": {"type": "sub", "list": {
            "press": {"type": "string", "label": "Short Press Command", "mandatory": True},
            "long-press": {"type": "string", "label": "Long Press Command", "mandatory": True},
        }},
        "long-time": {"type": "float", "label": "Long Press Duration (seconds)", "default-value": 2},
    }

    def __init__(self, button: "Button"):
        Activation.__init__(self, button=button)

        # Activation arguments
        cmdname = ":".join([self.button.get_id(), type(self).__name__])
        self._command_short = None
        self._command_long = None
        commands = button._config.get("commands", {}) or {}
        cmd_short = commands.get("press")
        cmd_long = commands.get("long-press")
        if cmd_short is not None:
            self._command_short = self.sim.instruction_factory(name=cmdname + ":short", instruction_block={CONFIG_KW.COMMAND.value: cmd_short})
        if cmd_long is not None:
            self._command_long = self.sim.instruction_factory(name=cmdname + ":long", instruction_block={CONFIG_KW.COMMAND.value: cmd_long})

        # Internal variables
        self.long_time = self._config.get("long-time", 2)

    def activate(self, event) -> bool:
        if not self.can_handle(event):
            return False
        if not super().activate(event):
            return False
        if not event.pressed:
            if self.num_commands() > 1:
                if self.duration < self.long_time:
                    self._command_short.execute()
                    logger.debug(f"short {self.duration}, {self.long_time}")
                else:
                    self._command_long.execute()
                    logger.debug(f"looooong {self.duration}, {self.long_time}")
        return True  # normal termination

    def num_commands(self):
        return int(self._command_short is not None) + int(self._command_long is not None)

    def is_valid(self):
        if self.num_commands() < 2:
            logger.error(f"button {self.button_name}: {type(self).__name__} must have command-short and command-long")
            return False
        return super().is_valid()

    def inspect(self, what: str | None = None):
        if what is not None and "activation" in what:
            super().inspect(what=what)

    def describe(self) -> str:
        """
        Describe what the button does in plain English
        """
        return "\n\r".join(
            [
                f"The button executes {self._command_short} when it is activated shortly (pressed).",
                f"The button executes {self._command_long} when it is de-activated after a long press (released after more than {self.long_time}secs.).",
                "(Begin and end command is a special terminology (phase of execution of a command) of X-Plane.)",
            ]
        )


# UpDown has been merged into Sweep (type: sweep with N commands in positional list)


class PushValue(Activation):
    """
    Push button that maintains a numeric value and writes it to a dataref on each press.
    Each press advances the value by `step`; when it would exceed `value-max` it wraps back
    to `value-min`. Requires `set-dataref`.

    Default parameters (step=1, value-min=0, value-max=1) give a simple 0/1 toggle.
    """

    ACTIVATION_NAME = "push-value"
    EDITOR_FAMILY = "Push Button"
    EDITOR_LABEL = "Push Value"
    REQUIRED_DECK_ACTIONS = [DECK_ACTIONS.PRESS, DECK_ACTIONS.LONGPRESS, DECK_ACTIONS.PUSH]

    PARAMETERS = PARAM_INITIAL_VALUE | PARAM_SETVALUE_BLOCK | {
        "step": {"type": "float", "label": "Step", "default-value": 1},
        "value-min": {"type": "float", "label": "Minimum Value", "default-value": 0},
        "value-max": {"type": "float", "label": "Maximum Value", "default-value": 1},
    }

    def __init__(self, button: "Button"):
        Activation.__init__(self, button=button)
        self.step = float(button._config.get("step", 1))
        self.value_min = float(button._config.get("value-min", 0))
        self.value_max = float(button._config.get("value-max", 1))
        self.current_value = float(self.initial_value) if self.initial_value is not None else self.value_min
        self._inited = True

    def is_valid(self):
        if self._set_sim_data is None:
            logger.error(f"button {self.button_name}: {type(self).__name__} has no set-dataref")
            return False
        return super().is_valid()

    def activate(self, event) -> bool:
        if not self.can_handle(event):
            return False
        if not super().activate(event):
            return False
        if event.pressed:
            x = self.current_value + self.step
            if x > self.value_max:
                x = self.value_min
            self.current_value = x
        return True

    def get_activation_value(self):
        return self.current_value

    def get_state_variables(self) -> dict:
        return {
            "step": self.step,
            "value_min": self.value_min,
            "value_max": self.value_max,
            "value": self.current_value,
        } | Activation.get_state_variables(self)

    def describe(self) -> str:
        a = [f"Each press advances the value by {self.step} in [{self.value_min}–{self.value_max}], wrapping around."]
        if self._set_sim_data is not None:
            a.append(f"The value is written to dataref {self._set_sim_data.name}.")
        return "\n\r".join(a)


#
# ###############################
# ENCODER TYPE ACTIVATION
#
#
""" Note: By vocabulary convention:
An Encoder has a stepped movement, and an action is triggered after each step.
A Know has a continuous value from a minimum value to a maximum value, very much like a slider.
An Encoder with a step value of 1 is more or less a variant of Knob.
"""


class EncoderProperties:
    """Trait for property definitions"""

    def __init__(self, button: "Button"):
        # Encoder commands (and more if available)
        self._commands = []
        cmds = button._config.get(CONFIG_KW.COMMANDS.value)
        if cmds is not None:
            cmdname = ":".join([self.button.get_id(), type(self).__name__])
            self._commands = [self.sim.instruction_factory(name=cmdname, instruction_block={CONFIG_KW.COMMAND.value: cmd}) for cmd in cmds]

    @property
    def _turns(self):
        path = ID_SEP.join([self.get_id(), COCKPITDECKS_INTVAR.ENCODER_TURNS.value])
        dref = self.button.sim.get_internal_variable(path)
        value = dref.value
        return 0 if value is None else value

    @property
    def _cw(self):
        path = ID_SEP.join([self.get_id(), COCKPITDECKS_INTVAR.ENCODER_CLOCKWISE.value])
        dref = self.button.sim.get_internal_variable(path)
        value = dref.value
        return 0 if value is None else value

    @property
    def _ccw(self):
        path = ID_SEP.join([self.get_id(), COCKPITDECKS_INTVAR.ENCODER_COUNTER_CLOCKWISE.value])
        dref = self.button.sim.get_internal_variable(path)
        value = dref.value
        return 0 if value is None else value


class Encoder(Activation, EncoderProperties):
    EDITOR_FAMILY = "Encoder"
    EDITOR_LABEL = "Encoder"
    """
    Encoder with stepped value.
    command-ccw fires when turned counter-clockwise, command-cw when turned clockwise.
    """

    ACTIVATION_NAME = "encoder"
    REQUIRED_DECK_ACTIONS = DECK_ACTIONS.ENCODER

    PARAMETERS = PARAM_INITIAL_VALUE | {
        "commands": {"type": "sub", "list": {
            "cw": {"type": "string", "label": "Clockwise Command"},
            "ccw": {"type": "string", "label": "Counter-clockwise Command"},
        }},
    }

    def __init__(self, button: "Button"):
        Activation.__init__(self, button=button)
        EncoderProperties.__init__(self, button=button)

        cmdname = ":".join([self.button.get_id(), type(self).__name__])
        commands = button._config.get("commands", {}) or {}
        cmd_ccw = commands.get("ccw")
        cmd_cw = commands.get("cw")
        self._command_ccw = (
            self.sim.instruction_factory(name=cmdname + ":ccw", instruction_block={CONFIG_KW.COMMAND.value: cmd_ccw})
            if cmd_ccw is not None
            else None
        )
        self._command_cw = (
            self.sim.instruction_factory(name=cmdname + ":cw", instruction_block={CONFIG_KW.COMMAND.value: cmd_cw})
            if cmd_cw is not None
            else None
        )

    def num_commands(self):
        return int(self._command_ccw is not None) + int(self._command_cw is not None)

    def is_valid(self):
        if self.num_commands() > 0 and self.num_commands() < 2:
            logger.error(f"button {self.button_name}: {type(self).__name__} must have both command-cw and command-ccw")
            return False
        return super().is_valid()

    def activate(self, event) -> bool:
        if not self.can_handle(event):
            return False
        if not super().activate(event):
            return False
        if event.turned_counter_clockwise:
            if self._command_ccw is not None:
                self._command_ccw.execute()
            self.inc(COCKPITDECKS_INTVAR.ENCODER_TURNS.value, -1)
            self.inc(COCKPITDECKS_INTVAR.ENCODER_COUNTER_CLOCKWISE.value)
        elif event.turned_clockwise:
            if self._command_cw is not None:
                self._command_cw.execute()
            self.inc(COCKPITDECKS_INTVAR.ENCODER_TURNS.value, 1)
            self.inc(COCKPITDECKS_INTVAR.ENCODER_CLOCKWISE.value)
        else:
            logger.warning(f"button {self.button_name}: {type(self).__name__} invalid event {event.turned_clockwise, event.turned_counter_clockwise}")
        return True

    def get_activation_value(self):
        return self._turns

    def get_state_variables(self) -> dict:
        a = {
            COCKPITDECKS_INTVAR.ENCODER_CLOCKWISE.value: self._cw,
            COCKPITDECKS_INTVAR.ENCODER_COUNTER_CLOCKWISE.value: self._ccw,
            COCKPITDECKS_INTVAR.ENCODER_TURNS.value: self._turns,
        }
        return a | super().get_state_variables()

    def describe(self) -> str:
        return "\n\r".join(
            [
                f"This encoder executes command {self._command_ccw} when turned counter-clockwise.",
                f"This encoder executes command {self._command_cw} when turned clockwise.",
            ]
        )


class EncoderPush(Push, EncoderProperties):
    EDITOR_FAMILY = "Encoder"
    EDITOR_LABEL = "Encoder Push"
    """
    Encoder coupled to a push button. Named command keys:
      command     — fires when pushed
      command-ccw — fires when turned counter-clockwise (or when not pressed, if longpush)
      command-cw  — fires when turned clockwise (or when not pressed, if longpush)
    With longpush option, also:
      command-push-ccw — fires when held and turned counter-clockwise
      command-push-cw  — fires when held and turned clockwise
    """

    ACTIVATION_NAME = "encoder-push"
    REQUIRED_DECK_ACTIONS = [DECK_ACTIONS.ENCODER, DECK_ACTIONS.PRESS, DECK_ACTIONS.LONGPRESS, DECK_ACTIONS.PUSH]

    PARAMETERS = PARAM_INITIAL_VALUE | {
        "commands": {"type": "sub", "list": {
            "press": {"type": "string", "label": "Push Command"},
            "cw": {"type": "string", "label": "Clockwise Command"},
            "ccw": {"type": "string", "label": "Counter-clockwise Command"},
            "push-cw": {"type": "string", "label": "Push + Clockwise Command"},
            "push-ccw": {"type": "string", "label": "Push + Counter-clockwise Command"},
        }},
    }

    def __init__(self, button: "Button"):
        Push.__init__(self, button=button)
        EncoderProperties.__init__(self, button=button)

        self.longpush = self.button.has_option("longpush")

        cmdname = ":".join([self.button.get_id(), type(self).__name__])
        commands = button._config.get("commands", {}) or {}

        def _mk(key, suffix):
            val = commands.get(key)
            if val is None:
                return None
            return self.sim.instruction_factory(name=cmdname + suffix, instruction_block={CONFIG_KW.COMMAND.value: val})

        self._command_ccw = _mk("ccw", ":ccw")
        self._command_cw = _mk("cw", ":cw")
        self._command_push_ccw = _mk("push-ccw", ":push-ccw")
        self._command_push_cw = _mk("push-cw", ":push-cw")

        # Push command is loaded by Push.__init__ via button._config.get(CONFIG_KW.COMMAND.value)
        # but we expose it through the same mechanism; just ensure _command is set.

    def num_commands(self):
        n = sum(1 for c in [self._command, self._command_ccw, self._command_cw, self._command_push_ccw, self._command_push_cw] if c is not None)
        return n

    def is_valid(self):
        if self.longpush and (self._command_push_ccw is None or self._command_push_cw is None):
            logger.warning(f"button {self.button_name}: {type(self).__name__} longpush mode requires command-push-ccw and command-push-cw")
            return False
        return True

    def activate(self, event) -> bool:
        if not self.can_handle(event):
            return False

        if type(event) is PushEvent:
            return super().activate(event)

        self.inc(COCKPITDECKS_INTVAR.ACTIVATION_COUNT.value)  # since super() not called

        if type(event) is EncoderEvent:
            if event.turned_counter_clockwise:
                if self.longpush and self.is_pressed():
                    if self._command_push_ccw is not None:
                        self._command_push_ccw.execute()
                    self.inc(COCKPITDECKS_INTVAR.ACTIVATION_LONGPUSH.value)
                else:
                    if self._command_ccw is not None:
                        self._command_ccw.execute()
                    self.inc(COCKPITDECKS_INTVAR.ACTIVATION_SHORTPUSH.value)
                self.inc(COCKPITDECKS_INTVAR.ENCODER_TURNS.value, -1)
                self.inc(COCKPITDECKS_INTVAR.ENCODER_COUNTER_CLOCKWISE.value)
            elif event.turned_clockwise:
                if self.longpush and self.is_pressed():
                    if self._command_push_cw is not None:
                        self._command_push_cw.execute()
                    self.inc(COCKPITDECKS_INTVAR.ACTIVATION_LONGPUSH.value)
                else:
                    if self._command_cw is not None:
                        self._command_cw.execute()
                    self.inc(COCKPITDECKS_INTVAR.ACTIVATION_SHORTPUSH.value)
                self.inc(COCKPITDECKS_INTVAR.ENCODER_TURNS.value)
                self.inc(COCKPITDECKS_INTVAR.ENCODER_CLOCKWISE.value)
            return True

        logger.warning(f"button {self.button_name}: {type(self).__name__} invalid event {event}")
        return True

    def get_activation_value(self):
        return self._turns

    def get_state_variables(self) -> dict:
        a = {
            COCKPITDECKS_INTVAR.ENCODER_CLOCKWISE.value: self._cw,
            COCKPITDECKS_INTVAR.ENCODER_COUNTER_CLOCKWISE.value: self._ccw,
            COCKPITDECKS_INTVAR.ENCODER_TURNS.value: self._turns,
        }
        return a | super().get_state_variables()

    def describe(self) -> str:
        if self.longpush:
            return "\n\r".join(
                [
                    "This encoder has longpush option.",
                    f"Executes command {self._command} when pushed.",
                    f"Executes command {self._command_ccw} when turned counter-clockwise (not held).",
                    f"Executes command {self._command_cw} when turned clockwise (not held).",
                    f"Executes command {self._command_push_ccw} when held and turned counter-clockwise.",
                    f"Executes command {self._command_push_cw} when held and turned clockwise.",
                ]
            )
        else:
            return "\n\r".join(
                [
                    "This encoder does not have longpush option.",
                    f"Executes command {self._command} when pushed.",
                    f"Executes command {self._command_ccw} when turned counter-clockwise.",
                    f"Executes command {self._command_cw} when turned clockwise.",
                ]
            )


class EncoderToggle(Activation, EncoderProperties):
    EDITOR_FAMILY = "Encoder"
    EDITOR_LABEL = "Encoder Toggle"
    """
    Encoder with a toggle state (on/off). Push alternates state and fires
    commands[0] (off→on) or commands[1] (on→off). Rotation fires
    commands[2] (CW) and commands[3] (CCW). With 'dual' option, rotation
    commands differ per state: commands[2/3] when ON, commands[4/5] when OFF.
    """

    ACTIVATION_NAME = "encoder-toggle"
    REQUIRED_DECK_ACTIONS = [DECK_ACTIONS.ENCODER, DECK_ACTIONS.PRESS, DECK_ACTIONS.LONGPRESS, DECK_ACTIONS.PUSH]

    PARAMETERS = PARAM_INITIAL_VALUE | {
        "commands": {"type": "sub", "list": {
            "toggle-on": {"type": "string", "label": "Command when toggling ON (press while OFF)"},
            "toggle-off": {"type": "string", "label": "Command when toggling OFF (press while ON)"},
            "cw": {"type": "string", "label": "Clockwise Command"},
            "ccw": {"type": "string", "label": "Counter-clockwise Command"},
            "cw-off": {"type": "string", "label": "Clockwise Command when OFF (dual mode)"},
            "ccw-off": {"type": "string", "label": "Counter-clockwise Command when OFF (dual mode)"},
        }},
    }

    def __init__(self, button: "Button"):
        Activation.__init__(self, button=button)
        EncoderProperties.__init__(self, button=button)

        # Toggle state: False = off (stop 0), True = on (stop 1)
        self._toggle_on = False
        # Activation options
        self.dual = self.button.has_option("dual")

        # Build named command references from commands dict
        cmdname = ":".join([self.button.get_id(), type(self).__name__])
        commands = button._config.get("commands", {}) or {}

        def _mk(key, suffix):
            val = commands.get(key)
            if val is None:
                return None
            return self.sim.instruction_factory(name=cmdname + suffix, instruction_block={CONFIG_KW.COMMAND.value: val})

        self._cmd_toggle_on  = _mk("toggle-on",  ":toggle-on")
        self._cmd_toggle_off = _mk("toggle-off", ":toggle-off")
        self._cmd_cw         = _mk("cw",         ":cw")
        self._cmd_ccw        = _mk("ccw",        ":ccw")
        self._cmd_cw_off     = _mk("cw-off",     ":cw-off")
        self._cmd_ccw_off    = _mk("ccw-off",    ":ccw-off")

        # Keep self._commands list for num_commands() compatibility (EncoderProperties uses it)
        self._commands = [c for c in [self._cmd_toggle_on, self._cmd_toggle_off,
                                      self._cmd_cw, self._cmd_ccw,
                                      self._cmd_cw_off, self._cmd_ccw_off] if c is not None]

    def num_commands(self):
        return len(self._commands) if self._commands is not None else 0

    def is_on(self):
        return self._toggle_on

    def is_off(self):
        return not self._toggle_on

    def is_valid(self):
        if self.dual and (self._cmd_cw_off is None or self._cmd_ccw_off is None):
            logger.warning(f"button {self.button_name}: {type(self).__name__} dual mode requires commands.cw-off and commands.ccw-off")
            return False
        return True

    def activate(self, event) -> bool:
        if not self.can_handle(event):
            return False

        if type(event) is PushEvent:
            if not Activation.activate(self, event):
                return False
            if event.pressed:
                if self.is_off() and self._cmd_toggle_on is not None:
                    self._cmd_toggle_on.execute()
                    self.inc(COCKPITDECKS_INTVAR.ACTIVATION_OFF.value)
                elif self.is_on() and self._cmd_toggle_off is not None:
                    self._cmd_toggle_off.execute()
                    self.inc(COCKPITDECKS_INTVAR.ACTIVATION_ON.value)
                self._toggle_on = not self._toggle_on
            return True

        self.inc(COCKPITDECKS_INTVAR.ACTIVATION_COUNT.value)  # since super() not called

        if type(event) is EncoderEvent:
            if event.turned_clockwise:
                cmd = (self._cmd_cw_off if (self.dual and self.is_off()) else self._cmd_cw)
                if cmd is not None:
                    cmd.execute()
                self.inc(COCKPITDECKS_INTVAR.ENCODER_TURNS.value)
                self.inc(COCKPITDECKS_INTVAR.ENCODER_CLOCKWISE.value)
            elif event.turned_counter_clockwise:
                cmd = (self._cmd_ccw_off if (self.dual and self.is_off()) else self._cmd_ccw)
                if cmd is not None:
                    cmd.execute()
                self.inc(COCKPITDECKS_INTVAR.ENCODER_TURNS.value, -1)
                self.inc(COCKPITDECKS_INTVAR.ENCODER_COUNTER_CLOCKWISE.value)
            return True

        logger.warning(f"button {self.button_name}: {type(self).__name__} invalid event {event}")
        return True

    def get_activation_value(self):
        return self._turns

    def get_state_variables(self) -> dict:
        a = {
            COCKPITDECKS_INTVAR.ENCODER_CLOCKWISE.value: self._cw,
            COCKPITDECKS_INTVAR.ENCODER_COUNTER_CLOCKWISE.value: self._ccw,
            COCKPITDECKS_INTVAR.ENCODER_TURNS.value: self._turns,
            COCKPITDECKS_INTVAR.ACTIVATION_ON.value: self.is_on(),
        }
        return a | Activation.get_state_variables(self)

    def describe(self) -> str:
        if self.dual:
            return "\n\r".join(
                [
                    "This encoder has dual option.",
                    f"Executes command {self._commands[0]} when pressed and OFF.",
                    f"Executes command {self._commands[1]} when pressed and ON.",
                    f"Executes command {self._commands[2]} when ON and turned clockwise.",
                    f"Executes command {self._commands[3]} when ON and turned counter-clockwise.",
                    f"Executes command {self._commands[4]} when OFF and turned clockwise.",
                    f"Executes command {self._commands[5]} when OFF and turned counter-clockwise.",
                ]
            )
        else:
            return "\n\r".join(
                [
                    "This encoder does not have dual option.",
                    f"Executes command {self._commands[0]} when pressed and OFF.",
                    f"Executes command {self._commands[1]} when pressed and ON.",
                    f"Executes command {self._commands[2]} when turned clockwise.",
                    f"Executes command {self._commands[3]} when turned counter-clockwise.",
                ]
            )


class EncoderValue(Activation, EncoderProperties):
    EDITOR_FAMILY = "Encoder"
    EDITOR_LABEL = "Encoder Value"
    """
    Activation that maintains an internal value and optionally write that value to a dataref
    """

    ACTIVATION_NAME = "encoder-value"
    REQUIRED_DECK_ACTIONS = [DECK_ACTIONS.ENCODER, DECK_ACTIONS.PRESS, DECK_ACTIONS.LONGPRESS, DECK_ACTIONS.PUSH]

    PARAMETERS = PARAM_INITIAL_VALUE | {
        "commands": {"type": "sub", "list": {
            "toggle-on": {"type": "string", "label": "Command when toggling ON (press while OFF)"},
            "toggle-off": {"type": "string", "label": "Command when toggling OFF (press while ON)"},
        }},
        "step": {"type": "float", "label": "Step", "default-value": 1},
        "step-xl": {"type": "float", "label": "Large Step", "default-value": 10},
        "value-min": {"type": "float", "label": "Minimum Value", "default-value": 0},
        "value-max": {"type": "float", "label": "Maximum Value", "default-value": 100},
    }

    def __init__(self, button: "Button"):
        Activation.__init__(self, button=button)
        EncoderProperties.__init__(self, button=button)

        # Activation arguments
        self.step = float(button._config.get("step", 1))
        self.stepxl = float(button._config.get("step-xl", 10))
        self.value_min = float(button._config.get("value-min", 0))
        self.value_max = float(button._config.get("value-max", 100))

        cmdname = ":".join([self.button.get_id(), type(self).__name__])
        commands = button._config.get("commands", {}) or {}

        def _mk(key, suffix):
            val = commands.get(key)
            if val is None:
                return None
            return self.sim.instruction_factory(name=cmdname + suffix, instruction_block={CONFIG_KW.COMMAND.value: val})

        self._cmd_toggle_on  = _mk("toggle-on",  ":toggle-on")
        self._cmd_toggle_off = _mk("toggle-off", ":toggle-off")
        # Keep self._commands list for num_commands() compatibility
        self._commands = [c for c in [self._cmd_toggle_on, self._cmd_toggle_off] if c is not None]

        # Internal variables
        self.encoder_current_value = 0
        self._toggle_on = False  # local toggle state for push

        self.init_differed()

    def init_differed(self):
        if self._inited:
            return
        value = self.button.value
        if value is not None:
            self.encoder_current_value = value
            logger.debug(f"button {self.button_name} initialized encoder value at {self.encoder_current_value}")
        elif self.initial_value is not None:
            self.encoder_current_value = self.initial_value
            logger.debug(f"button {self.button_name} initialized encoder value at {self.encoder_current_value} from initial-value")
        if self.encoder_current_value is not None:
            self._inited = True

    def is_valid(self):
        if self._set_sim_data is None:
            logger.error(f"button {self.button_name}: {type(self).__name__} must have a dataref to write to")
            return False
        return super().is_valid()

    def is_on(self):
        return self._toggle_on

    def is_off(self):
        return not self._toggle_on

    def activate(self, event) -> bool:
        if not self.can_handle(event):
            return False

        if type(event) is PushEvent:
            if event.pressed:
                if self.is_off() and self._cmd_toggle_on is not None:
                    self._cmd_toggle_on.execute()
                elif self.is_on() and self._cmd_toggle_off is not None:
                    self._cmd_toggle_off.execute()
                self._toggle_on = not self._toggle_on
            return True

        self.inc(COCKPITDECKS_INTVAR.ACTIVATION_COUNT.value)  # since super() not called

        if type(event) is EncoderEvent:
            ok = False
            x = self.encoder_current_value
            if x is None:  # why?
                x = 0
            if event.turned_counter_clockwise:  # rotate left
                x = max(self.value_min, x - self.step)
                ok = True
                self.inc(COCKPITDECKS_INTVAR.ENCODER_TURNS.value, -1)
                self.inc(COCKPITDECKS_INTVAR.ENCODER_COUNTER_CLOCKWISE.value)
            elif event.turned_clockwise:  # rotate right
                x = min(self.value_max, x + self.step)
                ok = True
                self.inc(COCKPITDECKS_INTVAR.ENCODER_TURNS.value)
                self.inc(COCKPITDECKS_INTVAR.ENCODER_CLOCKWISE.value)
            else:
                logger.warning(f"{type(self).__name__} invalid event {event}")

            if ok:
                self.encoder_current_value = x
            return True

        logger.warning(f"button {self.button_name}: {type(self).__name__} invalid event {event}")
        return False

    def get_activation_value(self):
        # On/Off status accessible through state variable only
        return self.encoder_current_value

    def get_state_variables(self) -> dict:
        a = {
            "step": self.step,
            "stepxl": self.stepxl,
            "value_min": self.value_min,
            "value_max": self.value_max,
            COCKPITDECKS_INTVAR.ENCODER_CLOCKWISE.value: self._cw,
            COCKPITDECKS_INTVAR.ENCODER_COUNTER_CLOCKWISE.value: self._ccw,
            COCKPITDECKS_INTVAR.ENCODER_TURNS.value: self._turns,
            "on": self._toggle_on,
            "value": self.encoder_current_value,
        }
        return a | Activation.get_state_variables(self)

    def describe(self) -> str:
        """
        Describe what the button does in plain English
        """
        a = [
            f"This encoder increases a value by {self.step} when it is turned clockwise.",
            f"This encoder decreases a value by {self.step} when it is turned counter-clockwise.",
            f"The value remains in the range [{self.value_min}-{self.value_max}].",
        ]
        if self._set_sim_data is not None:
            a.append(f"The value is written in dataref {self._set_sim_data.name}.")
        return "\n\r".join(a)


class EncoderValueExtended(Activation, EncoderProperties):
    EDITOR_FAMILY = "Encoder"
    EDITOR_LABEL = "Encoder Value Extended"
    """
    Activation that maintains an internal value and optionally write that value to a dataref
    """

    ACTIVATION_NAME = "encoder-value-extended"
    REQUIRED_DECK_ACTIONS = [DECK_ACTIONS.ENCODER, DECK_ACTIONS.PRESS, DECK_ACTIONS.LONGPRESS, DECK_ACTIONS.PUSH]

    PARAMETERS = {
        "value-min": {
            "type": "float",
            "prompt": "Minimum value",
        },
        "value-max": {
            "type": "float",
            "prompt": "Maximum value",
        },
        "step": {
            "type": "float",
            "prompt": "Step value",
        },
        "step-xl": {
            "type": "float",
            "prompt": "Large step value",
        },
        "set-dataref": {"type": "string", "prompt": "Dataref"},
    }

    def __init__(self, button: "Button"):
        Activation.__init__(self, button=button)
        EncoderProperties.__init__(self, button=button)

        # Activation arguments
        self.step = float(button._config.get("step", 1))
        self.stepxl = float(button._config.get("stepxl", 10))
        self.value_min = float(button._config.get("value-min", 0))
        self.value_max = float(button._config.get("value-max", 100))

        # Activation options
        self.options = button._config.get("options", None)

        # Internal variables
        self.encoder_current_value = float(button._config.get("initial-value", 1))
        self._step_mode = self.step

        self._local_dataref = None
        local_dataref = button._config.get("dataref", None)  # "local-dataref"
        if local_dataref is not None:
            self._local_dataref = self.button.sim.get_internal_variable(local_dataref)

        self.init_differed()

    def init_differed(self):
        if self._inited:
            return
        value = self.button.value
        if value is not None:
            self.encoder_current_value = value
            logger.debug(f"button {self.button_name} initialized on/off at {self.encoder_current_value}")
        elif self.initial_value is not None:
            self.encoder_current_value = self.initial_value
            logger.debug(f"button {self.button_name} initialized encoder value at {self.encoder_current_value} from initial-value")
        if self.encoder_current_value is not None:
            self._inited = True

    def decrease(self, x):
        if self.options == "modulo":
            new_x = (x - self._step_mode - self.value_min) % (self.value_max - self.value_min + 1) + self.value_min
            return new_x
        else:
            x = x - self._step_mode
            if x < self.value_min:
                return self.value_min
            return x

    def increase(self, x):
        if self.options == "modulo":
            new_x = (x + self._step_mode - self.value_min) % (self.value_max - self.value_min + 1) + self.value_min
            return new_x
        else:
            x = x + self._step_mode
            if x > self.value_max:
                return self.value_max
            return x

    def is_valid(self):
        if self._set_sim_data is None:
            logger.error(f"button {self.button_name}: {type(self).__name__} must have a dataref to write to")
            return False
        return super().is_valid()

    def activate(self, event) -> bool:
        if not self.can_handle(event):
            return False

        if type(event) is PushEvent:
            if not super().activate(event):
                return False

            if event.pressed:

                if self.has_long_press() and self.long_pressed():
                    self.long_press(event)
                    logger.debug(f"button {self.button_name}: {type(self).__name__}: long pressed")
                    return

                if self._step_mode == self.step:
                    self._step_mode = self.stepxl
                else:
                    self._step_mode = self.step
                return True

        self.inc(COCKPITDECKS_INTVAR.ACTIVATION_COUNT.value)  # since super() not called

        if type(event) is EncoderEvent:
            ok = False
            x = self.encoder_current_value
            if x is None:
                x = 0
            if not hasattr(event, "pressed"):
                if event.turned_counter_clockwise:  # anti-clockwise
                    x = self.decrease(x)
                    ok = True
                    self.inc(COCKPITDECKS_INTVAR.ENCODER_TURNS.value, -1)
                    self.inc(COCKPITDECKS_INTVAR.ENCODER_COUNTER_CLOCKWISE.value)
                elif event.turned_clockwise:  # clockwise
                    x = self.increase(x)
                    ok = True
                    self.inc(COCKPITDECKS_INTVAR.ENCODER_TURNS.value)
                    self.inc(COCKPITDECKS_INTVAR.ENCODER_CLOCKWISE.value)
            if ok:
                self.encoder_current_value = x
                if self._local_dataref is not None:
                    self._local_dataref.update_value(new_value=x)
            return True

        logger.warning(f"button {self.button_name}: {type(self).__name__} invalid event {event}")
        return False

    def get_activation_value(self):
        return self.encoder_current_value

    def get_state_variables(self) -> dict:
        a = {
            "step": self.step,
            "stepxl": self.stepxl,
            "value_min": self.value_min,
            "value_max": self.value_max,
            COCKPITDECKS_INTVAR.ENCODER_CLOCKWISE.value: self._cw,
            COCKPITDECKS_INTVAR.ENCODER_COUNTER_CLOCKWISE.value: self._ccw,
            COCKPITDECKS_INTVAR.ENCODER_TURNS.value: self._turns,
        }
        return a | super().get_state_variables()

    def describe(self) -> str:
        """
        Describe what the button does in plain English
        """
        a = [
            f"This encoder increases a value by {self.step} when it is turned clockwise.",
            f"This encoder decreases a value by {self.step} when it is turned counter-clockwise.",
            f"The value remains in the range [{self.value_min}-{self.value_max}].",
        ]
        if self._set_sim_data is not None:
            a.append(f"The value is written in dataref {self._set_sim_data.name}.")
        return "\n\r".join(a)


#
# ###############################
# CURSOR TYPE ACTIVATION
#
#
class Slider(Activation):  # Cursor?
    EDITOR_FAMILY = "Touch"
    EDITOR_LABEL = "Slider"
    """
    A Encoder that can turn left/right.
    """

    ACTIVATION_NAME = "slider"
    REQUIRED_DECK_ACTIONS = DECK_ACTIONS.CURSOR

    # Hardware range usually 0..100 (webdeck), some might be -100..100

    PARAMETERS = {
        "value-min": {
            "type": "float",
            "prompt": "Minimum value",
        },
        "value-max": {
            "type": "float",
            "prompt": "Maximum value",
        },
        "step": {
            "type": "float",
            "prompt": "Step value",
        },
        "set-dataref": {"type": "string", "prompt": "Dataref"},
    }

    def __init__(self, button: "Button"):
        Activation.__init__(self, button=button)

        # Activation arguments
        self.value_min = float(self._config.get("value-min", 0))
        self.value_max = float(self._config.get("value-max", 100))
        self.value_step = float(self._config.get("value-step", 0))
        if self.value_min > self.value_max:
            temp = self.value_min
            self.value_min = self.value_max
            self.value_max = temp
        self.current_value = 0

        self._slider_max = 100
        self._slider_min = 0 # webdeck defaults to 0..100

        bdefs = self.button.deck.deck_type.filter({DECK_KW.ACTION.value: DECK_ACTIONS.CURSOR.value})
        if bdefs:
            bdef = bdefs[0]
            range_values = bdef.get(DECK_KW.RANGE.value)
            if range_values is not None and type(range_values) in [list, tuple]:
                self._slider_max = max(range_values)
                self._slider_min = min(range_values)

    def is_valid(self):
        if self._set_sim_data is None:
            logger.error(f"button {self.button_name}: {type(self).__name__} must have a dataref to write to")
            return False
        return super().is_valid()

    def activate(self, event) -> bool:
        if not self.can_handle(event):
            return False

        pct = abs(event.value - self._slider_min) / (self._slider_max - self._slider_min)
        if self.value_step != 0:
            nstep = (self.value_max - self.value_min) / self.value_step
            pct = int(pct * nstep) / nstep
        value = self.value_min + pct * (self.value_max - self.value_min)
        self.current_value = value
        logger.debug(f"button {self.get_id()}: {type(self).__name__} written value={value} in {self._set_sim_data.name}")
        return True  # normal termination

    def get_activation_value(self):
        return self.current_value

    def describe(self) -> str:
        """
        Describe what the button does in plain English
        """
        a = [
            f"This slider produces a value between [{self.value_min}, {self.value_max}].",
            f"The raw value from slider is modified by formula {self.button.formula}.",
        ]
        if self._set_sim_data is not None:
            a.append(f"The value after modification by the formula is written in dataref {self._set_sim_data.name}.")
        return "\n\r".join(a)


#
# ###############################
# SWIPE TYPE ACTIVATION (2D SURFACE)
#
#
class Swipe(Activation):
    EDITOR_FAMILY = "Touch"
    EDITOR_LABEL = "Swipe"
    """
    Touch-surface swipe activation.
    Fires up/down commands a number of times proportional to swipe distance and direction.
    Useful for unbounded controls such as altitude or heading where a fixed dataref range
    is not appropriate.
    """

    ACTIVATION_NAME = "swipe"
    REQUIRED_DECK_ACTIONS = DECK_ACTIONS.SWIPE

    SWIPE_DEFAULT_STEP = 50      # pixels of swipe per command repeat
    SWIPE_MIN_DISTANCE = 20      # pixels below which the gesture is ignored

    PARAMETERS = {
        "commands": {"type": "sub", "list": {
            "up": {"type": "string", "label": "Swipe Up / Left", "hint": "Command fired when swiping up or left"},
            "down": {"type": "string", "label": "Swipe Down / Right", "hint": "Command fired when swiping down or right"},
        }},
        "step": {"type": "float", "label": "Step (px)", "hint": "Pixels of swipe per command repeat (default 50)"},
        "minimum-distance": {"type": "float", "label": "Min distance (px)", "hint": "Minimum swipe distance to trigger a command (default 20)"},
    }

    def __init__(self, button: "Button"):
        Activation.__init__(self, button=button)

        cmdname = ":".join([self.button.get_id(), type(self).__name__])
        commands = self._config.get("commands", {}) or {}

        def make_cmd(key):
            val = commands.get(key)
            return self.sim.instruction_factory(name=f"{cmdname}:{key}", instruction_block={CONFIG_KW.COMMAND.value: val}) if val else None

        self._cmd_up = make_cmd("up")
        self._cmd_down = make_cmd("down")
        self._commands = [c for c in [self._cmd_up, self._cmd_down] if c is not None]

        self.step = float(self._config.get("step", Swipe.SWIPE_DEFAULT_STEP))
        self.minimum_distance = float(self._config.get("minimum-distance", Swipe.SWIPE_MIN_DISTANCE))

    def is_valid(self):
        if not self._commands:
            logger.warning(f"button {self.button_name}: {type(self).__name__} has no commands defined")
            return False
        return super().is_valid()

    def activate(self, event) -> bool:
        if not self.can_handle(event):
            return False
        # Only act on touch-end events that carry a start reference (completing a swipe)
        if not isinstance(event, TouchEvent) or event.start is None:
            return True
        swipe = event.swipe(autorun=False)
        if swipe is None or swipe.swipe_distance < self.minimum_distance:
            return True
        dx = swipe.end_pos_x - swipe.start_pos_x
        dy = swipe.end_pos_y - swipe.start_pos_y
        # Primary axis: whichever delta is larger drives the direction.
        # Up (negative dy) or left (negative dx) → up command.
        if abs(dy) >= abs(dx):
            going_up = dy < 0
        else:
            going_up = dx < 0
        cmd = self._cmd_up if going_up else self._cmd_down
        if cmd is None:
            return True
        repeats = max(1, int(swipe.swipe_distance / self.step))
        for _ in range(repeats):
            cmd.execute()
        logger.debug(f"button {self.button_name}: swipe {'up' if going_up else 'down'} distance={swipe.swipe_distance:.0f}px repeats={repeats}")
        return True

    def describe(self) -> str:
        lines = ["Swipe gesture activation — fires commands proportional to swipe distance."]
        if self._cmd_up:
            lines.append(f"Swipe up/left fires: {self._cmd_up} (×distance÷{self.step:.0f}px).")
        if self._cmd_down:
            lines.append(f"Swipe down/right fires: {self._cmd_down} (×distance÷{self.step:.0f}px).")
        return "\n\r".join(lines)


class EncoderMode(Activation, EncoderProperties):
    EDITOR_FAMILY = "Encoder"
    EDITOR_LABEL = "Encoder Mode"
    """
    Encoder with two rotation modes switched by long-press.
    Mode A (on): commands.ccw / commands.cw
    Mode B (off): commands.ccw-off / commands.cw-off
    """

    ACTIVATION_NAME = "encoder-mode"
    REQUIRED_DECK_ACTIONS = [DECK_ACTIONS.ENCODER, DECK_ACTIONS.PRESS, DECK_ACTIONS.LONGPRESS, DECK_ACTIONS.PUSH]

    PARAMETERS = PARAM_INITIAL_VALUE | {
        "commands": {"type": "sub", "list": {
            "ccw": {"type": "string", "label": "Mode A: Counter-clockwise"},
            "cw": {"type": "string", "label": "Mode A: Clockwise"},
            "ccw-off": {"type": "string", "label": "Mode B: Counter-clockwise"},
            "cw-off": {"type": "string", "label": "Mode B: Clockwise"},
        }},
    }

    def __init__(self, button: "Button"):
        Activation.__init__(self, button=button)
        EncoderProperties.__init__(self, button=button)

        # Internal variables
        self.longpush = True
        self._on = True
        self._toggle_initialized = False

        cmdname = ":".join([self.button.get_id(), type(self).__name__])
        commands = button._config.get("commands", {}) or {}
        def make_cmd(key):
            val = commands.get(key)
            return self.sim.instruction_factory(name=f"{cmdname}:{key}", instruction_block={CONFIG_KW.COMMAND.value: val}) if val else None

        self._cmd_ccw = make_cmd("ccw")
        self._cmd_cw = make_cmd("cw")
        self._cmd_ccw_off = make_cmd("ccw-off")
        self._cmd_cw_off = make_cmd("cw-off")
        # Rebuild _commands list for num_commands() compatibility
        self._commands = [c for c in [self._cmd_ccw, self._cmd_cw, self._cmd_ccw_off, self._cmd_cw_off] if c is not None]

        # Optional labels for toggle state display (e.g., ["1 MHz", "25 kHz"])
        toggle_labels = self.button._config.get("toggle-labels")
        if toggle_labels is not None and isinstance(toggle_labels, list) and len(toggle_labels) == 2:
            self._on_label = str(toggle_labels[0])
            self._off_label = str(toggle_labels[1])
        else:
            self._on_label = None
            self._off_label = None

    def num_commands(self):
        return len(self._commands) if self._commands is not None else 0

    def is_valid(self):
        if self.num_commands() != 4:
            logger.warning(f"button {self.button_name}: {type(self).__name__} must have 4 commands (ccw, cw, ccw-off, cw-off)")
            return False
        return True  # super().is_valid()

    def _update_toggle_variable(self, cascade: bool = True):
        try:
            if self._on_label is not None:
                value = self._on_label if self._on else self._off_label
            else:
                value = 1.0 if self._on else 0.0
            self.button.sim.set_internal_variable(
                name=self.button.name + "-toggle",
                value=value,
                cascade=cascade,
            )
            self._toggle_initialized = True
            logger.info(f"button {self.button_name}: toggle={'ON' if self._on else 'OFF'} (data:{self.button.name}-toggle={value})")
        except Exception:
            logger.warning(f"button {self.button_name}: could not set toggle variable", exc_info=True)

    def activate(self, event) -> bool:
        if not self.can_handle(event):
            return False

        if not self._toggle_initialized:
            self._update_toggle_variable(cascade=False)

        if type(event) is PushEvent:
            if not super().activate(event):
                return False
            if not event.pressed and not self.long_pressed():
                self._on = not self._on
                self._update_toggle_variable()
            return True

        self.inc(COCKPITDECKS_INTVAR.ACTIVATION_COUNT.value)  # since super() not called

        if type(event) is EncoderEvent:
            if event.turned_counter_clockwise and not self.is_pressed():
                cmd = self._cmd_ccw if self._on else self._cmd_ccw_off
                if cmd:
                    cmd.execute()
                self.inc(COCKPITDECKS_INTVAR.ENCODER_TURNS.value, -1)
                self.inc(COCKPITDECKS_INTVAR.ENCODER_COUNTER_CLOCKWISE.value)

            elif event.turned_clockwise and not self.is_pressed():
                cmd = self._cmd_cw if self._on else self._cmd_cw_off
                if cmd:
                    cmd.execute()
                    self.inc(COCKPITDECKS_INTVAR.ACTIVATION_ON.value if self._on else COCKPITDECKS_INTVAR.ACTIVATION_OFF.value)
                self.inc(COCKPITDECKS_INTVAR.ENCODER_TURNS.value)
                self.inc(COCKPITDECKS_INTVAR.ENCODER_CLOCKWISE.value)
            return True

        logger.warning(f"button {self.button_name}: {type(self).__name__} invalid event {event}")
        return False  # normal termination

    def get_state_variables(self) -> dict:
        a = {
            COCKPITDECKS_INTVAR.ENCODER_CLOCKWISE.value: self._cw,
            COCKPITDECKS_INTVAR.ENCODER_COUNTER_CLOCKWISE.value: self._ccw,
            COCKPITDECKS_INTVAR.ENCODER_TURNS.value: self._turns,
        }
        return a | super().get_state_variables()

    def describe(self) -> str:
        """
        Describe what the button does in plain English
        """
        if self.longpush:
            return "\n\r".join(
                [
                    f"This encoder has longpush option.",
                    f"This encoder executes command {self._commands[0]} when it is not pressed and turned clockwise.",
                    f"This encoder executes command {self._commands[1]} when it is not pressed and turned counter-clockwise.",
                    f"This encoder executes command {self._commands[2]} when it is pressed and turned clockwise.",
                    f"This encoder executes command {self._commands[3]} when it is pressed and turned counter-clockwise.",
                ]
            )
        else:
            return "\n\r".join(
                [
                    f"This encoder does not have longpush option.",
                    f"This encoder executes command {self._commands[0]} when it is pressed.",
                    f"This encoder does not execute any command when it is released.",
                    f"This encoder executes command {self._commands[1]} when it is turned clockwise.",
                    f"This encoder executes command {self._commands[2]} when it is turned counter-clockwise.",
                ]
            )


#
# ###############################
# Touch screen activation for Mosaic-like icons
# (large icons composed from multiple icons)
#
class Mosaic(Activation):
    EDITOR_FAMILY = "Touch"
    EDITOR_LABEL = "Mosaic Surface"
    """
    Defines a Push activation.
    The supplied command is executed each time a button is pressed.
    (May be this proxy/transfer/indirection/forward could be done in driver?)
    """

    ACTIVATION_NAME = "mosaic"
    REQUIRED_DECK_ACTIONS = [DECK_ACTIONS.SWIPE, DECK_ACTIONS.PUSH]

    PARAMETERS = PARAM_PUSH_AUTOREPEAT | PARAM_INITIAL_VALUE | PARAM_COMMAND_BLOCK

    # Default values
    AUTO_REPEAT_DELAY = 1  # seconds
    AUTO_REPEAT_SPEED = 0.2  # seconds

    def __init__(self, button: "Button"):
        Activation.__init__(self, button=button)

        # Working variables
        self.pressed = False  # True while the button is pressed, False when released

    def __str__(self):  # print its status
        return str(super()) + "\n" + f", is_valid: {self.is_valid()}"

    def is_valid(self):
        return super().is_valid()

    def activate(self, event) -> bool:
        if not self.can_handle(event):
            return False
        if not super().activate(event):
            return False

        if type(event) is TouchEvent:
            coords = event.xy()
            button_def = self.button._definition.mosaic.get_button(x=coords[0], y=coords[1])
            if button_def is not None:
                logger.info(f"found button def {button_def.name}")
                button = self.button.page.find_button(button_def)
                if button is not None:
                    logger.info(f"found button {button.index}")
                    PushEvent(deck=event.deck, button=button.index, pressed=event.start is None)
            else:
                logger.debug(f"coordinates {coords} does not hit a button")

            return True
        else:  # swipe event
            logger.warning("swiped: {event.touched_only()}, {event.xy()}")
        # determine which tile was hit
        # activate proper event in tile
        return False  # normal termination

    def describe(self) -> str:
        """
        Describe what the button does in plain English
        """
        return "\n\r".join(
            [
                f"The button converts its swipe event into a push event for a tile.",
            ]
        )
