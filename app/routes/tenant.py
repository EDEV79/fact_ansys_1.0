"""Client-user routes: own dashboard and reports only."""

from flask import Blueprint, redirect, render_template, request, url_for
from flask_login import current_user

from app.security import client_required, get_accessible_client_or_403


tenant_bp = Blueprint("tenant", __name__)


@tenant_bp.route("/dashboard/<int:client_id>")
@client_required
def dashboard(client_id: int):
    from app.services.analytics import get_client_dashboard_data
    from app.services.ai_analysis import analyze_expenses

    client = get_accessible_client_or_403(client_id)
    page = request.args.get("page", 1, type=int)
    data = get_client_dashboard_data(client.id, request.args, page)
    ai_insights = analyze_expenses(client.id)

    return render_template("clients/detail.html", client=client, ai_insights=ai_insights, **data)


@tenant_bp.route("/reports/<int:client_id>")
@client_required
def reports(client_id: int):
    client = get_accessible_client_or_403(client_id)
    return redirect(url_for("tenant.dashboard", client_id=client.id))


@tenant_bp.route("/reports")
@client_required
def reports_me():
    client = get_accessible_client_or_403(current_user.client_id)
    return redirect(url_for("tenant.dashboard", client_id=client.id))
