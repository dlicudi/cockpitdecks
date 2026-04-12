import json
import os
import sys
import importlib
import pkgutil
from typing import Any, Dict

# Add the repository root to sys.path so we can import cockpitdecks
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

try:
    import cockpitdecks
    from cockpitdecks.buttons.activation.activation import Activation
    from cockpitdecks.buttons.representation.representation import Representation
    from cockpitdecks.constant import CONFIG_KW, DECK_KW, ENVIRON_KW, DECK_ACTIONS, DECK_FEEDBACK, COCKPITDECKS_DEFAULT_VALUES
except ImportError as e:
    print(f"Error: Could not import cockpitdecks. {e}")
    sys.exit(1)

def get_subclasses(cls):
    subclasses = {cls}
    stack = [cls]
    while stack:
        parent = stack.pop()
        for child in parent.__subclasses__():
            if child not in subclasses:
                subclasses.add(child)
                stack.append(child)
    return subclasses

def map_type(ptype):
    """Maps cockpitdecks parameter types to JSON Schema types."""
    if ptype == "int":
        return {"oneOf": [{"type": "integer"}, {"type": "string"}]}
    if ptype == "bool":
        return {"oneOf": [{"type": "boolean"}, {"type": "string"}]}
    if ptype == "float":
        return {"oneOf": [{"type": "number"}, {"type": "string"}]}
    if ptype == "color":
        return {"$ref": "#/$defs/color"}
    if ptype == "font":
        return {"type": "string", "description": "Font filename (e.g., D-DIN.otf)"}
    if ptype == "icon":
        return {"oneOf": [{"type": "string"}, {"type": "object"}]} # Icons can be shorthands
    if ptype == "sound":
        return {"type": "string", "description": "Sound filename (e.g., click.wav)"}
    return {"oneOf": [{"type": "string"}, {"type": "number"}, {"type": "boolean"}]}

def build_properties(parameters: Dict[str, Any]) -> Dict[str, Any]:
    props = {}
    for name, spec in (parameters or {}).items():
        if not isinstance(spec, dict):
            props[name] = {"type": "string"}
            continue
        
        ptype = spec.get("type", "string")
        
        if ptype == "list":
            item_type = spec.get("list", "string")
            if isinstance(item_type, dict):
                # If it's a list of objects, allow shorthand if only one property exists
                sub_props = build_properties(item_type)
                if len(sub_props) == 1 and list(sub_props.keys())[0].startswith("-"):
                    single_prop_type = list(sub_props.values())[0]
                    props[name] = {"type": "array", "items": {"oneOf": [single_prop_type, {"type": "object", "properties": sub_props}]}}
                else:
                    props[name] = {"type": "array", "items": {"type": "object", "properties": sub_props}}
            else:
                props[name] = {"type": "array", "items": {"type": "string"}}
        elif ptype == "sub":
            child = spec.get("list")
            if isinstance(child, dict):
                sub_props = build_properties(child)
                # A single key starting with "-" signals a shorthand: item can be a plain value or an object
                shorthand_keys = [k for k in sub_props if k.startswith("-")]
                is_shorthand = len(shorthand_keys) == len(sub_props) == 1
                # "min" or "max" indicates this is a multi-item array, not a single object
                is_array = name.startswith("multi-") or name in ["multi-icons", "icon-animate"] or "min" in spec or "max" in spec
                if is_array:
                    if is_shorthand:
                        item_type = sub_props[shorthand_keys[0]]
                        props[name] = {"type": "array", "items": {"oneOf": [item_type, {"type": "object", "properties": sub_props}]}}
                    else:
                        item_schema = {"type": "object", "properties": sub_props}
                        arr_schema = {"type": "array", "items": item_schema}
                        if "min" in spec and spec["min"]:
                            arr_schema["minItems"] = spec["min"]
                        props[name] = arr_schema
                elif is_shorthand:
                    # e.g. tick-labels: can be an array of plain strings
                    item_type = sub_props[shorthand_keys[0]]
                    props[name] = {"type": "array", "items": {"oneOf": [item_type, {"type": "object", "properties": sub_props}]}}
                else:
                    props[name] = {"type": "object", "properties": sub_props}
            else:
                props[name] = {"type": "string"}
        else:
            prop = map_type(ptype)
            if "label" in spec:
                prop["title"] = spec["label"]
            if "prompt" in spec:
                prop["title"] = spec["prompt"]
            if "hint" in spec:
                prop["description"] = spec["hint"]
            if "default" in spec:
                prop["default"] = spec["default"]
            if "lov" in spec:
                # Use enum as documentation/hint but don't enforce strictly
                prop["description"] = (prop.get("description", "") + f" Known values: {spec['lov']}").strip()
            if "choices" in spec:
                prop["description"] = (prop.get("description", "") + f" Known values: {spec['choices']}").strip()
            props[name] = prop

    return props

def merge_properties(target: Dict[str, Any], source: Dict[str, Any]) -> None:
    for key, value in (source or {}).items():
        if key not in target:
            target[key] = value

def main():
    # Force loading of all built-in extensions to find all activations/representations
    for folder in ["activation", "representation"]:
        package_name = f"cockpitdecks.buttons.{folder}"
        package = importlib.import_module(package_name)
        for loader, name, is_pkg in pkgutil.walk_packages(package.__path__):
            importlib.import_module(f"{package_name}.{name}")

    activations = get_subclasses(Activation)
    representations = get_subclasses(Representation)

    # Base Definitions
    # Build lists of known names for documentation purposes (extensions may add more at runtime)
    activation_names = sorted(list(set(
        [a.name().lower() for a in activations if a.name() not in ("base",)]
    )))
    representation_names = sorted(list(set(
        [r.name().lower() for r in representations if r.name() not in ("base", "none")]
    )))

    command_step = {
        "type": "object",
        "properties": {
            "command": {"type": "string"},
            "delay": {"type": "number", "description": "Delay in seconds before executing"},
            "condition": {"type": "string", "description": "Cockpitdecks formula condition"}
        },
        "required": ["command"]
    }

    defs = {
        "command": {
            "anyOf": [
                {"type": "string", "description": "Single command string"},
                {"type": "array", "items": command_step, "description": "Sequence of commands with optional delay/condition"}
            ]
        },
        "color": {
            "anyOf": [
                {"type": "string", "description": "Named or hex color (e.g., white, #ff0000)"},
                {"type": "array", "items": {"type": "integer", "minimum": 0, "maximum": 255}, "minItems": 3, "maxItems": 4, "description": "RGB or RGBA tuple"}
            ]
        },
        "formula": {
            "oneOf": [
                {"type": "string", "description": "Cockpitdecks formula (e.g., ${sim/cockpit/electrical/battery_on[0]} 0 eq)"},
                {"type": "number"},
                {"type": "boolean"}
            ]
        },
        "encoder-display-label": {
            "type": "object",
            "properties": {
                "label": {"type": "string"},
                "label-color": {"$ref": "#/$defs/color"},
                "label-size": {"type": "integer"},
                "label-font": {"type": "string"},
                "label-position": {"type": "string", "enum": ["lt", "ct", "rt", "lm", "cm", "rm", "lb", "cb", "rb"]},
                "text": {"type": "string"},
                "text-color": {"$ref": "#/$defs/color"},
                "text-size": {"type": "integer"},
                "text-font": {"type": "string"},
                "text-position": {"type": "string", "enum": ["lt", "ct", "rt", "lm", "cm", "rm", "lb", "cb", "rb"]},
                "formula": {"$ref": "#/$defs/formula"},
                "text-format": {"type": "string"}
            },
            "additionalProperties": True
        },
        "screen-config": {
            "type": "object",
            "properties": {
                "background": {"$ref": "#/$defs/color"},
                "render-cooldown-ms": {"type": "integer", "minimum": 0}
            },
            "additionalProperties": True
        },
        "activation": {
            "type": "object",
            "required": ["type"],
            "properties": {
                "type": {
                    "type": "string",
                    "description": f"Activation type. Known core values: {', '.join(activation_names)}. Extensions may add more."
                },
                "commands": {
                    "type": "object",
                    "description": "Named commands for this activation's events",
                    "properties": {
                        "press": {"$ref": "#/$defs/command"},
                        "long-press": {"$ref": "#/$defs/command"},
                        "cw": {"$ref": "#/$defs/command"},
                        "ccw": {"$ref": "#/$defs/command"},
                        "push-cw": {"$ref": "#/$defs/command"},
                        "push-ccw": {"$ref": "#/$defs/command"},
                        "toggle-on": {"$ref": "#/$defs/command"},
                        "toggle-off": {"$ref": "#/$defs/command"},
                        "cw-off": {"$ref": "#/$defs/command"},
                        "ccw-off": {"$ref": "#/$defs/command"}
                    },
                    "additionalProperties": {"$ref": "#/$defs/command"}
                },
                "positions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Ordered list of commands for sweep/positional activation"
                },
                "behaviour": {"type": "string", "enum": ["bounce", "loop"], "description": "Sweep behaviour"},
                "page": {"type": "string"},
                "pages": {"type": "array", "items": {"type": "string"}}
            },
            "additionalProperties": True,
            "allOf": []
        },
        "representation": {
            "type": "object",
            "required": ["type"],
            "properties": {
                "type": {
                    "type": "string",
                    "description": f"Representation type. Known core values: {', '.join(representation_names)}. Extensions may add more."
                },
                "label": {"type": "string"},
                "label-color": {"$ref": "#/$defs/color"},
                "label-size": {"type": "integer"},
                "label-font": {"type": "string"},
                "label-position": {"type": "string", "enum": ["lt", "ct", "rt", "lm", "cm", "rm", "lb", "cb", "rb"]},
                "text": {"type": "string"},
                "text-color": {"$ref": "#/$defs/color"},
                "text-size": {"type": "integer"},
                "text-font": {"type": "string"},
                "text-position": {"type": "string", "enum": ["lt", "ct", "rt", "lm", "cm", "rm", "lb", "cb", "rb"]},
                "text-format": {"type": "string"},
                "formula": {"$ref": "#/$defs/formula"},
                "icon": {"type": "string"},
                "side": {"type": "object", "additionalProperties": True}
            },
            "additionalProperties": True,
            "allOf": []
        },
        "button": {
            "type": "object",
            "required": ["index", "activation", "representation"],
            "properties": {
                "index": {"oneOf": [{"type": "integer"}, {"type": "string"}], "description": "Button index on the deck"},
                "name": {"oneOf": [{"type": "string"}, {"type": "number"}, {"type": "boolean"}], "description": "Optional friendly name"},
                "activation": {"$ref": "#/$defs/activation"},
                "representation": {"$ref": "#/$defs/representation"},
                "dataref": {"type": "string", "description": "Primary dataref for the button"},
                "set-dataref": {"type": "string"},
                "options": {"type": "string", "description": "Comma-separated options"},
                "deck": {"type": "string"},
                "formula": {"$ref": "#/$defs/formula"},
                "vibrate": {"type": "string"},
                "sound": {"type": "string"},
                "long-time": {"type": "number"},
                "initial-value": {"oneOf": [{"type": "string"}, {"type": "number"}, {"type": "boolean"}]}
            },
            "additionalProperties": True
        }
    }

    # Add activation-specific properties under activation.type
    for a in activations:
        a_name = a.name().lower()
        if a_name in ("base", "none") or not hasattr(a, "PARAMETERS"):
            continue
        a_props = build_properties(a.PARAMETERS)
        if a_props:
            merge_properties(defs["activation"]["properties"], a_props)
            defs["activation"]["allOf"].append({
                "if": {"properties": {"type": {"const": a_name}}},
                "then": {"properties": a_props}
            })

    # Add representation-specific properties under representation.type
    for r in representations:
        r_name = r.name().lower()
        if r_name == "none" or not hasattr(r, "PARAMETERS"):
            continue
        r_props = build_properties(r.PARAMETERS)
        if r_props:
            merge_properties(defs["representation"]["properties"], r_props)
            defs["representation"]["allOf"].append({
                "if": {"properties": {"type": {"const": r_name}}},
                "then": {"properties": r_props}
            })

    schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "$id": "https://raw.githubusercontent.com/dlicudi/cockpitdecks/main/schemas/cockpitdecks.schema.json",
        "title": "Cockpitdecks Configuration Schema",
        "description": "Schema for Cockpitdecks environment, deck, and page configurations.",
        "$defs": defs,
        "oneOf": [
            # Environment Config (environ.yaml)
            {
                "title": "Environment Configuration",
                "type": "object",
                "properties": {
                    k.value: {
                        "oneOf": [
                            {"type": "string"},
                            {"type": "integer"},
                            {"type": "boolean"},
                            {"type": "number"}
                        ]
                    } for k in ENVIRON_KW
                },
                "additionalProperties": True,
                "required": ["SIMULATOR_NAME"]
            },
            # Deck Config (config.yaml)
            {
                "title": "Deck Configuration",
                "type": "object",
                "properties": {
                    "aircraft": {"type": "string"},
                    "icao": {"type": "string"},
                    "model": {"type": "string"},
                    "description": {"type": "string"},
                    "decks": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "type": {"type": "string"},
                                "layout": {"type": "string"},
                                "brightness": {"type": "integer"}
                            }
                        }
                    }
                },
                "patternProperties": {
                    "^default-.*$": {"type": "string"}
                },
                "required": ["decks"]
            },
            # Page Config (page.yaml)
            {
                "title": "Page Configuration",
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "includes": {
                        "oneOf": [
                            {"type": "array", "items": {"type": "string"}},
                            {"type": "string"}
                        ],
                        "description": "List of page filenames to include (relative paths without .yaml)"
                    },
                    "buttons": {
                        "type": "array",
                        "items": {"$ref": "#/$defs/button"}
                    }
                },
                "additionalProperties": True,
                "required": ["buttons"]
            }
        ]
    }

    output_path = os.path.abspath(os.path.join(REPO_ROOT, "schemas", "cockpitdecks.schema.json"))
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    with open(output_path, "w") as f:
        json.dump(schema, f, indent=4)
    
    print(f"Schema generated successfully at {output_path}")

if __name__ == "__main__":
    main()
