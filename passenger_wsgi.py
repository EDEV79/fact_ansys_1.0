"""
passenger_wsgi.py — Entry point for cPanel Passenger WSGI

How cPanel Passenger works:
  - cPanel looks for a file named exactly `passenger_wsgi.py` in your app root.
  - It imports this file and looks for a callable named `application`.
  - Passenger manages worker processes; do NOT call app.run() here.

Upload location on cPanel:
  - Place this file at the root of your Python app directory, e.g.:
      /home/<cpanel_user>/<app_folder>/passenger_wsgi.py
  - The app root is the folder you set as "Application Root" in
    cPanel > Setup Python App.

How to restart after changes:
  - cPanel > Setup Python App > click "Restart" button, OR
  - SSH: touch /home/<cpanel_user>/<app_folder>/tmp/restart.txt
"""

import os
import sys
from pathlib import Path

# ── 1. Make sure the project root is on sys.path ─────────────────────────────
# This lets Python find `app`, `models`, etc. regardless of the cwd
# cPanel sets when spawning the worker.
APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

# ── 2. Load site-packages from cPanel virtualenv (preferred) ─────────────────
# IMPORTANT: A .venv uploaded from Windows is not valid on Linux cPanel.
# This block prioritizes cPanel's own environment at:
#   /home*/<user>/virtualenv/<app_root>/<python_version>/
def _inject_site_packages_from(venv_root: Path) -> bool:
    """Return True when at least one valid site-packages path is injected."""
    injected = False
    lib_dir = venv_root / "lib"
    if not lib_dir.is_dir():
        return False

    for py_dir in lib_dir.glob("python*"):
        site_pkg = py_dir / "site-packages"
        if site_pkg.is_dir() and str(site_pkg) not in sys.path:
            sys.path.insert(0, str(site_pkg))
            injected = True
    return injected


venv_candidates: list[Path] = []

# 2.1 If Passenger exported VIRTUAL_ENV, use it first.
if os.getenv("VIRTUAL_ENV"):
    venv_candidates.append(Path(os.environ["VIRTUAL_ENV"]))

# 2.2 Standard cPanel path: ~/virtualenv/<app-root>/<py-version>/
cpanel_venv_parent = Path.home() / "virtualenv" / APP_DIR.name
if cpanel_venv_parent.is_dir():
    for version_dir in sorted(cpanel_venv_parent.iterdir()):
        if version_dir.is_dir():
            venv_candidates.append(version_dir)

# 2.3 Fallbacks inside project root (only if they are real Linux venvs).
for candidate in ("venv", "env", ".venv", "virtualenv"):
    candidate_path = APP_DIR / candidate
    if candidate_path.exists():
        venv_candidates.append(candidate_path)

for venv_dir in venv_candidates:
    if _inject_site_packages_from(venv_dir):
        break

# ── 3. Load environment variables from .env before creating the app ──────────
# python-dotenv reads the .env file sitting next to this script.
# This must happen BEFORE create_app() so os.getenv() calls see all values.
try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=APP_DIR / ".env", override=True)
except ImportError:
    pass  # python-dotenv not installed — assume env vars are set by cPanel

# ── 4. Create the Flask application ──────────────────────────────────────────
from app import create_app

application = create_app()
