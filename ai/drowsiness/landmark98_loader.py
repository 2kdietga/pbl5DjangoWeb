import os
import threading
from dataclasses import dataclass

import cv2
import numpy as np
from django.conf import settings


INPUT_SIZE = 256
DEFAULT_FACE_MARGIN = 0.25

_MODEL_LOCK = threading.Lock()
_MODEL = None
_DEVICE = None
_FACE_CASCADE = None
_TORCH_IMPORTS = None


@dataclass
class Landmark98Result:
    landmarks: np.ndarray
    face_box: tuple[int, int, int, int]


def get_torch_imports():
    global _TORCH_IMPORTS

    if _TORCH_IMPORTS is None:
        try:
            import torch
            import torch.nn as nn
            import torchvision.models as models
        except ImportError as exc:
            raise RuntimeError(
                "PyTorch/torchvision is required for landmark_98_best.pth. "
                "Install the project's requirements before using drowsiness detection."
            ) from exc
        _TORCH_IMPORTS = torch, nn, models

    return _TORCH_IMPORTS


def build_landmark_net(num_landmarks=98):
    torch, nn, models = get_torch_imports()

    class HeatmapLandmarkNet(nn.Module):
        def __init__(self):
            super().__init__()
            base = models.mobilenet_v2(weights=None)
            self.features = base.features

            self.deconv_layers = nn.Sequential(
                nn.ConvTranspose2d(1280, 256, 4, 2, 1, bias=False),
                nn.BatchNorm2d(256),
                nn.ReLU(inplace=True),
                nn.ConvTranspose2d(256, 256, 4, 2, 1, bias=False),
                nn.BatchNorm2d(256),
                nn.ReLU(inplace=True),
                nn.ConvTranspose2d(256, 256, 4, 2, 1, bias=False),
                nn.BatchNorm2d(256),
                nn.ReLU(inplace=True),
                nn.Dropout2d(p=0.2),
            )

            self.head = nn.Conv2d(256, num_landmarks, 1, 1, 0)

        def forward(self, x):
            x = self.features(x)
            x = self.deconv_layers(x)
            out = self.head(x)
            return torch.sigmoid(out)

    return HeatmapLandmarkNet()


def get_model_path():
    default_path = os.path.join(settings.BASE_DIR, "ai", "models", "landmark_98_best.pth")
    return str(getattr(settings, "DROWSINESS_LANDMARK98_MODEL_PATH", default_path))


def get_device():
    torch, _, _ = get_torch_imports()
    device_name = getattr(settings, "DROWSINESS_LANDMARK98_DEVICE", "auto")
    if device_name == "auto":
        return "cuda" if torch.cuda.is_available() else "cpu"
    return str(device_name)


def build_model():
    torch, _, _ = get_torch_imports()
    model_path = get_model_path()
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"Landmark model not found: {model_path}")

    device = get_device()
    model = build_landmark_net(num_landmarks=98).to(device)
    checkpoint = torch.load(model_path, map_location=device, weights_only=False)
    state_dict = checkpoint.get("model_state_dict", checkpoint)
    model.load_state_dict(state_dict)
    model.eval()
    return model, device


def get_model():
    global _MODEL, _DEVICE

    if _MODEL is None:
        with _MODEL_LOCK:
            if _MODEL is None:
                _MODEL, _DEVICE = build_model()

    return _MODEL, _DEVICE


def get_face_cascade():
    global _FACE_CASCADE

    if _FACE_CASCADE is None:
        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        _FACE_CASCADE = cv2.CascadeClassifier(cascade_path)
        if _FACE_CASCADE.empty():
            raise RuntimeError(f"Cannot load OpenCV face cascade: {cascade_path}")

    return _FACE_CASCADE


def detect_largest_face(frame_bgr):
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    min_size = int(getattr(settings, "DROWSINESS_FACE_MIN_SIZE", 40))
    scale_factor = float(getattr(settings, "DROWSINESS_FACE_SCALE_FACTOR", 1.1))
    min_neighbors = int(getattr(settings, "DROWSINESS_FACE_MIN_NEIGHBORS", 5))

    faces = get_face_cascade().detectMultiScale(
        gray,
        scaleFactor=scale_factor,
        minNeighbors=min_neighbors,
        minSize=(min_size, min_size),
    )
    if len(faces) == 0:
        return None

    x, y, w, h = max(faces, key=lambda box: box[2] * box[3])
    return int(x), int(y), int(w), int(h)


def get_landmarks_from_heatmaps(heatmaps):
    torch, _, _ = get_torch_imports()
    b, c, h, w = heatmaps.shape
    heatmaps_flat = heatmaps.view(b, c, -1)
    max_idx = torch.argmax(heatmaps_flat, dim=2)

    preds_x = (max_idx % w).float()
    preds_y = (max_idx // w).float()

    points = torch.stack([preds_x, preds_y], dim=2)[0].detach().cpu().numpy()
    return points, w, h


def crop_face_for_inference(img, x, y, w, h, margin=DEFAULT_FACE_MARGIN):
    img_h, img_w = img.shape[:2]

    cx = x + w / 2.0
    cy = y + h / 2.0
    side = max(w, h) * (1.0 + margin * 2.0)

    nx1 = int(cx - side / 2)
    ny1 = int(cy - side / 2)
    nx2 = nx1 + int(side)
    ny2 = ny1 + int(side)

    pad_left = max(0, -nx1)
    pad_top = max(0, -ny1)
    pad_right = max(0, nx2 - img_w)
    pad_bottom = max(0, ny2 - img_h)

    if pad_left > 0 or pad_top > 0 or pad_right > 0 or pad_bottom > 0:
        img_pad = cv2.copyMakeBorder(
            img,
            pad_top,
            pad_bottom,
            pad_left,
            pad_right,
            cv2.BORDER_CONSTANT,
            value=[0, 0, 0],
        )
        crop = img_pad[ny1 + pad_top : ny2 + pad_top, nx1 + pad_left : nx2 + pad_left]
    else:
        crop = img[ny1:ny2, nx1:nx2]

    return crop, nx1, ny1, side


def preprocess_face(face_crop):
    input_img = cv2.resize(face_crop, (INPUT_SIZE, INPUT_SIZE))
    input_img = cv2.cvtColor(input_img, cv2.COLOR_BGR2RGB)
    input_img = input_img.astype(np.float32) / 255.0
    input_img = (input_img - 0.5) / 0.5
    input_img = np.transpose(input_img, (2, 0, 1))
    return input_img


def detect_landmarks(frame_bgr):
    face_box = detect_largest_face(frame_bgr)
    if face_box is None:
        return None

    x, y, w, h = face_box
    margin = float(getattr(settings, "DROWSINESS_FACE_CROP_MARGIN", DEFAULT_FACE_MARGIN))
    face_crop, nx1, ny1, side = crop_face_for_inference(frame_bgr, x, y, w, h, margin)
    if face_crop.size == 0:
        return None

    torch, _, _ = get_torch_imports()
    model, device = get_model()
    input_img = preprocess_face(face_crop)
    tensor_img = torch.tensor(input_img, dtype=torch.float32).unsqueeze(0).to(device)

    with torch.no_grad():
        heatmaps = model(tensor_img)

    preds, heatmap_w, heatmap_h = get_landmarks_from_heatmaps(heatmaps)
    scale_x = side / float(heatmap_w)
    scale_y = side / float(heatmap_h)

    landmarks = np.empty_like(preds, dtype=np.float32)
    landmarks[:, 0] = nx1 + preds[:, 0] * scale_x
    landmarks[:, 1] = ny1 + preds[:, 1] * scale_y

    return Landmark98Result(landmarks=landmarks, face_box=face_box)
