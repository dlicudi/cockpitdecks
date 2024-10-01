"""
Button action and activation abstraction
"""

from .activation import Activation, ACTIVATION_VALUE
from .activation import LoadPage, Reload, Inspect, Stop
from .activation import Push, OnOff, UpDown
from .activation import BeginEndPress
from .activation import Encoder, EncoderPush, EncoderOnOff, EncoderValue, EncoderToggle
from .activation import EncoderValueExtended
from .activation import Slider, Swipe

from cockpitdecks import DECK_ACTIONS


def get_activations_for(action: DECK_ACTIONS, all_activations) -> list:
    return [a for a in all_activations.values() if action in a.get_required_capability()]
