from django.contrib import admin

from .models import RetentionPolicy


@admin.register(RetentionPolicy)
class RetentionPolicyAdmin(admin.ModelAdmin):
    list_display = ['name', 'target', 'rollover_days', 'delete_after_days', 'sync_status', 'last_synced_at']
    readonly_fields = ['sync_status', 'sync_message', 'last_synced_at']
