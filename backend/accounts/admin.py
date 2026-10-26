from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User, UserPreference


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ['username', 'email', 'organization', 'role', 'is_staff', 'is_active']
    list_filter = ['organization', 'role', 'is_staff', 'is_active']
    fieldsets = BaseUserAdmin.fieldsets + (('LogHub', {'fields': ('organization', 'role', 'teams')}),)


admin.site.register(UserPreference)
