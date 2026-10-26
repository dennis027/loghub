from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import (
    FieldValuesView,
    LiveTailView,
    LogAggregateView,
    LogEventView,
    LogExportView,
    LogSearchView,
    SavedSearchViewSet,
)

router = SimpleRouter()
router.register('saved-searches', SavedSearchViewSet, basename='saved-search')

urlpatterns = [
    path('logs/search/', LogSearchView.as_view(), name='log-search'),
    path('logs/aggregate/', LogAggregateView.as_view(), name='log-aggregate'),
    path('logs/export/', LogExportView.as_view(), name='log-export'),
    path('logs/live/', LiveTailView.as_view(), name='log-live'),
    path('logs/fields/<str:field>/values/', FieldValuesView.as_view(), name='log-field-values'),
    path('logs/events/<str:event_id>/', LogEventView.as_view(), name='log-event'),
] + router.urls
