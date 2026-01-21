from . import views
from django.urls import path

urlpatterns = [
    path('list/', views.violation_list, name='violation_list'),
    path('detail/<int:violation_id>/', views.violation_detail, name='violation_detail'),
]
