import numpy as np
import tensorflow as tf
from django.conf import settings
from PIL import Image

_model = None

MODEL_PATH = settings.AI_MODEL_PATH
IMG_SIZE = settings.AI_IMG_SIZE

# map index -> class name (nếu bạn dùng c0..c9)
CLASS_NAMES = [f"c{i}" for i in range(10)]

def get_model():
    """Load model 1 lần, dùng lại nhiều request."""
    global _model
    if _model is None:
        model_path = str(settings.AI_MODEL_PATH)
        _model = tf.keras.models.load_model(model_path)
    return _model

def predict_violation(image_file):
    """
    image_file: file-like (request.FILES['image'])
    return: pred_idx, confidence, probs(list)
    """
    img_size = getattr(settings, "AI_IMG_SIZE", (256, 256))

    img = Image.open(image_file).convert("RGB")
    img = img.resize(img_size)

    x = np.asarray(img, dtype=np.float32) / 255.0
    x = np.expand_dims(x, axis=0)  # (1, H, W, 3)

    probs = get_model().predict(x, verbose=0)[0]
    pred_idx = int(np.argmax(probs))
    confidence = float(probs[pred_idx])

    return pred_idx, confidence, probs.tolist()