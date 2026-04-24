import os
import uuid
import cv2
import subprocess
from django.conf import settings


def export_frames_to_mp4(frames, fps=5, subdir="violations/videos", target_width=640):
    if not frames:
        return None

    media_root = settings.MEDIA_ROOT
    output_dir = os.path.join(media_root, subdir)
    os.makedirs(output_dir, exist_ok=True)

    video_id = uuid.uuid4().hex

    temp_filename = f"{video_id}_temp.mp4"
    final_filename = f"{video_id}.mp4"

    temp_abs_path = os.path.join(output_dir, temp_filename)
    final_abs_path = os.path.join(output_dir, final_filename)

    rel_path = os.path.join(subdir, final_filename).replace("\\", "/")

    first = frames[0]
    h, w = first.shape[:2]

    if w > target_width:
        new_w = target_width
        new_h = int(h * target_width / w)
    else:
        new_w = w
        new_h = h

    # H.264/web video thường thích kích thước chẵn
    if new_w % 2 != 0:
        new_w -= 1
    if new_h % 2 != 0:
        new_h -= 1

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(temp_abs_path, fourcc, fps, (new_w, new_h))

    try:
        for frame in frames:
            if frame is None:
                continue

            if frame.shape[1] != new_w or frame.shape[0] != new_h:
                frame = cv2.resize(frame, (new_w, new_h))

            writer.write(frame)
    finally:
        writer.release()

    # Convert sang MP4 chuẩn web: H.264 + yuv420p
    cmd = [
        "ffmpeg",
        "-y",
        "-i", temp_abs_path,
        "-vcodec", "libx264",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        final_abs_path,
    ]

    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        if os.path.exists(temp_abs_path):
            os.remove(temp_abs_path)

        return rel_path

    except Exception as e:
        print("FFmpeg convert error:", e)

        # fallback: nếu ffmpeg lỗi thì trả file temp
        fallback_rel_path = os.path.join(subdir, temp_filename).replace("\\", "/")
        return fallback_rel_path