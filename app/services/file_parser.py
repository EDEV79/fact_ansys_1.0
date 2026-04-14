"""Flexible and fault-tolerant ingestion service for CSV, Excel, and JSON uploads."""

from __future__ import annotations

import io
import logging
import re
import unicodedata
from datetime import datetime
from difflib import get_close_matches
from pathlib import Path
from typing import Any

import pandas as pd

from app.services.ai_analysis import categorize_factura
from saas_models import Client, Factura, db

logger = logging.getLogger(__name__)

CANONICAL_ALIASES: dict[str, list[str]] = {
    "cufe": ["cufe", "cudf"],
    "tipo_documento": [
        "tipo_documento",
        "tipo de documento",
        "tipo",
        "document_type",
        "tipo doc",
        "documento",
    ],
    "fecha_emision": [
        "fecha_emision",
        "fecha de emision",
        "fecha",
        "date",
        "invoice_date",
        "emission_date",
        "fecha factura",
    ],
    "ruc_emisor": [
        "ruc_emisor",
        "ruc",
        "nit",
        "numero_ruc",
        "iden_emisor",
        "tax_id",
    ],
    "nombre_emisor": [
        "nombre_emisor",
        "nombre del emisor",
        "nombre de emisor",
        "emisor",
        "proveedor",
        "provider",
        "supplier",
        "vendor",
    ],
    "subtotal": ["subtotal", "sub_total", "net_amount", "base_imponible"],
    "impuesto": ["impuesto", "itbms", "iva", "tax", "tax_amount", "taxes"],
    "total": ["total", "monto", "amount", "valor", "grand_total", "total_amount"],
    "naturaleza_operacion": [
        "naturaleza_operacion",
        "naturaleza",
        "naturaleza de la operacion",
    ],
}

CANONICAL_FIELDS = tuple(CANONICAL_ALIASES.keys())
REQUIRED_FIELDS = ("total", "fecha_emision")

DATE_FORMATS = (
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%d/%m/%Y",
    "%Y-%m-%d",
    "%m/%d/%Y",
    "%d-%m-%Y",
)


def _normalize_key(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


def _alias_reverse_map() -> tuple[dict[str, str], list[str]]:
    alias_to_canonical: dict[str, str] = {}
    alias_keys: list[str] = []
    for canonical, aliases in CANONICAL_ALIASES.items():
        normalized_canonical = _normalize_key(canonical)
        alias_to_canonical[normalized_canonical] = canonical
        if normalized_canonical not in alias_keys:
            alias_keys.append(normalized_canonical)
        for alias in aliases:
            normalized_alias = _normalize_key(alias)
            alias_to_canonical[normalized_alias] = canonical
            if normalized_alias not in alias_keys:
                alias_keys.append(normalized_alias)
    return alias_to_canonical, alias_keys


ALIAS_TO_CANONICAL, ALIAS_KEYS = _alias_reverse_map()


def _read_csv(raw: bytes) -> pd.DataFrame:
    for encoding in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
        for sep in (None, ",", ";", "\t", "|"):
            try:
                if sep is None:
                    return pd.read_csv(
                        io.BytesIO(raw),
                        engine="python",
                        sep=None,
                        encoding=encoding,
                        dtype=str,
                        on_bad_lines="skip",
                    )
                return pd.read_csv(
                    io.BytesIO(raw),
                    sep=sep,
                    encoding=encoding,
                    dtype=str,
                    on_bad_lines="skip",
                )
            except Exception:
                continue
    raise ValueError("No se pudo leer el archivo CSV. Verifica formato y codificacion.")


def _read_dataframe(filename: str, raw: bytes) -> pd.DataFrame:
    lower = (filename or "").lower()
    if lower.endswith(".csv"):
        return _read_csv(raw)
    if lower.endswith((".xlsx", ".xls")):
        return pd.read_excel(io.BytesIO(raw), dtype=str)
    if lower.endswith(".json"):
        return pd.read_json(io.BytesIO(raw), dtype=str)
    raise ValueError("Formato de archivo no soportado. Usa CSV, XLSX/XLS o JSON.")


def _map_columns(source_columns: list[str]) -> tuple[dict[str, str], list[dict[str, str]], list[str]]:
    rename_map: dict[str, str] = {}
    mapped: list[dict[str, str]] = []
    unmapped: list[str] = []
    used_targets: set[str] = set()

    for source_col in source_columns:
        normalized = _normalize_key(source_col)
        canonical = ALIAS_TO_CANONICAL.get(normalized)
        mode = "exact"

        if not canonical:
            fuzzy = get_close_matches(normalized, ALIAS_KEYS, n=1, cutoff=0.83)
            if fuzzy:
                canonical = ALIAS_TO_CANONICAL.get(fuzzy[0])
                mode = "fuzzy"

        if not canonical:
            unmapped.append(str(source_col))
            continue

        if canonical in used_targets:
            logger.warning(
                "Duplicate mapped target detected: source=%s target=%s (ignored)", source_col, canonical
            )
            unmapped.append(str(source_col))
            continue

        used_targets.add(canonical)
        rename_map[source_col] = canonical
        mapped.append({"source": str(source_col), "target": canonical, "mode": mode})

    return rename_map, mapped, unmapped


def _prepare_dataframe(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    original_columns = [str(c) for c in df.columns]
    rename_map, mapped, unmapped = _map_columns(list(df.columns))
    normalized_df = df.rename(columns=rename_map)
    normalized_df = normalized_df[[c for c in normalized_df.columns if c in CANONICAL_FIELDS]]

    warnings: list[str] = []
    missing_required = [field for field in REQUIRED_FIELDS if field not in normalized_df.columns]
    if missing_required:
        message = (
            f"Columnas importantes faltantes: {', '.join(missing_required)}. "
            "Se importara usando valores vacios o 0 cuando aplique."
        )
        logger.warning(message)
        warnings.append(message)

    if unmapped:
        message = f"Columnas ignoradas: {', '.join(unmapped)}"
        logger.warning(message)
        warnings.append(message)

    for field in CANONICAL_FIELDS:
        if field not in normalized_df.columns:
            normalized_df[field] = None

    normalized_df = normalized_df.where(pd.notna(normalized_df), None)

    analysis = {
        "row_count": int(len(normalized_df.index)),
        "detected_columns": original_columns,
        "mapped_columns": mapped,
        "unmapped_columns": unmapped,
        "missing_required": missing_required,
        "warnings": warnings,
    }
    return normalized_df, analysis


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null"}:
        return None
    return text


def _parse_date(value: Any) -> datetime | None:
    text = _clean_text(value)
    if not text:
        return None

    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue

    try:
        return pd.to_datetime(text, dayfirst=True, errors="coerce").to_pydatetime()
    except Exception:
        return None


def _clean_numeric(value: Any, default: float = 0.0) -> float:
    text = _clean_text(value)
    if text is None:
        return default

    cleaned = re.sub(r"[^\d,\.\-]", "", text)
    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")

    try:
        return float(cleaned)
    except ValueError:
        return default


def _load_and_prepare(raw: bytes, filename: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    df = _read_dataframe(filename, raw)
    if df.empty:
        raise ValueError("El archivo esta vacio o no contiene filas validas.")
    return _prepare_dataframe(df)


def _sample_rows(df: pd.DataFrame, size: int = 5) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    fields = [
        "cufe",
        "tipo_documento",
        "fecha_emision",
        "ruc_emisor",
        "nombre_emisor",
        "subtotal",
        "impuesto",
        "total",
    ]
    for _, row in df.head(size).iterrows():
        rows.append({field: row.get(field) for field in fields})
    return rows


def analyze_upload(file_storage) -> dict[str, Any]:
    raw = file_storage.read()
    filename = file_storage.filename or "upload"
    normalized_df, analysis = _load_and_prepare(raw, filename)
    analysis["sample_rows"] = _sample_rows(normalized_df)
    return analysis


def analyze_upload_path(file_path: str | Path, original_filename: str) -> dict[str, Any]:
    raw = Path(file_path).read_bytes()
    normalized_df, analysis = _load_and_prepare(raw, original_filename)
    analysis["sample_rows"] = _sample_rows(normalized_df)
    return analysis


def _build_facturas(df: pd.DataFrame, client_id: int) -> tuple[list[Factura], int, int]:
    facturas: list[Factura] = []
    skipped = 0
    patched_names = 0
    client = Client.query.get(client_id)
    tenant_id = client.tenant_id if client else None

    for _, row in df.iterrows():
        nombre = _clean_text(row.get("nombre_emisor"))
        if not nombre:
            nombre = "EMISOR DESCONOCIDO"
            patched_names += 1

        total = _clean_numeric(row.get("total"), default=0.0)
        cufe = _clean_text(row.get("cufe"))

        if cufe and Factura.query.filter_by(cufe=cufe).first():
            skipped += 1
            continue

        facturas.append(
            Factura(
                tenant_id=tenant_id,
                client_id=client_id,
                nombre_emisor=nombre,
                ruc_emisor=_clean_text(row.get("ruc_emisor")),
                fecha_emision=_parse_date(row.get("fecha_emision")),
                total=total,
                impuesto=_clean_numeric(row.get("impuesto"), default=0.0),
                subtotal=_clean_numeric(row.get("subtotal"), default=0.0),
                tipo_documento=_clean_text(row.get("tipo_documento")),
                naturaleza_operacion=_clean_text(row.get("naturaleza_operacion")),
                categoria=categorize_factura(nombre),
                cufe=cufe,
            )
        )

    return facturas, skipped, patched_names


def _insert_from_raw(raw: bytes, filename: str, client_id: int) -> dict[str, Any]:
    normalized_df, analysis = _load_and_prepare(raw, filename)
    facturas, skipped, patched_names = _build_facturas(normalized_df, client_id)

    if not facturas and skipped == 0:
        raise ValueError("No se encontraron filas validas para importar.")

    if patched_names:
        warning = (
            f"{patched_names} fila(s) sin nombre_emisor fueron guardadas como 'EMISOR DESCONOCIDO'."
        )
        analysis["warnings"].append(warning)
        logger.warning(warning)

    db.session.bulk_save_objects(facturas)
    return {
        "inserted": len(facturas),
        "skipped": skipped,
        "warnings": analysis.get("warnings", []),
        "missing_required": analysis.get("missing_required", []),
    }


def insert_upload(file_storage, client_id: int) -> dict[str, Any]:
    raw = file_storage.read()
    filename = file_storage.filename or "upload"
    return _insert_from_raw(raw, filename, client_id)


def insert_upload_path(file_path: str | Path, original_filename: str, client_id: int) -> dict[str, Any]:
    raw = Path(file_path).read_bytes()
    return _insert_from_raw(raw, original_filename, client_id)


def parse_upload(file_storage, client_id: int) -> dict[str, Any]:
    """Backward-compatible wrapper used by previous route implementation."""
    return insert_upload(file_storage, client_id)
