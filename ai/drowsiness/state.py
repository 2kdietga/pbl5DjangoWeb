from dataclasses import dataclass, field


@dataclass
class EyeState:
    is_calibrated: bool = False
    calib_ear_list: list = field(default_factory=list)
    baseline_ear: float = 0.25

    prev_ear: float | None = None
    eye_closed_streak: int = 0


STATE_STORE = {}


def get_state(device_key):
    if device_key not in STATE_STORE:
        STATE_STORE[device_key] = EyeState()
    return STATE_STORE[device_key]