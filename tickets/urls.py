from django.urls import path

app_name = "tickets"
urlpatterns = [path("<int:pk>/", lambda request, pk: None, name="detail")]
