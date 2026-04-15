import os
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, render

from ai.drowsiness.state import STATE_STORE
from .models import Device

def device_latest_frame(request, id):
    device = get_object_or_404(Device, id=id)

    if not device.latest_frame:
        raise Http404("No frame available")

    frame_path = device.latest_frame.path
    if not os.path.exists(frame_path):
        raise Http404("Frame file not found")

    return FileResponse(open(frame_path, "rb"), content_type="image/jpeg")

def device_live_view(request, id):
    device = get_object_or_404(Device, id=id)

    # nếu gọi bằng AJAX
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        state = STATE_STORE.get(device.token)

        if not state:
            return JsonResponse({
                "streak": 0
            })

        return JsonResponse({
            "streak": state.eye_closed_streak
        })

    # nếu load page
    return render(request, "live_view.html", {"device": device})