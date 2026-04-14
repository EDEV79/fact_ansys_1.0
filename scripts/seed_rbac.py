"""Seed default permissions and tenant roles for the RBAC system.

Usage:
  c:/xampp/htdocs/fact_ansys_1.0/.venv/Scripts/python.exe scripts/seed_rbac.py
"""

from app import create_app
from app.rbac import bootstrap_rbac


def main():
    app = create_app()
    with app.app_context():
        bootstrap_rbac()
        print("RBAC schema and seed data are ready.")


if __name__ == "__main__":
    main()
