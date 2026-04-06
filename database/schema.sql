CREATE DATABASE IF NOT EXISTS facturasdgi_analitics CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE facturasdgi_analitics;

CREATE TABLE IF NOT EXISTS facturas_dgi (
    cufe VARCHAR(255) PRIMARY KEY,
    tipo_de_documento VARCHAR(100) NOT NULL,
    fecha_de_emision DATETIME NULL,
    fecha_de_autorizacion DATETIME NULL,
    iden_emisor VARCHAR(50) NULL,
    nombre_de_emisor VARCHAR(255) NOT NULL,
    subtotal DECIMAL(12, 2) DEFAULT 0,
    itbms DECIMAL(12, 2) DEFAULT 0,
    monto DECIMAL(12, 2) DEFAULT 0,
    codigo_sucursal VARCHAR(50) NULL,
    naturaleza_de_la_operacion VARCHAR(255) NULL,
    tipo_de_operacion VARCHAR(255) NULL,
    INDEX idx_fecha_emision (fecha_de_emision),
    INDEX idx_nombre_emisor (nombre_de_emisor),
    INDEX idx_tipo_documento (tipo_de_documento),
    INDEX idx_iden_emisor (iden_emisor)
);
