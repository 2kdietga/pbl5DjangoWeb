import os
import logging
import re
import tempfile
import time
from pathlib import Path

from django.conf import settings
from django.utils import timezone


LIVE_FRAME_SLOT_COUNT = 3
_LIVE_FRAME_RE = re.compile(r"^live/device_(?P<device_id>\d+)_slot_(?P<slot>\d+)\.jpg$")
logger = logging.getLogger(__name__)


def _debug(message, *args):
    if getattr(settings, "LIVE_FRAME_DEBUG", False):
        logger.warning("[LIVE_FRAME] " + message, *args)


def _current_slot(device):
    match = _LIVE_FRAME_RE.match(device.latest_frame.name or "")
    if not match or int(match.group("device_id")) != device.id:
        return None
    return int(match.group("slot"))


def _candidate_slots(current_slot):
    start = 0 if current_slot is None else (current_slot + 1) % LIVE_FRAME_SLOT_COUNT
    for offset in range(LIVE_FRAME_SLOT_COUNT):
        slot = (start + offset) % LIVE_FRAME_SLOT_COUNT
        if slot != current_slot:
            yield slot


def _write_temp_frame(uploaded_file, live_dir):
    uploaded_file.seek(0)
    with tempfile.NamedTemporaryFile(
        dir=live_dir,
        prefix=".latest_frame_",
        suffix=".tmp",
        delete=False,
    ) as temp_file:
        for chunk in uploaded_file.chunks():
            temp_file.write(chunk)
        return Path(temp_file.name)


def save_latest_frame(device, uploaded_file):
    """
    Publish a complete JPEG into one of three rotating files.

    The currently published slot is never overwritten. This lets an in-flight
    live-view response finish reading its file while the next frame is written.
    """
    started_at = time.perf_counter()
    live_dir = Path(settings.MEDIA_ROOT) / "live"
    live_dir.mkdir(parents=True, exist_ok=True)
    current_slot = _current_slot(device)

    temp_started_at = time.perf_counter()
    temp_path = _write_temp_frame(uploaded_file, live_dir)
    temp_ms = (time.perf_counter() - temp_started_at) * 1000
    _debug(
        "publish-start device=%s current_slot=%s bytes=%s temp_ms=%.2f",
        device.id,
        current_slot,
        temp_path.stat().st_size,
        temp_ms,
    )

    try:
        for slot in _candidate_slots(current_slot):
            relative_path = f"live/device_{device.id}_slot_{slot}.jpg"
            target_path = Path(settings.MEDIA_ROOT) / relative_path
            replace_started_at = time.perf_counter()
            try:
                os.replace(temp_path, target_path)
            except PermissionError:
                # Windows can temporarily lock a slot still being served.
                _debug(
                    "slot-locked device=%s slot=%s replace_ms=%.2f",
                    device.id,
                    slot,
                    (time.perf_counter() - replace_started_at) * 1000,
                )
                continue

            replace_ms = (time.perf_counter() - replace_started_at) * 1000
            device.latest_frame.name = relative_path
            device.latest_frame_at = timezone.now()

            db_started_at = time.perf_counter()
            device.save(update_fields=["latest_frame", "latest_frame_at"])
            db_ms = (time.perf_counter() - db_started_at) * 1000
            _debug(
                "publish-done device=%s slot=%s replace_ms=%.2f db_ms=%.2f total_ms=%.2f",
                device.id,
                slot,
                replace_ms,
                db_ms,
                (time.perf_counter() - started_at) * 1000,
            )
            return

        raise PermissionError(f"No writable live-frame slot for device {device.id}")
    finally:
        if temp_path.exists():
            temp_path.unlink()
