# PARAMETERS

# ######################
# REPRESENTATIONS
#
# Common blocks

PARAM_TEXT = {
    "text": {"type": "string", "prompt": "Text", "hint": "Principal text shown on the button", "group": "Display", "sample": "HEADINGS", "required": True},
    "text-font": {"type": "font", "prompt": "Font", "hint": "Font file to use for the text", "group": "Display"},
    "text-size": {"type": "integer", "prompt": "Size", "hint": "Font size for the text", "group": "Display"},
    "text-color": {"type": "color", "prompt": "Color", "hint": "Color for the text", "group": "Display"},
    "text-position": {"type": "choice", "prompt": "Position", "choices": ["lt", "ct", "rt", "lm", "cm", "rm", "lb", "cb", "rb"], "hint": "Alignment of the text on the button", "group": "Display"},
}

PARAM_CHART_DATA = {
    "name": {"type": "string", "prompt": "Name", "required": True},
    "type": {
        "type": "string",
        "prompt": "Type",
        "lov": [
            "bar",
        ],
        "required": True
    },
    "rate": {"type": "bool", "prompt": "Rate?"},
    "keep": {"type": "integer", "prompt": "Keep"},
    "update": {"type": "float", "prompt": "Update rate (secs)"},
    "value-min": {"type": "integer", "prompt": "Min"},
    "value-max": {"type": "integer", "prompt": "Max"},
    "color": {"type": "color", "prompt": "Color"},
    "marker": {"type": "string", "prompt": "Marker", "lov": ["square"]},
    "marker-color": {"label": "Marker Color", "type": "color"},
    "dataref": {"type": "string", "prompt": "Data", "required": True},
}

# Button Drawing Parameters, loosely grouped per button type

PARAM_BTN_COMMON = {
    "button-fill-color": {"label": "Button Fill Color", "type": "color", "hint": "Background color of the button circular base", "group": "Appearance"},
    "button-size": {"label": "Button Size", "type": "int", "hint": "Diameter/scale of the button base", "group": "Appearance"},
    "button-stroke-color": {"label": "Button Stroke Color", "type": "color", "hint": "Border color of the button base", "group": "Appearance"},
    "button-stroke-width": {"label": "Button Stroke Width", "type": "int", "hint": "Width of the base border", "group": "Appearance"},
    "button-underline-color": {"label": "Button Underline Color", "type": "color", "hint": "Color for decorative underline", "group": "Appearance"},
    "button-underline-width": {"label": "Button Underline Width", "type": "int", "hint": "Width of decorative underline (0 to disable)", "group": "Appearance"},
    "base-fill-color": {"label": "Base Fill Color", "type": "color", "hint": "Color for the switch baseplate", "group": "Appearance"},
    "base-stroke-color": {"label": "Base Stroke Color", "type": "color", "hint": "Color for the baseplate border", "group": "Appearance"},
    "base-stroke-width": {"label": "Base Stroke Width", "type": "int", "hint": "Width of the baseplate border", "group": "Appearance"},
    "base-underline-color": {"label": "Base Underline Color", "type": "color", "hint": "Color for the baseplate decorative underline", "group": "Appearance"},
    "base-underline-width": {"label": "Base Underline Width", "type": "int", "hint": "Width of the baseplate decorative underline", "group": "Appearance"},
    "handle-fill-color": {"label": "Handle Fill Color", "type": "color", "hint": "Primary color of the switch handle/lever", "group": "Appearance"},
    "handle-stroke-color": {"label": "Handle Stroke Color", "type": "color", "hint": "Color for the handle border", "group": "Appearance"},
    "handle-stroke-width": {"label": "Handle Stroke Width", "type": "int", "hint": "Width of the handle border", "group": "Appearance"},
    "top-fill-color": {"label": "Top Fill Color", "type": "color", "hint": "Color for the top cap of the handle", "group": "Appearance"},
    "top-stroke-color": {"label": "Top Stroke Color", "type": "color", "hint": "Border color for the top cap", "group": "Appearance"},
    "top-stroke-width": {"label": "Top Stroke Width", "type": "int", "hint": "Width of the top cap border", "group": "Appearance"},
    "tick-from": {"label": "Tick From", "type": "string", "hint": "Starting angle (degrees) for the scale arc", "group": "Style", "sample": "-120"},
    "tick-to": {"label": "Tick To", "type": "string", "hint": "Ending angle (degrees) for the scale arc", "group": "Style", "sample": "120"},
    "tick-labels": {"type": "sub", "list": {"-label": {"type": "string", "label": "Position label"}}, "min": 1, "max": 0, "hint": "Label for each position (one per line in form)", "group": "Style", "sample": '[{"-label": "OFF"}, {"-label": "ON"}]'},
    "tick-color": {"label": "Tick Color", "type": "color", "hint": "Color for scale graduation marks", "group": "Ticks"},
    "tick-label-color": {"label": "Tick Label Color", "type": "color", "hint": "Color for graduation mark labels", "group": "Ticks"},
    "tick-label-size": {"label": "Tick Label Size", "type": "int", "hint": "Font size for graduation labels", "group": "Ticks"},
    "tick-label-space": {"label": "Tick Label Space", "type": "string", "hint": "Distance from tick to label", "group": "Ticks"},
    "tick-length": {"label": "Tick Length", "type": "int", "hint": "Length of graduation marks", "group": "Ticks"},
    "tick-space": {"label": "Tick Space", "type": "string", "hint": "Distance from base to graduation marks", "group": "Ticks"},
    "tick-underline-color": {"label": "Tick Underline Color", "type": "color", "hint": "Color for decorative scale underline", "group": "Ticks"},
    "tick-underline-width": {"label": "Tick Underline Width", "type": "int", "hint": "Width of decorative scale underline", "group": "Ticks"},
    "tick-width": {"label": "Tick Width", "type": "int", "hint": "Width/thickness of graduation marks", "group": "Ticks"},
    "needle-color": {"label": "Needle Color", "type": "color", "hint": "Color for the switch pointer/needle", "group": "Needle"},
    "needle-length": {"label": "Needle Length", "type": "int", "hint": "Length of the pointer", "group": "Needle"},
    "needle-start": {"label": "Needle Start", "type": "string", "hint": "Distance from center to start of needle", "group": "Needle"},
    "needle-tip-size": {"label": "Needle Tip Size", "type": "int", "hint": "Size of the pointer tip (arrow/ball)", "group": "Needle"},
    "needle-underline-color": {"label": "Needle Underline Color", "type": "color", "hint": "Color for decorative needle underline", "group": "Needle"},
    "needle-underline-width": {"label": "Needle Underline Width", "type": "int", "hint": "Width of decorative needle underline", "group": "Needle"},
    "needle-width": {"label": "Needle Width", "type": "int", "hint": "Width/thickness of the pointer", "group": "Needle"},
}

PARAM_BTN_SWITCH = {
    "switch-style": {"label": "Switch Style", "type": "string", "hint": "Visual style: 'round', 'rect', or '3dot'", "group": "Style", "sample": "round"},
    "switch-length": {"label": "Switch Length", "type": "int", "hint": "Total length of the switch lever", "group": "Appearance"},
    "switch-width": {"label": "Switch Width", "type": "int", "hint": "Width/thickness of the switch lever", "group": "Appearance"},
    "switch-handle-dot-color": {"label": "Handle Dot Color", "type": "color", "hint": "Color for the indicator dot on the switch handle", "group": "Appearance"},
}

PARAM_BTN_CIRCULAR_SWITCH = {
    "angle-start": {"label": "Angle Start", "type": "int", "hint": "Starting angle of the switch arc in degrees (0 = 12 o'clock, increasing clockwise)", "group": "Style"},
    "angle-end": {"label": "Angle End", "type": "int", "hint": "Ending angle of the switch arc in degrees (0 = 12 o'clock, increasing clockwise)", "group": "Style"},
    "ticks": {"type": "list", "list": "string", "label": "Ticks", "hint": "One label per stop, in order. Replaces tick-labels and determines stop count.", "group": "Style"},
}

PARAM_BTN_PUSH = {
    "witness-fill-color": {"label": "Witness Fill Color", "type": "color"},
    "witness-fill-off-color": {"label": "Witness Fill Off Color", "type": "color"},
    "witness-size": {"label": "Witness Size", "type": "int"},
    "witness-stroke-color": {"label": "Witness Stroke Color", "type": "color"},
    "witness-stroke-off-color": {"label": "Witness Stroke Off Color", "type": "color"},
    "witness-stroke-off-width": {"label": "Witness Stroke Off Width", "type": "int"},
    "witness-stroke-width": {"label": "Witness Stroke Width", "type": "int"},
}

PARAM_BTN_KNOB = {
    "button-dent-extension": {"label": "Button Dent Extension", "type": "string"},
    "button-dent-negative": {"label": "Button Dent Negative", "type": "string"},
    "button-dent-size": {"label": "Button Dent Size", "type": "int"},
    "button-dents": {"label": "Button Dents", "type": "string"},
    "knob-mark": {"label": "Knob Mark", "type": "string"},
    "knob-type": {"label": "Knob Type", "type": "string"},
    "mark-underline-color": {"label": "Mark Underline Color", "type": "color"},
    "mark-underline-outer": {"label": "Mark Underline Outer", "type": "string"},
    "mark-underline-width": {"label": "Mark Underline Width", "type": "int"},
}

# aircraft
# annunciator
# annunciator-animate
# chart
# colored-led
# data
# decor
# draw-animation
# draw-base
# icon
# icon-animation
# icon-color
# led
# multi-icons
# multi-texts
# none
# text

# special:
# ftg
# solari
# virtual-led
# virtual-encoder
# weather-base
# weather-metar
# weather-real
# weather-xp
# textpage

# TO DO

# knob
# circular-switch
# push-switch
# switch
# switch-base

# special
# encoder-leds
# fcu
# fma
# side
