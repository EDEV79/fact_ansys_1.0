"""
REST API routes — JSON endpoints for external integrations or AJAX.
All endpoints require authentication via Flask-Login session.
"""

from flask import Blueprint, jsonify, request, abort
from flask_login import login_required, current_user

from app.security import get_accessible_client_or_403
from saas_models import Client, Factura

api_bp = Blueprint("api", __name__, url_prefix="/api")


def _get_own_client_or_404(client_id: int) -> Client:
    return get_accessible_client_or_403(client_id)


# ── Clients ──────────────────────────────────────────────────────────────────

@api_bp.route("/clients")
@login_required
def list_clients():
    """GET /api/clients — list all clients for the current user."""
    if current_user.is_admin:
        clients = Client.query.filter_by(tenant_id=current_user.tenant_id).all()
    else:
        clients = (
            Client.query.filter_by(id=current_user.client_id, tenant_id=current_user.tenant_id).all()
            if current_user.client_id
            else []
        )
    return jsonify(
        [
            {
                "id": c.id,
                "name": c.name,
                "ruc": c.ruc,
                "description": c.description,
                "total_facturas": c.total_facturas,
                "created_at": c.created_at.isoformat(),
            }
            for c in clients
        ]
    )


# ── Facturas (paginated) ─────────────────────────────────────────────────────

@api_bp.route("/facturas/<int:client_id>")
@login_required
def list_facturas(client_id: int):
    """
    GET /api/facturas/<client_id>?page=1&per_page=50&nombre_emisor=...
    Returns paginated invoices for a client.
    """
    from app.services.analytics import build_filter_query

    client = _get_own_client_or_404(client_id)
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 50, type=int), 200)

    query, filters = build_filter_query(client_id, request.args)
    pagination = query.order_by(Factura.fecha_emision.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return jsonify(
        {
            "client_id": client_id,
            "client_name": client.name,
            "page": pagination.page,
            "pages": pagination.pages,
            "total": pagination.total,
            "per_page": per_page,
            "filters": filters,
            "items": [f.to_dict() for f in pagination.items],
        }
    )


# ── Analytics ────────────────────────────────────────────────────────────────

@api_bp.route("/analytics/<int:client_id>")
@login_required
def analytics(client_id: int):
    """
    GET /api/analytics/<client_id>
    Returns summary + monthly + top providers + categories.
    """
    from app.services.analytics import (
        get_summary,
        get_monthly_expenses,
        get_top_providers,
        get_expense_by_category,
    )

    _get_own_client_or_404(client_id)

    return jsonify(
        {
            "summary": get_summary(client_id, request.args),
            "monthly": get_monthly_expenses(client_id, request.args),
            "top_providers": get_top_providers(client_id, request.args),
            "categories": get_expense_by_category(client_id),
        }
    )


# ── AI Insights ──────────────────────────────────────────────────────────────

@api_bp.route("/insights/<int:client_id>")
@login_required
def insights(client_id: int):
    """GET /api/insights/<client_id> — return AI-generated expense insights."""
    from app.services.ai_analysis import analyze_expenses

    _get_own_client_or_404(client_id)
    return jsonify(analyze_expenses(client_id))
