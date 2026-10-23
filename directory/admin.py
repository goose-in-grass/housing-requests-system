from django.contrib import admin

from .models import Category, House, Section


@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    search_fields = ["name"]


@admin.register(House)
class HouseAdmin(admin.ModelAdmin):
    list_display = ["address", "section", "is_active"]
    list_filter = ["section", "is_active"]
    search_fields = ["address"]


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "norm_hours", "emergency_norm_hours", "is_active"]
    list_filter = ["is_active"]
