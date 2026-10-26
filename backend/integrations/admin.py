from django.contrib import admin

from .models import Integration


@admin.register(Integration)
class IntegrationAdmin(admin.ModelAdmin):
    list_display = ['name', 'provider', 'enabled', 'status', 'version', 'last_checked']
    readonly_fields = ['status', 'status_message', 'version', 'latency_ms', 'details', 'last_checked']
