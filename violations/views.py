from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils.dateparse import parse_date

from .models import Violation
from categories.models import Category  # hoặc import đúng chỗ Category của bạn

@login_required
def violation_list(request):
    # Chỉ lấy vi phạm của user đang đăng nhập
    qs = Violation.objects.filter(reporter=request.user).select_related(
        "category", "vehicle", "reporter"
    ).order_by("-reported_at")

    # Lấy dữ liệu filter từ querystring
    from_date_str = request.GET.get("from_date", "").strip()
    to_date_str = request.GET.get("to_date", "").strip()
    selected_category = request.GET.get("category", "").strip()

    # Filter theo ngày (reported_at là DateTimeField)
    from_date = parse_date(from_date_str) if from_date_str else None
    to_date = parse_date(to_date_str) if to_date_str else None

    if from_date:
        qs = qs.filter(reported_at__date__gte=from_date)
    if to_date:
        qs = qs.filter(reported_at__date__lte=to_date)

    # Filter theo category
    if selected_category:
        qs = qs.filter(category_id=selected_category)

    context = {
        "violations": qs,
        "links": Category.objects.all().order_by("name"),  # danh sách category cho dropdown
        "from_date": from_date_str,
        "to_date": to_date_str,
        "selected_category": selected_category,
    }
    return render(request, "violation_list.html", context)

@login_required
def violation_detail(request, violation_id):
    violation = Violation.objects.select_related("category", "vehicle").get(id=violation_id)
    # Đánh dấu vi phạm là đã xem
    violation.viewed = True
    violation.save()
    context = {
        "violation": violation,
    }
    return render(request, "violation_detail.html", context)
