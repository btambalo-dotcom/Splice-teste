
from flask import Blueprint, current_app, render_template, request, redirect, url_for, flash, send_from_directory
from werkzeug.utils import secure_filename
import os
import sqlite3
import shutil
import time
import zipfile
import json
import tempfile
import threading
import signal

backup_bp = Blueprint("backup_bp", __name__, url_prefix="/admin/backup")

ALLOWED_DB_EXT = {".db", ".sqlite", ".sqlite3", ".sql"}
ALLOWED_ZIP_EXT = {".zip"}


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


def get_backup_dir():
    d = current_app.config.get("BACKUP_UPLOAD_FOLDER", os.path.join(current_app.root_path, "backups"))
    os.makedirs(d, exist_ok=True)
    return d


def guess_data_dirs():
    dirs = []
    env_csv = os.environ.get("BACKUP_INCLUDE_DIRS")
    if env_csv:
        for p in env_csv.split(","):
            p = p.strip()
            if p and os.path.isdir(p):
                dirs.append(p)

    for key in ("UPLOAD_FOLDER", "MEDIA_ROOT", "DATA_DIR", "STATIC_UPLOADS"):
        p = os.environ.get(key)
        if p and os.path.isdir(p):
            if p not in dirs:
                dirs.append(p)

    candidates = [
        os.path.join(current_app.root_path, "uploads"),
        os.path.join(current_app.root_path, "media"),
        os.path.join(current_app.root_path, "static", "uploads"),
    ]
    for c in candidates:
        if os.path.isdir(c) and c not in dirs:
            dirs.append(c)

    # Deduplicate preserving order
    out, seen = [], set()
    for d in dirs:
        if d not in seen:
            out.append(d)
            seen.add(d)
    return out


def build_full_backup_zip(dest_folder, label="full"):
    os.makedirs(dest_folder, exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S")
    name = f"{label}-{ts}.zip"
    out_zip = os.path.join(dest_folder, name)

    db_path = get_db_path()
    data_dirs = guess_data_dirs()

    manifest = {
        "type": "splice-full-backup",
        "timestamp": ts,
        "db_path": db_path,
        "data_dirs": data_dirs,
        "app_root": current_app.root_path,
        "version": 1,
    }

    with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))

        if os.path.exists(db_path):
            z.write(db_path, arcname="db/app.db")

        for d in data_dirs:
            base = os.path.basename(d.rstrip(os.sep)) or "files"
            for root, _, files in os.walk(d):
                for f in files:
                    full = os.path.join(root, f)
                    rel = os.path.relpath(full, d)
                    arc = os.path.join("files", base, rel)
                    z.write(full, arcname=arc)

    return out_zip


def restore_from_full_zip(zip_path, merge_files=True):
    backup_dir = get_backup_dir()
    # Safety backup obrigatório
    safety_zip = build_full_backup_zip(backup_dir, label="safety")
    if not os.path.exists(safety_zip) or os.path.getsize(safety_zip) == 0:
        raise RuntimeError("Falha ao gerar backup de segurança. Restauração cancelada.")

    with zipfile.ZipFile(zip_path, "r") as z:
        try:
            manifest = json.loads(z.read("manifest.json").decode("utf-8"))
        except Exception:
            manifest = {}

        # Fechar conexões antes
        try:
            ext = getattr(current_app, "extensions", {}) or {}
            sa = ext.get("sqlalchemy") if isinstance(ext, dict) else None
            if sa and hasattr(sa, "db"):
                sa.db.engine.dispose()
        except Exception as _e:
            current_app.logger.info(f"SQLAlchemy dispose antes de restaurar: {_e}")

        db_path = get_db_path()
        os.makedirs(os.path.dirname(db_path), exist_ok=True)

        tempdir = tempfile.mkdtemp(prefix="restore_", dir=backup_dir)
        if "db/app.db" in z.namelist():
            extracted = z.extract("db/app.db", path=tempdir)
            tmp = db_path + ".tmp"
            shutil.copy2(extracted, tmp)
            os.replace(tmp, db_path)
        elif "db.sql" in z.namelist():
            extracted = z.extract("db.sql", path=tempdir)
            if os.path.exists(db_path):
                os.remove(db_path)
            conn = sqlite3.connect(db_path)
            with open(extracted, "r", encoding="utf-8") as f:
                conn.executescript(f.read())
            conn.commit()
            conn.close()

        # Arquivos
        file_members = [n for n in z.namelist() if n.startswith("files/")]
        groups = {}
        for n in file_members:
            parts = n.split("/", 3)
            if len(parts) >= 3:
                base = parts[1]
                groups.setdefault(base, []).append(n)

        target_dirs = manifest.get("data_dirs") or []
        mapping = {}
        for td in target_dirs:
            base = os.path.basename(td.rstrip(os.sep)) or "files"
            mapping[base] = td

        for base, members in groups.items():
            dest = mapping.get(base) or os.path.join(current_app.root_path, "uploads", base)
            os.makedirs(dest, exist_ok=True)
            if not merge_files:
                for item in os.listdir(dest):
                    p = os.path.join(dest, item)
                    if os.path.isdir(p):
                        shutil.rmtree(p, ignore_errors=True)
                    else:
                        try:
                            os.remove(p)
                        except Exception:
                            pass
            for n in members:
                if n.endswith("/"):
                    continue
                extracted = z.extract(n, path=tempdir)
                rel = n.split("/", 2)[-1]
                rel = rel.split("/", 1)[-1] if "/" in rel else os.path.basename(rel)
                target = os.path.join(dest, rel)
                os.makedirs(os.path.dirname(target), exist_ok=True)
                shutil.copy2(extracted, target)

        # Fechar conexões depois
        try:
            ext = getattr(current_app, "extensions", {}) or {}
            sa = ext.get("sqlalchemy") if isinstance(ext, dict) else None
            if sa and hasattr(sa, "db"):
                sa.db.engine.dispose()
        except Exception as _e:
            current_app.logger.info(f"SQLAlchemy dispose após restaurar: {_e}")


@backup_bp.route("/", methods=["GET"])
def index():
    backup_folder = get_backup_dir()
    files = [f for f in sorted(os.listdir(backup_folder)) if os.path.isfile(os.path.join(backup_folder, f))]
    return render_template("admin/backup.html", files=files, db_path=get_db_path())


@backup_bp.route("/download/<path:filename>")
def download(filename):
    return send_from_directory(get_backup_dir(), filename, as_attachment=True)


@backup_bp.route("/create", methods=["POST", "GET"])
def create_backup():
    backup_folder = get_backup_dir()
    db_path = get_db_path()
    if not os.path.exists(db_path):
        flash("Banco de dados não encontrado para criar backup.", "warning")
        return redirect(url_for("backup_bp.index"))
    ts = time.strftime("%Y%m%d-%H%M%S")
    name = f"app-{ts}.db"
    dest = os.path.join(backup_folder, name)
    try:
        shutil.copy2(db_path, dest)
        flash(f"Backup do DB criado: {name}", "success")
    except Exception as e:
        current_app.logger.exception("Erro ao criar backup do DB: %s", e)
        flash(f"Falha ao criar backup: {e}", "danger")
    return redirect(url_for("backup_bp.index"))


@backup_bp.route("/create_full", methods=["POST", "GET"])
def create_full():
    backup_folder = get_backup_dir()
    try:
        zpath = build_full_backup_zip(backup_folder, label="full")
        flash(f"Backup completo criado: {os.path.basename(zpath)}", "success")
    except Exception as e:
        current_app.logger.exception("Erro ao criar backup completo: %s", e)
        flash(f"Falha ao criar backup completo: {e}", "danger")
    return redirect(url_for("backup_bp.index"))


@backup_bp.route("/upload", methods=["POST"])
def upload():
    file = request.files.get("file")
    if not file or file.filename == "":
        flash("Selecione um arquivo de backup.", "warning")
        return redirect(url_for("backup_bp.index"))
    filename = secure_filename(file.filename)
    _, ext = os.path.splitext(filename.lower())
    if ext not in (ALLOWED_DB_EXT | ALLOWED_ZIP_EXT):
        flash("Extensão não permitida. Use .db, .sqlite, .sqlite3, .sql ou .zip.", "danger")
        return redirect(url_for("backup_bp.index"))
    dest = os.path.join(get_backup_dir(), f"{time.strftime('%Y%m%d-%H%M%S')}__{filename}")
    file.save(dest)
    flash(f"Arquivo enviado: {os.path.basename(dest)}", "success")
    return redirect(url_for("backup_bp.index"))


@backup_bp.route("/restore", methods=["POST"])
def restore():
    chosen = request.form.get("chosen")
    merge_files = request.form.get("merge_files") == "1"
    if not chosen:
        flash("Selecione um arquivo de backup para restaurar.", "warning")
        return redirect(url_for("backup_bp.index"))
    src = os.path.join(get_backup_dir(), chosen)
    if not os.path.exists(src):
        flash("Arquivo não encontrado.", "danger")
        return redirect(url_for("backup_bp.index"))

    _, ext = os.path.splitext(src.lower())
    try:
        if ext in ALLOWED_ZIP_EXT:
            restore_from_full_zip(src, merge_files=merge_files)
        elif ext in ALLOWED_DB_EXT:
            build_full_backup_zip(get_backup_dir(), label="safety")
            # Fechar engine antes
            try:
                extx = getattr(current_app, "extensions", {}) or {}
                sa = extx.get("sqlalchemy") if isinstance(extx, dict) else None
                if sa and hasattr(sa, "db"):
                    sa.db.engine.dispose()
            except Exception as _e:
                current_app.logger.info(f"SQLAlchemy dispose antes do restore DB: {_e}")
            db_path = get_db_path()
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
            if ext == ".sql":
                if os.path.exists(db_path):
                    os.remove(db_path)
                conn = sqlite3.connect(db_path)
                with open(src, "r", encoding="utf-8") as f:
                    conn.executescript(f.read())
                conn.commit()
                conn.close()
            else:
                tmp = db_path + ".tmp"
                shutil.copy2(src, tmp)
                os.replace(tmp, db_path)
            # Fechar engine depois
            try:
                extx = getattr(current_app, "extensions", {}) or {}
                sa = extx.get("sqlalchemy") if isinstance(extx, dict) else None
                if sa and hasattr(sa, "db"):
                    sa.db.engine.dispose()
            except Exception as _e:
                current_app.logger.info(f"SQLAlchemy dispose após restore DB: {_e}")
        else:
            flash("Extensão não suportada.", "danger")
            return redirect(url_for("backup_bp.index"))
    except Exception as e:
        current_app.logger.exception("Falha na restauração: %s", e)
        flash(f"Falha na restauração: {e}", "danger")
        return redirect(url_for("backup_bp.index"))

    # Mensagem e auto-restart robusto
    flash("Restauração concluída com sucesso. Aplicando alterações…", "success")

    def _kick_restart():
        try:
            pid = os.getpid()
            current_app.logger.warning(f"Enviando SIGTERM para o processo {pid} para aplicar restauração.")
            os.kill(pid, signal.SIGTERM)
            time.sleep(2.0)
        except Exception as e:
            try:
                current_app.logger.warning(f"Falha ao enviar SIGTERM: {e}")
            except Exception:
                pass
        try:
            current_app.logger.warning("Forçando saída (os._exit(0)) para garantir restart.")
        except Exception:
            pass
        os._exit(0)

    t = threading.Thread(target=_kick_restart, daemon=True)
    t.start()

    return redirect(url_for("backup_bp.index"))
