import os
from urllib.parse import quote_plus

from flask import Flask, redirect, url_for
from flask_login import current_user
from flask_login import LoginManager
from dotenv import load_dotenv
from sqlalchemy import text

from models import db, User, Client


login_manager = LoginManager()


@login_manager.user_loader
def load_user(user_id: str):
    return User.query.get(int(user_id))


def create_app():
    # Render must use dashboard environment variables, not a checked-in/local .env.
    running_on_render = os.getenv("RENDER", "").lower() == "true"
    if not running_on_render:
        # Load .env file — must be first so all os.getenv() calls see the values
        load_dotenv()

    # Detect environment — defaults to production for safety
    is_production = os.getenv("FLASK_ENV", "production").lower() == "production"

    app = Flask(__name__)

    # ── Security ────────────────────────────────────────────────────────────
    secret = os.getenv("SECRET_KEY", "")
    if not secret:
        raise RuntimeError("SECRET_KEY environment variable is not set.")
    app.config["SECRET_KEY"] = secret

    # Never run with DEBUG=True in production — exposes internals
    app.config["DEBUG"] = False
    app.config["TESTING"] = False

    # Reload templates only in development (saves disk I/O in production)
    app.config["TEMPLATES_AUTO_RELOAD"] = not is_production

    # ── Upload ──────────────────────────────────────────────────────────────
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB upload limit

    # ── Session cookies ─────────────────────────────────────────────────────
    # HttpOnly prevents JavaScript from reading the session cookie (XSS protection)
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    # SameSite=Lax blocks CSRF from cross-site POST requests
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    # Secure=True sends cookies only over HTTPS — enable once SSL is active on cPanel
    app.config["SESSION_COOKIE_SECURE"] = is_production

    # ── Database ────────────────────────────────────────────────────────────
    # Build URI from individual env vars so the password is URL-encoded safely
    db_user = os.getenv("DB_USER", "root")
    db_password = os.getenv("DB_PASSWORD", "")
    db_host = os.getenv("DB_HOST", "127.0.0.1")
    db_port = os.getenv("DB_PORT", "3306")
    db_name = os.getenv("DB_NAME", "dgi_fact")
    quoted_user = quote_plus(db_user)
    quoted_password = quote_plus(db_password)

    if is_production and running_on_render and db_host in {"localhost", "127.0.0.1"}:
        raise RuntimeError(
            "Render is using localhost as DB_HOST. Configure DB_HOST/DB_PORT/DB_USER/DB_PASSWORD/DB_NAME "
            "in the Render Environment settings for your external database."
        )

    # If a full DATABASE_URL is provided it takes precedence (useful for managed DBs)
    database_url = os.getenv("DATABASE_URL") or (
        f"mysql+pymysql://{quoted_user}:{quoted_password}@{db_host}:{db_port}/{db_name}"
    )
    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # TLS options for managed MySQL providers (e.g., TiDB public endpoints).
    # If DB_SSL_REQUIRED=true or host looks like TiDB Cloud, enable TLS.
    connect_args = {"charset": "utf8mb4"}
    db_ssl_required = os.getenv("DB_SSL_REQUIRED", "").lower() in {"1", "true", "yes"}
    db_ssl_ca = os.getenv("DB_SSL_CA", "").strip()
    looks_like_tidb = "tidbcloud.com" in db_host.lower()

    if db_ssl_required or looks_like_tidb:
        ssl_args = {}
        if db_ssl_ca:
            ssl_args["ca"] = db_ssl_ca
        else:
            try:
                import certifi
                ssl_args["ca"] = certifi.where()
            except Exception:
                pass

        connect_args["ssl"] = ssl_args if ssl_args else {}

    # ── SQLAlchemy connection pool (critical for production stability) ───────
    # pool_recycle: recycle connections before MySQL's default 8-hour timeout
    # pool_pre_ping: test connection health before using it (avoids "MySQL gone away")
    # pool_size / max_overflow: tune for shared hosting with limited connections
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_recycle": 280,
        "pool_pre_ping": True,
        "pool_size": 5,
        "max_overflow": 10,
        "connect_args": connect_args,
    }

    db.init_app(app)

    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Por favor inicia sesión para continuar."
    login_manager.login_message_category = "warning"

    # ── Blueprints ──────────────────────────────────────────────────────────
    from app.routes.auth import auth_bp
    from app.routes.dashboard import dashboard_bp
    from app.routes.clients import clients_bp
    from app.routes.upload import upload_bp
    from app.routes.export import export_bp
    from app.routes.api import api_bp
    from app.routes.admin import admin_bp
    from app.routes.tenant import tenant_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(clients_bp)
    app.register_blueprint(upload_bp)
    app.register_blueprint(export_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(tenant_bp)

    # ── Create new tables and ensure RBAC schema ────────────────────────────
    with app.app_context():
        db.create_all()
        ensure_rbac_schema()
        ensure_rbac_data()

    @app.route("/")
    def root():
        if current_user.is_authenticated:
            if current_user.is_admin:
                return redirect(url_for("admin.index"))
            if current_user.is_client and current_user.client_id:
                return redirect(url_for("tenant.dashboard", client_id=current_user.client_id))
            return redirect(url_for("upload.index"))

        return redirect(url_for("auth.login"))

    return app


def ensure_rbac_schema():
    """Best-effort schema updates for role/client RBAC fields in users table."""
    inspector_query = text(
        """
        SELECT COLUMN_NAME
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'users'
          AND COLUMN_NAME IN ('role', 'client_id')
        """
    )
    existing = {row[0] for row in db.session.execute(inspector_query).all()}

    if "role" not in existing:
        db.session.execute(
            text("ALTER TABLE users ADD COLUMN role ENUM('admin','client') NOT NULL DEFAULT 'client'")
        )

    if "client_id" not in existing:
        db.session.execute(text("ALTER TABLE users ADD COLUMN client_id INT NULL"))

    try:
        db.session.execute(text("ALTER TABLE users ADD INDEX idx_users_role (role)"))
    except Exception:
        pass

    try:
        db.session.execute(text("ALTER TABLE users ADD INDEX idx_users_client_id (client_id)"))
    except Exception:
        pass

    try:
        db.session.execute(
            text(
                "ALTER TABLE users ADD CONSTRAINT fk_users_client "
                "FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE SET NULL"
            )
        )
    except Exception:
        pass

    db.session.commit()


def ensure_rbac_data():
    """Repair RBAC data inconsistencies in legacy databases."""
    changed = False

    # Client users must always have a tenant client_id.
    client_users = User.query.filter_by(role="client").all()
    for user in client_users:
        if user.client_id:
            continue

        existing_client = Client.query.filter_by(user_id=user.id).order_by(Client.id.asc()).first()
        if existing_client:
            user.client_id = existing_client.id
            changed = True
            continue

        created_client = Client(
            user_id=user.id,
            name=f"Cliente de {user.full_name or user.usuario}",
            description="Cliente auto-reparado por migración RBAC",
        )
        db.session.add(created_client)
        db.session.flush()
        user.client_id = created_client.id
        changed = True

    # Admin users should never keep tenant links.
    admin_users = User.query.filter_by(role="admin").all()
    for user in admin_users:
        if user.client_id is not None:
            user.client_id = None
            changed = True

    if changed:
        db.session.commit()
