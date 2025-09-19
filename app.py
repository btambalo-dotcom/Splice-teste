import os, sqlite3
from contextlib import closing
from flask import Flask, request, redirect, url_for, render_template, flash, session, send_from_directory, abort, Response

# ===== Persistência segura para DigitalOcean App Platform =====
DATA_DIR = os.environ.get('DATA_DIR', '/var/data')
DB_FILE  = os.environ.get('DATABASE_FILE', 'splice.db')
DB_PATH  = os.environ.get('DB_PATH', os.path.join(DATA_DIR, DB_FILE))
UPLOAD_FOLDER  = os.environ.get('UPLOAD_FOLDER', os.path.join(DATA_DIR, 'uploads'))
WORKMAP_FOLDER = os.environ.get('WORKMAP_FOLDER', os.path.join(DATA_DIR, 'workmaps'))
BACKUP_DIR     = os.path.join(DATA_DIR, 'backups')

for _p in (DATA_DIR, UPLOAD_FOLDER, WORKMAP_FOLDER, BACKUP_DIR):
    os.makedirs(_p, exist_ok=True)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-change-me')
max_len_mb = int(os.environ.get('MAX_CONTENT_LENGTH_MB', '20'))
app.config['MAX_CONTENT_LENGTH'] = max_len_mb * 1024 * 1024

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
    except Exception:
        pass
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/healthz')
def healthz():
    return 'ok', 200
