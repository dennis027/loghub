from django.contrib import admin

from .models import Collector, LogSource


@admin.register(LogSource)
class LogSourceAdmin(admin.ModelAdmin):
    list_display = ['name', 'organization', 'source_type', 'environment', 'status', 'last_seen', 'log_route']
    list_filter = ['organization', 'source_type', 'status', 'log_route']
    exclude = ['token_hash']
    readonly_fields = ['token_prefix', 'status', 'last_seen', 'events_24h']


admin.site.register(Collector)
