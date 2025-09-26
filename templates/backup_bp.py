from flask import Blueprint, current_app, render_template, request, redirect, url_for, flash, send_from_directory
from werkzeug.utils import secure_filename
import os, sqlite3, shutil, time

backup_bp = Blueprint("backup_bp", __name__, url_prefix="/admin/backup")

ALLOWED_EXTENSIONS = {".db", ".sqlite", ".sqlite3", ".sql"}

def allowed_ext(filename: str) -> bool:
    _, ext = os.path.splitext(filename.lower())
    return ext in ALLOWED_EXTENSIONS

def get_db_path():
    db_path = os.environ.get("SQLITE_PATH")
    if db_path:
        return db_path
    candidates = [
        os.path.join(current_app.instance_path, "app.db"),
        os.path.join(current_app.root_path, "app.db"),
        os.path.join(os.getcwd(), "app.db"),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    os.makedirs(current_app.instance_path, exist_ok=True)
    return os.path.join(current_app.instance_path, "app.db")

@backup_bp.route("/", methods=["GET"])
def index():
    backup_folder = current_app.config.get("BACKUP_UPLOAD_FOLDER", os.path.join(current_app.root_path, "backups"))
    os.makedirs(backup_folder, exist_ok=True)
    files = []
    for f in sorted(os.listdir(backup_folder)):
        p = os.path.join(backup_folder, f)
        if os.path.isfile(p):
            files.append(f)
    return render_template("admin/backup.html", files=files, db_path=get_db_path())

@backup_bp.route("/download/<path:filename>")
def download(filename):
    backup_folder = current_app.config.get("BACKUP_UPLOAD_FOLDER", os.path.join(current_app.root_path, "backups"))
    return send_from_directory(backup_folder, filename, as_attachment=True)

@backup_bp.route("/upload", methods=["POST"])
def upload():
    file = request.files.get("file")
    if not file or file.filename == "":
        flash("Selecione um arquivo de backup (.db, .sqlite, .sqlite3, .sql).", "warning")
        return redirect(url_for("backup_bp.index"))
    _, ext = os.path.splitext(file.filename.lower())
    if ext not in ALLOWED_EXTENSIONS:
        flash("Extensão não permitida. Use .db, .sqlite, .sqlite3 ou .sql.", "danger")
        return redirect(url_for("backup_bp.index"))
    backup_folder = current_app.config.get("BACKUP_UPLOAD_FOLDER", os.path.join(current_app.root_path, "backups"))
    os.makedirs(backup_folder, exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S")
    filename = secure_filename(file.filename)
    stored = f"{ts}__{filename}"
    dest = os.path.join(backup_folder, stored)
    file.save(dest)
    flash(f"Backup enviado: {stored}", "success")
    return redirect(url_for("backup_bp.index"))

@backup_bp.route("/restore", methods=["POST"])
def restore():
    chosen = request.form.get("chosen")
    if not chosen:
        flash("Selecione um arquivo de backup para restaurar.", "warning")
        return redirect(url_for("backup_bp.index"))
    backup_folder = current_app.config.get("BACKUP_UPLOAD_FOLDER", os.path.join(current_app.root_path, "backups"))
    src = os.path.join(backup_folder, chosen)
    if not os.path.exists(src):
        flash("Arquivo não encontrado.", "danger")
        return redirect(url_for("backup_bp.index"))
    db_path = get_db_path()
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    safedir = os.path.join(backup_folder, "_auto_safety")
    os.makedirs(safedir, exist_ok=True)
    safety_copy = os.path.join(safedir, f"safety__{time.strftime('%Y%m%d-%H%M%S')}__{os.path.basename(db_path)}")
    if os.path.exists(db_path):
        try:
            shutil.copy2(db_path, safety_copy)
        except Exception as e:
            current_app.logger.exception("Erro ao criar cópia de segurança: %s", e)
    _, ext = os.path.splitext(src.lower())
    try:
        if ext in {".db", ".sqlite", ".sqlite3"}:
            shutil.copy2(src, db_path)
        elif ext == ".sql":
            if os.path.exists(db_path):
                os.remove(db_path)
            conn = sqlite3.connect(db_path)
            with open(src, "r", encoding="utf-8") as f:
                sql_script = f.read()
            conn.executescript(sql_script)
            conn.commit()
            conn.close()
        else:
            flash("Extensão não suportada.", "danger")
            return redirect(url_for("backup_bp.index"))
    except Exception as e:
        current_app.logger.exception("Falha na restauração: %s", e)
        flash(f"Falha na restauração: {e}", "danger")
        return redirect(url_for("backup_bp.index"))
    flash("Restauração concluída com sucesso. Reinicie o serviço para aplicar totalmente.", "success")
    return redirect(url_for("backup_bp.index"))

@backup_bp.route("/create", methods=["POST", "GET"])
def create_backup():
    backup_folder = current_app.config.get("BACKUP_UPLOAD_FOLDER", os.path.join(current_app.root_path, "backups"))
    os.makedirs(backup_folder, exist_ok=True)
    db_path = get_db_path()
    if not os.path.exists(db_path):
        flash("Banco de dados não encontrado para criar backup.", "warning")
        return redirect(url_for("backup_bp.index"))
    ts = time.strftime("%Y%m%d-%H%M%S")
    name = f"app-{ts}.db"
    dest = os.path.join(backup_folder, name)
    try:
        shutil.copy2(db_path, dest)
        flash(f"Backup criado: {name}", "success")
    except Exception as e:
        current_app.logger.exception("Erro ao criar backup: %s", e)
        flash(f"Falha ao criar backup: {e}", "danger")
    return redirect(url_for("backup_bp.index"))
