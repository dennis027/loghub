from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.routers import DefaultRouter

from accounts.views import UserViewSet
from audit.views import AuditEventViewSet
from health import views as health_views
from log_sources.ingest import IngestView
from organizations.views import CurrentOrganizationView, EnvironmentViewSet, TeamViewSet

router = DefaultRouter()
router.register('users', UserViewSet, basename='user')
router.register('teams', TeamViewSet, basename='team')
router.register('environments', EnvironmentViewSet, basename='environment')
router.register('audit-events', AuditEventViewSet, basename='audit-event')

api = [
    path('auth/', include('accounts.urls')),
    path('organization/', CurrentOrganizationView.as_view(), name='current-organization'),
    path('ingest/', IngestView.as_view(), name='ingest'),
    path('', include('search.urls')),
    path('', include('log_sources.urls')),
    path('', include('integrations.urls')),
    path('', include('alerts.urls')),
    path('', include('notifications.urls')),
    path('', include('retention.urls')),
    path('', include('dashboards.urls')),
    path('', include('reports.urls')),
    path('', include('health.urls')),
    path('schema/', SpectacularAPIView.as_view(), name='schema'),
    path('docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
] + router.urls

urlpatterns = [
    path('django-admin/', admin.site.urls),
    path('health/live', health_views.live, name='health-live'),
    path('health/ready', health_views.ready, name='health-ready'),
    path('api/', include(api)),
]
