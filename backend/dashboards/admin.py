from django.contrib import admin

from .models import Dashboard


@admin.register(Dashboard)
class DashboardAdmin(admin.ModelAdmin):
    list_display = ['name', 'organization', 'folder', 'category', 'is_template', 'updated_at']
    list_filter = ['organization', 'category', 'is_template']
    search_fields = ['name', 'description']
