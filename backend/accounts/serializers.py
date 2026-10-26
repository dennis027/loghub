from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from organizations.models import Team

from .models import UserPreference

User = get_user_model()


class UserPreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserPreference
        fields = ['timezone', 'default_time_range', 'live_event_limit']

    def validate_live_event_limit(self, value):
        if not 50 <= value <= 5000:
            raise serializers.ValidationError('Must be between 50 and 5000.')
        return value


class CurrentUserSerializer(serializers.ModelSerializer):
    organization = serializers.SerializerMethodField()
    preferences = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id',
            'username',
            'email',
            'first_name',
            'last_name',
            'role',
            'is_staff',
            'organization',
            'preferences',
            'last_login',
        ]
        read_only_fields = fields

    def get_organization(self, obj):
        org = obj.organization
        return {'id': org.id, 'name': org.name, 'slug': org.slug} if org else None

    def get_preferences(self, obj):
        prefs, _ = UserPreference.objects.get_or_create(user=obj)
        return UserPreferenceSerializer(prefs).data


class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, style={'input_type': 'password'})
    teams = serializers.PrimaryKeyRelatedField(many=True, queryset=Team.objects.all(), required=False)

    class Meta:
        model = User
        fields = [
            'id',
            'username',
            'email',
            'first_name',
            'last_name',
            'role',
            'is_active',
            'teams',
            'password',
            'last_login',
            'date_joined',
        ]
        read_only_fields = ['id', 'last_login', 'date_joined']

    def validate_teams(self, teams):
        org = self.context['request'].user.organization
        if any(team.organization_id != org.id for team in teams):
            raise serializers.ValidationError('Teams must belong to your organization.')
        return teams

    def validate(self, attrs):
        if self.instance is None and not attrs.get('password'):
            raise serializers.ValidationError({'password': 'A password is required for new users.'})
        if attrs.get('password'):
            validate_password(attrs['password'], user=self.instance)
        return attrs

    def create(self, validated_data):
        teams = validated_data.pop('teams', [])
        password = validated_data.pop('password')
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        user.teams.set(teams)
        return user

    def update(self, instance, validated_data):
        teams = validated_data.pop('teams', None)
        password = validated_data.pop('password', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()
        if teams is not None:
            instance.teams.set(teams)
        return instance


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        user = self.context['request'].user
        if not user.check_password(attrs['current_password']):
            raise serializers.ValidationError({'current_password': 'Incorrect password.'})
        validate_password(attrs['new_password'], user=user)
        return attrs
