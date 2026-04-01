import os
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, render
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
    return render(request, "live_view.html", {"device": device})