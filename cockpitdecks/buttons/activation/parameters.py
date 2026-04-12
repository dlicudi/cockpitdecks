# PARAMETERS

# ######################
# COMMON
#
PARAM_DESCRIPTION = {
    "name": {"type": "string", "label": "Name", "hint": "Friendly name for internal identification", "group": "Identification", "required": True},
    "label": {"type": "string", "label": "Label", "hint": "Top label shown on the button", "group": "Visuals"},
    "label-size": {"type": "int", "label": "Lbl size", "hint": "Font size for the top label", "group": "Visuals"},
    "label-font": {"type": "font", "label": "Lbl font", "default": "DIN.ttf", "hint": "Font file to use for the label", "group": "Visuals"},
    "label-position": {"type": "lov", "label": "Lbl position", "lov": ["lt", "ct", "rt", "lm", "cm", "rm", "lb", "cb", "rb"], "hint": "Alignment of the label on the button", "group": "Visuals"},
    "label-color": {"type": "color", "label": "Lbl color", "hint": "Color for the label text", "group": "Visuals"},
}

PARAM_INITIAL_VALUE = {
    "initial-value": {"type": "integer", "label": "Initial value", "hint": "Starting value/state for this button", "group": "Logic"},
    "option": {"type": "string", "label": "Options", "hint": "Comma-separated special behavior flags (e.g., '3way', 'invert')", "group": "Logic"},
}

PARAM_DECK = {
    "sound": {"label": "Sound", "type": "sound", "hint": "Sound file to play on activation", "group": "Effects"},
    "vibrate": {"label": "Vibrate", "type": "string", "hint": "Haptic feedback pattern (for supported decks)", "group": "Effects"},
}

# ######################
# ACTIVATION
#
# COMMON BLOCKS
PARAM_COMMAND_BLOCK = {
    "command": {"type": "string", "label": "Command", "hint": "Simulator command path (e.g., sim/annun/test)", "group": "Execution", "required": True},
    "set-dataref": {"type": "string", "label": "Set Simulator Value", "hint": "Update a dataref value directly", "group": "Execution"},
    "delay": {"type": "string", "label": "Delay", "hint": "Time in seconds before execution (can be formula)", "group": "Execution"},
    "condition": {"type": "string", "label": "Condition", "hint": "Only execute if this formula evaluates to true", "group": "Execution"},
}

PARAM_SETVALUE_BLOCK = {
    "set-dataref": {"type": "string", "label": "Set Simulator Value", "hint": "Update a dataref value directly"},
    "delay": {"type": "string", "label": "Delay", "hint": "Time in seconds before execution (can be formula)"},
    "condition": {"type": "string", "label": "Condition", "hint": "Only execute if this formula evaluates to true"},
}

PARAM_PUSH_AUTOREPEAT = {
    "auto-repeat": {"type": "boolean", "label": "Auto-repeat", "hint": "Keep triggering the command while held", "group": "Logic"},
    "auto-repeat-delay": {"type": "float", "label": "Auto-repeat delay", "hint": "Delay in seconds before repeat starts", "group": "Logic"},
    "auto-repeat-speed": {"type": "float", "label": "Auto-repeat speed", "hint": "Repeats per second", "group": "Logic"},
}

# list on nov. 2025
# activation-template
# base
# begin-end-command
# dimmer
# encoder
# encoder-onoff
# encoder-push
# encoder-toggle
# encoder-value
# encoder-value-extended
# inspect
# mosaic
# none
# obs
# onoff
# page
# push
# random
# reload
# short-or-long-press
# simulator
# slider
# stop
# swipe
# theme
# updown


# ######################
# OBSERVABLE
#
# - command: cockpitdecks-accumulator
#   name: test
#   save: 60
#   variables:
#     - sim/flightmodel/position/latitude
#     - sim/flightmodel/position/longitude
#     - sim/flightmodel2/position/pressure_altitude
