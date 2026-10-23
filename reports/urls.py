from django.urls import path

from . import views

app_name = "reports"
urlpatterns = [
    path("", views.index, name="index"),
    path("<str:code>/", views.show, name="show"),
]
