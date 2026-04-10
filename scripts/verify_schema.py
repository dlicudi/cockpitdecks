import yaml
import json
from jsonschema import validate, ValidationError
import os

SCHEMA_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "schemas", "cockpitdecks.schema.json"))
CONFIG_TO_TEST = "/Users/duanelicudi/GitHub/cockpitdecks-configs/decks/aerobask-robin-dr401/deckconfig/loupedecklive1/switches.yaml"

with open(SCHEMA_PATH, "r") as f:
    schema = json.load(f)

with open(CONFIG_TO_TEST, "r") as f:
    config = yaml.safe_load(f)

try:
    validate(instance=config, schema=schema)
    print("Validation successful!")
except ValidationError as e:
    print(f"Validation failed: {e.message}")
    print(f"Path: {list(e.path)}")
