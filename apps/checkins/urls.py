from django.urls import path

from . import views

urlpatterns = [
    path("checkins/", views.MyCheckInsView.as_view(), name="my-checkins"),
    path("checkins/scan/", views.ScanView.as_view(), name="checkin-scan"),
]
