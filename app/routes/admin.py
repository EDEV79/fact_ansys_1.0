"""Admin-only routes."""

from flask import Blueprint, jsonify, render_template
from flask_login import current_user
from sqlalchemy import func

from app.rbac import build_roles_permissions_ui_payload
from app.security import admin_required
from app.security import permission_required
from saas_models import Client, Factura, User


admin_bp = Blueprint("admin", __name__)


@admin_bp.route("/admin")
@admin_required
def index():
    summary = {
        "users": User.query.filter_by(tenant_id=current_user.tenant_id).count(),
        "clients": Client.query.filter_by(tenant_id=current_user.tenant_id).count(),
        "facturas": Factura.query.filter_by(tenant_id=current_user.tenant_id).count(),
        "admins": User.query.filter_by(tenant_id=current_user.tenant_id, role="admin").count(),
        "client_users": User.query.filter_by(tenant_id=current_user.tenant_id, role="client").count(),
    }

    latest_clients = (
        Client.query.filter_by(tenant_id=current_user.tenant_id)
        .order_by(Client.created_at.desc())
        .limit(10)
        .all()
    )
    return render_template("admin/index.html", summary=summary, latest_clients=latest_clients)


@admin_bp.route("/all-data")
@admin_required
def all_data():
    rows = (
        Factura.query.with_entities(
            Factura.client_id,
            func.count(Factura.id).label("count"),
            func.coalesce(func.sum(Factura.total), 0).label("total"),
        )
        .filter(Factura.tenant_id == current_user.tenant_id)
        .group_by(Factura.client_id)
        .all()
    )

    return jsonify(
        {
            "by_client": [
                {"client_id": r.client_id, "facturas": r.count, "total": float(r.total or 0)}
                for r in rows
            ]
        }
    )


@admin_bp.route("/admin/rbac/roles")
@permission_required("view_roles")
def roles_permissions():
    return jsonify(build_roles_permissions_ui_payload(current_user.tenant_id))
