from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import ChangePasswordView, CurrentUserView, LoginView, LogoutView, PreferencesView

urlpatterns = [
    path('login/', LoginView.as_view(), name='login'),
    path('refresh/', TokenRefreshView.as_view(), name='token-refresh'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('me/', CurrentUserView.as_view(), name='current-user'),
    path('me/preferences/', PreferencesView.as_view(), name='preferences'),
    path('me/password/', ChangePasswordView.as_view(), name='change-password'),
]
