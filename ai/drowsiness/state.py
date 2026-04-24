from collections import deque
from dataclasses import dataclass, field
from django.conf import settings


def get_buffer_size():
    fps = int(getattr(settings, "DROWSINESS_FPS", 5))
    seconds = int(getattr(settings, "DROWSINESS_BUFFER_SECONDS", 5))
    return max(1, fps * seconds)


@dataclass
class EyeState:
    # ===== calibration / ear =====
    is_calibrated: bool = False
    calib_ear_list: list = field(default_factory=list)
    baseline_ear: float = 0.25
    prev_ear: float | None = None

    # ===== drowsiness =====
    eye_closed_streak: int = 0
    is_sleeping: bool = False
    drowsiness_frames: deque = field(default_factory=lambda: deque(maxlen=get_buffer_size()))

    # ===== head turn =====
    head_turn_score: int = 0
    is_head_turning_violation: bool = False
    head_direction: str = "FORWARD"
    last_yaw: float = 0.0
    head_turn_frames: deque = field(default_factory=lambda: deque(maxlen=get_buffer_size()))


STATE_STORE = {}


def get_state(device_key):
    if device_key not in STATE_STORE:
        STATE_STORE[device_key] = EyeState()
    return STATE_STORE[device_key]


def clear_state(device_key):
    if device_key in STATE_STORE:
        del STATE_STORE[device_key]