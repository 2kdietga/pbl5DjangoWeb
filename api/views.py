from datetime import timedelta

from django.utils import timezone
from django.conf import settings

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from accounts.models import Account
from categories.models import Category
from devices.services import save_latest_frame
from vehicles.models import Vehicle
from violations.models import Violation
from devices.models import Device

from ai.drowsiness.engine import process_frame


class UploadAndDetectAPIView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        try:
            image = request.FILES.get("image")
        except Exception as e:
            return Response({
                "detail": "Upload interrupted",
                "error": str(e)
            }, status=400)
        # ===== 1. DEVICE =====
        token = request.headers.get("X-DEVICE-TOKEN")
        if not token:
            return Response({"detail": "Missing X-DEVICE-TOKEN"}, status=401)

        device = Device.objects.filter(token=token, is_active=True)\
            .select_related("vehicle").first()

        if not device:
            return Response({"detail": "Invalid device token"}, status=401)

        device.last_seen = timezone.now()
        device.save(update_fields=["last_seen"])

        # ===== 2. IMAGE =====
        # image = request.FILES.get("image")
        # if not image:
        #     return Response({"detail": "Missing image"}, status=400)

        save_latest_frame(device, image)
        image.seek(0)

        # ===== 3. DRIVER =====
        card_uid = (request.data.get("card_uid") or "").strip()
        if not card_uid:
            return Response({"detail": "Missing card_uid"}, status=400)

        reporter = Account.objects.filter(card_uid=card_uid).first()
        if not reporter:
            return Response({"detail": "Driver not found"}, status=404)

        # ===== 4. VEHICLE =====
        vehicle = device.vehicle
        if vehicle is None:
            return Response({"detail": "Device has no vehicle"}, status=400)

        # ===== 5. AI =====
        try:
            result = process_frame(image, device.token)
        except Exception as e:
            return Response({"detail": f"AI error: {str(e)}"}, status=500)

        image.seek(0)

        status_eye = result.get("status")
        should_create_violation = result.get("should_create_violation", False)
        streak = result.get("eye_closed_streak", 0)

        # ===== 6. CHƯA VI PHẠM =====
        if not should_create_violation:
            return Response({
                "ok": True,
                "status": status_eye,
                "eye_closed_streak": streak,
                "violation": False,
                "vehicle": vehicle.license_plate,
                "driver": reporter.username,
            }, status=200)

        # ===== 7. VI PHẠM =====
        category_name = "Drowsiness"
        category, _ = Category.objects.get_or_create(name=category_name)

        cooldown = int(getattr(settings, "DROWSINESS_VIOLATION_COOLDOWN_SECONDS", 20))
        now = timezone.now()

        recent = Violation.objects.filter(
            reporter=reporter,
            vehicle=vehicle,
            category=category,
            reported_at__gte=now - timedelta(seconds=cooldown)
        ).first()

        if recent:
            return Response({
                "ok": True,
                "status": status_eye,
                "violation": True,
                "created": False,
                "cooldown": True,
                "eye_closed_streak": streak
            }, status=200)

        # ===== 8. CREATE =====
        violation = Violation.objects.create(
            category=category,
            reporter=reporter,
            vehicle=vehicle,
            title="Drowsiness",
            description=f"Eye closed too long ({streak} frames)"
        )

        violation.image.save(image.name, image, save=True)

        return Response({
            "ok": True,
            "status": status_eye,
            "violation": True,
            "created": True,
            "violation_id": violation.id,
            "eye_closed_streak": streak
        }, status=201)