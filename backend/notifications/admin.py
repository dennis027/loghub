from django.contrib import admin

from .models import NotificationChannel, NotificationDelivery


@admin.register(NotificationChannel)
class NotificationChannelAdmin(admin.ModelAdmin):
    list_display = ['name', 'organization', 'channel_type', 'enabled', 'send_resolved']
    list_filter = ['organization', 'channel_type', 'enabled']
    exclude = ['secret']


@admin.register(NotificationDelivery)
class NotificationDeliveryAdmin(admin.ModelAdmin):
    list_display = ['channel', 'kind', 'status', 'attempts', 'created_at', 'sent_at']
    list_filter = ['status', 'kind']
    readonly_fields = [f.name for f in NotificationDelivery._meta.fields]
