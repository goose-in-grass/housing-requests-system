from django.contrib import admin

from .models import Photo, StatusHistory, Ticket


class HistoryInline(admin.TabularInline):
    model = StatusHistory
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ["number", "category", "house", "status", "priority", "master", "deadline_at"]
    list_filter = ["status", "priority", "category"]
    search_fields = ["number", "resident__full_name"]
    inlines = [HistoryInline]


admin.site.register(Photo)
