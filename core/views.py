from django.http import HttpResponse
from django.shortcuts import render

def test_view(request):
    return render(request, "auth/login.html")
