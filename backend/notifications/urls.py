from rest_framework.routers import SimpleRouter

from .views import NotificationChannelViewSet, NotificationDeliveryViewSet

router = SimpleRouter()
router.register('notification-channels', NotificationChannelViewSet, basename='notification-channel')
router.register('notification-deliveries', NotificationDeliveryViewSet, basename='notification-delivery')

urlpatterns = router.urls
