import numpy as np
from django.test import SimpleTestCase

from .drowsiness.metrics import (
    LEFT_EYE_MEDIAPIPE,
    RIGHT_EYE_MEDIAPIPE,
    get_ear_mediapipe,
    get_head_yaw,
)
from .phone.engine import get_phone_class_index


class MediaPipeMetricsTests(SimpleTestCase):
    def test_ear_uses_mediapipe_eye_landmarks(self):
        landmarks = np.zeros((478, 2), dtype=np.float32)
        eye = np.asarray(
            [(0, 0), (1, 1), (3, 1), (4, 0), (3, -1), (1, -1)],
            dtype=np.float32,
        )
        landmarks[LEFT_EYE_MEDIAPIPE] = eye
        landmarks[RIGHT_EYE_MEDIAPIPE] = eye + (10, 0)

        self.assertAlmostEqual(get_ear_mediapipe(landmarks), 0.5)

    def test_yaw_defaults_to_zero_without_transformation_matrix(self):
        self.assertEqual(get_head_yaw(None), 0.0)

    def test_yaw_is_zero_for_identity_transformation_matrix(self):
        self.assertAlmostEqual(get_head_yaw(np.eye(4, dtype=np.float32)), 0.0)


class PhoneMetricsTests(SimpleTestCase):
    def test_phone_class_index_follows_configured_labels(self):
        self.assertEqual(get_phone_class_index(["Safe", "Phone"]), 1)
