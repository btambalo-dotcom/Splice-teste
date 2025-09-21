import os, sqlite3, shutil
from datetime import datetime
from contextlib import closing
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_from_directory, abort, Response, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

def _pick_data_dir():
    base = os.getenv("DATA_DIR") or "/workspace/data"
    try:
        os.makedirs(base, exist_ok=True)
        with open(os.path.join(base, ".w"), "w") as f: f.write("ok")
        os.remove(os.path.join(base, ".w"))
    except Exception:
        base = "/tmp/splice-data"
        os.makedirs(base, exist_ok=True)
    return base

DATA_DIR = _pick_data_dir()
DB_FILE  = os.getenv("DATABASE_FILE", "splice.db")
DB_PATH  = os.path.join(DATA_DIR, DB_FILE)

UPLOADS_DIR   = os.path.join(DATA_DIR, "uploads")
WORKMAPS_DIR  = os.path.join(DATA_DIR, "workmaps")
BACKUPS_DIR   = os.path.join(DATA_DIR, "backups")
for d in (UPLOADS_DIR, WORKMAPS_DIR, BACKUPS_DIR):
    os.makedirs(d, exist_ok=True)

PKG_SEED_DB = os.path.join(os.path.dirname(__file__), "seed", "splice.db")
if not os.path.exists(DB_PATH) and os.path.exists(PKG_SEED_DB):
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    shutil.copyfile(PKG_SEED_DB, DB_PATH)

os.environ.setdefault("DATABASE_URL", f"sqlite:///{DB_PATH}")
os.environ.setdefault("SQLALCHEMY_DATABASE_URI", f"sqlite:///{DB_PATH}")
os.environ.setdefault("DB_PATH", DB_PATH)

ALLOWED_EXT = {"png","jpg","jpeg","gif","webp","pdf","txt","csv","json"}

# === AUTO_INIT_DO ===
try:
    from pathlib import Path
    import os, subprocess, sys
    DATA_DIR = Path(os.getenv("DATA_DIR", "/workspace/data"))
    (DATA_DIR/"uploads").mkdir(parents=True, exist_ok=True)
    (DATA_DIR/"workmaps").mkdir(parents=True, exist_ok=True)
    (DATA_DIR/"backup").mkdir(parents=True, exist_ok=True)

    DB_FILE = os.getenv("DATABASE_FILE", "splice.db")
    DB_PATH = DATA_DIR/DB_FILE

    # Força init se banco não existir ou ADMIN_PASSWORD_FORCE=1
    if (not DB_PATH.exists()) or (os.getenv("ADMIN_PASSWORD_FORCE","0") == "1"):
        # executa o script de inicialização
        _cmd = [sys.executable, "-u", str(Path(__file__).parent/"scripts"/"init_db.py")]
        subprocess.run(_cmd, check=True)
        # se quiser também forçar reset do admin:
        if os.getenv("ADMIN_PASSWORD"):
            _cmd2 = [sys.executable, "-u", str(Path(__file__).parent/"scripts"/"reset_admin.py")]
            os.environ["PYTHONUNBUFFERED"] = "1"
            subprocess.run(_cmd2, check=True)
except Exception as e:
    print("[BOOT][WARN] Auto-init falhou:", e)
# === /AUTO_INIT_DO ===

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "CHANGE_ME")
app.config["MAX_CONTENT_LENGTH"] = int(os.getenv("MAX_CONTENT_LENGTH_MB", "50")) * 1024 * 1024

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
    except Exception:
        pass
    conn.row_factory = sqlite3.Row
    return conn

def init_schema_and_admin():
    admin_user = os.getenv("ADMIN_USERNAME", "admin")
    admin_pass = os.getenv("ADMIN_PASSWORD", "admin123")
    force_reset = os.getenv("ADMIN_PASSWORD_FORCE", "0").lower() in ("1","true","yes")

    with closing(get_db()) as db:
        db.executescript('''
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
            body  TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS photos(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            record_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            uploaded_at TEXT NOT NULL,
            FOREIGN KEY(record_id) REFERENCES records(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS devices(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            serial TEXT UNIQUE NOT NULL,
            launched INTEGER NOT NULL DEFAULT 0,
            owner_id INTEGER,
            created_at TEXT NOT NULL,
            FOREIGN KEY(owner_id) REFERENCES users(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS workmaps(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            owner_id INTEGER NOT NULL,
            uploaded_at TEXT NOT NULL,
            FOREIGN KEY(owner_id) REFERENCES users(id) ON DELETE CASCADE
        );
        ''')

        u = db.execute("SELECT id, username FROM users WHERE username=?", (admin_user,)).fetchone()
        if u is None:
            db.execute(
                "INSERT INTO users(username, password_hash, is_admin) VALUES(?,?,1)",
                (admin_user, generate_password_hash(admin_pass))
            )
            db.commit()
        elif force_reset:
            db.execute("UPDATE users SET password_hash=? WHERE id=?", (generate_password_hash(admin_pass), u["id"]))
            db.commit()

try:
    init_schema_and_admin()
except Exception as e:
    print("[WARN] init_schema_and_admin:", e)

def current_user():
    uid = session.get("uid")
    if not uid: return None
    with closing(get_db()) as db:
        return db.execute("SELECT id, username, is_admin FROM users WHERE id=?", (uid,)).fetchone()

def login_required(fn):
    from functools import wraps
    @wraps(fn)
    def _w(*a, **kw):
        if not current_user():
            flash("Faça login.", "error"); return redirect(url_for("login"))
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

def allowed_file(filename):
    return "." in filename and filename.rsplit(".",1)[1].lower() in {"png","jpg","jpeg","gif","webp","pdf","txt","csv","json"}

@app.get("/healthz")
def health(): return "ok", 200

@app.get("/debug/env")
def debug_env(): return jsonify({"DATA_DIR": DATA_DIR, "DB_PATH": DB_PATH})

@app.get("/")
def home():
    if current_user(): return redirect(url_for("dashboard"))
    return redirect(url_for("login"))

@app.get("/login")
def login():
    if current_user(): return redirect(url_for("dashboard"))
    return render_template("login.html")

@app.post("/login")
def do_login():
    username = request.form.get("username","").strip()
    password = request.form.get("password","")
    with closing(get_db()) as db:
        u = db.execute("SELECT id, username, password_hash FROM users WHERE username=?", (username,)).fetchone()
    if not u or not check_password_hash(u["password_hash"], password):
        flash("Usuário ou senha inválidos.", "error"); return redirect(url_for('login'))
    session["uid"] = u["id"]; flash("Bem-vindo!", "ok"); return redirect(url_for("dashboard"))

@app.get("/logout")
def logout():
    session.clear(); return redirect(url_for("login"))

@app.get("/register")
def register(): return render_template("register.html")

@app.post("/register")
def do_register():
    username = request.form.get("username","").strip()
    password = request.form.get("password","")
    if not username or not password:
        flash("Preencha usuário e senha.", "error"); return redirect(url_for("register"))
    try:
        with closing(get_db()) as db:
            db.execute("INSERT INTO users(username, password_hash, is_admin) VALUES(?,?,0)",
                       (username, generate_password_hash(password)))
            db.commit()
        flash("Conta criada. Faça login.", "ok"); return redirect(url_for("login"))
    except sqlite3.IntegrityError:
        flash("Usuário já existe.", "error"); return redirect(url_for("register"))

@app.get("/dashboard")
def dashboard():
    u = current_user()
    if not u: return redirect(url_for("login"))
    with closing(get_db()) as db:
        recs = db.execute("SELECT r.id, r.title, substr(r.body,1,140) preview, r.created_at, u.username FROM records r JOIN users u ON u.id=r.user_id ORDER BY r.id DESC LIMIT 50").fetchall()
        devs = db.execute("SELECT id, name, serial, launched, created_at FROM devices ORDER BY id DESC LIMIT 20").fetchall()
    return render_template("dashboard.html", user=u, records=recs, devices=devs)

@app.get("/records/new")
def new_record():
    if not current_user(): return redirect(url_for("login"))
    return render_template("new_record.html")

@app.post("/records")
def create_record():
    u = current_user()
    if not u: return redirect(url_for("login"))
    title = request.form.get("title","").strip()
    body  = request.form.get("body","").strip()
    foto  = request.files.get("photo")
    if not title or not body:
        flash("Preencha título e texto.", "error"); return redirect(url_for("new_record"))
    with closing(get_db()) as db:
        cur = db.execute("INSERT INTO records(user_id,title,body,created_at) VALUES(?,?,?,?)",
                         (u["id"], title, body, datetime.utcnow().isoformat(timespec="seconds")))
        rid = cur.lastrowid; db.commit()
    if foto and foto.filename and allowed_file(foto.filename):
        from werkzeug.utils import secure_filename
        fname = secure_filename(foto.filename)
        dest = os.path.join(os.environ.get("UPLOADS_DIR", os.path.join(DATA_DIR,'uploads')), fname)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        foto.save(dest)
        with closing(get_db()) as db:
            db.execute("INSERT INTO photos(record_id,filename,uploaded_at) VALUES(?,?,?)",
                       (rid, fname, datetime.utcnow().isoformat(timespec="seconds"))); db.commit()
    flash("Registro criado.", "ok"); return redirect(url_for("view_record", record_id=rid))

@app.get("/records/<int:record_id>")
def view_record(record_id):
    if not current_user(): return redirect(url_for("login"))
    with closing(get_db()) as db:
        rec = db.execute("SELECT r.*, u.username FROM records r JOIN users u ON u.id=r.user_id WHERE r.id=?",(record_id,)).fetchone()
        if not rec: abort(404)
        photos = db.execute("SELECT * FROM photos WHERE record_id=? ORDER BY id DESC",(record_id,)).fetchall()
    return render_template("view_record.html", rec=rec, photos=photos)

@app.get("/uploads/<path:name>")
def serve_upload(name):
    if not current_user(): return redirect(url_for("login"))
    return send_from_directory(os.path.join(DATA_DIR,'uploads'), name)

@app.get("/workmaps")
def my_workmaps():
    u = current_user()
    if not u: return redirect(url_for("login"))
    with closing(get_db()) as db:
        items = db.execute("SELECT * FROM workmaps WHERE owner_id=? ORDER BY id DESC", (u["id"],)).fetchall()
    return render_template("my_workmaps.html", files=items)

@app.post("/workmaps/upload")
def upload_workmap():
    u = current_user()
    if not u: return redirect(url_for("login"))
    f = request.files.get("file")
    if not f or not f.filename:
        flash("Selecione um arquivo.", "error"); return redirect(url_for("my_workmaps"))
    from werkzeug.utils import secure_filename
    name = secure_filename(f.filename)
    if "." not in name or name.rsplit(".",1)[1].lower() not in {"png","jpg","jpeg","gif","webp","pdf","txt","csv","json"}:
        flash("Extensão não permitida.", "error"); return redirect(url_for("my_workmaps"))
    dest_dir = os.path.join(DATA_DIR,'workmaps'); os.makedirs(dest_dir, exist_ok=True)
    f.save(os.path.join(dest_dir, name))
    with closing(get_db()) as db:
        db.execute("INSERT INTO workmaps(filename, owner_id, uploaded_at) VALUES(?,?,?)",
                   (name, u["id"], datetime.utcnow().isoformat(timespec="seconds"))); db.commit()
    flash("Workmap salvo.", "ok"); return redirect(url_for("my_workmaps"))

@app.post("/workmaps/delete/<int:w_id>")
def delete_workmap(w_id):
    u = current_user()
    if not u: return redirect(url_for("login"))
    with closing(get_db()) as db:
        row = db.execute("SELECT * FROM workmaps WHERE id=? AND owner_id=?", (w_id, u["id"])).fetchone()
        if row:
            try: os.remove(os.path.join(DATA_DIR,'workmaps', row["filename"]))
            except FileNotFoundError: pass
            db.execute("DELETE FROM workmaps WHERE id=?", (w_id,)); db.commit()
    flash("Removido.", "ok"); return redirect(url_for("my_workmaps"))

@app.get("/workmaps/files/<path:name>")
def serve_workmap(name):
    if not current_user(): return redirect(url_for("login"))
    return send_from_directory(os.path.join(DATA_DIR,'workmaps'), name, as_attachment=True)

@app.get("/devices/new")
def new_device():
    if not current_user(): return redirect(url_for("login"))
    return render_template("new_device.html")

@app.post("/devices")
def create_device():
    if not current_user(): return redirect(url_for("login"))
    name = request.form.get("name","").strip()
    serial= request.form.get("serial","").strip()
    if not name or not serial:
        flash("Nome e serial são obrigatórios.", "error"); return redirect(url_for("new_device"))
    try:
        with closing(get_db()) as db:
            db.execute("INSERT INTO devices(name, serial, owner_id, created_at) VALUES(?,?,?,?)",
                       (name, serial, current_user()['id'], datetime.utcnow().isoformat(timespec="seconds"))); db.commit()
        flash("Dispositivo cadastrado.", "ok"); return redirect(url_for("dashboard"))
    except sqlite3.IntegrityError:
        flash("Serial já existe.", "error"); return redirect(url_for("new_device"))

@app.post("/admin/devices/<int:did>/toggle-launched")
def toggle_device(did):
    u=current_user()
    if not u or not u['is_admin']: abort(403)
    with closing(get_db()) as db:
        row = db.execute("SELECT id, launched FROM devices WHERE id=?", (did,)).fetchone()
        if not row: abort(404)
        db.execute("UPDATE devices SET launched=? WHERE id=?", (0 if row['launched'] else 1, did)); db.commit()
    return redirect(url_for("dashboard"))

@app.get("/admin")
def admin_home():
    u=current_user()
    if not u or not u['is_admin']: abort(403)
    with closing(get_db()) as db:
        su = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        sr = db.execute("SELECT COUNT(*) FROM records").fetchone()[0]
        sd = db.execute("SELECT COUNT(*) FROM devices").fetchone()[0]
    return render_template("admin_home.html", stats={"users": su, "records": sr, "devices": sd})

@app.get("/admin/users")
def admin_users():
    u=current_user()
    if not u or not u['is_admin']: abort(403)
    with closing(get_db()) as db:
        rows = db.execute("SELECT id, username, is_admin FROM users ORDER BY id DESC").fetchall()
    return render_template("admin_users.html", users=rows)

@app.post("/admin/users/<int:uid>/toggle-admin")
def toggle_admin(uid):
    u=current_user()
    if not u or not u['is_admin']: abort(403)
    with closing(get_db()) as db:
        row = db.execute("SELECT id, is_admin FROM users WHERE id=?", (uid,)).fetchone()
        if not row: abort(404)
        db.execute("UPDATE users SET is_admin=? WHERE id=?", (0 if row['is_admin'] else 1, uid)); db.commit()
    return redirect(url_for("admin_users"))

@app.get("/admin/records")
def admin_records():
    u=current_user()
    if not u or not u['is_admin']: abort(403)
    with closing(get_db()) as db:
        rows = db.execute("SELECT r.id, r.title, r.created_at, u.username FROM records r JOIN users u ON u.id=r.user_id ORDER BY r.id DESC").fetchall()
    return render_template("admin_records.html", records=rows)

@app.get("/admin/backups")
def admin_backups():
    u=current_user()
    if not u or not u['is_admin']: abort(403)
    files = sorted([f for f in os.listdir(os.path.join(DATA_DIR,'backups')) if f.endswith('.zip')], reverse=True)
    return render_template("admin_backups.html", backups=files)

@app.post("/admin/backups/create")
def create_backup():
    u=current_user()
    if not u or not u['is_admin']: abort(403)
    import zipfile, os
    from datetime import datetime
    DATA_DIR=os.getenv("DATA_DIR") or "/workspace/data"
    BACKUPS_DIR=os.path.join(DATA_DIR,"backups"); os.makedirs(BACKUPS_DIR, exist_ok=True)
    DB_PATH=os.path.join(DATA_DIR, os.getenv("DATABASE_FILE","splice.db"))
    ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    name = f"backup-{ts}.zip"; path = os.path.join(BACKUPS_DIR, name)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        if os.path.exists(DB_PATH): z.write(DB_PATH, arcname=os.path.basename(DB_PATH))
        for folder in (os.path.join(DATA_DIR,'uploads'), os.path.join(DATA_DIR,'workmaps')):
            if not os.path.exists(folder): continue
            for r,_,files in os.walk(folder):
                for f in files:
                    full = os.path.join(r, f)
                    arc  = os.path.relpath(full, start=DATA_DIR)
                    z.write(full, arcname=arc)
    flash("Backup criado.", "ok"); return redirect(url_for("admin_backups"))

@app.get("/admin/backups/download/<path:name>")
def download_backup(name):
    u=current_user()
    if not u or not u['is_admin']: abort(403)
    return send_from_directory(os.path.join(DATA_DIR,'backups'), name, as_attachment=True)

@app.get("/admin/reports")
def admin_reports():
    u=current_user()
    if not u or not u['is_admin']: abort(403)
    def gen():
        yield "id,title,body,user,created_at\n"
        with closing(get_db()) as db:
            cur = db.execute("SELECT r.id, r.title, r.body, u.username, r.created_at FROM records r JOIN users u ON u.id=r.user_id ORDER BY r.id")
            for row in cur:
                def esc(s): s=str(s).replace('"','""'); return f'"{s}"'
                yield f'{row[0]},{esc(row[1])},{esc(row[2])},{esc(row[3])},{row[4]}\n'
    return Response(gen(), mimetype="text/csv", headers={"Content-Disposition":"attachment; filename=records.csv"})

@app.errorhandler(403)
def e403(e): return render_template("403.html"), 403
@app.errorhandler(404)
def e404(e): return render_template("404.html"), 404
@app.errorhandler(500)
def e500(e): return render_template("500.html"), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT","8080")), debug=True)