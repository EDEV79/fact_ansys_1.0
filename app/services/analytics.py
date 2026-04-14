"""
Analytics service — aggregation queries over the Factura table,
scoped to a single client.
"""

from __future__ import annotations

from datetime import datetime, time
from typing import Any

from sqlalchemy import func, cast, Numeric

from saas_models import Client, Factura, db

PER_PAGE = 15


# ---------------------------------------------------------------------------
# Filter helpers
# ---------------------------------------------------------------------------

def _parse_date(value: str | None, end_of_day: bool = False) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d")
        return datetime.combine(parsed.date(), time.max if end_of_day else time.min)
    except ValueError:
        return None


def build_filter_query(client_id: int, args) -> tuple:
    """
    Build a filtered SQLAlchemy query for client's Facturas.

    Returns:
        (query, filters_dict)
    """
    client = Client.query.get_or_404(client_id)
    query = Factura.query.filter_by(client_id=client_id, tenant_id=client.tenant_id)

    nombre_emisor = args.get("nombre_emisor", "").strip()
    ruc_emisor = args.get("ruc_emisor", "").strip()
    fecha_inicio = args.get("fecha_inicio", "").strip()
    fecha_fin = args.get("fecha_fin", "").strip()
    tipo_documento = args.get("tipo_documento", "").strip()
    categoria = args.get("categoria", "").strip()
    monto_min = args.get("monto_min", "").strip()
    monto_max = args.get("monto_max", "").strip()

    if nombre_emisor:
        query = query.filter(Factura.nombre_emisor.ilike(f"%{nombre_emisor}%"))
    if ruc_emisor:
        query = query.filter(Factura.ruc_emisor.ilike(f"%{ruc_emisor}%"))
    if fecha_inicio:
        dt = _parse_date(fecha_inicio)
        if dt:
            query = query.filter(Factura.fecha_emision >= dt)
    if fecha_fin:
        dt = _parse_date(fecha_fin, end_of_day=True)
        if dt:
            query = query.filter(Factura.fecha_emision <= dt)
    if tipo_documento:
        query = query.filter(Factura.tipo_documento == tipo_documento)
    if categoria:
        query = query.filter(Factura.categoria == categoria)
    if monto_min:
        try:
            query = query.filter(Factura.total >= float(monto_min))
        except ValueError:
            pass
    if monto_max:
        try:
            query = query.filter(Factura.total <= float(monto_max))
        except ValueError:
            pass

    filters = {
        "nombre_emisor": nombre_emisor,
        "ruc_emisor": ruc_emisor,
        "fecha_inicio": fecha_inicio,
        "fecha_fin": fecha_fin,
        "tipo_documento": tipo_documento,
        "categoria": categoria,
        "monto_min": monto_min,
        "monto_max": monto_max,
    }
    return query, filters


# ---------------------------------------------------------------------------
# Aggregation functions
# ---------------------------------------------------------------------------

def get_summary(client_id: int, args) -> dict:
    query, _ = build_filter_query(client_id, args)
    row = query.with_entities(
        func.count(Factura.id),
        func.coalesce(func.sum(cast(Factura.total, Numeric(14, 2))), 0),
        func.coalesce(func.sum(cast(Factura.impuesto, Numeric(14, 2))), 0),
    ).one()

    total_facturas = row[0]
    total_monto = float(row[1])
    total_impuesto = float(row[2])
    avg_factura = total_monto / total_facturas if total_facturas else 0.0

    return {
        "total_facturas": total_facturas,
        "total_monto": total_monto,
        "total_impuesto": total_impuesto,
        "avg_factura": avg_factura,
    }


def get_monthly_expenses(client_id: int, args) -> list[dict]:
    """Aggregate totals by year-month, ordered chronologically."""
    query, _ = build_filter_query(client_id, args)
    rows = (
        query.filter(Factura.fecha_emision.isnot(None))
        .with_entities(
            func.year(Factura.fecha_emision).label("year"),
            func.month(Factura.fecha_emision).label("month"),
            func.coalesce(func.sum(cast(Factura.total, Numeric(14, 2))), 0).label("total"),
            func.count(Factura.id).label("count"),
        )
        .group_by("year", "month")
        .order_by("year", "month")
        .all()
    )

    month_names = [
        "", "Ene", "Feb", "Mar", "Abr", "May", "Jun",
        "Jul", "Ago", "Sep", "Oct", "Nov", "Dic",
    ]

    return [
        {
            "month": f"{int(r.year):04d}-{int(r.month):02d}",
            "month_label": f"{month_names[int(r.month)]} {int(r.year)}",
            "total": float(r.total),
            "count": r.count,
        }
        for r in rows
    ]


def get_top_providers(client_id: int, args, limit: int = 10) -> list[dict]:
    """Return top N providers by total amount."""
    query, _ = build_filter_query(client_id, args)
    rows = (
        query.with_entities(
            Factura.nombre_emisor,
            func.coalesce(func.sum(cast(Factura.total, Numeric(14, 2))), 0).label("total"),
            func.count(Factura.id).label("count"),
        )
        .group_by(Factura.nombre_emisor)
        .order_by(func.sum(cast(Factura.total, Numeric(14, 2))).desc())
        .limit(limit)
        .all()
    )

    grand_total = sum(float(r.total) for r in rows) or 1
    return [
        {
            "nombre_emisor": r.nombre_emisor,
            "total": float(r.total),
            "count": r.count,
            "pct": float(r.total) / grand_total * 100,
        }
        for r in rows
    ]


def get_expense_by_category(client_id: int) -> list[dict]:
    """Aggregate totals by categoria."""
    client = Client.query.get_or_404(client_id)
    rows = (
        Factura.query.filter_by(client_id=client_id, tenant_id=client.tenant_id)
        .with_entities(
            func.coalesce(Factura.categoria, "sin_categoria").label("categoria"),
            func.coalesce(func.sum(cast(Factura.total, Numeric(14, 2))), 0).label("total"),
            func.count(Factura.id).label("count"),
        )
        .group_by(Factura.categoria)
        .order_by(func.sum(cast(Factura.total, Numeric(14, 2))).desc())
        .all()
    )

    grand_total = sum(float(r.total) for r in rows) or 1
    return [
        {
            "categoria": r.categoria,
            "total": float(r.total),
            "count": r.count,
            "pct": float(r.total) / grand_total * 100,
        }
        for r in rows
    ]


def get_document_types(client_id: int) -> list[str]:
    client = Client.query.get_or_404(client_id)
    rows = (
        Factura.query.filter_by(client_id=client_id, tenant_id=client.tenant_id)
        .with_entities(Factura.tipo_documento)
        .distinct()
        .order_by(Factura.tipo_documento)
        .all()
    )
    return [r.tipo_documento for r in rows if r.tipo_documento]


def get_categories(client_id: int) -> list[str]:
    client = Client.query.get_or_404(client_id)
    rows = (
        Factura.query.filter_by(client_id=client_id, tenant_id=client.tenant_id)
        .with_entities(Factura.categoria)
        .distinct()
        .order_by(Factura.categoria)
        .all()
    )
    return [r.categoria for r in rows if r.categoria]


# ---------------------------------------------------------------------------
# Full dashboard data bundle
# ---------------------------------------------------------------------------

def get_client_dashboard_data(client_id: int, args, page: int) -> dict:
    import json

    query, filters = build_filter_query(client_id, args)

    pagination = query.order_by(Factura.fecha_emision.desc()).paginate(
        page=page, per_page=PER_PAGE, error_out=False
    )

    summary = get_summary(client_id, args)
    monthly = get_monthly_expenses(client_id, args)
    top_providers = get_top_providers(client_id, args, limit=10)
    categories = get_expense_by_category(client_id)

    monthly_json = json.dumps(
        {
            "labels": [m["month_label"] for m in monthly],
            "values": [m["total"] for m in monthly],
        }
    )
    category_json = json.dumps(
        {
            "labels": [c["categoria"] for c in categories],
            "values": [c["total"] for c in categories],
        }
    )

    return {
        "summary": summary,
        "monthly": monthly,
        "top_providers": top_providers,
        "categories": categories,
        "pagination": pagination,
        "filters": filters,
        "document_types": get_document_types(client_id),
        "category_list": get_categories(client_id),
        "monthly_json": monthly_json,
        "category_json": category_json,
    }
