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
        "button": {
            "type": "object",
            "required": ["index"],
            "properties": {
                "index": {"oneOf": [{"type": "integer"}, {"type": "string"}], "description": "Button index on the deck"},
                "name": {"oneOf": [{"type": "string"}, {"type": "number"}, {"type": "boolean"}], "description": "Optional friendly name"},
                "activation": {
                    "type": "string",
                    "description": f"Activation type. Known core values: {', '.join(activation_names)}. Extensions may add more."
                },
                "representation": {
                    "type": "string",
                    "description": f"Representation type. Known core values: {', '.join(representation_names)}. Extensions may add more."
                },
                "dataref": {"type": "string", "description": "Primary dataref for the button"},
                "formula": {"$ref": "#/$defs/formula"},
                "options": {"type": "string", "description": "Comma-separated options"},
                "label": {"type": "string"},
                "label-color": {"$ref": "#/$defs/color"},
                "label-size": {"type": "integer"},
                "label-font": {"type": "string"},
                "label-position": {"type": "string", "enum": ["lt", "ct", "rt", "lm", "cm", "rm", "lb", "cb", "rb"]},
                "icon": {"type": "string"},
                "commands": {
                    "type": "object",
                    "description": "Named commands for this button's activation events",
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
                "set-dataref": {"type": "string"},
                "vibrate": {"type": "string"},
                "sound": {"type": "string"},
                "long-time": {"type": "number"},
                "initial-value": {"oneOf": [{"type": "string"}, {"type": "number"}, {"type": "boolean"}]}
            },
            "patternProperties": {
                "^representation-.*$": {"type": "object"}
            },
            "allOf": []
        }
    }

    # Top-level button properties that are fully defined — skip these from activation allOf conditions
    # to avoid conflicting constraints (e.g., activation PARAMETERS define commands.press as string,
    # but top-level allows arrays for macros).
    SKIP_IN_ACTIVATION_THEN = {"commands", "positions", "behaviour"}

    # Add activation-specific properties to Button
    for a in activations:
        a_name = a.name().lower()
        if a_name in ("base", "none") or not hasattr(a, "PARAMETERS"):
            continue
        a_props = build_properties({k: v for k, v in a.PARAMETERS.items() if k not in SKIP_IN_ACTIVATION_THEN})
        if a_props:
            defs["button"]["allOf"].append({
                "if": {"properties": {"activation": {"const": a_name}}},
                "then": {"properties": a_props}
            })

    # Add representation-specific properties to Button
    for r in representations:
        r_name = r.name().lower()
        if r_name == "none" or not hasattr(r, "PARAMETERS"):
            continue
        params = r.PARAMETERS

        # Detect the "-items" pattern: a "-"-prefixed key in PARAMETERS signals that
        # this representation is an ARRAY at the button level. The "-key"'s list value
        # defines the item schema.
        array_signal_key = next((k for k in params if k.startswith("-")), None)
        if array_signal_key is not None:
            # Build item properties from the list sub-schema of the array signal key
            item_spec = params[array_signal_key]
            if isinstance(item_spec, dict) and item_spec.get("type") == "sub":
                item_params = item_spec.get("list", {})
                if isinstance(item_params, dict):
                    item_props = build_properties(item_params)
                    base_prop = {"type": "array", "items": {"type": "object", "properties": item_props}}
                else:
                    base_prop = {"type": "array", "items": {"type": "string"}}
            elif isinstance(item_spec, dict):
                # Non-sub: the item schema is the type of the signal key itself
                item_schema = build_properties({array_signal_key: item_spec}).get(array_signal_key, {})
                base_prop = {"type": "array", "items": {"oneOf": [item_schema, {"type": "object"}]}}
            else:
                base_prop = {"type": "array", "items": {}}
        # When the representation's PARAMETERS has a single key equal to the representation name,
        # the value at button level IS that property's schema directly (no extra nesting).
        elif list(params.keys()) == [r_name]:
            r_props = build_properties(params)
            base_prop = r_props[r_name]
        elif r_name in ["icon", "text", "label", "icon-color", "ftg"]:
            # These can appear as simple scalar values OR as representation config objects
            r_props = build_properties(params)
            base_prop = {
                "oneOf": [
                    {"type": "string"},
                    {"type": "boolean"},
                    {"type": "number"},
                    {"type": "object", "properties": r_props}
                ]
            }
        else:
            r_props = build_properties(params)
            base_prop = {"type": "object", "properties": r_props}

        defs["button"]["properties"][r_name] = base_prop

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
