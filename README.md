# CRM básico de facturación con Flask

Aplicación web básica tipo CRM para visualizar datos de facturación desde MySQL usando Flask, SQLAlchemy, Bootstrap 5 y Chart.js.

## Características

- Login con sesión validado contra la tabla `users`
- Dashboard con métricas clave
- Filtros por emisor, rango de fecha y tipo de documento
- Agrupación por emisor usando `GROUP BY` y `SUM`
- Tabla paginada de facturas
- Exportación de resultados a CSV
- UI administrativa con navbar y sidebar

## Estructura

```bash
facturasdgi-analitics/
├── app/
│   ├── routes/
│   ├── static/
│   └── templates/
├── database/
│   └── schema.sql
├── app.py
├── models.py
├── requirements.txt
└── .env.example
```

## Configuración

1. Crear un entorno virtual e instalar dependencias:

```bash
pip install -r requirements.txt
```

2. Crear un archivo `.env` a partir de `.env.example`.

3. Configurar las credenciales de MySQL para la base `dgi_fact`.

4. Verificar que existan las tablas `users` y `factura_ed_dgi`.

5. Ejecutar la aplicación:

```bash
flask run
```

## Variables de entorno

```env
FLASK_APP=app.py
FLASK_ENV=development
SECRET_KEY=cambia-esta-clave
DB_USER=root
DB_PASSWORD=
DB_HOST=127.0.0.1
DB_PORT=3306
DB_NAME=dgi_fact
```

## Rutas principales

- `/login`
- `/dashboard`
- `/facturas`
- `/facturas/exportar`

## Nota

La autenticación consulta la tabla `users` usando el campo `usuario` y valida `contrasena`. El proyecto soporta hashes `bcrypt` estilo PHP (`$2y$`), SHA1 y texto plano si existiera algún registro heredado.
