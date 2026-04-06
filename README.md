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

## Despliegue en Render

Este proyecto usa MySQL. Render no ofrece MySQL administrado en el mismo panel (sí ofrece Postgres), por lo que debes usar una base MySQL externa.

### Opción A: usando `render.yaml` (recomendado)

1. Sube este repositorio a GitHub.
2. En Render: **New** -> **Blueprint**.
3. Conecta tu repo y selecciona la rama.
4. Define las variables en el servicio (las marcadas como `sync: false` no se guardan en git).
5. Render ejecutará:
   - Build: `pip install -r requirements.txt`
   - Start: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120`

### Opción B: creando Web Service manual

1. En Render: **New Web Service**.
2. Runtime: **Python**.
3. Build Command: `pip install -r requirements.txt`.
4. Start Command: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120`.
5. Plan: Free o el que prefieras.
6. Configura variables de entorno:

```env
FLASK_ENV=production
SECRET_KEY=<una-clave-larga-y-segura>
DB_USER=<usuario_mysql>
DB_PASSWORD=<password_mysql>
DB_HOST=<host_mysql>
DB_PORT=3306
DB_NAME=<nombre_bd>
```

Opcionalmente puedes usar una sola variable:

```env
DATABASE_URL=mysql+pymysql://usuario:password@host:3306/basedatos
```

Si defines `DATABASE_URL`, tendrá prioridad sobre `DB_*`.
