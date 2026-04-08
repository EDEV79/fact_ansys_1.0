from __future__ import annotations

import argparse
from pathlib import Path


SUPPORTED_TABLES = (
    "users",
    "clients",
    "facturas",
    "factura_dgi",
    "factura_ca_dgi",
    "factura_ed_dgi",
)

LEGACY_USER_ORDER = [
    "client_id",
    "role",
    "id",
    "nempleado",
    "nombre",
    "apellido",
    "email",
    "celular",
    "direccion",
    "dir_entrega",
    "usuario",
    "contrasena",
    "permiso",
    "status",
    "reg_date",
    "last_pass_change",
]

TARGET_USER_ORDER = [
    "id",
    "nempleado",
    "nombre",
    "apellido",
    "email",
    "celular",
    "direccion",
    "dir_entrega",
    "usuario",
    "contrasena",
    "permiso",
    "role",
    "client_id",
    "status",
    "reg_date",
    "last_pass_change",
]


def split_sql_values(row: str) -> list[str]:
    values: list[str] = []
    current: list[str] = []
    in_string = False
    index = 0

    while index < len(row):
        char = row[index]

        if char == "'":
            current.append(char)
            if in_string and index + 1 < len(row) and row[index + 1] == "'":
                current.append(row[index + 1])
                index += 1
            else:
                in_string = not in_string
        elif char == "," and not in_string:
            values.append("".join(current).strip())
            current = []
        else:
            current.append(char)

        index += 1

    if current:
        values.append("".join(current).strip())

    return values


def reorder_user_insert(insert_line: str) -> str:
    prefix, raw_values = insert_line.split("VALUES", 1)
    row = raw_values.strip().rstrip(";")
    if not (row.startswith("(") and row.endswith(")")):
        return insert_line

    parsed = split_sql_values(row[1:-1])
    if len(parsed) != len(LEGACY_USER_ORDER):
        return insert_line

    mapped = dict(zip(LEGACY_USER_ORDER, parsed))
    reordered = ", ".join(mapped[column] for column in TARGET_USER_ORDER)
    return f"INSERT INTO `users` VALUES ({reordered});"


def collect_insert_lines(source_sql: str) -> dict[str, list[str]]:
    inserts: dict[str, list[str]] = {table: [] for table in SUPPORTED_TABLES}

    for raw_line in source_sql.splitlines():
        line = raw_line.strip()
        if not line.startswith("INSERT INTO `"):
            continue

        for table in SUPPORTED_TABLES:
            prefix = f"INSERT INTO `{table}`"
            if line.startswith(prefix):
                if table == "users":
                    line = reorder_user_insert(line)
                inserts[table].append(line)
                break

    return inserts


def build_tidb_sql(inserts: dict[str, list[str]]) -> str:
    lines: list[str] = []

    lines.extend(
        [
            "SET NAMES utf8mb4;",
            "SET FOREIGN_KEY_CHECKS = 0;",
            "",
            "DROP TABLE IF EXISTS `facturas`;",
            "DROP TABLE IF EXISTS `factura_ed_dgi`;",
            "DROP TABLE IF EXISTS `factura_ca_dgi`;",
            "DROP TABLE IF EXISTS `factura_dgi`;",
            "DROP TABLE IF EXISTS `clients`;",
            "DROP TABLE IF EXISTS `users`;",
            "",
            "CREATE TABLE `users` (",
            "  `id` int NOT NULL AUTO_INCREMENT,",
            "  `nempleado` varchar(10) NULL,",
            "  `nombre` varchar(50) NOT NULL,",
            "  `apellido` varchar(50) NULL DEFAULT '',",
            "  `email` varchar(100) NOT NULL,",
            "  `celular` varchar(25) NULL,",
            "  `direccion` varchar(50) NULL DEFAULT NULL,",
            "  `dir_entrega` varchar(50) NULL DEFAULT NULL,",
            "  `usuario` varchar(50) NOT NULL,",
            "  `contrasena` varchar(255) NOT NULL,",
            "  `permiso` int NOT NULL DEFAULT 1,",
            "  `role` enum('admin','client') NOT NULL DEFAULT 'client',",
            "  `client_id` int NULL DEFAULT NULL,",
            "  `status` int NOT NULL DEFAULT 1,",
            "  `reg_date` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,",
            "  `last_pass_change` datetime NULL DEFAULT NULL,",
            "  PRIMARY KEY (`id`),",
            "  KEY `ix_users_email` (`email`),",
            "  KEY `ix_users_usuario` (`usuario`),",
            "  KEY `idx_users_role` (`role`),",
            "  KEY `idx_users_client_id` (`client_id`)",
            ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;",
            "",
        ]
    )

    lines.extend(inserts["users"])
    lines.append("")

    lines.extend(
        [
            "CREATE TABLE `clients` (",
            "  `id` int NOT NULL AUTO_INCREMENT,",
            "  `user_id` int NOT NULL,",
            "  `name` varchar(100) NOT NULL,",
            "  `ruc` varchar(50) NULL DEFAULT NULL,",
            "  `description` varchar(255) NULL DEFAULT NULL,",
            "  `created_at` datetime NOT NULL,",
            "  PRIMARY KEY (`id`),",
            "  KEY `ix_clients_user_id` (`user_id`),",
            "  CONSTRAINT `clients_ibfk_users` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT",
            ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;",
            "",
        ]
    )

    lines.extend(inserts["clients"])
    lines.extend(
        [
            "",
            "ALTER TABLE `users`",
            "  ADD CONSTRAINT `users_ibfk_clients` FOREIGN KEY (`client_id`) REFERENCES `clients` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT;",
            "",
            "CREATE TABLE `facturas` (",
            "  `id` int NOT NULL AUTO_INCREMENT,",
            "  `client_id` int NOT NULL,",
            "  `nombre_emisor` varchar(255) NOT NULL,",
            "  `ruc_emisor` varchar(50) NULL DEFAULT NULL,",
            "  `fecha_emision` datetime NULL DEFAULT NULL,",
            "  `total` decimal(14,2) NOT NULL DEFAULT 0.00,",
            "  `impuesto` decimal(14,2) NULL DEFAULT 0.00,",
            "  `subtotal` decimal(14,2) NULL DEFAULT 0.00,",
            "  `tipo_documento` varchar(100) NULL DEFAULT NULL,",
            "  `naturaleza_operacion` varchar(255) NULL DEFAULT NULL,",
            "  `categoria` varchar(100) NULL DEFAULT NULL,",
            "  `cufe` varchar(255) NULL DEFAULT NULL,",
            "  `created_at` datetime NOT NULL,",
            "  PRIMARY KEY (`id`),",
            "  KEY `ix_facturas_client_id` (`client_id`),",
            "  KEY `ix_facturas_nombre_emisor` (`nombre_emisor`),",
            "  KEY `ix_facturas_ruc_emisor` (`ruc_emisor`),",
            "  KEY `ix_facturas_fecha_emision` (`fecha_emision`),",
            "  KEY `ix_facturas_categoria` (`categoria`),",
            "  CONSTRAINT `facturas_ibfk_clients` FOREIGN KEY (`client_id`) REFERENCES `clients` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT",
            ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;",
            "",
        ]
    )

    lines.extend(inserts["facturas"])
    lines.extend(
        [
            "",
            "CREATE TABLE `factura_dgi` (",
            "  `numero_ruc` varchar(50) NULL DEFAULT NULL,",
            "  `usuario` varchar(150) NULL DEFAULT NULL,",
            "  `CUFE` varchar(255) NOT NULL,",
            "  `tipo_de_documento` varchar(255) NULL DEFAULT NULL,",
            "  `fecha_de_emision` varchar(255) NULL DEFAULT NULL,",
            "  `fecha_de_Autorizacion` varchar(255) NULL DEFAULT NULL,",
            "  `iden_emisor` varchar(255) NULL DEFAULT NULL,",
            "  `nombre_de_emisor` varchar(255) NULL DEFAULT NULL,",
            "  `subtotal` varchar(255) NULL DEFAULT NULL,",
            "  `itbms` varchar(255) NULL DEFAULT NULL,",
            "  `monto` varchar(255) NULL DEFAULT NULL,",
            "  `codigo_sucursal` varchar(255) NULL DEFAULT NULL,",
            "  `naturaleza_de_la_operacion` varchar(255) NULL DEFAULT NULL,",
            "  `tipo_de_operacion` varchar(255) NULL DEFAULT NULL,",
            "  `destino_de_la_peracion` varchar(255) NULL DEFAULT NULL,",
            "  `tiempo_de_pago` varchar(255) NULL DEFAULT NULL,",
            "  PRIMARY KEY (`CUFE`),",
            "  KEY `ix_factura_dgi_numero_ruc` (`numero_ruc`),",
            "  KEY `ix_factura_dgi_usuario` (`usuario`),",
            "  KEY `ix_factura_dgi_fecha` (`fecha_de_emision`),",
            "  KEY `ix_factura_dgi_iden_emisor` (`iden_emisor`),",
            "  KEY `ix_factura_dgi_nombre_emisor` (`nombre_de_emisor`)",
            ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;",
            "",
        ]
    )

    lines.extend(inserts["factura_dgi"])

    for legacy_table in ("factura_ca_dgi", "factura_ed_dgi"):
        if not inserts[legacy_table]:
            continue

        lines.extend(
            [
                "",
                f"CREATE TABLE `{legacy_table}` (",
                "  `numero_ruc` varchar(50) NULL DEFAULT NULL,",
                "  `usuario` varchar(150) NULL DEFAULT NULL,",
                "  `CUFE` varchar(255) NULL DEFAULT NULL,",
                "  `tipo_de_documento` varchar(255) NULL DEFAULT NULL,",
                "  `fecha_de_emision` varchar(255) NULL DEFAULT NULL,",
                "  `fecha_de_Autorizacion` varchar(255) NULL DEFAULT NULL,",
                "  `iden_emisor` varchar(255) NULL DEFAULT NULL,",
                "  `nombre_de_emisor` varchar(255) NULL DEFAULT NULL,",
                "  `subtotal` varchar(255) NULL DEFAULT NULL,",
                "  `itbms` varchar(255) NULL DEFAULT NULL,",
                "  `monto` varchar(255) NULL DEFAULT NULL,",
                "  `codigo_sucursal` varchar(255) NULL DEFAULT NULL,",
                "  `naturaleza_de_la_operacion` varchar(255) NULL DEFAULT NULL,",
                "  `tipo_de_operacion` varchar(255) NULL DEFAULT NULL,",
                "  `destino_de_la_peracion` varchar(255) NULL DEFAULT NULL,",
                "  `tiempo_de_pago` varchar(255) NULL DEFAULT NULL",
                ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;",
                "",
            ]
        )
        lines.extend(inserts[legacy_table])

    lines.extend(["", "SET FOREIGN_KEY_CHECKS = 1;", ""])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert a Navicat/MariaDB dump into a TiDB-friendly SQL import.")
    parser.add_argument("source", help="Path to the original .sql dump")
    parser.add_argument(
        "-o",
        "--output",
        default="database/tidb_import.sql",
        help="Path to the generated TiDB-compatible SQL file",
    )
    args = parser.parse_args()

    source_path = Path(args.source)
    output_path = Path(args.output)

    source_sql = source_path.read_text(encoding="utf-8")
    inserts = collect_insert_lines(source_sql)
    tidb_sql = build_tidb_sql(inserts)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(tidb_sql, encoding="utf-8")

    print(f"Generated TiDB import SQL: {output_path}")
    for table in SUPPORTED_TABLES:
        print(f"{table}: {len(inserts[table])} INSERT statements")


if __name__ == "__main__":
    main()