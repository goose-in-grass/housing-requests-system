from django.contrib import admin

from .models import Employee, Resident


@admin.register(Resident)
class ResidentAdmin(admin.ModelAdmin):
    list_display = ["full_name", "phone", "house", "apartment", "user"]
    list_filter = ["house"]
    search_fields = ["full_name", "phone", "email"]


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ["full_name", "role", "section", "is_active"]
    list_filter = ["role", "section", "is_active"]
    search_fields = ["full_name", "phone"]
