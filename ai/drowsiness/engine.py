import io
import numpy as np
import cv2
import mediapipe as mp
from PIL import Image

from .state import get_state
from .metrics import get_ear
from .mediapipe_loader import get_landmarker
from django.conf import settings


def read_image(image_file):
    image_file.seek(0)
    pil = Image.open(io.BytesIO(image_file.read())).convert("RGB")
    image_file.seek(0)
    rgb = np.array(pil)
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def smooth(prev, current, alpha=0.2):
    if prev is None:
        return current
    return (1 - alpha) * prev + alpha * current


def process_frame(image_file, device_key):
    state = get_state(device_key)

    frame = read_image(image_file)

    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

    landmarker = get_landmarker()
    result = landmarker.detect(mp_image)

    # ❌ không thấy mặt
    if not result.face_landmarks:
        state.eye_closed_streak = 0
        state.is_sleeping = False
        return {
            "status": "NO_FACE",
            "should_create_violation": False
        }

    landmarks = result.face_landmarks[0]

    # ===== TÍNH EAR =====
    ear = get_ear(landmarks)
    ear = smooth(state.prev_ear, ear)
    state.prev_ear = ear

    # ===== CALIBRATION =====
    if not state.is_calibrated:
        state.calib_ear_list.append(ear)

        if len(state.calib_ear_list) >= 10:
            state.baseline_ear = float(np.median(state.calib_ear_list))
            state.is_calibrated = True

        return {
            "status": "CALIBRATING",
            "should_create_violation": False,
            "ear": ear
        }

    # ===== DETECT =====
    is_eye_closed = (
        ear < state.baseline_ear * getattr(settings, "DROWSINESS_EYE_CLOSED_RATIO", 0.85)
        or ear < getattr(settings, "DROWSINESS_EYE_CLOSED_ABS", 0.20)
    )

    if is_eye_closed:
        state.eye_closed_streak += 1
    else:
        state.eye_closed_streak = 0

    # ===== VIOLATION =====
    should_create_violation = state.eye_closed_streak >= getattr(settings, "DROWSINESS_EYE_CLOSED_FRAMES", 6)

    return {
        "status": "EYE_CLOSED" if is_eye_closed else "EYE_OPEN",
        "should_create_violation": should_create_violation,
        "eye_closed_streak": state.eye_closed_streak,
        "ear": float(ear),
        "baseline_ear": state.baseline_ear
    }