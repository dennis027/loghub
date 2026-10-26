from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import IntegrationViewSet, PipelineStatusView

router = SimpleRouter()
router.register('integrations', IntegrationViewSet, basename='integration')

urlpatterns = [path('pipelines/status/', PipelineStatusView.as_view(), name='pipeline-status')] + router.urls
