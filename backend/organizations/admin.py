from django.contrib import admin

from .models import Environment, Organization, Team

admin.site.register(Organization)
admin.site.register(Team)
admin.site.register(Environment)
