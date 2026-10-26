from django.urls import path

from .views import (
    OrganizationListCreateView,
    OrganizationRetrieveUpdateDestroyView,
    TeamListCreateView,
    TeamRetrieveUpdateDestroyView,
)

urlpatterns = [
    path('', OrganizationListCreateView.as_view(), name='organization-list-create'),
    path('<int:pk>/', OrganizationRetrieveUpdateDestroyView.as_view(), name='organization-detail'),
    path('<int:organization_id>/teams/', TeamListCreateView.as_view(), name='team-list-create'),
    path('<int:organization_id>/teams/<int:pk>/', TeamRetrieveUpdateDestroyView.as_view(), name='team-detail'),
]
