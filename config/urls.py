from django.contrib import admin
from django.urls import include, path

from accounts import views as account_views

urlpatterns = [
    path("", account_views.home, name="home"),
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("tickets/", include("tickets.urls")),
    path("reports/", include("reports.urls")),
]
