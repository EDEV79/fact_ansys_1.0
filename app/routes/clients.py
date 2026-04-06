"""
Client management routes — CRUD for multi-tenant clients.
Each User can own multiple Clients; data is fully isolated per Client.
"""

from flask import Blueprint, flash, redirect, render_template, request, url_for, abort
from flask_login import login_required, current_user

from app.security import admin_required, get_accessible_client_or_403
from models import Client, Factura, db

clients_bp = Blueprint("clients", __name__, url_prefix="/clients")


def _get_own_client_or_404(client_id: int) -> Client:
    """Return client if current user can access it (admin all, client own)."""
    return get_accessible_client_or_403(client_id)


# ── List ─────────────────────────────────────────────────────────────────────

@clients_bp.route("/")
@admin_required
def index():
    clients = Client.query.order_by(Client.created_at.desc()).all()
    return render_template("clients/index.html", clients=clients)


# ── Create ───────────────────────────────────────────────────────────────────

@clients_bp.route("/new", methods=["GET", "POST"])
@admin_required
def new():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        ruc = request.form.get("ruc", "").strip()
        description = request.form.get("description", "").strip()

        if not name:
            flash("El nombre del cliente es obligatorio.", "danger")
            return render_template("clients/new.html")

        client = Client(
            user_id=current_user.id,
            name=name,
            ruc=ruc or None,
            description=description or None,
        )
        db.session.add(client)
        db.session.commit()
        flash(f"Cliente «{name}» creado correctamente.", "success")
        return redirect(url_for("clients.detail", client_id=client.id))

    return render_template("clients/new.html")


# ── Detail / Client Dashboard ────────────────────────────────────────────────

@clients_bp.route("/<int:client_id>")
@admin_required
def detail(client_id: int):
    from app.services.analytics import get_client_dashboard_data
    from app.services.ai_analysis import analyze_expenses

    client = _get_own_client_or_404(client_id)
    page = request.args.get("page", 1, type=int)
    data = get_client_dashboard_data(client_id, request.args, page)
    ai_insights = analyze_expenses(client_id)

    return render_template(
        "clients/detail.html",
        client=client,
        ai_insights=ai_insights,
        **data,
    )


# ── Edit ─────────────────────────────────────────────────────────────────────

@clients_bp.route("/<int:client_id>/edit", methods=["GET", "POST"])
@admin_required
def edit(client_id: int):
    client = _get_own_client_or_404(client_id)

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("El nombre es obligatorio.", "danger")
            return render_template("clients/edit.html", client=client)

        client.name = name
        client.ruc = request.form.get("ruc", "").strip() or None
        client.description = request.form.get("description", "").strip() or None
        db.session.commit()
        flash("Cliente actualizado.", "success")
        return redirect(url_for("clients.detail", client_id=client.id))

    return render_template("clients/edit.html", client=client)


# ── Delete ───────────────────────────────────────────────────────────────────

@clients_bp.route("/<int:client_id>/delete", methods=["POST"])
@admin_required
def delete(client_id: int):
    client = _get_own_client_or_404(client_id)
    name = client.name
    db.session.delete(client)
    db.session.commit()
    flash(f"Cliente «{name}» y todos sus datos fueron eliminados.", "info")
    return redirect(url_for("clients.index"))
