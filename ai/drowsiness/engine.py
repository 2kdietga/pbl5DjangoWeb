import io
import numpy as np
import cv2
import mediapipe as mp
from PIL import Image
from django.conf import settings

from .state import get_state
from .metrics import get_ear, get_head_yaw
from .mediapipe_loader import get_landmarker


def read_image(image_file):
    image_file.seek(0)
    pil = Image.open(io.BytesIO(image_file.read())).convert("RGB")
    image_file.seek(0)
    rgb = np.array(pil)
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def smooth(prev, current, alpha=0.2):
    if prev is None:
        return float(current)
    return float((1 - alpha) * prev + alpha * current)


def process_frame(image_file, device_key):
    state = get_state(device_key)

    frame = read_image(image_file)

    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

    landmarker = get_landmarker()
    result = landmarker.detect(mp_image)

    eye_closed_ratio = float(
        getattr(settings, "DROWSINESS_EYE_CLOSED_RATIO", 0.85)
    )
    eye_closed_abs = float(
        getattr(settings, "DROWSINESS_EYE_CLOSED_ABS", 0.20)
    )
    eye_closed_frames = int(
        getattr(settings, "DROWSINESS_EYE_CLOSED_FRAMES", 6)
    )

    head_yaw_threshold = float(
        getattr(settings, "DROWSINESS_HEAD_YAW_THRESHOLD", 25)
    )
    head_turn_violation_frames = int(
        getattr(settings, "DROWSINESS_HEAD_TURN_VIOLATION_FRAMES", 15)
    )
    head_turn_decay = int(
        getattr(settings, "DROWSINESS_HEAD_TURN_DECAY", 1)
    )
    calib_frames = int(
        getattr(settings, "DROWSINESS_CALIB_FRAMES", 10)
    )

    # Không thấy mặt
    if not result.face_landmarks or not result.facial_transformation_matrixes:
        state.eye_closed_streak = 0
        state.is_sleeping = False

        state.head_turn_score = max(0, state.head_turn_score - head_turn_decay)
        if state.head_turn_score == 0:
            state.is_head_turning_violation = False
            state.head_direction = "FORWARD"

        state.last_yaw = 0.0

        return {
            "status": "EYE_OPEN",
            "should_create_violation": False,
            "eye_closed_streak": 0,
            "ear": None,
            "baseline_ear": state.baseline_ear,
            "is_calibrated": state.is_calibrated,

            "head_yaw": 0.0,
            "head_direction": state.head_direction,
            "head_turn_score": state.head_turn_score,
            "head_status": "SAFE" if state.head_turn_score == 0 else "TURNING",
            "should_create_head_turn_violation": False,
        }

    landmarks = result.face_landmarks[0]
    transformation_matrix = result.facial_transformation_matrixes[0]

    # ===== HEAD TURN =====
    yaw = get_head_yaw(transformation_matrix)
    state.last_yaw = float(yaw)

    if yaw > head_yaw_threshold:
        state.head_direction = "RIGHT"
        state.head_turn_score += 1
    elif yaw < -head_yaw_threshold:
        state.head_direction = "LEFT"
        state.head_turn_score += 1
    else:
        state.head_direction = "FORWARD"
        state.head_turn_score = max(0, state.head_turn_score - head_turn_decay)
        if state.head_turn_score == 0:
            state.is_head_turning_violation = False

    should_create_head_turn_violation = False
    if (
        state.head_turn_score >= head_turn_violation_frames
        and not state.is_head_turning_violation
    ):
        should_create_head_turn_violation = True
        state.is_head_turning_violation = True

    if state.head_turn_score == 0:
        head_status = "SAFE"
    elif state.head_turn_score < head_turn_violation_frames:
        head_status = "TURNING"
    else:
        head_status = "VIOLATION"

    # ===== EYE EAR =====
    ear = get_ear(landmarks)
    ear = smooth(state.prev_ear, ear)
    state.prev_ear = ear

    # ===== CALIBRATION =====
    if not state.is_calibrated:
        state.calib_ear_list.append(ear)

        if len(state.calib_ear_list) >= calib_frames:
            state.baseline_ear = float(np.median(state.calib_ear_list))
            state.is_calibrated = True

        return {
            "status": "CALIBRATING",
            "should_create_violation": False,
            "eye_closed_streak": state.eye_closed_streak,
            "ear": float(ear),
            "baseline_ear": state.baseline_ear,
            "is_calibrated": state.is_calibrated,

            "head_yaw": float(yaw),
            "head_direction": state.head_direction,
            "head_turn_score": state.head_turn_score,
            "head_status": head_status,
            "should_create_head_turn_violation": should_create_head_turn_violation,
        }

    # ===== EYE DETECT =====
    is_eye_closed = (
        ear < state.baseline_ear * eye_closed_ratio
        or ear < eye_closed_abs
    )

    if is_eye_closed:
        state.eye_closed_streak += 1
    else:
        state.eye_closed_streak = 0
        state.is_sleeping = False

    should_create_violation = False
    if state.eye_closed_streak >= eye_closed_frames and not state.is_sleeping:
        should_create_violation = True
        state.is_sleeping = True

    return {
        "status": "EYE_CLOSED" if is_eye_closed else "EYE_OPEN",
        "should_create_violation": should_create_violation,
        "eye_closed_streak": state.eye_closed_streak,
        "ear": float(ear),
        "baseline_ear": state.baseline_ear,
        "is_calibrated": state.is_calibrated,

        "head_yaw": float(yaw),
        "head_direction": state.head_direction,
        "head_turn_score": state.head_turn_score,
        "head_status": head_status,
        "should_create_head_turn_violation": should_create_head_turn_violation,
    }