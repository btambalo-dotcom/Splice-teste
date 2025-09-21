
import os
import sqlite3
from datetime import datetime
from contextlib import closing
from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, session, send_from_directory, abort, Response, jsonify
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# --------------------------- Persistência segura ---------------------------
def _pick_data_dir():
    # Preferido p/ DO App Platform: /workspace/data (monte um Volume aqui)
    base = os.getenv("DATA_DIR", "/workspace/data")
    try:
        os.makedirs(base, exist_ok=True)
        testf = os.path.join(base, ".wtest")
        with open(testf, "w") as f:
            f.write("ok")
        os.remove(testf)
    except Exception:
        base = "/tmp/splice-data"
        os.makedirs(base, exist_ok=True)
    return base

DATA_DIR = _pick_data_dir()
DB_FILE  = os.getenv("DATABASE_FILE", "splice.db")
DB_PATH  = os.path.join(DATA_DIR, DB_FILE)

UPLOAD_FOLDER   = os.path.join(DATA_DIR, "uploads")
WORKMAP_FOLDER  = os.path.join(DATA_DIR, "workmaps")
BACKUP_DIR      = os.path.join(DATA_DIR, "backups")
for p in (UPLOAD_FOLDER, WORKMAP_FOLDER, BACKUP_DIR):
    os.makedirs(p, exist_ok=True)

# Popular URLs p/ libs comuns
os.environ.setdefault("DATABASE_URL", f"sqlite:///{DB_PATH}")
os.environ.setdefault("SQLALCHEMY_DATABASE_URI", f"sqlite:///{DB_PATH}")
os.environ.setdefault("DB_PATH", DB_PATH)

# ------------------------------ Flask config ------------------------------
app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "change-me")
app.config["MAX_CONTENT_LENGTH"] = int(os.getenv("MAX_CONTENT_LENGTH_MB", "50")) * 1024 * 1024

# ----------------------------- DB helpers ---------------------------------
def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
    except Exception:
        pass
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with closing(get_db()) as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                is_admin INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS records(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS photos(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                record_id INTEGER NOT NULL,
                filename TEXT NOT NULL,
                uploaded_at TEXT NOT NULL,
                FOREIGN KEY(record_id) REFERENCES records(id)
            );
            """
        )
        # seed admin if none
        cur = db.execute("SELECT COUNT(*) FROM users")
        if cur.fetchone()[0] == 0:
            db.execute(
                "INSERT INTO users(username, password_hash, is_admin) VALUES(?,?,1)",
                ("admin", generate_password_hash("admin"))
            )
        db.commit()

# ----------------------------- Auth helpers -------------------------------
def current_user():
    uid = session.get("uid")
    if not uid:
        return None
    with closing(get_db()) as db:
        u = db.execute("SELECT id, username, is_admin FROM users WHERE id=?", (uid,)).fetchone()
    return u

def login_required(fn):
    from functools import wraps
    @wraps(fn)
    def _w(*a, **kw):
        if not current_user():
            flash("Faça login.", "error")
            return redirect(url_for("login"))
        return fn(*a, **kw)
    return _w

def admin_required(fn):
    from functools import wraps
    @wraps(fn)
    def _w(*a, **kw):
        u = current_user()
        if not u or not u["is_admin"]:
            abort(403)
        return fn(*a, **kw)
    return _w

# ------------------------------- Routes -----------------------------------
@app.before_first_request
def _boot():
    init_db()

@app.get("/healthz")
def health():
    return "ok", 200

@app.get("/debug/env")
def debug_env():
    return jsonify({"DATA_DIR": DATA_DIR, "DB_PATH": DB_PATH})

@app.get("/")
@login_required
def dashboard():
    u = current_user()
    with closing(get_db()) as db:
        rows = db.execute(
            "SELECT r.id, r.title, r.body, r.created_at, u.username "
            "FROM records r JOIN users u ON u.id = r.user_id "
            "ORDER BY r.id DESC"
        ).fetchall()
    return render_template("dashboard.html", user=u, records=rows, data_dir=DATA_DIR)

# --- Auth ---
@app.get("/login")
def login():
    if current_user():
        return redirect(url_for("dashboard"))
    return render_template("login.html")

@app.post("/login")
def do_login():
    username = request.form.get("username","").strip()
    password = request.form.get("password","")
    with closing(get_db()) as db:
        u = db.execute("SELECT id, username, password_hash, is_admin FROM users WHERE username=?",(username,)).fetchone()
    if not u or not check_password_hash(u["password_hash"], password):
        flash("Usuário ou senha inválidos.", "error")
        return redirect(url_for("login"))
    session["uid"] = u["id"]
    flash("Bem-vindo!", "ok")
    return redirect(url_for("dashboard"))

@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.get("/register")
def register():
    return render_template("register.html")

@app.post("/register")
def do_register():
    username = request.form.get("username","").strip()
    password = request.form.get("password","")
    if not username or not password:
        flash("Preencha usuário e senha.", "error")
        return redirect(url_for("register"))
    try:
        with closing(get_db()) as db:
            db.execute(
                "INSERT INTO users(username, password_hash, is_admin) VALUES(?,?,0)",
                (username, generate_password_hash(password)),
            )
            db.commit()
        flash("Conta criada. Faça login.", "ok")
        return redirect(url_for("login"))
    except sqlite3.IntegrityError:
        flash("Usuário já existe.", "error")
        return redirect(url_for("register"))

# --- Records ---
@app.get("/records/new")
@login_required
def new_record():
    return render_template("new_record.html")

@app.post("/records")
@login_required
def create_record():
    u = current_user()
    title = request.form.get("title","").strip()
    body  = request.form.get("body","").strip()
    file  = request.files.get("photo")
    if not title or not body:
        flash("Preencha título e texto.", "error")
        return redirect(url_for("new_record"))
    with closing(get_db()) as db:
        cur = db.execute(
            "INSERT INTO records(user_id, title, body, created_at) VALUES(?,?,?,?)",
            (u["id"], title, body, datetime.utcnow().isoformat(timespec="seconds")),
        )
        rid = cur.lastrowid
        db.commit()
    if file and file.filename:
        fname = secure_filename(file.filename)
        dest  = os.path.join(UPLOAD_FOLDER, fname)
        file.save(dest)
        with closing(get_db()) as db:
            db.execute(
                "INSERT INTO photos(record_id, filename, uploaded_at) VALUES(?,?,?)",
                (rid, fname, datetime.utcnow().isoformat(timespec="seconds"))
            )
            db.commit()
    flash("Registro criado.", "ok")
    return redirect(url_for("view_record", record_id=rid))

@app.get("/records/<int:record_id>")
@login_required
def view_record(record_id):
    with closing(get_db()) as db:
        rec = db.execute(
            "SELECT r.*, u.username FROM records r JOIN users u ON u.id=r.user_id WHERE r.id=?",
            (record_id,)
        ).fetchone()
        if not rec:
            abort(404)
        photos = db.execute("SELECT * FROM photos WHERE record_id=? ORDER BY id DESC", (record_id,)).fetchall()
    return render_template("view_record.html", rec=rec, photos=photos)

@app.get("/uploads/<path:name>")
@login_required
def serve_upload(name):
    return send_from_directory(UPLOAD_FOLDER, name)

# --- Workmaps simples ---
@app.get("/workmaps")
@login_required
def my_workmaps():
    u = current_user()
    items = sorted(os.listdir(WORKMAP_FOLDER))
    return render_template("my_workmaps.html", user=u, files=items)

@app.post("/workmaps/upload")
@login_required
def upload_workmap():
    f = request.files.get("file")
    if not f or not f.filename:
        flash("Selecione um arquivo.", "error")
        return redirect(url_for("my_workmaps"))
    name = secure_filename(f.filename)
    f.save(os.path.join(WORKMAP_FOLDER, name))
    flash("Workmap salvo.", "ok")
    return redirect(url_for("my_workmaps"))

# --- Admin ---
@app.get("/admin")
@admin_required
def admin_home():
    with closing(get_db()) as db:
        total_users  = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        total_records= db.execute("SELECT COUNT(*) FROM records").fetchone()[0]
        total_photos = db.execute("SELECT COUNT(*) FROM photos").fetchone()[0]
    return render_template("admin_home.html", stats={"users": total_users, "records": total_records, "photos": total_photos})

@app.get("/admin/users")
@admin_required
def admin_users():
    with closing(get_db()) as db:
        rows = db.execute("SELECT id, username, is_admin FROM users ORDER BY id DESC").fetchall()
    return render_template("admin_users.html", users=rows)

@app.post("/admin/users/<int:uid>/toggle-admin")
@admin_required
def toggle_admin(uid):
    with closing(get_db()) as db:
        u = db.execute("SELECT id, is_admin FROM users WHERE id=?", (uid,)).fetchone()
        if not u: abort(404)
        db.execute("UPDATE users SET is_admin=? WHERE id=?", (0 if u["is_admin"] else 1, uid))
        db.commit()
    return redirect(url_for("admin_users"))

@app.get("/admin/photos")
@admin_required
def admin_photos():
    files = sorted(os.listdir(UPLOAD_FOLDER))
    return render_template("admin_photos.html", files=files)

@app.get("/admin/records")
@admin_required
def admin_records():
    with closing(get_db()) as db:
        rows = db.execute(
            "SELECT r.id, r.title, r.created_at, u.username FROM records r JOIN users u ON u.id=r.user_id ORDER BY r.id DESC"
        ).fetchall()
    return render_template("admin_records.html", records=rows)

@app.get("/admin/reports")
@admin_required
def admin_reports():
    # Exporta CSV simples de registros
    def gen():
        yield "id,title,body,user,created_at\\n"
        with closing(get_db()) as db:
            cur = db.execute(
                "SELECT r.id, r.title, r.body, u.username, r.created_at "
                "FROM records r JOIN users u ON u.id=r.user_id ORDER BY r.id"
            )
            for row in cur:
                # escapar vírgulas simples
                def esc(s):
                    s = str(s).replace('"','""')
                    return f'"{s}"'
                yield f"{row[0]},{esc(row[1])},{esc(row[2])},{esc(row[3])},{row[4]}\\n"
    return Response(gen(), mimetype="text/csv", headers={"Content-Disposition":"attachment; filename=records.csv"})

@app.get("/admin/backups")
@admin_required
def admin_backups():
    files = sorted([f for f in os.listdir(BACKUP_DIR) if f.endswith(".zip")], reverse=True)
    return render_template("admin_backups.html", backups=files)

@app.post("/admin/backups/create")
@admin_required
def create_backup():
    import zipfile
    ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    name = f"backup-{ts}.zip"
    path = os.path.join(BACKUP_DIR, name)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.write(DB_PATH, arcname=os.path.basename(DB_PATH))
        for folder in (UPLOAD_FOLDER, WORKMAP_FOLDER):
            for root, dirs, files in os.walk(folder):
                for f in files:
                    full = os.path.join(root, f)
                    arc  = os.path.relpath(full, start=DATA_DIR)
                    z.write(full, arcname=arc)
    flash("Backup criado.", "ok")
    return redirect(url_for("admin_backups"))

@app.get("/admin/backups/download/<path:name>")
@admin_required
def download_backup(name):
    return send_from_directory(BACKUP_DIR, name, as_attachment=True)

# --------------------------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8080")), debug=True)
