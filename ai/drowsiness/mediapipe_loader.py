import os
import threading
import urllib.request

import mediapipe as mp
from django.conf import settings


_MODEL_LOCK = threading.Lock()
_LANDMARKER = None


def get_model_path():
    default_path = os.path.join(settings.BASE_DIR, "ai", "models", "face_landmarker.task")
    model_path = getattr(settings, "DROWSINESS_MODEL_PATH", default_path)
    return str(model_path)


def download_model_if_needed(model_path=None):
    model_path = str(model_path or get_model_path())

    model_dir = os.path.dirname(model_path)
    if model_dir:
        os.makedirs(model_dir, exist_ok=True)

    if not os.path.exists(model_path):
        url = (
            "https://storage.googleapis.com/mediapipe-models/"
            "face_landmarker/face_landmarker/float16/1/face_landmarker.task"
        )
        urllib.request.urlretrieve(url, model_path)

    return model_path


def build_landmarker():
    model_path = str(download_model_if_needed())

    BaseOptions = mp.tasks.BaseOptions
    FaceLandmarker = mp.tasks.vision.FaceLandmarker
    FaceLandmarkerOptions = mp.tasks.vision.FaceLandmarkerOptions
    VisionRunningMode = mp.tasks.vision.RunningMode

    options = FaceLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=model_path),
        running_mode=VisionRunningMode.IMAGE,
        output_facial_transformation_matrixes=True,
        num_faces=1,
        min_face_detection_confidence=0.6,
        min_tracking_confidence=0.6,
    )

    return FaceLandmarker.create_from_options(options)


def get_landmarker():
    global _LANDMARKER

    if _LANDMARKER is None:
        with _MODEL_LOCK:
            if _LANDMARKER is None:
                _LANDMARKER = build_landmarker()

    return _LANDMARKER