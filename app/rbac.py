from __future__ import annotations

from functools import wraps

from flask import abort, jsonify
from flask_login import current_user, login_required
from sqlalchemy import text
from sqlalchemy.orm import selectinload

from saas_models import (
    Client,
    Factura,
    Permission,
    Role,
    RolePermission,
    Tenant,
    User,
    UserRole,
    db,
)

DEFAULT_PERMISSIONS = (
    {"name": "view_dashboard", "module": "dashboard", "action": "read"},
    {"name": "view_invoice", "module": "invoices", "action": "read"},
    {"name": "create_invoice", "module": "invoices", "action": "write"},
    {"name": "delete_invoice", "module": "invoices", "action": "delete"},
    {"name": "export_invoice", "module": "invoices", "action": "export"},
    {"name": "approve_invoice", "module": "invoices", "action": "approve"},
    {"name": "view_client", "module": "clients", "action": "read"},
    {"name": "create_client", "module": "clients", "action": "write"},
    {"name": "delete_client", "module": "clients", "action": "delete"},
    {"name": "export_client", "module": "clients", "action": "export"},
    {"name": "view_report", "module": "reports", "action": "read"},
    {"name": "export_report", "module": "reports", "action": "export"},
    {"name": "approve_report", "module": "reports", "action": "approve"},
    {"name": "view_roles", "module": "roles", "action": "read"},
    {"name": "manage_roles", "module": "roles", "action": "write"},
    {"name": "assign_permissions", "module": "roles", "action": "approve"},
)

DEFAULT_ROLE_PERMISSIONS = {
    "admin": {permission["name"] for permission in DEFAULT_PERMISSIONS},
    "accountant": {
        "view_dashboard",
        "view_invoice",
        "create_invoice",
        "export_invoice",
        "approve_invoice",
        "view_report",
        "export_report",
    },
    "viewer": {
        "view_dashboard",
        "view_invoice",
        "view_client",
        "view_report",
        "view_roles",
    },
}

DEFAULT_ROLE_DESCRIPTIONS = {
    "admin": "Full tenant administration with access to users, roles, invoices, clients, and reports.",
    "accountant": "Operational access to invoices and reports, including export and approval workflows.",
    "viewer": "Read-only access to dashboards, invoices, clients, and reports.",
}


def ensure_rbac_schema() -> None:
    """Best-effort schema migration for legacy databases without Alembic."""

    ddl_statements = (
        """
        CREATE TABLE IF NOT EXISTS tenants (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(150) NOT NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_tenants_created_at (created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
        """
        CREATE TABLE IF NOT EXISTS permissions (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            module VARCHAR(50) NOT NULL,
            action VARCHAR(50) NOT NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_permissions_name (name),
            KEY idx_permissions_module_action (module, action)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
        """
        CREATE TABLE IF NOT EXISTS roles (
            id INT AUTO_INCREMENT PRIMARY KEY,
            tenant_id INT NOT NULL,
            name VARCHAR(50) NOT NULL,
            description VARCHAR(255) NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_roles_tenant_name (tenant_id, name),
            KEY idx_roles_tenant_id (tenant_id),
            CONSTRAINT fk_roles_tenant FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
        """
        CREATE TABLE IF NOT EXISTS role_permissions (
            id INT AUTO_INCREMENT PRIMARY KEY,
            role_id INT NOT NULL,
            permission_id INT NOT NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_role_permissions_role_permission (role_id, permission_id),
            KEY idx_role_permissions_role_id (role_id),
            KEY idx_role_permissions_permission_id (permission_id),
            CONSTRAINT fk_role_permissions_role FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE CASCADE,
            CONSTRAINT fk_role_permissions_permission FOREIGN KEY (permission_id) REFERENCES permissions(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
        """
        CREATE TABLE IF NOT EXISTS user_roles (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            role_id INT NOT NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_user_roles_user_role (user_id, role_id),
            KEY idx_user_roles_user_id (user_id),
            KEY idx_user_roles_role_id (role_id),
            CONSTRAINT fk_user_roles_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            CONSTRAINT fk_user_roles_role FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
    )

    for statement in ddl_statements:
        db.session.execute(text(statement))

    column_statements = (
        ("users", "tenant_id", "ALTER TABLE users ADD COLUMN tenant_id INT NULL"),
        ("users", "created_at", "ALTER TABLE users ADD COLUMN created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP"),
        ("clients", "tenant_id", "ALTER TABLE clients ADD COLUMN tenant_id INT NULL"),
        ("facturas", "tenant_id", "ALTER TABLE facturas ADD COLUMN tenant_id INT NULL"),
    )
    for table_name, column_name, statement in column_statements:
        if not _column_exists(table_name, column_name):
            db.session.execute(text(statement))

    index_statements = (
        "ALTER TABLE users ADD INDEX idx_users_tenant_id (tenant_id)",
        "ALTER TABLE roles ADD INDEX idx_roles_tenant_id_alt (tenant_id)",
        "ALTER TABLE role_permissions ADD INDEX idx_role_permissions_role_id_alt (role_id)",
        "ALTER TABLE user_roles ADD INDEX idx_user_roles_user_id_alt (user_id)",
        "ALTER TABLE clients ADD INDEX idx_clients_tenant_id_alt (tenant_id)",
        "ALTER TABLE facturas ADD INDEX idx_facturas_tenant_id_alt (tenant_id)",
        "ALTER TABLE facturas ADD INDEX idx_facturas_tenant_client_alt (tenant_id, client_id)",
    )
    for statement in index_statements:
        try:
            db.session.execute(text(statement))
        except Exception:
            db.session.rollback()

    foreign_key_statements = (
        "ALTER TABLE users ADD CONSTRAINT fk_users_tenant FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE",
        "ALTER TABLE clients ADD CONSTRAINT fk_clients_tenant FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE",
        "ALTER TABLE facturas ADD CONSTRAINT fk_facturas_tenant FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE",
    )
    for statement in foreign_key_statements:
        try:
            db.session.execute(text(statement))
        except Exception:
            db.session.rollback()

    db.session.commit()


def bootstrap_rbac() -> None:
    ensure_rbac_schema()
    seed_default_permissions()
    ensure_default_tenants_and_roles()
    backfill_tenant_scope()
    seed_legacy_user_assignments()


def seed_default_permissions() -> None:
    existing = {permission.name for permission in Permission.query.all()}
    for definition in DEFAULT_PERMISSIONS:
        if definition["name"] in existing:
            continue
        db.session.add(Permission(**definition))
    db.session.commit()


def ensure_default_roles_for_tenant(tenant_id: int) -> None:
    permissions_by_name = {permission.name: permission for permission in Permission.query.all()}
    existing_roles = {role.name: role for role in Role.query.filter_by(tenant_id=tenant_id).all()}

    for role_name, permission_names in DEFAULT_ROLE_PERMISSIONS.items():
        role = existing_roles.get(role_name)
        if role is None:
            role = Role(
                tenant_id=tenant_id,
                name=role_name,
                description=DEFAULT_ROLE_DESCRIPTIONS.get(role_name),
            )
            db.session.add(role)
            db.session.flush()
            existing_roles[role_name] = role

        assigned_permission_ids = {permission.id for permission in role.permissions}
        for permission_name in permission_names:
            permission = permissions_by_name[permission_name]
            if permission.id in assigned_permission_ids:
                continue
            db.session.add(RolePermission(role_id=role.id, permission_id=permission.id))

    db.session.commit()


def ensure_default_tenants_and_roles() -> None:
    for user in User.query.order_by(User.id.asc()).all():
        if user.tenant_id:
            continue

        tenant_name = user.full_name or user.usuario or user.email or f"Tenant {user.id}"
        tenant = Tenant(name=f"{tenant_name} Workspace")
        db.session.add(tenant)
        db.session.flush()
        user.tenant_id = tenant.id

    db.session.commit()

    for tenant in Tenant.query.order_by(Tenant.id.asc()).all():
        ensure_default_roles_for_tenant(tenant.id)


def backfill_tenant_scope() -> None:
    changed = False

    for user in User.query.filter(User.created_at.is_(None)).all():
        user.created_at = user.reg_date
        changed = True

    for client in Client.query.options(selectinload(Client.owner)).all():
        if client.tenant_id:
            continue
        if client.owner and client.owner.tenant_id:
            client.tenant_id = client.owner.tenant_id
            changed = True

    for factura in Factura.query.options(selectinload(Factura.client)).all():
        if factura.tenant_id:
            continue
        if factura.client and factura.client.tenant_id:
            factura.tenant_id = factura.client.tenant_id
            changed = True

    if changed:
        db.session.commit()


def seed_legacy_user_assignments() -> None:
    changed = False

    for user in User.query.options(selectinload(User.roles)).all():
        if user.is_client and not user.client_id:
            existing_client = Client.query.filter_by(user_id=user.id).order_by(Client.id.asc()).first()
            if existing_client:
                user.client_id = existing_client.id
                changed = True
            else:
                created_client = Client(
                    user_id=user.id,
                    tenant_id=user.tenant_id,
                    name=f"Cliente de {user.full_name or user.usuario}",
                    description="Cliente auto-creado para migracion multi-tenant",
                )
                db.session.add(created_client)
                db.session.flush()
                user.client_id = created_client.id
                changed = True

        if user.client_id:
            client = Client.query.get(user.client_id)
            if client and client.tenant_id != user.tenant_id:
                client.tenant_id = user.tenant_id
                changed = True

        target_role_name = "admin" if user.is_admin else "viewer"
        role = Role.query.filter_by(tenant_id=user.tenant_id, name=target_role_name).first()
        if role and not any(existing_role.id == role.id for existing_role in user.roles):
            db.session.add(UserRole(user_id=user.id, role_id=role.id))
            changed = True

    if changed:
        db.session.commit()


def has_permission(user_id: int, permission_name: str, tenant_id: int | None = None) -> bool:
    query = (
        db.session.query(Permission.id)
        .select_from(User)
        .join(UserRole, UserRole.user_id == User.id)
        .join(Role, Role.id == UserRole.role_id)
        .join(RolePermission, RolePermission.role_id == Role.id)
        .join(Permission, Permission.id == RolePermission.permission_id)
        .filter(User.id == user_id)
        .filter(Permission.name == permission_name)
    )

    if tenant_id is not None:
        query = query.filter(User.tenant_id == tenant_id, Role.tenant_id == tenant_id)

    return db.session.query(query.exists()).scalar() or False


def permission_required(permission_name: str):
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated or not current_user.tenant_id:
                abort(403)
            if not has_permission(current_user.id, permission_name, current_user.tenant_id):
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorator


def tenant_filtered_clients_query():
    if not current_user.is_authenticated or not current_user.tenant_id:
        abort(403)
    return Client.query.filter(Client.tenant_id == current_user.tenant_id)


def tenant_filtered_facturas_query(client_id: int | None = None):
    if not current_user.is_authenticated or not current_user.tenant_id:
        abort(403)

    query = Factura.query.filter(Factura.tenant_id == current_user.tenant_id)
    if client_id is not None:
        query = query.filter(Factura.client_id == client_id)
    return query


def get_tenant_client_or_403(client_id: int) -> Client:
    client = tenant_filtered_clients_query().filter(Client.id == client_id).first()
    if client is None:
        abort(404)
    return client


def build_roles_permissions_ui_payload(tenant_id: int) -> dict:
    roles = (
        Role.query.options(selectinload(Role.permissions))
        .filter(Role.tenant_id == tenant_id)
        .order_by(Role.name.asc())
        .all()
    )
    permissions = Permission.query.order_by(Permission.module.asc(), Permission.action.asc()).all()

    matrix: dict[str, dict[str, dict]] = {}
    for permission in permissions:
        module_row = matrix.setdefault(permission.module, {})
        module_row[permission.action] = {
            "permission_id": permission.id,
            "permission_name": permission.name,
            "action": permission.action,
        }

    role_rows = []
    for role in roles:
        permission_names = {permission.name for permission in role.permissions}
        role_matrix: dict[str, dict[str, bool]] = {}
        for permission in permissions:
            module_row = role_matrix.setdefault(permission.module, {})
            module_row[permission.action] = permission.name in permission_names
        role_rows.append(
            {
                "id": role.id,
                "name": role.name,
                "description": role.description,
                "tenant_id": role.tenant_id,
                "permissions": sorted(permission_names),
                "matrix": role_matrix,
            }
        )

    modules = {}
    for permission in permissions:
        modules.setdefault(permission.module, []).append(
            {
                "id": permission.id,
                "name": permission.name,
                "action": permission.action,
            }
        )

    return {
        "tenant_id": tenant_id,
        "roles": role_rows,
        "permissions": [
            {
                "id": permission.id,
                "name": permission.name,
                "module": permission.module,
                "action": permission.action,
            }
            for permission in permissions
        ],
        "modules": modules,
        "matrix": matrix,
    }


def roles_permissions_response():
    if not current_user.is_authenticated or not current_user.tenant_id:
        return jsonify({"error": "Unauthorized"}), 403
    return jsonify(build_roles_permissions_ui_payload(current_user.tenant_id))


def _column_exists(table_name: str, column_name: str) -> bool:
    result = db.session.execute(
        text(
            """
            SELECT COUNT(*)
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = :table_name
              AND COLUMN_NAME = :column_name
            """
        ),
        {"table_name": table_name, "column_name": column_name},
    ).scalar()
    return bool(result)
