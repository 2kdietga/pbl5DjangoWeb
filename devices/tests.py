import shutil
import tempfile
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from .models import Device
from .services import save_latest_frame


class LatestFrameTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.settings_override = override_settings(MEDIA_ROOT=self.media_root)
        self.settings_override.enable()
        self.device = Device.objects.create(name="Camera", token="token")

    def tearDown(self):
        self.settings_override.disable()
        shutil.rmtree(self.media_root)

    def save_frame(self, content):
        image = SimpleUploadedFile("camera.jpg", content, content_type="image/jpeg")
        save_latest_frame(self.device, image)
        self.device.refresh_from_db()

    def test_latest_frame_rotates_through_three_slots(self):
        for content in (b"frame-0", b"frame-1", b"frame-2", b"frame-3"):
            self.save_frame(content)

        self.assertEqual(
            self.device.latest_frame.name,
            f"live/device_{self.device.id}_slot_0.jpg",
        )
        self.assertEqual(
            sorted(path.name for path in (Path(self.media_root) / "live").glob("*.jpg")),
            [
                f"device_{self.device.id}_slot_0.jpg",
                f"device_{self.device.id}_slot_1.jpg",
                f"device_{self.device.id}_slot_2.jpg",
            ],
        )
        self.assertEqual(Path(self.device.latest_frame.path).read_bytes(), b"frame-3")

    def test_latest_frame_view_disables_browser_cache(self):
        self.save_frame(b"jpeg-bytes")

        response = self.client.get(f"/devices/{self.device.id}/frame/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertEqual(b"".join(response.streaming_content), b"jpeg-bytes")

    def test_open_live_response_keeps_old_frame_while_new_frame_is_published(self):
        self.save_frame(b"old-frame")
        old_slot = self.device.latest_frame.name
        response = self.client.get(f"/devices/{self.device.id}/frame/")

        self.save_frame(b"new-frame")

        self.assertNotEqual(self.device.latest_frame.name, old_slot)
        self.assertEqual(b"".join(response.streaming_content), b"old-frame")
        self.assertEqual(Path(self.device.latest_frame.path).read_bytes(), b"new-frame")
