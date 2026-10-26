from rest_framework.routers import SimpleRouter

from .views import AlertEventViewSet, AlertRuleViewSet

router = SimpleRouter()
router.register('alert-rules', AlertRuleViewSet, basename='alert-rule')
router.register('alert-events', AlertEventViewSet, basename='alert-event')

urlpatterns = router.urls
