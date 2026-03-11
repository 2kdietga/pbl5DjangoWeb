from django.utils import timezone
from django.conf import settings

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from accounts.models import Account
from categories.models import Category
from vehicles.models import Vehicle
from violations.models import Violation
from devices.models import Device

from ai.engine import predict_violation


class UploadAndDetectAPIView(APIView):
    """
    ESP32-CAM gửi:
      - Header: X-DEVICE-TOKEN
      - Form-data: image=@file.jpg
      - (optional) license_plate=... nếu device chưa gắn vehicle
    """

    authentication_classes = []
    permission_classes = []

    def post(self, request):
        # 1) Validate token -> device
        token = request.headers.get("X-DEVICE-TOKEN")
        if not token:
            return Response({"detail": "Missing X-DEVICE-TOKEN"}, status=status.HTTP_401_UNAUTHORIZED)

        device = Device.objects.filter(token=token, is_active=True).select_related("vehicle").first()
        if not device:
            return Response({"detail": "Invalid device token"}, status=status.HTTP_401_UNAUTHORIZED)

        device.last_seen = timezone.now()
        device.save(update_fields=["last_seen"])

        # 2) Validate image
        image = request.FILES.get("image")
        if not image:
            return Response({"detail": "Missing image (field name must be 'image')"}, status=status.HTTP_400_BAD_REQUEST)

        # 3) Get vehicle (from device or from request)
        vehicle = device.vehicle
        if vehicle is None:
            license_plate = (request.data.get("license_plate") or "").strip()
            model_name = (request.data.get("model") or "Unknown").strip()
            reg_date = request.data.get("registration_date")  # "YYYY-MM-DD" (optional)

            if not license_plate:
                return Response(
                    {"detail": "Device has no vehicle. Send license_plate or assign vehicle to device."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            vehicle, _ = Vehicle.objects.get_or_create(
                license_plate=license_plate,
                defaults={
                    "model": model_name,
                    "registration_date": reg_date or timezone.now().date(),
                },
            )
            device.vehicle = vehicle
            device.save(update_fields=["vehicle"])

        # 4) AI predict
        pred_idx, confidence, probs = predict_violation(image)

        threshold = float(getattr(settings, "AI_CONF_THRESHOLD", 0.70))
        class_to_category = getattr(settings, "AI_CLASS_TO_CATEGORY", {pred_idx: f"C{pred_idx}"})
        cat_name = class_to_category.get(pred_idx, f"C{pred_idx}")

        is_violation = confidence >= threshold

        # 5) Nếu không vi phạm -> trả luôn, không lưu ảnh/DB
        if not is_violation or class_to_category.get(pred_idx) == "C0":
            return Response({
                "ok": True,
                "violation": False,
                "pred_class": pred_idx,
                "confidence": confidence,
                "category_guess": cat_name,
                "probs": probs,
                "vehicle": vehicle.license_plate,
            }, status=status.HTTP_200_OK)

        # 6) Vi phạm -> tạo Violation với reporter mặc định id=1
        reporter = Account.objects.filter(id=1).first()
        if not reporter:
            return Response({"detail": "Default reporter Account id=1 not found"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        category, _ = Category.objects.get_or_create(name=cat_name)

        violation = Violation.objects.create(
            category=category,
            reporter=reporter,
            vehicle=vehicle,
            title="Violation Report",
            description=f"AI detected {cat_name} (confidence={confidence:.3f})",
        )

        # chỉ lưu ảnh khi vi phạm
        violation.image.save(image.name, image, save=True)

        return Response({
            "ok": True,
            "violation": True,
            "violation_id": violation.id,
            "pred_class": pred_idx,
            "confidence": confidence,
            "category": category.name,
            "vehicle": vehicle.license_plate,
        }, status=status.HTTP_201_CREATED)
