import os
import threading
from dataclasses import dataclass

import cv2
import mediapipe as mp
import numpy as np
from django.conf import settings
from mediapipe.tasks import python
from mediapipe.tasks.python import vision


_LANDMARKER_LOCK = threading.RLock()
_LANDMARKER = None


@dataclass
class MediaPipeResult:
    landmarks: np.ndarray
    transformation_matrix: np.ndarray | None
    face_box: tuple[int, int, int, int]


def get_model_path():
    default_path = os.path.join(settings.BASE_DIR, "ai", "models", "face_landmarker.task")
    return str(getattr(settings, "DROWSINESS_MEDIAPIPE_MODEL_PATH", default_path))


def build_landmarker():
    model_path = get_model_path()
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"MediaPipe face landmarker model not found: {model_path}")

    options = vision.FaceLandmarkerOptions(
        base_options=python.BaseOptions(model_asset_path=model_path),
        running_mode=vision.RunningMode.IMAGE,
        num_faces=1,
        min_face_detection_confidence=float(
            getattr(settings, "DROWSINESS_MEDIAPIPE_MIN_FACE_DETECTION_CONFIDENCE", 0.5)
        ),
        min_face_presence_confidence=float(
            getattr(settings, "DROWSINESS_MEDIAPIPE_MIN_FACE_PRESENCE_CONFIDENCE", 0.5)
        ),
        min_tracking_confidence=float(
            getattr(settings, "DROWSINESS_MEDIAPIPE_MIN_TRACKING_CONFIDENCE", 0.5)
        ),
        output_facial_transformation_matrixes=True,
    )
    return vision.FaceLandmarker.create_from_options(options)


def get_landmarker():
    global _LANDMARKER

    if _LANDMARKER is None:
        with _LANDMARKER_LOCK:
            if _LANDMARKER is None:
                _LANDMARKER = build_landmarker()

    return _LANDMARKER


def detect_landmarks(frame_bgr):
    frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)

    # A shared Tasks landmarker is used to avoid rebuilding its graph per frame.
    with _LANDMARKER_LOCK:
        result = get_landmarker().detect(mp_image)

    if not result.face_landmarks:
        return None

    height, width = frame_bgr.shape[:2]
    landmarks = np.asarray(
        [(point.x * width, point.y * height) for point in result.face_landmarks[0]],
        dtype=np.float32,
    )
    x_min, y_min = np.floor(np.min(landmarks, axis=0)).astype(int)
    x_max, y_max = np.ceil(np.max(landmarks, axis=0)).astype(int)

    transformation_matrix = None
    if result.facial_transformation_matrixes:
        transformation_matrix = np.asarray(
            result.facial_transformation_matrixes[0], dtype=np.float32
        )

    return MediaPipeResult(
        landmarks=landmarks,
        transformation_matrix=transformation_matrix,
        face_box=(x_min, y_min, x_max - x_min, y_max - y_min),
    )
