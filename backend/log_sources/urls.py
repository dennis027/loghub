from rest_framework.routers import SimpleRouter

from .views import CollectorViewSet, LogSourceViewSet

router = SimpleRouter()
router.register('log-sources', LogSourceViewSet, basename='log-source')
router.register('collectors', CollectorViewSet, basename='collector')

urlpatterns = router.urls
