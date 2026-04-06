"""Admin-only routes."""

from flask import Blueprint, jsonify, render_template
from sqlalchemy import func

from app.security import admin_required
from models import Client, Factura, User


admin_bp = Blueprint("admin", __name__)


@admin_bp.route("/admin")
@admin_required
def index():
    summary = {
        "users": User.query.count(),
        "clients": Client.query.count(),
        "facturas": Factura.query.count(),
        "admins": User.query.filter_by(role="admin").count(),
        "client_users": User.query.filter_by(role="client").count(),
    }

    latest_clients = Client.query.order_by(Client.created_at.desc()).limit(10).all()
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
