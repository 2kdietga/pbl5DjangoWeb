import os
from django.core.files.base import ContentFile
from django.utils import timezone

def save_latest_frame(device, uploaded_file):
    """
    Chỉ giữ 1 frame mới nhất cho mỗi device.
    Mỗi lần upload mới sẽ ghi đè file cũ.
    """
    ext = os.path.splitext(uploaded_file.name)[1].lower() or ".jpg"
    filename = f"device_{device.id}{ext}"

    # nếu đã có ảnh cũ thì xóa trước
    if device.latest_frame:
        device.latest_frame.delete(save=False)

    # ghi file mới
    device.latest_frame.save(
        filename,
        ContentFile(uploaded_file.read()),
        save=False
    )
    device.latest_frame_at = timezone.now()
    device.save(update_fields=["latest_frame", "latest_frame_at"])