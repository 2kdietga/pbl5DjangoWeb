from django.shortcuts import render
from categories.models import Category
from .models import Violation

from django.shortcuts import render
from django.utils.dateparse import parse_date
from .models import Violation, Category

def violation_list(request):
    qs = Violation.objects.select_related("category", "vehicle").all().order_by("-reported_at")
    categories = Category.objects.all().order_by("name")

    from_date = request.GET.get("from_date", "")
    to_date = request.GET.get("to_date", "")
    category_id = request.GET.get("category", "")

    if from_date:
        d = parse_date(from_date)
        if d:
            qs = qs.filter(reported_at__date__gte=d)

    if to_date:
        d = parse_date(to_date)
        if d:
            qs = qs.filter(reported_at__date__lte=d)

    if category_id:
        qs = qs.filter(category_id=category_id)

    context = {
        "violations": qs,
        "categories": categories,
        # để giữ lại trạng thái filter trên UI
        "from_date": from_date,
        "to_date": to_date,
        "selected_category": category_id,
    }
    return render(request, "violation_list.html", context)