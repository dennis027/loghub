from rest_framework.routers import SimpleRouter

from .views import RetentionPolicyViewSet

router = SimpleRouter()
router.register('retention-policies', RetentionPolicyViewSet, basename='retention-policy')
urlpatterns = router.urls
