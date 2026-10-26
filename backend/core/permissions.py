from rest_framework import permissions

ROLE_ADMIN = 'admin'
ROLE_EDITOR = 'editor'
ROLE_ANALYST = 'analyst'
ROLE_VIEWER = 'viewer'
ROLE_CHOICES = [
    (ROLE_ADMIN, 'Administrator'),
    (ROLE_EDITOR, 'Editor'),
    (ROLE_ANALYST, 'Analyst'),
    (ROLE_VIEWER, 'Viewer'),
]
# Higher rank includes every capability of the lower ranks.
ROLE_RANK = {ROLE_VIEWER: 0, ROLE_ANALYST: 1, ROLE_EDITOR: 2, ROLE_ADMIN: 3}


def has_role(user, minimum):
    if not user or not user.is_authenticated:
        return False
    return ROLE_RANK.get(getattr(user, 'role', ROLE_VIEWER), 0) >= ROLE_RANK[minimum]


class IsOrganizationMember(permissions.BasePermission):
    """Every tenant-scoped API requires the user to belong to an organization."""

    message = 'Your account is not assigned to an organization.'

    def has_permission(self, request, view):
        if getattr(view, 'organization_optional', False):
            return True
        user = request.user
        return bool(user and user.is_authenticated and user.organization_id)


class RoleRequired(permissions.BasePermission):
    """Reads need `read_role` (viewer by default); writes need `write_role` (editor)."""

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            minimum = getattr(view, 'read_role', ROLE_VIEWER)
        else:
            minimum = getattr(view, 'write_role', ROLE_EDITOR)
        return has_role(request.user, minimum)


class CanExportData(permissions.BasePermission):
    message = 'Exporting log data requires the analyst role or higher.'

    def has_permission(self, request, view):
        return has_role(request.user, ROLE_ANALYST)


class IsPlatformAdmin(permissions.BasePermission):
    """Cluster-wide settings (retention, integrations) affect every organization."""

    message = 'Only platform administrators (staff) can change cluster-wide settings.'

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return bool(request.user and request.user.is_staff and has_role(request.user, ROLE_ADMIN))
