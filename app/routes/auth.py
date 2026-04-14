import hashlib
import hmac
import string
from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from flask_login import login_user, logout_user, login_required, current_user

import bcrypt
from sqlalchemy import func, or_

from app.rbac import ensure_default_roles_for_tenant
from saas_models import Client, Role, Tenant, User, UserRole, db


auth_bp = Blueprint("auth", __name__)


def ensure_client_assignment(user: User) -> None:
    """Ensure client-role users always have a valid client_id."""
    if not user or not user.is_client or user.client_id:
        return

    if not user.tenant_id:
        tenant = Tenant(name=f"{user.full_name or user.usuario} Workspace")
        db.session.add(tenant)
        db.session.flush()
        user.tenant_id = tenant.id
        ensure_default_roles_for_tenant(tenant.id)
        default_role_name = "admin" if user.is_admin else "viewer"
        default_role = Role.query.filter_by(tenant_id=tenant.id, name=default_role_name).first()
        if default_role:
            db.session.add(UserRole(user_id=user.id, role_id=default_role.id))

    client = Client.query.filter_by(user_id=user.id).order_by(Client.id.asc()).first()
    if not client:
        client = Client(
            user_id=user.id,
            tenant_id=user.tenant_id,
            name=f"Cliente de {user.full_name or user.usuario}",
            description="Cliente auto-creado por corrección RBAC",
        )
        db.session.add(client)
        db.session.flush()
    elif client.tenant_id != user.tenant_id:
        client.tenant_id = user.tenant_id

    user.client_id = client.id
    db.session.commit()


# ── Password verification (legacy + werkzeug) ───────────────────────────────

def verify_password(plain_password: str, stored_password: str) -> bool:
    """Verify password supporting bcrypt, SHA-1, and Werkzeug hashes."""
    if not stored_password:
        return False

    # Werkzeug pbkdf2/scrypt
    if stored_password.startswith(("pbkdf2:", "scrypt:")):
        from werkzeug.security import check_password_hash
        return check_password_hash(stored_password, plain_password)

    # bcrypt ($2y$ PHP / $2b$ Python)
    if stored_password.startswith(("$2y$", "$2b$", "$2a$")):
        normalized = stored_password.replace("$2y$", "$2b$", 1)
        return bcrypt.checkpw(plain_password.encode("utf-8"), normalized.encode("utf-8"))

    # SHA-1 hex (legacy)
    is_sha1 = len(stored_password) == 40 and all(c in string.hexdigits for c in stored_password)
    if is_sha1:
        sha1 = hashlib.sha1(plain_password.encode("utf-8")).hexdigest()
        return hmac.compare_digest(sha1, stored_password.lower())

    return hmac.compare_digest(plain_password, stored_password)


def find_login_candidates(identifier: str) -> list[User]:
    """Find active users that can match a username or phone identifier."""
    candidates = User.query.filter(User.status == 1, User.usuario == identifier).all()

    phone_candidates = User.query.filter(User.status == 1, User.celular == identifier).all()
    for c in phone_candidates:
        if c not in candidates:
            candidates.append(c)

    normalized = "".join(c for c in identifier if c.isdigit())
    if normalized:
        normalized_celular = func.replace(func.replace(User.celular, "-", ""), " ", "")
        norm_candidates = User.query.filter(User.status == 1, normalized_celular == normalized).all()
        for c in norm_candidates:
            if c not in candidates:
                candidates.append(c)

    return candidates


# ── Login ────────────────────────────────────────────────────────────────────

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        ensure_client_assignment(current_user)
        if current_user.is_admin:
            return redirect(url_for("admin.index"))
        if current_user.is_client and current_user.client_id:
            return redirect(url_for("tenant.dashboard", client_id=current_user.client_id))
        return redirect(url_for("upload.index"))

    if request.method == "POST":
        identifier = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not identifier or not password:
            flash("Por favor completa todos los campos.", "warning")
            return render_template("auth/login.html")

        # Build candidate list to avoid ambiguity when the same celular exists in multiple accounts.
        candidates = find_login_candidates(identifier)

        # Pick the first account whose stored hash matches the submitted password.
        user = next((u for u in candidates if verify_password(password, u.contrasena)), None)

        if user:
            ensure_client_assignment(user)
            login_user(user, remember=True)
            # Keep legacy session keys for backward compat
            session["user"] = user.usuario
            session["user_id"] = user.id
            session["display_name"] = user.full_name

            # Role-based post-login redirect
            if user.is_admin:
                return redirect(url_for("admin.index"))

            if user.is_client and user.client_id:
                return redirect(url_for("tenant.dashboard", client_id=user.client_id))

            next_page = request.args.get("next")
            return redirect(next_page or url_for("clients.index"))

        flash("Credenciales inválidas.", "danger")

    return render_template("auth/login.html")


# ── Register ─────────────────────────────────────────────────────────────────

@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        if current_user.is_admin:
            return redirect(url_for("admin.index"))
        if current_user.is_client and current_user.client_id:
            return redirect(url_for("tenant.dashboard", client_id=current_user.client_id))
        return redirect(url_for("clients.index"))

    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        apellido = request.form.get("apellido", "").strip()
        email = request.form.get("email", "").strip().lower()
        usuario = request.form.get("usuario", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        errors = []
        if not all([nombre, email, usuario, password]):
            errors.append("Todos los campos obligatorios deben completarse.")
        if password != confirm:
            errors.append("Las contraseñas no coinciden.")
        if len(password) < 8:
            errors.append("La contraseña debe tener al menos 8 caracteres.")
        if User.query.filter_by(usuario=usuario).first():
            errors.append(f"El usuario «{usuario}» ya existe.")
        if User.query.filter_by(email=email).first():
            errors.append("Ya existe una cuenta con ese correo.")

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("auth/register.html")

        from werkzeug.security import generate_password_hash
        new_user = User(
            nombre=nombre,
            apellido=apellido,
            email=email,
            usuario=usuario,
            contrasena=generate_password_hash(password),
            nempleado="",
            celular="",
            permiso=1,
            role="client",
            status=1,
        )
        db.session.add(new_user)

        # Default registration creates tenant client profile and assigns it to the user.
        db.session.flush()
        tenant = Tenant(name=f"{new_user.full_name or new_user.usuario} Workspace")
        db.session.add(tenant)
        db.session.flush()
        new_user.tenant_id = tenant.id
        ensure_default_roles_for_tenant(tenant.id)
        client = Client(
            user_id=new_user.id,
            tenant_id=new_user.tenant_id,
            name=f"Cliente de {new_user.full_name or new_user.usuario}",
            description="Cliente creado automáticamente durante el registro",
        )
        db.session.add(client)
        db.session.flush()

        new_user.client_id = client.id
        admin_role = Role.query.filter_by(tenant_id=new_user.tenant_id, name="admin").first()
        if admin_role:
            db.session.add(UserRole(user_id=new_user.id, role_id=admin_role.id))
        db.session.commit()

        login_user(new_user, remember=True)
        session["user"] = new_user.usuario
        session["user_id"] = new_user.id
        session["display_name"] = new_user.full_name
        flash("¡Cuenta creada correctamente!", "success")
        return redirect(url_for("tenant.dashboard", client_id=new_user.client_id))

    return render_template("auth/register.html")


# ── Logout ───────────────────────────────────────────────────────────────────

@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    session.clear()
    response = redirect(url_for("auth.login"))
    response.delete_cookie("remember_token")
    return response


@auth_bp.route("/change-password", methods=["GET", "POST"])
def change_password():
    """Allow password change for logged users and from login with identity validation."""
    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip()
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        errors = []
        if not current_user.is_authenticated and not identifier:
            errors.append("Ingresa tu usuario o celular.")

        if not current_password or not new_password or not confirm_password:
            errors.append("Completa todos los campos de contraseña.")

        if len(new_password) < 8:
            errors.append("La nueva contraseña debe tener al menos 8 caracteres.")

        if new_password != confirm_password:
            errors.append("La confirmación de la contraseña no coincide.")

        if current_password and new_password and current_password == new_password:
            errors.append("La nueva contraseña debe ser diferente a la actual.")

        target_user = None
        if current_user.is_authenticated:
            target_user = current_user
            if not current_user.check_password(current_password):
                errors.append("La contraseña actual no es correcta.")
        else:
            candidates = find_login_candidates(identifier)
            target_user = next((u for u in candidates if verify_password(current_password, u.contrasena)), None)
            if not target_user:
                errors.append("Usuario/celular o contraseña actual inválidos.")

        if errors:
            for err in errors:
                flash(err, "danger")
            return render_template("auth/change_password.html")

        target_user.set_password(new_password)
        target_user.last_pass_change = datetime.utcnow()
        db.session.commit()
        flash("Contraseña actualizada correctamente.", "success")

        if not current_user.is_authenticated:
            return redirect(url_for("auth.login"))

        if current_user.is_admin:
            return redirect(url_for("admin.index"))
        if current_user.is_client and current_user.client_id:
            return redirect(url_for("tenant.dashboard", client_id=current_user.client_id))
        return redirect(url_for("upload.index"))

    return render_template("auth/change_password.html")
