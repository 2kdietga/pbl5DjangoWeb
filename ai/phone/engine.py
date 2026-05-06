import io
import threading

import cv2
import numpy as np
import torch
from PIL import Image
from django.conf import settings

from .model import PhoneCNNGRU
from .state import get_state


_MODEL_LOCK = threading.Lock()
_MODEL = None
_DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
_IMAGENET_MEAN = torch.tensor([0.485, 0.456, 0.406]).view(3, 1, 1)
_IMAGENET_STD = torch.tensor([0.229, 0.224, 0.225]).view(3, 1, 1)


def read_frame(image_file):
    image_file.seek(0)
    pil = Image.open(io.BytesIO(image_file.read())).convert("RGB")
    image_file.seek(0)
    return np.array(pil)


def preprocess_frame(frame_rgb):
    image_size = int(getattr(settings, "PHONE_IMAGE_SIZE", 112))
    resized = cv2.resize(frame_rgb, (image_size, image_size), interpolation=cv2.INTER_AREA)
    tensor = torch.from_numpy(resized).float().permute(2, 0, 1) / 255.0
    return (tensor - _IMAGENET_MEAN) / _IMAGENET_STD


def get_model_path():
    default_path = settings.BASE_DIR / "ai" / "models" / "model_ep26_val0.9268.pth"
    return str(getattr(settings, "PHONE_MODEL_PATH", default_path))


def load_phone_model():
    model = PhoneCNNGRU(num_classes=2)
    checkpoint = torch.load(get_model_path(), map_location=_DEVICE)
    if isinstance(checkpoint, dict) and any(
        key in checkpoint for key in ("state_dict", "model_state_dict", "model")
    ):
        state_dict = (
            checkpoint.get("state_dict")
            or checkpoint.get("model_state_dict")
            or checkpoint.get("model")
        )
    else:
        state_dict = checkpoint

    if any(key.startswith("module.") for key in state_dict.keys()):
        state_dict = {key.replace("module.", "", 1): value for key, value in state_dict.items()}

    model.load_state_dict(state_dict)
    model.to(_DEVICE)
    model.eval()
    return model


def get_phone_model():
    global _MODEL

    if _MODEL is None:
        with _MODEL_LOCK:
            if _MODEL is None:
                _MODEL = load_phone_model()

    return _MODEL


def process_frame(image_file, device_key):
    state = get_state(device_key)
    frame_rgb = read_frame(image_file)
    state.frames.append(frame_rgb)

    sequence_length = int(getattr(settings, "PHONE_SEQUENCE_LENGTH", 12))
    labels = getattr(settings, "PHONE_CLASS_LABELS", ["Safe", "Phone"])
    threshold = float(getattr(settings, "PHONE_CONFIDENCE_THRESHOLD", 0.7))

    if len(state.frames) < sequence_length:
        return {
            "status": "COLLECTING",
            "label": state.last_label,
            "confidence": state.last_confidence,
            "phone_probability": state.last_phone_probability,
            "frames_collected": len(state.frames),
            "sequence_length": sequence_length,
            "should_create_violation": False,
            "video_frames": [],
        }

    sequence = list(state.frames)[-sequence_length:]
    tensors = [preprocess_frame(frame) for frame in sequence]
    batch = torch.stack(tensors).unsqueeze(0).to(_DEVICE)

    with torch.no_grad():
        logits = get_phone_model()(batch)
        probabilities = torch.softmax(logits, dim=1)[0].detach().cpu()

    class_index = int(torch.argmax(probabilities).item())
    label = labels[class_index] if class_index < len(labels) else str(class_index)
    confidence = float(probabilities[class_index].item())
    phone_probability = float(probabilities[1].item()) if len(probabilities) > 1 else 0.0

    state.last_label = label
    state.last_confidence = confidence
    state.last_phone_probability = phone_probability

    is_phone = label.lower() == "phone" and phone_probability >= threshold
    should_create_violation = is_phone and not state.is_phone_active
    status = "PHONE" if is_phone else "SAFE"

    if is_phone:
        state.is_phone_active = True
    else:
        state.is_phone_active = False

    state.last_status = status

    video_frames = []
    if should_create_violation:
        video_frames = [cv2.cvtColor(frame, cv2.COLOR_RGB2BGR) for frame in sequence]

    return {
        "status": status,
        "label": label,
        "confidence": confidence,
        "phone_probability": phone_probability,
        "frames_collected": len(state.frames),
        "sequence_length": sequence_length,
        "should_create_violation": should_create_violation,
        "video_frames": video_frames,
    }
