-- ============================================================
--  Fact Ansys 1.0 — Schema for cPanel / phpMyAdmin import
--  Database : cpanel_db_name
--
--  IMPORT INSTRUCTIONS
--  1. In phpMyAdmin make sure you have selected "cpanel_db_name"
--     from the left sidebar BEFORE clicking Import.
--  2. Choose this file and click "Go".
--  3. Leave "FOREIGN_KEY_CHECKS" alone — this script handles it.
-- ============================================================

SET NAMES utf8mb4;
SET CHARACTER SET utf8mb4;
SET collation_connection = utf8mb4_unicode_ci;

-- Disable FK checks during import so table creation order doesn't matter
SET FOREIGN_KEY_CHECKS = 0;

-- ── 1. users ────────────────────────────────────────────────────────────────
-- Must be created FIRST because clients.user_id references users.id
CREATE TABLE IF NOT EXISTS `users` (
    `id`              INT            NOT NULL AUTO_INCREMENT,
    `nempleado`       VARCHAR(10)    NULL,
    `nombre`          VARCHAR(50)    NOT NULL,
    `apellido`        VARCHAR(50)    NULL      DEFAULT '',
    `email`           VARCHAR(100)   NOT NULL,
    `celular`         VARCHAR(25)    NULL,
    `direccion`       VARCHAR(50)    NULL,
    `dir_entrega`     VARCHAR(50)    NULL,
    `usuario`         VARCHAR(50)    NOT NULL,
    `contrasena`      VARCHAR(255)   NOT NULL,
    `permiso`         INT            NOT NULL  DEFAULT 1,
    `role`            ENUM('admin','client') NOT NULL DEFAULT 'client',
    `client_id`       INT            NULL,
    `status`          INT            NOT NULL  DEFAULT 1,
    `reg_date`        DATETIME       NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    `last_pass_change` DATETIME      NULL,
    PRIMARY KEY (`id`),
    INDEX `ix_users_email`     (`email`),
    INDEX `ix_users_usuario`   (`usuario`),
    INDEX `idx_users_role`     (`role`),
    INDEX `idx_users_client_id` (`client_id`)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;


-- ── 2. clients ───────────────────────────────────────────────────────────────
-- References users.id  →  users must exist first (already created above)
CREATE TABLE IF NOT EXISTS `clients` (
    `id`          INT            NOT NULL AUTO_INCREMENT,
    `user_id`     INT            NOT NULL,
    `name`        VARCHAR(100)   NOT NULL,
    `ruc`         VARCHAR(50)    NULL      DEFAULT NULL,
    `description` VARCHAR(255)   NULL      DEFAULT NULL,
    `created_at`  DATETIME       NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    INDEX `ix_clients_user_id` (`user_id`),
    CONSTRAINT `clients_ibfk_users`
        FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)
        ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;


-- ── 3. Add FK from users.client_id → clients.id ─────────────────────────────
-- Deferred to here because clients didn't exist when users was created
ALTER TABLE `users`
    ADD CONSTRAINT `users_ibfk_clients`
  FOREIGN KEY (`client_id`) REFERENCES `clients` (`id`)
    ON DELETE SET NULL ON UPDATE RESTRICT;


-- ── 4. facturas ──────────────────────────────────────────────────────────────
-- References clients.id  →  clients must exist first (already created above)
CREATE TABLE IF NOT EXISTS `facturas` (
    `id`                   INT            NOT NULL AUTO_INCREMENT,
    `client_id`            INT            NOT NULL,
    `nombre_emisor`        VARCHAR(255)   NOT NULL,
    `ruc_emisor`           VARCHAR(50)    NULL,
    `fecha_emision`        DATETIME       NULL,
    `total`                DECIMAL(14,2)  NOT NULL  DEFAULT 0.00,
    `impuesto`             DECIMAL(14,2)  NULL      DEFAULT 0.00,
    `subtotal`             DECIMAL(14,2)  NULL      DEFAULT 0.00,
    `tipo_documento`       VARCHAR(100)   NULL,
    `naturaleza_operacion` VARCHAR(255)   NULL,
    `categoria`            VARCHAR(100)   NULL,
    `cufe`                 VARCHAR(255)   NULL,
    `created_at`           DATETIME       NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    INDEX `ix_facturas_client_id`    (`client_id`),
    INDEX `ix_facturas_nombre_emisor`(`nombre_emisor`),
    INDEX `ix_facturas_ruc_emisor`   (`ruc_emisor`),
    INDEX `ix_facturas_fecha_emision`(`fecha_emision`),
    INDEX `ix_facturas_categoria`    (`categoria`),
    CONSTRAINT `facturas_ibfk_clients`
        FOREIGN KEY (`client_id`) REFERENCES `clients` (`id`)
        ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;


-- ── 5. factura_dgi (legacy DGI table) ───────────────────────────────────────
-- Standalone — no foreign keys
CREATE TABLE IF NOT EXISTS `factura_dgi` (
    `numero_ruc`                  VARCHAR(50)  NULL,
    `usuario`                     VARCHAR(150) NULL,
    `CUFE`                        VARCHAR(255) NOT NULL,
    `tipo_de_documento`           VARCHAR(100) NOT NULL,
    `fecha_de_emision`            VARCHAR(255) NULL,
    `fecha_de_Autorizacion`       VARCHAR(255) NULL,
    `iden_emisor`                 VARCHAR(50)  NULL,
    `nombre_de_emisor`            VARCHAR(255) NOT NULL,
    `subtotal`                    VARCHAR(255) NULL      DEFAULT '0',
    `itbms`                       VARCHAR(255) NULL      DEFAULT '0',
    `monto`                       VARCHAR(255) NULL      DEFAULT '0',
    `codigo_sucursal`             VARCHAR(50)  NULL,
    `naturaleza_de_la_operacion`  VARCHAR(255) NULL,
    `tipo_de_operacion`           VARCHAR(255) NULL,
    `destino_de_la_peracion`      VARCHAR(255) NULL,
    `tiempo_de_pago`              VARCHAR(255) NULL,
    PRIMARY KEY (`CUFE`),
    INDEX `ix_factura_dgi_numero_ruc`    (`numero_ruc`),
    INDEX `ix_factura_dgi_usuario`       (`usuario`),
    INDEX `ix_factura_dgi_fecha`         (`fecha_de_emision`),
    INDEX `ix_factura_dgi_iden_emisor`   (`iden_emisor`),
    INDEX `ix_factura_dgi_nombre_emisor` (`nombre_de_emisor`)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;


-- ── 6. Seed: default admin user ──────────────────────────────────────────────
-- Password: Admin2026! (pbkdf2:sha256 hash via Werkzeug)
-- CHANGE this password immediately after first login via /change-password
INSERT IGNORE INTO `users`
    (`nombre`, `apellido`, `email`, `usuario`, `contrasena`, `permiso`, `role`, `status`, `reg_date`)
VALUES (
    'Admin',
    'Fact Ansys',
    'admin@factansys.local',
    'admin',
    'scrypt:32768:8:1$otpr0T3wFXpqEYE5$2231e2240b58b0987a273254396293bcd61065331747aa566801621a7b31472acada116b0e0eff80850dc1690a2e6e0b9a53dbb779668a23c86f6a1aee384d96',
    1,
    'admin',
    1,
    NOW()
);

-- Re-enable FK checks
SET FOREIGN_KEY_CHECKS = 1;

-- ============================================================
--  DONE. Expected result: 4 tables created, 1 admin user.
--
--  After import you MUST:
--  1. Go to /change-password and update the admin password.
--  2. Or run scripts/seed_admin.py via SSH to set a known password.
-- ============================================================
