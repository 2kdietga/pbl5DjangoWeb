import os
import logging
import time

from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.conf import settings

from ai.drowsiness.state import STATE_STORE
from ai.phone.state import PHONE_STATE_STORE
from .models import Device


logger = logging.getLogger(__name__)


def device_latest_frame(request, id):
    started_at = time.perf_counter()
    device = get_object_or_404(Device, id=id)

    if not device.latest_frame:
        raise Http404("No frame available")

    frame_path = device.latest_frame.path
    if not os.path.exists(frame_path):
        raise Http404("Frame file not found")

    file_started_at = time.perf_counter()
    frame_file = open(frame_path, "rb")
    if getattr(settings, "LIVE_FRAME_DEBUG", False):
        logger.warning(
            "[LIVE_FRAME] serve device=%s file=%s bytes=%s query_ms=%.2f open_ms=%.2f total_ms=%.2f",
            device.id,
            device.latest_frame.name,
            os.path.getsize(frame_path),
            (file_started_at - started_at) * 1000,
            (time.perf_counter() - file_started_at) * 1000,
            (time.perf_counter() - started_at) * 1000,
        )

    response = FileResponse(frame_file, content_type="image/jpeg")
    response["Cache-Control"] = "no-store"
    return response


def device_live_view(request, id):
    device = get_object_or_404(Device, id=id)

    # AJAX: trả JSON trạng thái realtime
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        state = STATE_STORE.get(device.token)
        phone_state = PHONE_STATE_STORE.get(device.token)

        head_turn_threshold = int(
            getattr(settings, "DROWSINESS_HEAD_TURN_VIOLATION_FRAMES", 15)
        )

        if not state:
            return JsonResponse({
                "eye_closed_streak": 0,
                "head_direction": "FORWARD",
                "head_turn_score": 0,
                "head_yaw": 0.0,
                "head_status": "SAFE",
                "phone_status": getattr(phone_state, "last_status", "UNKNOWN"),
                "phone_label": getattr(phone_state, "last_label", "UNKNOWN"),
                "phone_confidence": getattr(phone_state, "last_confidence", 0.0),
                "phone_probability": getattr(phone_state, "last_phone_probability", 0.0),
                "phone_frames_collected": len(getattr(phone_state, "frames", [])) if phone_state else 0,
            })

        head_turn_score = getattr(state, "head_turn_score", 0)
        head_direction = getattr(state, "head_direction", "FORWARD")
        head_yaw = getattr(state, "last_yaw", 0.0)

        if head_turn_score == 0:
            head_status = "SAFE"
        elif head_turn_score < head_turn_threshold:
            head_status = "TURNING"
        else:
            head_status = "VIOLATION"

        return JsonResponse({
            "eye_closed_streak": getattr(state, "eye_closed_streak", 0),
            "head_direction": head_direction,
            "head_turn_score": head_turn_score,
            "head_yaw": head_yaw,
            "head_status": head_status,
            "phone_status": getattr(phone_state, "last_status", "UNKNOWN"),
            "phone_label": getattr(phone_state, "last_label", "UNKNOWN"),
            "phone_confidence": getattr(phone_state, "last_confidence", 0.0),
            "phone_probability": getattr(phone_state, "last_phone_probability", 0.0),
            "phone_frames_collected": len(getattr(phone_state, "frames", [])) if phone_state else 0,
        })

    # Render HTML
    return render(
        request,
        "live_view.html",
        {
            "device": device,
            "DROWSINESS_EYE_CLOSED_FRAMES": getattr(
                settings, "DROWSINESS_EYE_CLOSED_FRAMES", 6
            ),
        },
    )
