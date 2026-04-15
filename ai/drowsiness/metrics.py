import cv2
import numpy as np


def calculate_distance(p1, p2):
    return np.linalg.norm(np.array(p1) - np.array(p2))


def get_ear(landmarks):
    def ear_single_eye(indices):
        p = [[landmarks[i].x, landmarks[i].y] for i in indices]
        v1 = calculate_distance(p[1], p[5])
        v2 = calculate_distance(p[2], p[4])
        h = calculate_distance(p[0], p[3])
        return (v1 + v2) / (2.0 * h) if h != 0 else 0.0

    left_ear = ear_single_eye([33, 160, 158, 133, 153, 144])
    right_ear = ear_single_eye([362, 385, 387, 263, 373, 380])
    return (left_ear + right_ear) / 2.0


def get_mar(landmarks):
    v = calculate_distance(
        [landmarks[13].x, landmarks[13].y],
        [landmarks[14].x, landmarks[14].y],
    )
    h = calculate_distance(
        [landmarks[78].x, landmarks[78].y],
        [landmarks[308].x, landmarks[308].y],
    )
    return v / h if h != 0 else 0.0


def get_head_pitch(transformation_matrix):
    rotation_matrix = transformation_matrix[:3, :3]
    euler_angles, _, _, _, _, _ = cv2.RQDecomp3x3(rotation_matrix)
    return float(euler_angles[0])


def get_brightness_bgr(frame_bgr):
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    return float(np.mean(gray))