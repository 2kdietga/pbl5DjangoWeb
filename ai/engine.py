import io
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import mediapipe as mp

from PIL import Image
from django.conf import settings
from torchvision import models, transforms


# =========================================================
# CONFIG
# =========================================================
CLASS_NAMES = getattr(
    settings,
    "AI_CLASS_NAMES",
    ["class_interior", "class_personal", "class_phone", "class_safe"]
)

AI_DEVICE = getattr(settings, "AI_DEVICE", "cuda")
IMG_SIZE = getattr(settings, "AI_IMG_SIZE", (256, 256))


# =========================================================
# MODEL DEFINITION
# =========================================================
class HybridModel(nn.Module):
    def __init__(self, num_classes=4):
        super().__init__()

        # MobileNetV3-Large backbone
        mobilenet = models.mobilenet_v3_large(weights=None)
        self.cnn_out_features = mobilenet.classifier[0].in_features  # 960
        self.cnn_feature_extractor = mobilenet.features
        self.avgpool = nn.AdaptiveAvgPool2d(1)

        # Skeleton branch
        self.skeleton_mlp = nn.Sequential(
            nn.Linear(132, 128),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(128, 128),
            nn.ReLU()
        )
        self.skeleton_out_features = 128

        # Final classifier
        combined = self.cnn_out_features + self.skeleton_out_features  # 1088
        self.classifier = nn.Sequential(
            nn.Linear(combined, 256),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(256, num_classes)
        )

    def forward(self, image, skeleton):
        x1 = self.cnn_feature_extractor(image)  # [B, 960, H, W]
        x1 = self.avgpool(x1)                   # [B, 960, 1, 1]
        x1 = torch.flatten(x1, 1)              # [B, 960]

        x2 = self.skeleton_mlp(skeleton)       # [B, 128]

        x_cat = torch.cat((x1, x2), dim=1)     # [B, 1088]
        return self.classifier(x_cat)


# =========================================================
# GLOBALS
# =========================================================
_model = None
_device = None
_pose = None

_transform = transforms.Compose([
    transforms.Resize((256, 256)),
    transforms.CenterCrop((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize(
        mean=[0.485, 0.456, 0.406],
        std=[0.229, 0.224, 0.225]
    )
])


# =========================================================
# HELPERS
# =========================================================
def get_device():
    global _device
    if _device is None:
        use_cuda = AI_DEVICE == "cuda" and torch.cuda.is_available()
        _device = torch.device("cuda" if use_cuda else "cpu")
    return _device


def get_model():
    global _model

    if _model is None:
        model_path = str(settings.AI_MODEL_PATH)
        device = get_device()

        model = HybridModel(num_classes=len(CLASS_NAMES))

        checkpoint = torch.load(model_path, map_location=device)

        # hỗ trợ cả 2 kiểu:
        # 1) raw state_dict
        # 2) dict có key 'state_dict'
        if isinstance(checkpoint, dict) and "state_dict" in checkpoint:
            state_dict = checkpoint["state_dict"]
        else:
            state_dict = checkpoint

        model.load_state_dict(state_dict, strict=True)
        model.to(device)
        model.eval()

        _model = model

    return _model


def get_pose():
    global _pose
    if _pose is None:
        mp_pose = mp.solutions.pose
        _pose = mp_pose.Pose(
            static_image_mode=True,
            min_detection_confidence=0.5
        )
    return _pose


def _read_image_file_safely(image_file):
    """
    Đọc UploadedFile an toàn để:
    - predict xong vẫn có thể save lại file ở nơi khác
    - tránh lỗi con trỏ file
    """
    if hasattr(image_file, "seek"):
        image_file.seek(0)

    raw_bytes = image_file.read()

    if hasattr(image_file, "seek"):
        image_file.seek(0)

    image_pil = Image.open(io.BytesIO(raw_bytes)).convert("RGB")
    return image_pil


def _extract_skeleton_vector(image_pil):
    """
    Trả về:
    - skeleton_vector: np.ndarray shape (132,)
    - skeleton_detected: bool
    """
    image_np = np.array(image_pil)
    pose = get_pose()
    results = pose.process(image_np)

    if results.pose_landmarks:
        landmarks = []
        for lm in results.pose_landmarks.landmark:
            landmarks.extend([lm.x, lm.y, lm.z, lm.visibility])

        skeleton_vector = np.array(landmarks, dtype=np.float32)
        skeleton_detected = True
    else:
        skeleton_vector = np.zeros(33 * 4, dtype=np.float32)
        skeleton_detected = False

    return skeleton_vector, skeleton_detected


def _prepare_inputs(image_file):
    image_pil = _read_image_file_safely(image_file)

    image_tensor = _transform(image_pil).unsqueeze(0)  # [1, 3, 224, 224]

    skeleton_vector, skeleton_detected = _extract_skeleton_vector(image_pil)
    skeleton_tensor = torch.tensor(skeleton_vector, dtype=torch.float32).unsqueeze(0)  # [1,132]

    return image_tensor, skeleton_tensor, skeleton_detected


# =========================================================
# PUBLIC API
# =========================================================
def predict_violation(image_file):
    """
    image_file: request.FILES['image']

    return:
    {
        "pred_idx": int,
        "pred_class": str,
        "confidence": float,
        "probs": list[float],
        "skeleton_detected": bool
    }
    """
    model = get_model()
    device = get_device()

    image_tensor, skeleton_tensor, skeleton_detected = _prepare_inputs(image_file)

    image_tensor = image_tensor.to(device)
    skeleton_tensor = skeleton_tensor.to(device)

    with torch.no_grad():
        outputs = model(image_tensor, skeleton_tensor)
        probs = F.softmax(outputs, dim=1)[0]

        confidence, predicted_idx = torch.max(probs, dim=0)

    pred_idx = int(predicted_idx.item())
    confidence = float(confidence.item())
    probs_list = probs.detach().cpu().numpy().tolist()
    pred_class = CLASS_NAMES[pred_idx]

    return {
        "pred_idx": pred_idx,
        "pred_class": pred_class,
        "confidence": confidence,
        "probs": probs_list,
        "skeleton_detected": skeleton_detected,
    }