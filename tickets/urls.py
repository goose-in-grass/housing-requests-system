from django.urls import path

from . import views

app_name = "tickets"
urlpatterns = [
    path("my/", views.my_tickets, name="my"),
    path("queue/", views.queue, name="queue"),
    path("tasks/", views.tasks, name="tasks"),
    path("create/", views.create, name="create"),
    path("<int:pk>/", views.detail, name="detail"),
    path("<int:pk>/<str:action>/", views.action, name="action"),
    path("photo/<int:pk>/", views.photo, name="photo"),
]
