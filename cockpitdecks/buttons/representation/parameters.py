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

# Label fields — stored at the representation root (not inside the nested block).
# IconBase reads label/label-* from self._config (the representation root), so these
# must NOT carry storage_mode "nested_block".
PARAM_LABEL = {
    "label": {"label": "Label", "type": "string", "hint": "Text caption displayed on the button", "group": "Label", "sample": "ON"},
    "label-color": {"label": "Label Color", "type": "color", "hint": "Color for the label text", "group": "Label"},
    "label-font": {"label": "Label Font", "type": "font", "hint": "Font file for the label", "group": "Label"},
    "label-size": {"label": "Label Size", "type": "integer", "hint": "Font size for the label", "group": "Label"},
    "label-position": {"label": "Label Position", "type": "choice", "choices": ["lt", "ct", "rt", "lm", "cm", "rm", "lb", "cb", "rb"], "hint": "Alignment of the label on the button", "group": "Label"},
}

# Position/scale overrides for nested-block switch representations.
# SwitchBase reads these from self.switch (the nested config block), so they must be
# written into that block — hence storage_mode "nested_block".
PARAM_SWITCH_POSITION = {
    "scale": {"label": "Scale", "type": "float", "hint": "Scale factor for the drawn element (0.5–2.0)", "group": "Layout", "storage_mode": "nested_block"},
    "left": {"label": "Shift Left", "type": "integer", "hint": "Shift drawing left (pixels)", "group": "Layout", "storage_mode": "nested_block"},
    "right": {"label": "Shift Right", "type": "integer", "hint": "Shift drawing right (pixels)", "group": "Layout", "storage_mode": "nested_block"},
    "up": {"label": "Shift Up", "type": "integer", "hint": "Shift drawing up (pixels)", "group": "Layout", "storage_mode": "nested_block"},
    "down": {"label": "Shift Down", "type": "integer", "hint": "Shift drawing down (pixels)", "group": "Layout", "storage_mode": "nested_block"},
}

# Button Drawing Parameters, loosely grouped per button type.
# All entries carry storage_mode "nested_block" because every representation that uses
# PARAM_BTN_COMMON stores its config inside a named nested block (switch:, circular-switch:, etc.).
_NB = "nested_block"

PARAM_BTN_COMMON = {
    "button-fill-color": {"label": "Button Fill Color", "type": "color", "hint": "Background color of the button circular base", "group": "Appearance", "storage_mode": _NB},
    "button-size": {"label": "Button Size", "type": "int", "hint": "Diameter/scale of the button base", "group": "Appearance", "storage_mode": _NB},
    "button-stroke-color": {"label": "Button Stroke Color", "type": "color", "hint": "Border color of the button base", "group": "Appearance", "storage_mode": _NB},
    "button-stroke-width": {"label": "Button Stroke Width", "type": "int", "hint": "Width of the base border", "group": "Appearance", "storage_mode": _NB},
    "button-underline-color": {"label": "Button Underline Color", "type": "color", "hint": "Color for decorative underline", "group": "Appearance", "storage_mode": _NB},
    "button-underline-width": {"label": "Button Underline Width", "type": "int", "hint": "Width of decorative underline (0 to disable)", "group": "Appearance", "storage_mode": _NB},
    "base-fill-color": {"label": "Base Fill Color", "type": "color", "hint": "Color for the switch baseplate", "group": "Appearance", "storage_mode": _NB},
    "base-stroke-color": {"label": "Base Stroke Color", "type": "color", "hint": "Color for the baseplate border", "group": "Appearance", "storage_mode": _NB},
    "base-stroke-width": {"label": "Base Stroke Width", "type": "int", "hint": "Width of the baseplate border", "group": "Appearance", "storage_mode": _NB},
    "base-underline-color": {"label": "Base Underline Color", "type": "color", "hint": "Color for the baseplate decorative underline", "group": "Appearance", "storage_mode": _NB},
    "base-underline-width": {"label": "Base Underline Width", "type": "int", "hint": "Width of the baseplate decorative underline", "group": "Appearance", "storage_mode": _NB},
    "handle-fill-color": {"label": "Handle Fill Color", "type": "color", "hint": "Primary color of the switch handle/lever", "group": "Appearance", "storage_mode": _NB},
    "handle-stroke-color": {"label": "Handle Stroke Color", "type": "color", "hint": "Color for the handle border", "group": "Appearance", "storage_mode": _NB},
    "handle-stroke-width": {"label": "Handle Stroke Width", "type": "int", "hint": "Width of the handle border", "group": "Appearance", "storage_mode": _NB},
    "top-fill-color": {"label": "Top Fill Color", "type": "color", "hint": "Color for the top cap of the handle", "group": "Appearance", "storage_mode": _NB},
    "top-stroke-color": {"label": "Top Stroke Color", "type": "color", "hint": "Border color for the top cap", "group": "Appearance", "storage_mode": _NB},
    "top-stroke-width": {"label": "Top Stroke Width", "type": "int", "hint": "Width of the top cap border", "group": "Appearance", "storage_mode": _NB},
    "tick-from": {"label": "Tick From", "type": "int", "hint": "Starting angle (degrees) for the scale arc", "group": "Style", "sample": -120, "storage_mode": _NB},
    "tick-to": {"label": "Tick To", "type": "int", "hint": "Ending angle (degrees) for the scale arc", "group": "Style", "sample": 120, "storage_mode": _NB},
    "tick-labels": {"type": "sub", "list": {"-label": {"type": "string", "label": "Position label"}}, "min": 1, "max": 0, "hint": "Label for each position (one per line in form)", "group": "Style", "sample": '[{"-label": "OFF"}, {"-label": "ON"}]', "storage_mode": _NB},
    "tick-color": {"label": "Tick Color", "type": "color", "hint": "Color for scale graduation marks", "group": "Ticks", "storage_mode": _NB},
    "tick-label-color": {"label": "Tick Label Color", "type": "color", "hint": "Color for graduation mark labels", "group": "Ticks", "storage_mode": _NB},
    "tick-label-font": {"label": "Tick Label Font", "type": "font", "hint": "Font for graduation mark labels (falls back to label-font)", "group": "Ticks", "storage_mode": _NB},
    "tick-label-size": {"label": "Tick Label Size", "type": "int", "hint": "Font size for graduation labels", "group": "Ticks", "storage_mode": _NB},
    "tick-label-space": {"label": "Tick Label Space", "type": "int", "hint": "Distance from tick to label (pixels)", "group": "Ticks", "storage_mode": _NB},
    "tick-length": {"label": "Tick Length", "type": "int", "hint": "Length of graduation marks", "group": "Ticks", "storage_mode": _NB},
    "tick-space": {"label": "Tick Space", "type": "int", "hint": "Distance from base to graduation marks (pixels)", "group": "Ticks", "storage_mode": _NB},
    "tick-underline-color": {"label": "Tick Underline Color", "type": "color", "hint": "Color for decorative scale underline", "group": "Ticks", "storage_mode": _NB},
    "tick-underline-width": {"label": "Tick Underline Width", "type": "int", "hint": "Width of decorative scale underline", "group": "Ticks", "storage_mode": _NB},
    "tick-width": {"label": "Tick Width", "type": "int", "hint": "Width/thickness of graduation marks", "group": "Ticks", "storage_mode": _NB},
    "needle-color": {"label": "Needle Color", "type": "color", "hint": "Color for the switch pointer/needle", "group": "Needle", "storage_mode": _NB},
    "needle-length": {"label": "Needle Length", "type": "int", "hint": "Length of the pointer", "group": "Needle", "storage_mode": _NB},
    "needle-start": {"label": "Needle Start", "type": "int", "hint": "Distance from center to start of needle (pixels)", "group": "Needle", "storage_mode": _NB},
    "needle-tip-size": {"label": "Needle Tip Size", "type": "int", "hint": "Size of the pointer tip (arrow/ball)", "group": "Needle", "storage_mode": _NB},
    "needle-underline-color": {"label": "Needle Underline Color", "type": "color", "hint": "Color for decorative needle underline", "group": "Needle", "storage_mode": _NB},
    "needle-underline-width": {"label": "Needle Underline Width", "type": "int", "hint": "Width of decorative needle underline", "group": "Needle", "storage_mode": _NB},
    "needle-width": {"label": "Needle Width", "type": "int", "hint": "Width/thickness of the pointer", "group": "Needle", "storage_mode": _NB},
}

PARAM_BTN_SWITCH = {
    "switch-style": {"label": "Switch Style", "type": "choice", "choices": ["round", "rect", "3dot"], "hint": "Visual style of the switch handle", "group": "Style", "sample": "round", "storage_mode": _NB},
    "switch-length": {"label": "Switch Length", "type": "int", "hint": "Total length of the switch lever", "group": "Appearance", "storage_mode": _NB},
    "switch-width": {"label": "Switch Width", "type": "int", "hint": "Width/thickness of the switch lever", "group": "Appearance", "storage_mode": _NB},
    "switch-handle-dot-color": {"label": "Handle Dot Color", "type": "color", "hint": "Color for the indicator dot on the switch handle", "group": "Appearance", "storage_mode": _NB},
}

PARAM_BTN_CIRCULAR_SWITCH = {
    "angle-start": {"label": "Angle Start", "type": "int", "hint": "Starting angle in degrees (0 = 12 o'clock, clockwise)", "group": "Style", "storage_mode": _NB},
    "angle-end": {"label": "Angle End", "type": "int", "hint": "Ending angle in degrees (0 = 12 o'clock, clockwise)", "group": "Style", "storage_mode": _NB},
    "ticks": {"type": "list", "list": "string", "label": "Ticks", "hint": "One label per stop, in order. Determines stop count.", "group": "Style", "storage_mode": _NB},
}

PARAM_BTN_PUSH = {
    "witness-fill-color": {"label": "Witness Fill Color", "type": "color", "storage_mode": _NB},
    "witness-fill-off-color": {"label": "Witness Fill Off Color", "type": "color", "storage_mode": _NB},
    "witness-size": {"label": "Witness Size", "type": "int", "storage_mode": _NB},
    "witness-stroke-color": {"label": "Witness Stroke Color", "type": "color", "storage_mode": _NB},
    "witness-stroke-off-color": {"label": "Witness Stroke Off Color", "type": "color", "storage_mode": _NB},
    "witness-stroke-off-width": {"label": "Witness Stroke Off Width", "type": "int", "storage_mode": _NB},
    "witness-stroke-width": {"label": "Witness Stroke Width", "type": "int", "storage_mode": _NB},
}

PARAM_BTN_KNOB = {
    "button-dent-extension": {"label": "Button Dent Extension", "type": "string", "storage_mode": _NB},
    "button-dent-negative": {"label": "Button Dent Negative", "type": "string", "storage_mode": _NB},
    "button-dent-size": {"label": "Button Dent Size", "type": "int", "storage_mode": _NB},
    "button-dents": {"label": "Button Dents", "type": "string", "storage_mode": _NB},
    "knob-mark": {"label": "Knob Mark", "type": "string", "storage_mode": _NB},
    "knob-type": {"label": "Knob Type", "type": "string", "storage_mode": _NB},
    "mark-underline-color": {"label": "Mark Underline Color", "type": "color", "storage_mode": _NB},
    "mark-underline-outer": {"label": "Mark Underline Outer", "type": "string", "storage_mode": _NB},
    "mark-underline-width": {"label": "Mark Underline Width", "type": "int", "storage_mode": _NB},
}
