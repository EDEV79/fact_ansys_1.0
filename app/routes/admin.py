"""Admin-only routes."""

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import func
from sqlalchemy.orm import selectinload

from app.rbac import build_roles_permissions_ui_payload
from app.security import admin_required, permission_required
from saas_models import Client, Factura, Permission, Role, RolePermission, User, UserRole, db


admin_bp = Blueprint("admin", __name__)


def _admin_summary() -> dict:
    return {
        "users": User.query.filter_by(tenant_id=current_user.tenant_id).count(),
        "clients": Client.query.filter_by(tenant_id=current_user.tenant_id).count(),
        "facturas": Factura.query.filter_by(tenant_id=current_user.tenant_id).count(),
        "admins": User.query.filter_by(tenant_id=current_user.tenant_id, role="admin").count(),
        "client_users": User.query.filter_by(tenant_id=current_user.tenant_id, role="client").count(),
        "custom_roles": Role.query.filter_by(tenant_id=current_user.tenant_id).count(),
    }


def _latest_clients():
    return (
        Client.query.filter_by(tenant_id=current_user.tenant_id)
        .order_by(Client.created_at.desc())
        .limit(10)
        .all()
    )


def _role_matrix_context() -> dict:
    roles = (
        Role.query.options(selectinload(Role.permissions))
        .filter_by(tenant_id=current_user.tenant_id)
        .order_by(Role.name.asc())
        .all()
    )
    users = (
        User.query.options(selectinload(User.roles))
        .filter_by(tenant_id=current_user.tenant_id)
        .order_by(User.nombre.asc(), User.apellido.asc(), User.usuario.asc())
        .all()
    )
    permissions = Permission.query.order_by(Permission.module.asc(), Permission.action.asc()).all()

    permissions_by_module: dict[str, list[Permission]] = {}
    for permission in permissions:
        permissions_by_module.setdefault(permission.module, []).append(permission)

    return {
        "summary": _admin_summary(),
        "latest_clients": _latest_clients(),
        "roles": roles,
        "users": users,
        "permissions": permissions,
        "permissions_by_module": permissions_by_module,
    }


def _sync_role_permissions(role: Role, permission_ids: list[int]) -> None:
    allowed_ids = {permission.id for permission in Permission.query.filter(Permission.id.in_(permission_ids)).all()}
    existing_ids = {permission.id for permission in role.permissions}

    for permission_id in existing_ids - allowed_ids:
        RolePermission.query.filter_by(role_id=role.id, permission_id=permission_id).delete()

    for permission_id in allowed_ids - existing_ids:
        db.session.add(RolePermission(role_id=role.id, permission_id=permission_id))


def _sync_user_roles(user: User, role_ids: list[int]) -> None:
    tenant_role_ids = {
        role.id for role in Role.query.filter(Role.tenant_id == current_user.tenant_id, Role.id.in_(role_ids)).all()
    }
    existing_ids = {role.id for role in user.roles}

    for role_id in existing_ids - tenant_role_ids:
        UserRole.query.filter_by(user_id=user.id, role_id=role_id).delete()

    for role_id in tenant_role_ids - existing_ids:
        db.session.add(UserRole(user_id=user.id, role_id=role_id))


@admin_bp.route("/admin")
@admin_required
def index():
    return render_template("admin/index.html", summary=_admin_summary(), latest_clients=_latest_clients())


@admin_bp.route("/admin/roles")
@permission_required("view_roles")
def manage_roles():
    return render_template("admin/roles_grid.html", **_role_matrix_context())


@admin_bp.route("/admin/roles", methods=["POST"])
@permission_required("manage_roles")
def create_role():
    name = request.form.get("name", "").strip().lower()
    description = request.form.get("description", "").strip()
    permission_ids = request.form.getlist("permission_ids")

    if not name:
        flash("El nombre del rol es obligatorio.", "danger")
        return redirect(url_for("admin.manage_roles"))

    existing_role = Role.query.filter_by(tenant_id=current_user.tenant_id, name=name).first()
    if existing_role:
        flash(f"El rol '{name}' ya existe en este tenant.", "warning")
        return redirect(url_for("admin.manage_roles"))

    role = Role(tenant_id=current_user.tenant_id, name=name, description=description or None)
    db.session.add(role)
    db.session.flush()
    _sync_role_permissions(role, [int(permission_id) for permission_id in permission_ids if permission_id.isdigit()])
    db.session.commit()
    flash(f"Rol '{name}' creado correctamente.", "success")
    return redirect(url_for("admin.manage_roles"))


@admin_bp.route("/admin/roles/<int:role_id>", methods=["POST"])
@permission_required("manage_roles")
def update_role(role_id: int):
    role = Role.query.filter_by(id=role_id, tenant_id=current_user.tenant_id).first_or_404()
    role.name = request.form.get("name", role.name).strip().lower() or role.name
    role.description = request.form.get("description", "").strip() or None
    permission_ids = [int(permission_id) for permission_id in request.form.getlist("permission_ids") if permission_id.isdigit()]
    _sync_role_permissions(role, permission_ids)
    db.session.commit()
    flash(f"Rol '{role.name}' actualizado.", "success")
    return redirect(url_for("admin.manage_roles"))


@admin_bp.route("/admin/users/<int:user_id>/roles", methods=["POST"])
@permission_required("manage_roles")
def update_user_roles(user_id: int):
    user = User.query.filter_by(id=user_id, tenant_id=current_user.tenant_id).first_or_404()
    role_ids = [int(role_id) for role_id in request.form.getlist("role_ids") if role_id.isdigit()]
    legacy_role = request.form.get("legacy_role", user.role)
    status = request.form.get("status", str(user.status))

    if legacy_role in {"admin", "client"}:
        user.role = legacy_role
    user.status = 1 if status == "1" else 0
    _sync_user_roles(user, role_ids)
    db.session.commit()
    flash(f"Roles del usuario '{user.full_name or user.usuario}' actualizados.", "success")
    return redirect(url_for("admin.manage_roles"))


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
