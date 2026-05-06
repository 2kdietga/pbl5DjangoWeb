from collections import deque
from dataclasses import dataclass, field

from django.conf import settings


def get_sequence_length():
    return int(getattr(settings, "PHONE_SEQUENCE_LENGTH", 12))


@dataclass
class PhoneState:
    frames: deque = field(default_factory=lambda: deque(maxlen=get_sequence_length()))
    last_status: str = "UNKNOWN"
    last_label: str = "UNKNOWN"
    last_confidence: float = 0.0
    last_phone_probability: float = 0.0
    is_phone_active: bool = False


PHONE_STATE_STORE = {}


def get_state(device_key):
    if device_key not in PHONE_STATE_STORE:
        PHONE_STATE_STORE[device_key] = PhoneState()
    return PHONE_STATE_STORE[device_key]


def clear_state(device_key):
    if device_key in PHONE_STATE_STORE:
        del PHONE_STATE_STORE[device_key]
