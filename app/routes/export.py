"""
Export routes — generate Excel (.xlsx) and PDF reports for a Client.
Filters from query string are forwarded to the export queries.
"""

import io
from datetime import datetime

from flask import Blueprint, Response, abort, request, current_app
from flask_login import login_required, current_user

from app.security import get_accessible_client_or_403
from saas_models import Client

export_bp = Blueprint("export", __name__, url_prefix="/export")


def _get_own_client_or_404(client_id: int) -> Client:
    return get_accessible_client_or_403(client_id)


# ── Excel ────────────────────────────────────────────────────────────────────

@export_bp.route("/excel/<int:client_id>")
@login_required
def excel(client_id: int):
    import pandas as pd

    from app.services.analytics import build_filter_query, get_summary, get_top_providers

    client = _get_own_client_or_404(client_id)
    query, _ = build_filter_query(client_id, request.args)
    records = query.all()

    if not records:
        abort(404, "No hay datos para exportar con los filtros seleccionados.")

    summary = get_summary(client_id, request.args)
    top_providers = get_top_providers(client_id, request.args, limit=20)

    # ── Sheet 1: facturas ────────────────────────────────────────────────────
    rows = [
        {
            "ID": r.id,
            "Emisor": r.nombre_emisor,
            "RUC": r.ruc_emisor or "",
            "Fecha Emisión": r.fecha_emision.strftime("%d/%m/%Y") if r.fecha_emision else "",
            "Subtotal": float(r.subtotal or 0),
            "Impuesto": float(r.impuesto or 0),
            "Total": float(r.total or 0),
            "Tipo Documento": r.tipo_documento or "",
            "Categoría": r.categoria or "",
        }
        for r in records
    ]
    df_facturas = pd.DataFrame(rows)

    # ── Sheet 2: summary ─────────────────────────────────────────────────────
    df_summary = pd.DataFrame(
        [
            {"Métrica": "Total facturas", "Valor": summary["total_facturas"]},
            {"Métrica": "Monto total", "Valor": summary["total_monto"]},
            {"Métrica": "Impuesto total", "Valor": summary["total_impuesto"]},
            {"Métrica": "Promedio por factura", "Valor": summary["avg_factura"]},
        ]
    )

    # ── Sheet 3: top providers ───────────────────────────────────────────────
    df_prov = pd.DataFrame(
        [
            {
                "Emisor": p["nombre_emisor"],
                "Total": p["total"],
                "Facturas": p["count"],
                "% del total": f"{p['pct']:.1f}%",
            }
            for p in top_providers
        ]
    )

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df_facturas.to_excel(writer, sheet_name="Facturas", index=False)
        df_summary.to_excel(writer, sheet_name="Resumen", index=False)
        if not df_prov.empty:
            df_prov.to_excel(writer, sheet_name="Por emisor", index=False)

        # Auto-fit columns in Facturas sheet
        wb = writer.book
        ws = writer.sheets["Facturas"]
        header_fmt = wb.add_format({"bold": True, "bg_color": "#14213d", "font_color": "#ffffff"})
        for col_num, col_name in enumerate(df_facturas.columns):
            ws.write(0, col_num, col_name, header_fmt)
            width = max(len(str(col_name)), df_facturas[col_name].astype(str).str.len().max())
            ws.set_column(col_num, col_num, min(width + 2, 40))

    output.seek(0)
    filename = f"{client.name}_facturas_{datetime.now().strftime('%Y%m%d')}.xlsx"
    return Response(
        output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── PDF ──────────────────────────────────────────────────────────────────────

@export_bp.route("/pdf/<int:client_id>")
@login_required
def pdf(client_id: int):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        SimpleDocTemplate,
        Table,
        TableStyle,
        Paragraph,
        Spacer,
        HRFlowable,
    )

    from app.services.analytics import build_filter_query, get_summary, get_top_providers

    client = _get_own_client_or_404(client_id)
    query, filters = build_filter_query(client_id, request.args)
    records = query.order_by(None).limit(100).all()
    summary = get_summary(client_id, request.args)
    top_providers = get_top_providers(client_id, request.args, limit=10)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=0.75 * inch, rightMargin=0.75 * inch)
    styles = getSampleStyleSheet()
    story = []

    # ── Header ───────────────────────────────────────────────────────────────
    navy = colors.HexColor("#14213d")
    title_style = ParagraphStyle("title", parent=styles["Title"], textColor=navy, spaceAfter=4)
    sub_style = ParagraphStyle("sub", parent=styles["Normal"], textColor=colors.grey, spaceAfter=12)

    story.append(Paragraph(f"Reporte de Facturas — {client.name}", title_style))
    story.append(Paragraph(f"Generado el {datetime.now().strftime('%d/%m/%Y %H:%M')}", sub_style))
    story.append(HRFlowable(width="100%", thickness=1, color=navy))
    story.append(Spacer(1, 0.2 * inch))

    # ── Summary table ────────────────────────────────────────────────────────
    story.append(Paragraph("Resumen", styles["Heading2"]))
    summary_data = [
        ["Métrica", "Valor"],
        ["Total facturas", str(summary["total_facturas"])],
        ["Monto total", f"${summary['total_monto']:,.2f}"],
        ["Impuesto total", f"${summary['total_impuesto']:,.2f}"],
        ["Promedio por factura", f"${summary['avg_factura']:,.2f}"],
    ]
    t = Table(summary_data, colWidths=[3 * inch, 3 * inch])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), navy),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f6f8fb")]),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dee2e6")),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(t)
    story.append(Spacer(1, 0.3 * inch))

    # ── Top providers ────────────────────────────────────────────────────────
    if top_providers:
        story.append(Paragraph("Top Emisores", styles["Heading2"]))
        prov_data = [["Emisor", "Total", "Facturas", "%"]] + [
            [p["nombre_emisor"][:40], f"${p['total']:,.2f}", str(p["count"]), f"{p['pct']:.1f}%"]
            for p in top_providers
        ]
        pt = Table(prov_data, colWidths=[3.5 * inch, 1.5 * inch, 1 * inch, 0.75 * inch])
        pt.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), navy),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f6f8fb")]),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dee2e6")),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                ]
            )
        )
        story.append(pt)
        story.append(Spacer(1, 0.3 * inch))

    # ── Facturas detail (up to 100) ──────────────────────────────────────────
    story.append(Paragraph(f"Detalle de Facturas (primeras {len(records)})", styles["Heading2"]))
    fact_data = [["Fecha", "Emisor", "Subtotal", "Impuesto", "Total"]] + [
        [
            r.fecha_emision.strftime("%d/%m/%Y") if r.fecha_emision else "-",
            (r.nombre_emisor or "")[:35],
            f"${float(r.subtotal or 0):,.2f}",
            f"${float(r.impuesto or 0):,.2f}",
            f"${float(r.total or 0):,.2f}",
        ]
        for r in records
    ]
    ft = Table(
        fact_data,
        colWidths=[1.1 * inch, 3 * inch, 1.1 * inch, 1.1 * inch, 1.1 * inch],
    )
    ft.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), navy),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f6f8fb")]),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dee2e6")),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
            ]
        )
    )
    story.append(ft)

    doc.build(story)
    buf.seek(0)
    filename = f"{client.name}_reporte_{datetime.now().strftime('%Y%m%d')}.pdf"
    return Response(
        buf,
        mimetype="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
