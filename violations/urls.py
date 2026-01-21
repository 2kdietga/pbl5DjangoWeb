from . import views
from django.urls import path

urlpatterns = [
    path('list/', views.violation_list, name='violation_list'),
]
