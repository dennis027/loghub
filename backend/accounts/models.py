from django.contrib.auth.models import AbstractUser
from django.db import models

from core.permissions import ROLE_CHOICES, ROLE_VIEWER


class User(AbstractUser):
    organization = models.ForeignKey(
        'organizations.Organization',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='members',
    )
    teams = models.ManyToManyField('organizations.Team', blank=True, related_name='members')
    role = models.CharField(max_length=16, choices=ROLE_CHOICES, default=ROLE_VIEWER)

    class Meta:
        db_table = 'accounts_user'
        ordering = ['username']

    def __str__(self):
        return self.username


class UserPreference(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='preferences')
    timezone = models.CharField(max_length=64, default='UTC')
    default_time_range = models.CharField(max_length=16, default='1h')
    live_event_limit = models.PositiveIntegerField(default=500)

    def __str__(self):
        return f'preferences for {self.user}'
