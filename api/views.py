from datetime import timedelta

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
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        # 1) Validate token -> device
        token = request.headers.get("X-DEVICE-TOKEN")
        if not token:
            return Response(
                {"detail": "Missing X-DEVICE-TOKEN"},
                status=status.HTTP_401_UNAUTHORIZED
            )

        device = Device.objects.filter(
            token=token,
            is_active=True
        ).select_related("vehicle").first()

        if not device:
            return Response(
                {"detail": "Invalid device token"},
                status=status.HTTP_401_UNAUTHORIZED
            )

        device.last_seen = timezone.now()
        device.save(update_fields=["last_seen"])

        # 2) Validate image
        image = request.FILES.get("image")
        if not image:
            return Response(
                {"detail": "Missing image (field name must be 'image')"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 3) card_uid
        card_uid = (request.data.get("card_uid") or "").strip()
        if not card_uid:
            return Response(
                {"detail": "Missing card_uid"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 4) vehicle
        vehicle = device.vehicle
        if vehicle is None:
            license_plate = (request.data.get("license_plate") or "").strip()
            model_name = (request.data.get("model") or "Unknown").strip()
            reg_date = request.data.get("registration_date")

            if not license_plate:
                return Response(
                    {
                        "detail": "Device has no vehicle. Send license_plate or assign vehicle to device."
                    },
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

        # 5) reporter
        reporter = Account.objects.filter(card_uid=card_uid).first()
        if not reporter:
            return Response(
                {"detail": f"No Account found with card_uid={card_uid}"},
                status=status.HTTP_404_NOT_FOUND
            )

        # 6) AI predict
        try:
            result = predict_violation(image)
        except Exception as e:
            return Response(
                {"detail": f"AI prediction error: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        pred_idx = result["pred_idx"]
        pred_class = result["pred_class"]
        confidence = result["confidence"]
        probs = result["probs"]
        skeleton_detected = result.get("skeleton_detected", False)

        threshold = float(getattr(settings, "AI_CONF_THRESHOLD", 0.70))
        cooldown_seconds = int(getattr(settings, "AI_VIOLATION_COOLDOWN_SECONDS", 10))

        class_to_category = getattr(
            settings,
            "AI_CLASS_TO_CATEGORY",
            {
                "class_interior": "Interior",
                "class_personal": "Personal",
                "class_phone": "Phone",
                "class_safe": "Safe",
            }
        )

        cat_name = class_to_category.get(pred_class, pred_class)
        is_safe = (pred_class == "class_safe")
        is_violation = (not is_safe) and (confidence >= threshold)

        # 7) Không vi phạm
        if not is_violation:
            return Response({
                "ok": True,
                "violation_detected": False,
                "created": False,
                "pred_idx": pred_idx,
                "pred_class": pred_class,
                "confidence": confidence,
                "category_guess": cat_name,
                "probs": probs,
                "skeleton_detected": skeleton_detected,
                "vehicle": vehicle.license_plate,
                "reporter": f"{reporter.first_name} {reporter.last_name}".strip() or reporter.username,
                "card_uid": reporter.card_uid,
            }, status=status.HTTP_200_OK)

        # 8) Có vi phạm -> lấy/create category
        category, _ = Category.objects.get_or_create(name=cat_name)

        # 9) Kiểm tra cooldown
        now = timezone.now()
        cooldown_from = now - timedelta(seconds=cooldown_seconds)

        recent_violation = Violation.objects.filter(
            reporter=reporter,
            vehicle=vehicle,
            category=category,
            reported_at__gte=cooldown_from
        ).order_by("-reported_at").first()

        if recent_violation:
            seconds_since_last = (now - recent_violation.reported_at).total_seconds()

            return Response({
                "ok": True,
                "violation_detected": True,
                "created": False,
                "cooldown_active": True,
                "cooldown_seconds": cooldown_seconds,
                "seconds_since_last": round(seconds_since_last, 2),
                "last_violation_id": recent_violation.id,
                "pred_idx": pred_idx,
                "pred_class": pred_class,
                "confidence": confidence,
                "category": category.name,
                "probs": probs,
                "skeleton_detected": skeleton_detected,
                "vehicle": vehicle.license_plate,
                "reporter": reporter.username,
                "card_uid": reporter.card_uid,
            }, status=status.HTTP_200_OK)

        # 10) Hết cooldown -> tạo violation mới
        violation = Violation.objects.create(
            category=category,
            reporter=reporter,
            vehicle=vehicle,
            title="Violation Report",
            description=(
                f"AI detected {pred_class} -> {cat_name} "
                f"(confidence={confidence:.3f}) | "
                f"card_uid={card_uid} | "
                f"skeleton_detected={skeleton_detected}"
            ),
        )

        violation.image.save(image.name, image, save=True)

        return Response({
            "ok": True,
            "violation_detected": True,
            "created": True,
            "cooldown_active": False,
            "violation_id": violation.id,
            "pred_idx": pred_idx,
            "pred_class": pred_class,
            "confidence": confidence,
            "category": category.name,
            "probs": probs,
            "skeleton_detected": skeleton_detected,
            "vehicle": vehicle.license_plate,
            "reporter": reporter.username,
            "card_uid": reporter.card_uid,
        }, status=status.HTTP_201_CREATED)