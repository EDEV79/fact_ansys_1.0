"""Create or update an admin user for RBAC bootstrap.

Usage:
  c:/xampp/htdocs/fact_ansys_1.0/.venv/Scripts/python.exe scripts/seed_admin.py \
      --name Admin --email admin@example.com --username admin --password ChangeMe123!
"""

import argparse

from app import create_app
from models import User, db


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

        if user:
            user.nombre = args.name
            user.email = args.email.lower().strip()
            user.usuario = args.username.strip()
            user.role = "admin"
            user.client_id = None
            user.status = 1
            user.set_password(args.password)
            db.session.commit()
            print(f"Updated admin user: {user.usuario}")
            return

        admin = User(
            nombre=args.name.strip(),
            apellido="",
            email=args.email.lower().strip(),
            usuario=args.username.strip(),
            nempleado="",
            celular="",
            permiso=99,
            role="admin",
            client_id=None,
            status=1,
        )
        admin.set_password(args.password)
        db.session.add(admin)
        db.session.commit()
        print(f"Created admin user: {admin.usuario}")


if __name__ == "__main__":
    main()
