from datetime import datetime
from decimal import Decimal, InvalidOperation

from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin


db = SQLAlchemy()


class User(UserMixin, db.Model):
    """Application user — acts as the multi-tenant account owner."""

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    nempleado = db.Column(db.String(10), nullable=True)
    nombre = db.Column(db.String(50), nullable=False)
    apellido = db.Column(db.String(50), nullable=True, default="")
    email = db.Column(db.String(100), nullable=False, index=True)
    celular = db.Column(db.String(25), nullable=True)
    direccion = db.Column(db.String(50), nullable=True)
    dir_entrega = db.Column(db.String(50), nullable=True)
    usuario = db.Column(db.String(50), nullable=False, index=True)
    contrasena = db.Column(db.String(255), nullable=False)
    permiso = db.Column(db.Integer, nullable=False, default=1)
    role = db.Column(
        db.Enum("admin", "client", name="user_role"),
        nullable=False,
        default="client",
        index=True,
    )
    client_id = db.Column(
        db.Integer,
        db.ForeignKey("clients.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status = db.Column(db.Integer, nullable=False, default=1)
    reg_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    last_pass_change = db.Column(db.DateTime, nullable=True)

    # Multi-tenant relationship
    clients = db.relationship(
        "Client",
        back_populates="owner",
        lazy="dynamic",
        cascade="all, delete-orphan",
        foreign_keys="Client.user_id",
    )
    assigned_client = db.relationship("Client", foreign_keys=[client_id], lazy="joined", post_update=True)

    @property
    def full_name(self):
        return f"{self.nombre} {self.apellido}".strip()

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def is_client(self) -> bool:
        return self.role == "client"

    def set_password(self, password: str) -> None:
        """Hash password with Werkzeug for new accounts."""
        from werkzeug.security import generate_password_hash
        self.contrasena = generate_password_hash(password)

    def check_password(self, plain: str) -> bool:
        """Verify password — supports bcrypt (legacy) and Werkzeug hashes."""
        import hashlib
        import hmac
        import string

        stored = self.contrasena or ""

        # Werkzeug pbkdf2/scrypt hash
        if stored.startswith(("pbkdf2:", "scrypt:")):
            from werkzeug.security import check_password_hash
            return check_password_hash(stored, plain)

        # bcrypt hash ($2y$ / $2b$ / $2a$)
        if stored.startswith(("$2y$", "$2b$", "$2a$")):
            import bcrypt
            normalized = stored.replace("$2y$", "$2b$", 1)
            return bcrypt.checkpw(plain.encode("utf-8"), normalized.encode("utf-8"))

        # SHA-1 hex (legacy)
        if len(stored) == 40 and all(c in string.hexdigits for c in stored):
            sha1 = hashlib.sha1(plain.encode("utf-8")).hexdigest()
            return hmac.compare_digest(sha1, stored.lower())

        return hmac.compare_digest(plain, stored)


class Client(db.Model):
    """A client/entity owned by a User — isolates financial data per tenant."""

    __tablename__ = "clients"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = db.Column(db.String(100), nullable=False)
    ruc = db.Column(db.String(50), nullable=True)
    description = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    owner = db.relationship("User", back_populates="clients", foreign_keys=[user_id])

    facturas = db.relationship(
        "Factura",
        backref="client",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )

    @property
    def total_facturas(self) -> int:
        return self.facturas.count()


class Factura(db.Model):
    """Individual invoice/transaction linked to a Client (multi-tenant)."""

    __tablename__ = "facturas"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    client_id = db.Column(
        db.Integer,
        db.ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    nombre_emisor = db.Column(db.String(255), nullable=False, index=True)
    ruc_emisor = db.Column(db.String(50), nullable=True, index=True)
    fecha_emision = db.Column(db.DateTime, nullable=True, index=True)
    total = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    impuesto = db.Column(db.Numeric(14, 2), nullable=True, default=0)
    subtotal = db.Column(db.Numeric(14, 2), nullable=True, default=0)
    tipo_documento = db.Column(db.String(100), nullable=True)
    naturaleza_operacion = db.Column(db.String(255), nullable=True)
    categoria = db.Column(db.String(100), nullable=True, index=True)
    cufe = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "client_id": self.client_id,
            "nombre_emisor": self.nombre_emisor,
            "ruc_emisor": self.ruc_emisor,
            "fecha_emision": self.fecha_emision.isoformat() if self.fecha_emision else None,
            "total": float(self.total or 0),
            "impuesto": float(self.impuesto or 0),
            "subtotal": float(self.subtotal or 0),
            "tipo_documento": self.tipo_documento,
            "categoria": self.categoria,
        }


class FacturaDGI(db.Model):
    __tablename__ = "factura_dgi"

    numero_ruc = db.Column(db.String(50), nullable=True, index=True)
    usuario = db.Column(db.String(150), nullable=True, index=True)
    cufe = db.Column("CUFE", db.String(255), primary_key=True)
    tipo_de_documento = db.Column(db.String(100), nullable=False)
    fecha_de_emision = db.Column(db.String(255), nullable=True, index=True)
    fecha_de_autorizacion = db.Column("fecha_de_Autorizacion", db.String(255), nullable=True)
    iden_emisor = db.Column(db.String(50), nullable=True, index=True)
    nombre_de_emisor = db.Column("nombre_de_emisor", db.String(255), nullable=False, index=True)
    subtotal = db.Column(db.String(255), nullable=True, default="0")
    itbms = db.Column(db.String(255), nullable=True, default="0")
    monto = db.Column(db.String(255), nullable=True, default="0")
    codigo_sucursal = db.Column(db.String(50), nullable=True)
    naturaleza_de_la_operacion = db.Column(db.String(255), nullable=True)
    tipo_de_operacion = db.Column(db.String(255), nullable=True)
    destino_de_la_operacion = db.Column("destino_de_la_peracion", db.String(255), nullable=True)
    tiempo_de_pago = db.Column(db.String(255), nullable=True)

    @staticmethod
    def parse_decimal(raw_value):
        if raw_value in (None, ""):
            return Decimal("0")

        cleaned_value = str(raw_value).replace(",", "").replace("$", "").strip()
        try:
            return Decimal(cleaned_value)
        except InvalidOperation:
            return Decimal("0")

    @property
    def subtotal_value(self):
        return self.parse_decimal(self.subtotal)

    @property
    def itbms_value(self):
        return self.parse_decimal(self.itbms)

    @property
    def monto_value(self):
        return self.parse_decimal(self.monto)

    def to_dict(self):
        return {
            "numero_ruc": self.numero_ruc,
            "usuario": self.usuario,
            "cufe": self.cufe,
            "tipo_de_documento": self.tipo_de_documento,
            "fecha_de_emision": self.fecha_de_emision or "",
            "fecha_de_autorizacion": self.fecha_de_autorizacion or "",
            "iden_emisor": self.iden_emisor,
            "nombre_de_emisor": self.nombre_de_emisor,
            "subtotal": float(self.subtotal_value),
            "itbms": float(self.itbms_value),
            "monto": float(self.monto_value),
            "codigo_sucursal": self.codigo_sucursal,
            "naturaleza_de_la_operacion": self.naturaleza_de_la_operacion,
            "tipo_de_operacion": self.tipo_de_operacion,
        }
