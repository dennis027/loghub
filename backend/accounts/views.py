import contextlib

from django.contrib.auth import get_user_model
from rest_framework import generics, permissions, status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from audit.services import record_audit
from core.permissions import ROLE_ADMIN, RoleRequired
from core.tenancy import OrganizationScopedMixin

from .models import UserPreference
from .serializers import ChangePasswordSerializer, CurrentUserSerializer, UserPreferenceSerializer, UserSerializer

User = get_user_model()


class LoginView(TokenObtainPairView):
    """Exchange username/password for a JWT pair. Successful and failed attempts are audited."""

    permission_classes = [permissions.AllowAny]
    throttle_scope = 'login'
    serializer_class = TokenObtainPairSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        username = str(request.data.get('username', ''))[:150]
        try:
            serializer.is_valid(raise_exception=True)
        except Exception:
            user = User.objects.filter(username=username).first()
            record_audit(
                request,
                'login_failed',
                target_type='user',
                target_repr=username,
                changes={'username': username},
                organization=user.organization if user else None,
            )
            raise
        user = serializer.user
        if not user.organization_id:
            return Response(
                {'error': {'code': 'no_organization', 'message': 'Account has no organization.', 'details': None}},
                status=status.HTTP_403_FORBIDDEN,
            )
        record_audit(request, 'login', target_type='user', target_id=user.pk, target_repr=user.username, user=user)
        return Response(serializer.validated_data, status=status.HTTP_200_OK)


class LogoutView(APIView):
    def post(self, request):
        with contextlib.suppress(TokenError):  # already invalid or expired: nothing to revoke
            RefreshToken(request.data.get('refresh', '')).blacklist()
        record_audit(
            request, 'logout', target_type='user', target_id=request.user.pk, target_repr=request.user.username
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class CurrentUserView(APIView):
    organization_optional = True

    def get(self, request):
        return Response(CurrentUserSerializer(request.user).data)


class PreferencesView(generics.RetrieveUpdateAPIView):
    serializer_class = UserPreferenceSerializer
    organization_optional = True

    def get_object(self):
        prefs, _ = UserPreference.objects.get_or_create(user=self.request.user)
        return prefs


class ChangePasswordView(APIView):
    organization_optional = True

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        request.user.set_password(serializer.validated_data['new_password'])
        request.user.save(update_fields=['password'])
        record_audit(
            request, 'password_change', target_type='user', target_id=request.user.pk, target_repr=request.user.username
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class UserViewSet(OrganizationScopedMixin, viewsets.ModelViewSet):
    """Organization user management; administrators only."""

    queryset = User.objects.prefetch_related('teams')
    serializer_class = UserSerializer
    permission_classes = [RoleRequired]
    read_role = ROLE_ADMIN
    write_role = ROLE_ADMIN
    search_fields = ['username', 'email', 'first_name', 'last_name']
    audit_target_type = 'user'

    def perform_destroy(self, instance):
        if instance == self.request.user:
            from rest_framework.exceptions import ValidationError

            raise ValidationError('You cannot delete your own account.')
        super().perform_destroy(instance)

    def perform_update(self, serializer):
        if serializer.instance == self.request.user and serializer.validated_data.get('role', ROLE_ADMIN) != ROLE_ADMIN:
            from rest_framework.exceptions import ValidationError

            raise ValidationError({'role': 'You cannot remove your own administrator role.'})
        super().perform_update(serializer)
