import cv2
import numpy as np


LEFT_EYE_98 = [60, 61, 62, 63, 64, 65, 66, 67]
RIGHT_EYE_98 = [68, 69, 70, 71, 72, 73, 74, 75]
LEFT_PUPIL_98 = 96
RIGHT_PUPIL_98 = 97
NOSE_TIP_98 = 54
LEFT_EYE_MEDIAPIPE = [33, 160, 158, 133, 153, 144]
RIGHT_EYE_MEDIAPIPE = [362, 385, 387, 263, 373, 380]


def calculate_distance(p1, p2):
    return np.linalg.norm(np.array(p1) - np.array(p2))


def get_ear(landmarks):
    points = np.asarray(landmarks, dtype=np.float32)

    def ear_single_eye(indices):
        p = points[indices]
        v1 = calculate_distance(p[1], p[7])
        v2 = calculate_distance(p[2], p[6])
        v3 = calculate_distance(p[3], p[5])
        h = calculate_distance(p[0], p[4])
        return (v1 + v2 + v3) / (3.0 * h) if h != 0 else 0.0

    left_ear = ear_single_eye(LEFT_EYE_98)
    right_ear = ear_single_eye(RIGHT_EYE_98)
    return (left_ear + right_ear) / 2.0


def get_mar(landmarks):
    points = np.asarray(landmarks, dtype=np.float32)
    v = calculate_distance(points[88], points[92])
    h = calculate_distance(points[76], points[82])
    return v / h if h != 0 else 0.0


def get_head_pitch(transformation_matrix):
    rotation_matrix = transformation_matrix[:3, :3]
    euler_angles, _, _, _, _, _ = cv2.RQDecomp3x3(rotation_matrix)
    return float(euler_angles[0])


def get_head_yaw(transformation_matrix):
    if transformation_matrix is None:
        return 0.0
    rotation_matrix = transformation_matrix[:3, :3]
    euler_angles, _, _, _, _, _ = cv2.RQDecomp3x3(rotation_matrix)
    return float(euler_angles[1])


def get_brightness_bgr(frame_bgr):
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    return float(np.mean(gray))


def get_head_yaw_98(landmarks):
    points = np.asarray(landmarks, dtype=np.float32)
    if len(points) > RIGHT_PUPIL_98:
        left_eye_center = points[LEFT_PUPIL_98]
        right_eye_center = points[RIGHT_PUPIL_98]
    else:
        left_eye_center = np.mean(points[LEFT_EYE_98], axis=0)
        right_eye_center = np.mean(points[RIGHT_EYE_98], axis=0)

    nose_tip = points[NOSE_TIP_98]
    eye_center = (left_eye_center + right_eye_center) / 2.0
    interocular = calculate_distance(left_eye_center, right_eye_center)
    if interocular == 0:
        return 0.0

    return float(((nose_tip[0] - eye_center[0]) / interocular) * 45.0)


def get_ear_mediapipe(landmarks):
    points = np.asarray(landmarks, dtype=np.float32)

    def ear_single_eye(indices):
        p = points[indices]
        vertical = calculate_distance(p[1], p[5]) + calculate_distance(p[2], p[4])
        horizontal = 2.0 * calculate_distance(p[0], p[3])
        return vertical / horizontal if horizontal != 0 else 0.0

    left_ear = ear_single_eye(LEFT_EYE_MEDIAPIPE)
    right_ear = ear_single_eye(RIGHT_EYE_MEDIAPIPE)
    return (left_ear + right_ear) / 2.0
