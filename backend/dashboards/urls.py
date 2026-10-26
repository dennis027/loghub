from rest_framework.routers import SimpleRouter

from .views import DashboardViewSet

router = SimpleRouter()
router.register('dashboards', DashboardViewSet, basename='dashboard')
urlpatterns = router.urls
