
import os, sqlite3
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, session, abort
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "app.db"
UPLOAD_PHOTOS = BASE_DIR / "static" / "uploads" / "photos"
UPLOAD_MAPS = BASE_DIR / "static" / "uploads" / "maps"

ALLOWED_PHOTO_EXT = {"jpg","jpeg","png","webp"}
ALLOWED_PDF_EXT = {"pdf"}

app = Flask(__name__)
app.secret_key = "mude-esta-chave"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    db = get_db()
    db.executescript("""
    PRAGMA foreign_keys=ON;
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        name TEXT,
        password_hash TEXT NOT NULL,
        is_admin INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS maps(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        filename TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS user_map_access(
        user_id INTEGER,
        map_id INTEGER,
        PRIMARY KEY(user_id, map_id),
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY(map_id) REFERENCES maps(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS devices(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        label TEXT NOT NULL,
        created_by INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'Pendente',
        selected_map_id INTEGER NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY(created_by) REFERENCES users(id),
        FOREIGN KEY(selected_map_id) REFERENCES maps(id)
    );
    CREATE TABLE IF NOT EXISTS device_photos(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        device_id INTEGER NOT NULL,
        filename TEXT NOT NULL,
        FOREIGN KEY(device_id) REFERENCES devices(id) ON DELETE CASCADE
    );
    """)
    cur = db.execute("SELECT COUNT(*) c FROM users")
    if cur.fetchone()["c"] == 0:
        db.execute("INSERT INTO users(email,name,password_hash,is_admin) VALUES(?,?,?,1)",
                   ("admin@example.com","Admin", generate_password_hash("admin123")))
        db.execute("INSERT INTO users(email,name,password_hash,is_admin) VALUES(?,?,?,0)",
                   ("tech@example.com","Técnico", generate_password_hash("tech123")))
        db.commit()

def require_login():
    if "user_id" not in session:
        return redirect(url_for("login"))
    return None

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email","").strip().lower()
        pw = request.form.get("password","")
        db = get_db()
        u = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if u and check_password_hash(u["password_hash"], pw):
            session["user_id"] = u["id"]
            session["is_admin"] = bool(u["is_admin"])
            session["name"] = u["name"] or email
            return redirect(url_for("index"))
        flash("E-mail ou senha inválidos.", "error")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/")
def index():
    if "user_id" not in session:
        return redirect(url_for("login"))
    if session.get("is_admin"):
        return redirect(url_for("admin_reports"))
    return redirect(url_for("new_device"))

@app.route("/device/new", methods=["GET","POST"])
def new_device():
    redir = require_login()
    if redir: return redir
    uid = session["user_id"]
    db = get_db()
    maps = db.execute("""SELECT m.* FROM maps m
                         JOIN user_map_access uma ON uma.map_id=m.id
                         WHERE uma.user_id=? ORDER BY m.title""", (uid,)).fetchall()
    if request.method == "POST":
        label = request.form.get("label","").strip()
        map_id = request.form.get("map_id", type=int)
        if not label or not map_id:
            flash("Informe o nome do dispositivo e selecione um mapa.", "error")
            return render_template("device_new.html", maps=maps)
        cur = db.execute("INSERT INTO devices(label, created_by, selected_map_id) VALUES(?,?,?)",
                   (label, uid, map_id))
        device_id = cur.lastrowid
        files = request.files.getlist("photos")
        adicionadas = 0
        for f in files[:5]:
            if not f or not f.filename:
                continue
            ext = f.filename.rsplit(".",1)[-1].lower()
            if ext not in ALLOWED_PHOTO_EXT:
                continue
            fn = f"{device_id}_{adicionadas}_" + secure_filename(f.filename)
            dest = UPLOAD_PHOTOS / fn
            dest.parent.mkdir(parents=True, exist_ok=True)
            f.save(dest)
            db.execute("INSERT INTO device_photos(device_id, filename) VALUES(?,?)", (device_id, fn))
            adicionadas += 1
        db.commit()
        flash("Dispositivo lançado com sucesso.", "success")
        return redirect(url_for("device_detail", device_id=device_id))
    return render_template("device_new.html", maps=maps)

@app.route("/device/<int:device_id>")
def device_detail(device_id):
    redir = require_login()
    if redir: return redir
    db = get_db()
    d = db.execute("""SELECT d.*, u.name as creator, m.title as map_title
                      FROM devices d 
                      JOIN users u ON u.id=d.created_by
                      JOIN maps m ON m.id=d.selected_map_id
                      WHERE d.id=?""", (device_id,)).fetchone()
    if not d: abort(404)
    photos = db.execute("SELECT * FROM device_photos WHERE device_id=?", (device_id,)).fetchall()
    return render_template("device_detail.html", d=d, photos=photos)

@app.route("/admin/reports")
def admin_reports():
    redir = require_login()
    if redir: return redir
    if not session.get("is_admin"): abort(403)
    db = get_db()
    rows = db.execute("""SELECT d.id, d.label, d.status, d.created_at, u.name as creator, m.title as map_title
                         FROM devices d 
                         JOIN users u ON u.id=d.created_by
                         JOIN maps m ON m.id=d.selected_map_id
                         ORDER BY d.created_at DESC""").fetchall()
    return render_template("admin_reports.html", rows=rows)

@app.route("/admin/mark_launched/<int:device_id>", methods=["POST"])
def admin_mark_launched(device_id):
    redir = require_login()
    if redir: return redir
    if not session.get("is_admin"): abort(403)
    db = get_db()
    db.execute("UPDATE devices SET status='Lançado' WHERE id=?", (device_id,))
    db.commit()
    flash("Status atualizado para Lançado.", "success")
    return redirect(url_for("device_detail", device_id=device_id))

@app.route("/admin/maps", methods=["GET","POST"])
def admin_maps():
    redir = require_login()
    if redir: return redir
    if not session.get("is_admin"): abort(403)
    db = get_db()
    if request.method == "POST":
        title = request.form.get("title","").strip()
        f = request.files.get("pdf")
        if not title or not f or not f.filename.lower().endswith(".pdf"):
            flash("Informe o título e selecione um arquivo PDF.", "error")
        else:
            fn = secure_filename(f.filename)
            dest = UPLOAD_MAPS / fn
            f.save(dest)
            db.execute("INSERT INTO maps(title, filename) VALUES(?,?)", (title, fn))
            db.commit()
            flash("Mapa enviado.", "success")
    maps = db.execute("SELECT * FROM maps ORDER BY id DESC").fetchall()
    users = db.execute("SELECT id, name, email FROM users ORDER BY is_admin DESC, name").fetchall()
    access = db.execute("SELECT user_id, map_id FROM user_map_access").fetchall()
    access_pairs = {(a[0], a[1]) for a in access}
    return render_template("admin_maps.html", maps=maps, users=users, access_pairs=access_pairs)

@app.route("/admin/maps/assign", methods=["POST"])
def admin_maps_assign():
    redir = require_login()
    if redir: return redir
    if not session.get("is_admin"): abort(403)
    db = get_db()
    user_id = request.form.get("user_id", type=int)
    map_id = request.form.get("map_id", type=int)
    action = request.form.get("action")
    if user_id and map_id and action in {"grant","revoke"}:
        if action == "grant":
            db.execute("INSERT OR IGNORE INTO user_map_access(user_id,map_id) VALUES(?,?)",(user_id,map_id))
        else:
            db.execute("DELETE FROM user_map_access WHERE user_id=? AND map_id=?", (user_id,map_id))
        db.commit()
        flash("Acesso atualizado.", "success")
    return redirect(url_for("admin_maps"))

@app.route("/maps/download/<int:map_id>")
def download_map(map_id):
    redir = require_login()
    if redir: return redir
    db = get_db()
    uid = session["user_id"]
    ok = db.execute("SELECT 1 FROM user_map_access WHERE user_id=? AND map_id=?", (uid,map_id)).fetchone()
    if not (ok or session.get("is_admin")):
        abort(403)
    row = db.execute("SELECT * FROM maps WHERE id=?", (map_id,)).fetchone()
    if not row: abort(404)
    return send_from_directory(UPLOAD_MAPS, row["filename"], as_attachment=True)

@app.before_request
def _ensure_db():
    if not DB_PATH.exists():
        init_db()

@app.route("/force_reset_admin")
def force_reset_admin():
    db = get_db()
    db.execute("UPDATE users SET password_hash=? WHERE is_admin=1",
               (generate_password_hash("admin123"),))
    db.commit()
    return "Senha do admin redefinida para admin123 (remova esta rota em produção)."

if __name__ == "__main__":
    app.run(debug=True)


@app.route("/health")
def health():
    return "OK", 200
