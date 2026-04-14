"""Create or update an admin user for RBAC bootstrap.

Usage:
  c:/xampp/htdocs/fact_ansys_1.0/.venv/Scripts/python.exe scripts/seed_admin.py \
      --name Admin --email admin@example.com --username admin --password ChangeMe123!
"""

import argparse

from app import create_app
from app.rbac import ensure_default_roles_for_tenant
from saas_models import Role, Tenant, User, UserRole, db


def main():
    parser = argparse.ArgumentParser(description="Seed admin user")
    parser.add_argument("--name", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", required=True)
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        user = User.query.filter((User.usuario == args.username) | (User.email == args.email)).first()
        tenant = None

        if user:
            if not user.tenant_id:
                tenant = Tenant(name=f"{args.name.strip()} Workspace")
                db.session.add(tenant)
                db.session.flush()
                user.tenant_id = tenant.id
            ensure_default_roles_for_tenant(user.tenant_id)
            user.nombre = args.name
            user.email = args.email.lower().strip()
            user.usuario = args.username.strip()
            user.role = "admin"
            user.client_id = None
            user.status = 1
            user.set_password(args.password)
            admin_role = Role.query.filter_by(tenant_id=user.tenant_id, name="admin").first()
            if admin_role and not any(role.id == admin_role.id for role in user.roles):
                db.session.add(UserRole(user_id=user.id, role_id=admin_role.id))
            db.session.commit()
            print(f"Updated admin user: {user.usuario}")
            return

        tenant = Tenant(name=f"{args.name.strip()} Workspace")
        db.session.add(tenant)
        db.session.flush()
        ensure_default_roles_for_tenant(tenant.id)

        admin = User(
            nombre=args.name.strip(),
            apellido="",
            email=args.email.lower().strip(),
            usuario=args.username.strip(),
            nempleado="",
            celular="",
            permiso=99,
            role="admin",
            tenant_id=tenant.id,
            client_id=None,
            status=1,
        )
        admin.set_password(args.password)
        db.session.add(admin)
        db.session.flush()
        admin_role = Role.query.filter_by(tenant_id=tenant.id, name="admin").first()
        if admin_role:
            db.session.add(UserRole(user_id=admin.id, role_id=admin_role.id))
        db.session.commit()
        print(f"Created admin user: {admin.usuario}")


if __name__ == "__main__":
    main()
