from django.http import HttpResponse
from django.shortcuts import render

def test_view(request):
    return render(request, "violations_detail.html")
