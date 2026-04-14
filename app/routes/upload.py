"""
File upload route — accepts .csv, .xlsx, .json files and imports
them as Factura records linked to a Client.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import login_required, current_user

from app.security import get_accessible_client_or_403
from saas_models import Client, db

upload_bp = Blueprint("upload", __name__, url_prefix="/upload")

ALLOWED_EXTENSIONS = {"csv", "xlsx", "xls", "json"}


def _allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _load_clients_context() -> tuple[list[Client], int | None]:
    if current_user.is_admin:
        clients = Client.query.filter_by(tenant_id=current_user.tenant_id).order_by(Client.name).all()
        preselect = request.args.get("client_id", type=int)
    else:
        clients = (
            Client.query.filter_by(id=current_user.client_id, tenant_id=current_user.tenant_id).all()
            if current_user.client_id
            else []
        )
        preselect = current_user.client_id
    return clients, preselect


def _staging_dir() -> Path:
    path = Path(current_app.instance_path) / "upload_staging"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _build_redirect_after_upload(client_id: int):
    if current_user.is_admin:
        return redirect(url_for("clients.detail", client_id=client_id))
    return redirect(url_for("tenant.dashboard", client_id=client_id))


@upload_bp.route("/", methods=["GET"])
@login_required
def index():
    clients, preselect = _load_clients_context()
    return render_template("upload/index.html", clients=clients, preselect=preselect, preview=None)


@upload_bp.route("/", methods=["POST"])
@login_required
def upload():
    from app.services.file_parser import analyze_upload_path, insert_upload_path

    submitted_client_id = request.form.get("client_id", type=int)
    client_id = submitted_client_id if current_user.is_admin else current_user.client_id
    action = request.form.get("action", "preview")

    # ── Validate client ownership ────────────────────────────────────────────
    if not client_id:
        flash("Debes seleccionar un cliente válido.", "danger")
        return redirect(url_for("upload.index"))

    try:
        client = get_accessible_client_or_403(client_id)
    except Exception:
        flash("Cliente no válido o no tienes permiso.", "danger")
        return redirect(url_for("upload.index"))

    if action == "confirm":
        preview_token = request.form.get("preview_token", "")
        preview_state = request.form.get("preview_state", "")
        session_payload = session.get("upload_preview")

        if not preview_token or not preview_state or not session_payload:
            flash("La previsualizacion expiro. Vuelve a cargar el archivo.", "warning")
            return redirect(url_for("upload.index", client_id=client_id))

        if (
            preview_token != session_payload.get("token")
            or preview_state != session_payload.get("state")
            or session_payload.get("client_id") != client_id
        ):
            flash("La confirmacion no coincide con la previsualizacion actual.", "danger")
            return redirect(url_for("upload.index", client_id=client_id))

        staged_path = Path(session_payload.get("path", ""))
        original_filename = session_payload.get("original_filename", "upload")
        if not staged_path.exists():
            session.pop("upload_preview", None)
            flash("No se encontro el archivo temporal. Sube el archivo nuevamente.", "warning")
            return redirect(url_for("upload.index", client_id=client_id))

        try:
            result = insert_upload_path(staged_path, original_filename, client_id)
            db.session.commit()
            flash(
                f"✓ {result['inserted']} facturas importadas"
                + (f" ({result['skipped']} duplicadas omitidas)." if result["skipped"] else "."),
                "success",
            )
            for warning in result.get("warnings", []):
                flash(warning, "warning")
        except ValueError as exc:
            db.session.rollback()
            flash(f"Error en el archivo: {exc}", "danger")
            return redirect(url_for("upload.index", client_id=client_id))
        except Exception as exc:
            db.session.rollback()
            current_app.logger.exception("Upload confirm error: %s", exc)
            flash("Error inesperado al procesar la importacion.", "danger")
            return redirect(url_for("upload.index", client_id=client_id))
        finally:
            try:
                staged_path.unlink(missing_ok=True)
            except OSError:
                current_app.logger.warning("No se pudo eliminar temporal: %s", staged_path)
            session.pop("upload_preview", None)

        return _build_redirect_after_upload(client_id)

    file = request.files.get("file")
    if not file or file.filename == "":
        flash("No seleccionaste ningun archivo.", "warning")
        return redirect(url_for("upload.index", client_id=client_id))

    if not _allowed_file(file.filename):
        flash("Formato no soportado. Usa .csv, .xlsx, .xls o .json.", "danger")
        return redirect(url_for("upload.index", client_id=client_id))

    extension = file.filename.rsplit(".", 1)[1].lower()
    token = uuid.uuid4().hex
    staged_path = _staging_dir() / f"{token}.{extension}"

    try:
        file_bytes = file.read()
        staged_path.write_bytes(file_bytes)
        preview = analyze_upload_path(staged_path, file.filename)
        preview_state = uuid.uuid4().hex
        preview["token"] = token
        preview["state"] = preview_state
        preview["client_id"] = client_id
        preview["filename"] = file.filename

        session["upload_preview"] = {
            "token": token,
            "state": preview_state,
            "path": str(staged_path),
            "client_id": client_id,
            "original_filename": file.filename,
        }

        clients, _ = _load_clients_context()
        return render_template("upload/index.html", clients=clients, preselect=client_id, preview=preview)
    except ValueError as exc:
        flash(f"Error en el archivo: {exc}", "danger")
    except Exception as exc:
        current_app.logger.exception("Upload preview error: %s", exc)
        flash("Error inesperado al previsualizar el archivo.", "danger")
    finally:
        if not session.get("upload_preview") or session["upload_preview"].get("token") != token:
            try:
                os.remove(staged_path)
            except OSError:
                pass

    return redirect(url_for("upload.index", client_id=client_id))
