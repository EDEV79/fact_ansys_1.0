import csv
from datetime import datetime, time
from io import StringIO

from flask import Blueprint, Response, render_template, request
from flask_login import login_required
from sqlalchemy import Numeric, cast, func

from app.security import admin_required
from saas_models import FacturaDGI


dashboard_bp = Blueprint("dashboard", __name__)

PER_PAGE = 10
DATE_FORMAT = "%d/%m/%Y %H:%i:%s"


def parse_date(value, end_of_day=False):
    if not value:
        return None

    parsed = datetime.strptime(value, "%Y-%m-%d")
    if end_of_day:
        return datetime.combine(parsed.date(), time.max)
    return datetime.combine(parsed.date(), time.min)


def amount_expr(column):
    normalized_value = func.nullif(func.replace(func.replace(column, ",", ""), "$", ""), "")
    return cast(func.coalesce(normalized_value, "0"), Numeric(14, 2))


def emission_date_expr():
    return func.str_to_date(FacturaDGI.fecha_de_emision, DATE_FORMAT)


def build_filtered_query(args):
    query = FacturaDGI.query
    emission_date = emission_date_expr()

    emisor = args.get("nombre_de_emisor", "").strip()
    numero_ruc = args.get("numero_ruc", "").strip()
    usuario = args.get("usuario", "").strip()
    fecha_inicio = args.get("fecha_inicio", "").strip()
    fecha_fin = args.get("fecha_fin", "").strip()
    tipo_documento = args.get("tipo_documento", "").strip()

    if emisor:
        query = query.filter(FacturaDGI.nombre_de_emisor.ilike(f"%{emisor}%"))

    if numero_ruc:
        query = query.filter(FacturaDGI.numero_ruc.ilike(f"%{numero_ruc}%"))

    if usuario:
        query = query.filter(FacturaDGI.usuario.ilike(f"%{usuario}%"))

    if fecha_inicio:
        query = query.filter(emission_date >= parse_date(fecha_inicio))

    if fecha_fin:
        query = query.filter(emission_date <= parse_date(fecha_fin, end_of_day=True))

    if tipo_documento:
        query = query.filter(FacturaDGI.tipo_de_documento == tipo_documento)

    return query, {
        "nombre_de_emisor": emisor,
        "numero_ruc": numero_ruc,
        "usuario": usuario,
        "fecha_inicio": fecha_inicio,
        "fecha_fin": fecha_fin,
        "tipo_documento": tipo_documento,
    }


def get_dashboard_data(args, page):
    query, filters = build_filtered_query(args)
    monto_value = amount_expr(FacturaDGI.monto)
    itbms_value = amount_expr(FacturaDGI.itbms)
    emission_date = emission_date_expr()

    summary = query.with_entities(
        func.count(FacturaDGI.cufe),
        func.coalesce(func.sum(monto_value), 0),
        func.coalesce(func.sum(itbms_value), 0),
    ).one()

    grouped_by_emisor = query.with_entities(
        FacturaDGI.nombre_de_emisor,
        func.coalesce(func.sum(monto_value), 0).label("total_monto"),
    ).group_by(FacturaDGI.nombre_de_emisor).order_by(func.sum(monto_value).desc()).limit(10).all()

    pagination = query.order_by(emission_date.desc()).paginate(
        page=page,
        per_page=PER_PAGE,
        error_out=False,
    )

    document_types = (
        FacturaDGI.query.with_entities(FacturaDGI.tipo_de_documento)
        .distinct()
        .order_by(FacturaDGI.tipo_de_documento.asc())
        .all()
    )

    chart_labels = [row.nombre_de_emisor for row in grouped_by_emisor]
    chart_values = [float(row.total_monto or 0) for row in grouped_by_emisor]

    return {
        "summary": {
            "total_facturas": summary[0],
            "total_monto": float(summary[1] or 0),
            "total_itbms": float(summary[2] or 0),
        },
        "grouped_by_emisor": grouped_by_emisor,
        "pagination": pagination,
        "filters": filters,
        "document_types": [row.tipo_de_documento for row in document_types],
        "chart_labels": chart_labels,
        "chart_values": chart_values,
    }


@dashboard_bp.route("/dashboard")
@admin_required
def index():
    page = request.args.get("page", default=1, type=int)
    data = get_dashboard_data(request.args, page)
    return render_template("dashboard/index.html", **data)


@dashboard_bp.route("/facturas")
@admin_required
def facturas():
    page = request.args.get("page", default=1, type=int)
    data = get_dashboard_data(request.args, page)
    return render_template("dashboard/facturas.html", **data)


@dashboard_bp.route("/facturas/exportar")
@admin_required
def export_csv():
    query, _ = build_filtered_query(request.args)
    records = query.order_by(emission_date_expr().desc()).all()

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "fecha_de_emision",
        "nombre_de_emisor",
        "tipo_de_documento",
        "subtotal",
        "itbms",
        "monto",
    ])

    for factura in records:
        writer.writerow([
            factura.fecha_de_emision or "",
            factura.nombre_de_emisor,
            factura.tipo_de_documento,
            factura.subtotal,
            factura.itbms,
            factura.monto,
        ])

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=facturas_filtradas.csv"},
    )
