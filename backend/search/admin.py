from django.contrib import admin

from .models import SavedSearch


@admin.register(SavedSearch)
class SavedSearchAdmin(admin.ModelAdmin):
    list_display = ['name', 'organization', 'provider', 'created_by', 'is_shared', 'updated_at']
    list_filter = ['organization', 'provider', 'is_shared']
    search_fields = ['name', 'query']
