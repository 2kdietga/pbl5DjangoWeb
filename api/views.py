import os
import secrets
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.core.files.storage import default_storage
from django.utils import timezone
from devices.models import Device


@csrf_exempt
def upload_frame(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "POST only"}, status=405)

    # 1) lấy token từ header (khuyên dùng)
    token = request.headers.get("X-DEVICE-TOKEN") or request.META.get("HTTP_X_DEVICE_TOKEN")
    if not token:
        return JsonResponse({"ok": False, "error": "Missing X-DEVICE-TOKEN"}, status=401)

    # 2) tìm device
    device = Device.objects.filter(token=token, is_active=True).first()
    if not device:
        return JsonResponse({"ok": False, "error": "Invalid device token"}, status=401)

    # 3) lấy file ảnh
    f = request.FILES.get("image")
    if not f:
        return JsonResponse({"ok": False, "error": "Missing file field 'image'"}, status=400)

    # 4) update last_seen
    device.last_seen = timezone.now()
    device.save(update_fields=["last_seen"])

    # 5) lưu ảnh vào media/frames/<device_id>/
    ext = os.path.splitext(f.name)[1].lower()
    if ext not in [".jpg", ".jpeg", ".png", ".webp", ".bmp"]:
        ext = ".jpg"

    filename = f"{timezone.now().strftime('%Y%m%d_%H%M%S')}_{secrets.token_hex(4)}{ext}"
    path = f"frames/device_{device.id}/{filename}"
    saved_path = default_storage.save(path, f)

    return JsonResponse({
        "ok": True,
        "device": {"id": device.id, "name": device.name},
        "saved": saved_path,
        "vehicle": device.vehicle.license_plate if device.vehicle else None,
    })
