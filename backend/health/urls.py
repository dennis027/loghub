from django.urls import path

from .views import InfrastructureView, MetricsRangeView, OverviewView, PlatformHealthView, ServicesView

urlpatterns = [
    path('health/', PlatformHealthView.as_view(), name='platform-health'),
    path('stats/overview/', OverviewView.as_view(), name='overview'),
    path('services/', ServicesView.as_view(), name='services'),
    path('infrastructure/', InfrastructureView.as_view(), name='infrastructure'),
    path('metrics/query_range/', MetricsRangeView.as_view(), name='metrics-range'),
]
