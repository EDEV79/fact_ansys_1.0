"""RBAC helpers and decorators for role-based access control."""

from functools import wraps

from flask import abort
from flask_login import current_user, login_required

from app.rbac import get_tenant_client_or_403, permission_required
from saas_models import Client


def admin_required(view):
    """Allow access only to authenticated admin users."""

    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return view(*args, **kwargs)

    return wrapped


def client_required(view):
    """Allow access only to authenticated client users."""

    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_client:
            abort(403)
        return view(*args, **kwargs)

    return wrapped


def get_accessible_client_or_403(client_id: int) -> Client:
    """Return client if current_user can access it, else raise 403/404."""
    client = get_tenant_client_or_403(client_id)

    if current_user.is_admin:
        return client

    if current_user.is_client and current_user.client_id == client.id and client.tenant_id == current_user.tenant_id:
        return client

    abort(403)
