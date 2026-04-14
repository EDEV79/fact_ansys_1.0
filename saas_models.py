from datetime import datetime
from decimal import Decimal, InvalidOperation

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy


db = SQLAlchemy()


class Tenant(db.Model):
    """A company/workspace in the multi-tenant SaaS environment."""

    __tablename__ = "tenants"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    users = db.relationship("User", back_populates="tenant", lazy="dynamic")
    roles = db.relationship("Role", back_populates="tenant", lazy="dynamic", cascade="all, delete-orphan")
    clients = db.relationship("Client", back_populates="tenant", lazy="dynamic")
    facturas = db.relationship("Factura", back_populates="tenant", lazy="dynamic")


class UserRole(db.Model):
    __tablename__ = "user_roles"
    __table_args__ = (
        db.UniqueConstraint("user_id", "role_id", name="uq_user_roles_user_role"),
        db.Index("idx_user_roles_user_id", "user_id"),
        db.Index("idx_user_roles_role_id", "role_id"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role_id = db.Column(db.Integer, db.ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    user = db.relationship("User", back_populates="user_role_links", overlaps="roles,users")
    role = db.relationship("Role", back_populates="user_role_links", overlaps="roles,users")


class RolePermission(db.Model):
    __tablename__ = "role_permissions"
    __table_args__ = (
        db.UniqueConstraint("role_id", "permission_id", name="uq_role_permissions_role_permission"),
        db.Index("idx_role_permissions_role_id", "role_id"),
        db.Index("idx_role_permissions_permission_id", "permission_id"),
    )

    id = db.Column(db.Integer, primary_key=True)
    role_id = db.Column(db.Integer, db.ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)
    permission_id = db.Column(db.Integer, db.ForeignKey("permissions.id", ondelete="CASCADE"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    role = db.relationship("Role", back_populates="role_permission_links", overlaps="permissions,roles")
    permission = db.relationship(
        "Permission",
        back_populates="role_permission_links",
        overlaps="permissions,roles",
    )


class Role(db.Model):
    __tablename__ = "roles"
    __table_args__ = (
        db.UniqueConstraint("tenant_id", "name", name="uq_roles_tenant_name"),
        db.Index("idx_roles_tenant_id", "tenant_id"),
    )

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    name = db.Column(db.String(50), nullable=False)
    description = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    tenant = db.relationship("Tenant", back_populates="roles")
    user_role_links = db.relationship(
        "UserRole",
        back_populates="role",
        cascade="all, delete-orphan",
        overlaps="roles,users",
    )
    role_permission_links = db.relationship(
        "RolePermission",
        back_populates="role",
        cascade="all, delete-orphan",
        overlaps="permissions,roles",
    )
    users = db.relationship(
        "User",
        secondary="user_roles",
        back_populates="roles",
        overlaps="user,user_role_links,role",
        lazy="selectin",
    )
    permissions = db.relationship(
        "Permission",
        secondary="role_permissions",
        back_populates="roles",
        overlaps="role,role_permission_links,permission",
        lazy="selectin",
    )


class Permission(db.Model):
    __tablename__ = "permissions"
    __table_args__ = (
        db.UniqueConstraint("name", name="uq_permissions_name"),
        db.Index("idx_permissions_module_action", "module", "action"),
    )

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    module = db.Column(db.String(50), nullable=False)
    action = db.Column(db.String(50), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    role_permission_links = db.relationship(
        "RolePermission",
        back_populates="permission",
        cascade="all, delete-orphan",
        overlaps="permissions,roles",
    )
    roles = db.relationship(
        "Role",
        secondary="role_permissions",
        back_populates="permissions",
        overlaps="role,role_permission_links,permission",
        lazy="selectin",
    )


class User(UserMixin, db.Model):
    """Application user with legacy profile fields plus tenant-aware RBAC."""

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True)
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
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    reg_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    last_pass_change = db.Column(db.DateTime, nullable=True)

    tenant = db.relationship("Tenant", back_populates="users")
    clients = db.relationship(
        "Client",
        back_populates="owner",
        lazy="dynamic",
        cascade="all, delete-orphan",
        foreign_keys="Client.user_id",
    )
    assigned_client = db.relationship("Client", foreign_keys=[client_id], lazy="joined", post_update=True)
    user_role_links = db.relationship(
        "UserRole",
        back_populates="user",
        cascade="all, delete-orphan",
        overlaps="roles,users",
    )
    roles = db.relationship(
        "Role",
        secondary="user_roles",
        back_populates="users",
        overlaps="user,user_role_links,role",
        lazy="selectin",
    )

    @property
    def full_name(self):
        return f"{self.nombre} {self.apellido}".strip()

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def is_client(self) -> bool:
        return self.role == "client"

    @property
    def is_active(self) -> bool:
        return self.status == 1

    @property
    def role_names(self) -> list[str]:
        return sorted({role.name for role in self.roles})

    def has_role(self, role_name: str) -> bool:
        return role_name in self.role_names

    def has_permission(self, permission_name: str) -> bool:
        from app.rbac import has_permission

        return has_permission(self.id, permission_name, tenant_id=self.tenant_id)

    def set_password(self, password: str) -> None:
        from werkzeug.security import generate_password_hash

        self.contrasena = generate_password_hash(password)

    def check_password(self, plain: str) -> bool:
        import hashlib
        import hmac
        import string

        stored = self.contrasena or ""

        if stored.startswith(("pbkdf2:", "scrypt:")):
            from werkzeug.security import check_password_hash

            return check_password_hash(stored, plain)

        if stored.startswith(("$2y$", "$2b$", "$2a$")):
            import bcrypt

            normalized = stored.replace("$2y$", "$2b$", 1)
            return bcrypt.checkpw(plain.encode("utf-8"), normalized.encode("utf-8"))

        if len(stored) == 40 and all(c in string.hexdigits for c in stored):
            sha1 = hashlib.sha1(plain.encode("utf-8")).hexdigest()
            return hmac.compare_digest(sha1, stored.lower())

        return hmac.compare_digest(plain, stored)


class Client(db.Model):
    """Tenant-owned client entity used by the current application."""

    __tablename__ = "clients"
    __table_args__ = (
        db.Index("idx_clients_tenant_id", "tenant_id"),
        db.Index("idx_clients_user_tenant", "user_id", "tenant_id"),
    )

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True)
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

    tenant = db.relationship("Tenant", back_populates="clients")
    owner = db.relationship("User", back_populates="clients", foreign_keys=[user_id])
    facturas = db.relationship(
        "Factura",
        back_populates="client",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )

    @property
    def total_facturas(self) -> int:
        return self.facturas.count()


class Factura(db.Model):
    """Individual invoice/transaction linked to a tenant and client."""

    __tablename__ = "facturas"
    __table_args__ = (
        db.Index("idx_facturas_tenant_id", "tenant_id"),
        db.Index("idx_facturas_tenant_client", "tenant_id", "client_id"),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True)
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
    cufe = db.Column(db.String(255), nullable=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    tenant = db.relationship("Tenant", back_populates="facturas")
    client = db.relationship("Client", back_populates="facturas")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
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
