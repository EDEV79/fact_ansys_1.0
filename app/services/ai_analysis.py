"""
AI expense analysis service — rule-based categorisation and insight generation.
No external API required; uses keyword matching + statistical heuristics.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

# ---------------------------------------------------------------------------
# Category rules — (category_key, [keyword substrings])
# Priority: first match wins (most specific rules first)
# ---------------------------------------------------------------------------
CATEGORY_RULES: list[tuple[str, list[str]]] = [
    ("servicios_publicos", [
        "electricidad", "enet", "etesa", "idaan", "agua", "gas natural",
        "cable", "internet", "claro", "tigo", "digicel", "movistar",
        "mas movil", "cwp", "natcom", "telecomunicacion",
    ]),
    ("combustible", [
        "gasolina", "combustible", "petro", "puma", "delta oil",
        "uno oil", "texaco", "shell", "bp oil", "primax", "zeta gas",
    ]),
    ("transporte", [
        "taxi", "uber", "cabify", "lyft", "bus", "metro", "peaje",
        "transporte", "aerolinea", "copa airlines", "air panama", "vuelo",
    ]),
    ("alimentacion", [
        "restauran", "comida", "alimentos", "super 99", "riba smith",
        "rey", "macrobiotica", "fresh market", "el machetazo",
        "cafe", "casablanca", "niko", "pollo", "pizza", "burger",
        "soda", "mercado", "panaderia", "frutas", "verduras",
    ]),
    ("salud", [
        "farmacia", "arrocha", "metro plus", "medico", "hospital",
        "clinica", "laboratorio", "salud", "dental", "optica",
        "gorgas", "caja de seguro", "css",
    ]),
    ("oficina_papeleria", [
        "office depot", "papeleria", "imprenta", "toner", "papel bond",
        "computadora", "laptop", "monitor", "teclado", "impresora",
        "cartucho", "fotocopiadora",
    ]),
    ("tecnologia", [
        "amazon", "microsoft", "adobe", "google", "apple", "software",
        "licencia", "hosting", "dominio", "nube", "cloud", "saas",
    ]),
    ("construccion_ferreteria", [
        "ferreteria", "do it center", "novey", "el yanqui", "construrama",
        "construccion", "cemento", "tuberia", "varilla", "madera",
        "pintura", "material",
    ]),
    ("entretenimiento", [
        "cine", "teatro", "albrook mall", "multiplaza", "costa del este",
        "entretenimiento", "juego", "deporte", "gym", "fitness", "piscina",
    ]),
    ("financiero_seguros", [
        "banco", "bank", "seguro", "insurance", "aseguradora",
        "prestamo", "credito", "financiera", "caja de ahorros",
        "global bank", "banistmo", "bac", "scotiabank", "hsbc",
    ]),
    ("servicios_profesionales", [
        "consultor", "asesoria", "abogado", "contador", "juridico",
        "legal", "auditoria", "notaria", "registro", "tramite",
    ]),
    ("publicidad_marketing", [
        "publicidad", "marketing", "agencia", "diseño", "imprenta",
        "volante", "banner", "redes sociales", "seo",
    ]),
    ("limpieza_mantenimiento", [
        "limpieza", "mantenimiento", "aseo", "conserjeria", "jardineria",
        "plomeria", "electricista", "reparacion", "fumigacion",
    ]),
]

# Human-readable category labels
CATEGORY_LABELS: dict[str, str] = {
    "alimentacion": "Alimentación",
    "transporte": "Transporte",
    "combustible": "Combustible",
    "servicios_publicos": "Servicios públicos",
    "oficina_papeleria": "Oficina / Papelería",
    "tecnologia": "Tecnología",
    "salud": "Salud",
    "construccion_ferreteria": "Construcción / Ferretería",
    "entretenimiento": "Entretenimiento",
    "financiero_seguros": "Financiero / Seguros",
    "servicios_profesionales": "Servicios profesionales",
    "publicidad_marketing": "Publicidad / Marketing",
    "limpieza_mantenimiento": "Limpieza / Mantenimiento",
    "otro": "Otro",
    "sin_categoria": "Sin categoría",
}


# ---------------------------------------------------------------------------
# Categorisation
# ---------------------------------------------------------------------------

def categorize_factura(nombre_emisor: str) -> str:
    """Map a provider name to a category using keyword rules."""
    if not nombre_emisor:
        return "otro"

    text = nombre_emisor.lower()
    text = re.sub(r"\s+", " ", text)

    for category, keywords in CATEGORY_RULES:
        if any(kw in text for kw in keywords):
            return category

    return "otro"


def get_category_label(key: str) -> str:
    return CATEGORY_LABELS.get(key, key.replace("_", " ").title())


# ---------------------------------------------------------------------------
# Main analysis function
# ---------------------------------------------------------------------------

def analyze_expenses(client_id: int) -> dict[str, Any]:
    """
    Generate rule-based insights for a client's expense data.

    Returns a dict with:
    - insights: list of human-readable insight strings
    - top_category: str
    - top_provider: str
    - anomalies: list of months with unusual spend
    - category_breakdown: dict[str, float]
    """
    from app.services.analytics import (
        get_expense_by_category,
        get_monthly_expenses,
        get_top_providers,
        get_summary,
    )
    from flask import request as flask_request

    # Use no filters for AI analysis to get the full picture
    class EmptyArgs:
        def get(self, *_a, **_kw):
            return ""

    args = EmptyArgs()

    summary = get_summary(client_id, args)
    if summary["total_facturas"] == 0:
        return {"insights": ["No hay datos suficientes para generar análisis."], "anomalies": []}

    categories = get_expense_by_category(client_id)
    monthly = get_monthly_expenses(client_id, args)
    providers = get_top_providers(client_id, args, limit=5)

    insights: list[str] = []
    anomalies: list[dict] = []

    # ── Category insights ────────────────────────────────────────────────────
    top_cat = categories[0] if categories else None
    if top_cat:
        label = get_category_label(top_cat["categoria"])
        insights.append(
            f"Tu categoría de mayor gasto es «{label}» "
            f"con ${top_cat['total']:,.2f} ({top_cat['pct']:.1f}% del total)."
        )

    # ── Provider insights ────────────────────────────────────────────────────
    if providers:
        top_prov = providers[0]
        insights.append(
            f"El emisor principal es «{top_prov['nombre_emisor']}» "
            f"con ${top_prov['total']:,.2f} ({top_prov['pct']:.1f}% del gasto total)."
        )

    # ── Monthly trend anomaly detection ─────────────────────────────────────
    if len(monthly) >= 3:
        totals = [m["total"] for m in monthly]
        avg = sum(totals[:-1]) / len(totals[:-1])  # average excluding last month
        last = monthly[-1]

        if avg > 0:
            change_pct = (last["total"] - avg) / avg * 100
            if change_pct >= 30:
                insights.append(
                    f"⚠️  En {last['month_label']} gastaste ${last['total']:,.2f}, "
                    f"un {change_pct:.0f}% más que el promedio mensual (${avg:,.2f})."
                )
                anomalies.append(
                    {
                        "month": last["month"],
                        "month_label": last["month_label"],
                        "total": last["total"],
                        "avg": avg,
                        "change_pct": change_pct,
                    }
                )
            elif change_pct <= -30:
                insights.append(
                    f"✓ En {last['month_label']} redujiste gastos un {abs(change_pct):.0f}% "
                    f"respecto al promedio mensual."
                )

    # ── High average ticket ──────────────────────────────────────────────────
    if summary["avg_factura"] > 1000:
        insights.append(
            f"El monto promedio por factura es ${summary['avg_factura']:,.2f} — "
            "considera revisar facturas de alto valor individualmente."
        )

    # ── Category diversity ───────────────────────────────────────────────────
    if top_cat and top_cat["pct"] > 70:
        label = get_category_label(top_cat["categoria"])
        insights.append(
            f"Más del 70% de tu gasto está concentrado en «{label}». "
            "Considera diversificar proveedores para mejores precios."
        )

    # ── Low transaction count ────────────────────────────────────────────────
    if summary["total_facturas"] < 5:
        insights.append(
            "Tienes pocos registros. Sube más datos para obtener análisis más precisos."
        )

    return {
        "insights": insights or ["No se detectaron patrones inusuales."],
        "top_category": top_cat["categoria"] if top_cat else None,
        "top_provider": providers[0]["nombre_emisor"] if providers else None,
        "anomalies": anomalies,
        "category_breakdown": {c["categoria"]: c["total"] for c in categories},
    }
