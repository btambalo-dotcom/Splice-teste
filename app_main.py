# -*- coding: utf-8 -*-
"""
Splice Admin App - Sistema Completo de Gerenciamento de Registros
"""

import os

# === INICIALIZAÇÃO DO BANCO DE DADOS ===
from database_manager import DatabaseManager

# Inicializar gerenciador de banco de dados
db_manager = DatabaseManager()
# Garantir que o banco está completamente inicializado
db_manager.initialize_complete_database()

# Usar as configurações do gerenciador
DATA_DIR = db_manager.data_dir
DB_PATH = db_manager.db_path
DATABASE_URL = f"sqlite:///{DB_PATH}"

# === IMPORTS PRINCIPAIS ===
from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, session, send_from_directory, abort, Response, jsonify
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import sqlite3, csv, zipfile, json
from contextlib import closing
from io import StringIO, BytesIO
from datetime import datetime

# === CONFIGURAÇÃO DA APLICAÇÃO ===
app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")
max_len_mb = int(os.environ.get("MAX_CONTENT_LENGTH_MB", "20"))
app.config["MAX_CONTENT_LENGTH"] = max_len_mb * 1024 * 1024

# Configurações de diretórios
UPLOAD_FOLDER = os.path.join(DATA_DIR, "uploads")
WORKMAP_FOLDER = os.path.join(DATA_DIR, "workmaps")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
MAX_FILES_PER_RECORD = 6

# Criar diretórios necessários
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(WORKMAP_FOLDER, exist_ok=True)

# === FUNÇÕES DE BANCO DE DADOS ===
def get_db():
    """Retorna conexão com o banco de dados"""
    return db_manager.get_connection()

def log_user_action(user_id, action, table_name=None, record_id=None, old_values=None, new_values=None):
    """Registra ações do usuário para auditoria"""
    try:
        with closing(get_db()) as db:
            db.execute("""
                INSERT INTO system_logs 
                (user_id, action, table_name, record_id, old_values, new_values, ip_address, user_agent)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                user_id, action, table_name, record_id,
                json.dumps(old_values) if old_values else None,
                json.dumps(new_values) if new_values else None,
                request.remote_addr if request else None,
                request.user_agent.string if request and request.user_agent else None
            ))
            db.commit()
    except Exception as e:
        print(f"Erro ao registrar log: {e}")

# === DECORADORES ===
def login_required(view):
    from functools import wraps
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped

def admin_required(view):
    from functools import wraps
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        if not session.get("is_admin"):
            flash("Acesso restrito ao administrador.", "error")
            return redirect(url_for("dashboard"))
        return view(*args, **kwargs)
    return wrapped

# === FUNÇÕES AUXILIARES ===
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def user_has_access_to_map(user_id, work_map_id):
    with closing(get_db()) as db:
        row = db.execute(
            "SELECT 1 FROM user_work_map_access WHERE user_id=? AND work_map_id=?",
            (user_id, work_map_id)
        ).fetchone()
        return row is not None

def get_user_accessible_maps(user_id):
    with closing(get_db()) as db:
        return db.execute("""
            SELECT wm.* FROM work_maps wm 
            JOIN user_work_map_access a ON a.work_map_id = wm.id 
            WHERE a.user_id=? 
            ORDER BY wm.uploaded_at DESC
        """, (user_id,)).fetchall()

# === ROTAS DE AUTENTICAÇÃO ===
@app.route("/register", methods=["GET", "POST"])
def register():
    with closing(get_db()) as db:
        total_users = db.execute("SELECT COUNT(1) FROM users").fetchone()[0]
        if total_users > 0:
            flash("Registro desativado. Apenas o administrador pode criar novos usuários.", "error")
            return redirect(url_for("login"))

        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "").strip()
            
            if not username or not password:
                flash("Preencha todos os campos.", "error")
                return redirect(url_for("register"))
            
            is_admin = 1  # Primeiro usuário é admin
            pw_hash = generate_password_hash(password)
            
            try:
                cursor = db.cursor()
                cursor.execute(
                    "INSERT INTO users (username, password_hash, is_admin) VALUES (?, ?, ?)", 
                    (username, pw_hash, is_admin)
                )
                user_id = cursor.lastrowid
                db.commit()
                
                # Log da ação
                log_user_action(user_id, "USER_REGISTERED", "users", user_id, 
                              None, {"username": username, "is_admin": is_admin})
                
                flash("Usuário criado. Faça login.", "success")
                return redirect(url_for("login"))
                
            except sqlite3.IntegrityError:
                flash("Nome de usuário já existe.", "error")
                return redirect(url_for("register"))
    
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        
        with closing(get_db()) as db:
            row = db.execute(
                "SELECT id, password_hash, is_admin FROM users WHERE username = ?", 
                (username,)
            ).fetchone()
            
            if not row or not check_password_hash(row["password_hash"], password):
                flash("Credenciais inválidas.", "error")
                return redirect(url_for("login"))
            
            session["user_id"] = row["id"]
            session["username"] = username
            session["is_admin"] = bool(row["is_admin"])
            
            # Log da ação
            log_user_action(row["id"], "USER_LOGIN")
            
            return redirect(url_for("dashboard"))
    
    return render_template("login.html")

@app.route("/logout")
def logout():
    user_id = session.get("user_id")
    if user_id:
        log_user_action(user_id, "USER_LOGOUT")
    
    session.clear()
    flash("Sessão encerrada.", "info")
    return redirect(url_for("login"))

# === ROTAS PRINCIPAIS ===
@app.route("/")
@login_required
def dashboard():
    with closing(get_db()) as db:
        # Buscar registros com informações adicionais
        recs = db.execute("""
            SELECT r.id, r.device_name, r.fusion_count, r.created_at, r.status,
                   wm.title as work_map_title,
                   COUNT(p.id) as photo_count
            FROM records r 
            LEFT JOIN work_maps wm ON r.work_map_id = wm.id
            LEFT JOIN photos p ON p.record_id = r.id
            WHERE r.user_id = ? 
            GROUP BY r.id
            ORDER BY r.created_at DESC
        """, (session["user_id"],)).fetchall()
        
        # Estatísticas do usuário
        stats = db.execute("""
            SELECT 
                COUNT(*) as total_records,
                SUM(fusion_count) as total_fusions,
                COUNT(DISTINCT device_name) as unique_devices
            FROM records 
            WHERE user_id = ?
        """, (session["user_id"],)).fetchone()
    
    return render_template("dashboard.html", records=recs, stats=stats)

@app.route("/new", methods=["GET", "POST"])
@login_required
def new_record():
    user_id = session["user_id"]
    
    with closing(get_db()) as db:
        # Carregar mapas disponíveis para o usuário
        try:
            maps = get_user_accessible_maps(user_id)
        except Exception:
            maps = []
        
        if request.method == "POST":
            device_name = request.form.get("device_name", "").strip()
            fusion_count = request.form.get("fusion_count", "").strip()
            work_map_id = request.form.get("work_map_id", type=int)
            notes = request.form.get("notes", "").strip()
            
            if not device_name or not fusion_count.isdigit():
                flash("Preencha o nome do dispositivo e um número de fusões válido.", "error")
                return render_template("new_record.html", maps=maps)
            
            # Validar mapa de trabalho (opcional para admin)
            if work_map_id and not session.get("is_admin") and not any(m["id"] == work_map_id for m in maps):
                flash("Você não tem acesso a esse Mapa de Trabalho.", "error")
                return render_template("new_record.html", maps=maps)
            
            cursor = db.cursor()
            cursor.execute("""
                INSERT INTO records (user_id, device_name, fusion_count, status, work_map_id, notes) 
                VALUES (?, ?, ?, 'draft', ?, ?)
            """, (user_id, device_name, int(fusion_count), work_map_id, notes))
            
            record_id = cursor.lastrowid
            
            # Processar fotos
            files = request.files.getlist("photos")
            saved_photos = []
            
            for f in files[:MAX_FILES_PER_RECORD]:
                if not f.filename:
                    continue
                
                ext = f.filename.rsplit(".", 1)[-1].lower()
                if ext not in ALLOWED_EXTENSIONS:
                    continue
                
                # Nome seguro para o arquivo
                safe_filename = secure_filename(f.filename)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                final_filename = f"{timestamp}_{safe_filename}"
                dest_path = os.path.join(UPLOAD_FOLDER, final_filename)
                
                try:
                    f.save(dest_path)
                    file_size = os.path.getsize(dest_path)
                    
                    cursor.execute("""
                        INSERT INTO photos (record_id, filename, original_filename, file_size) 
                        VALUES (?, ?, ?, ?)
                    """, (record_id, final_filename, f.filename, file_size))
                    
                    saved_photos.append(final_filename)
                except Exception as e:
                    print(f"Erro ao salvar foto {f.filename}: {e}")
            
            db.commit()
            
            # Log da ação
            log_user_action(user_id, "RECORD_CREATED", "records", record_id, 
                          None, {
                              "device_name": device_name, 
                              "fusion_count": int(fusion_count),
                              "photos_count": len(saved_photos)
                          })
            
            if len(files) > 0 and len(saved_photos) == 0:
                flash("Registro criado, mas nenhuma foto foi salva (verifique os tipos permitidos).", "warning")
            else:
                flash("Registro criado com sucesso!", "success")
            
            return redirect(url_for("dashboard"))
    
    return render_template("new_record.html", maps=maps)

@app.route("/record/<int:record_id>")
@login_required
def view_record(record_id):
    uid = session.get('user_id')
    is_admin = bool(session.get('is_admin'))
    
    with closing(get_db()) as db:
        # Buscar registro com informações completas
        rec = db.execute("""
            SELECT r.*, u.username AS author, wm.title as work_map_title
            FROM records r 
            JOIN users u ON u.id = r.user_id 
            LEFT JOIN work_maps wm ON r.work_map_id = wm.id
            WHERE r.id = ? AND (r.user_id = ? OR ?)
        """, (record_id, uid, 1 if is_admin else 0)).fetchone()
        
        if not rec:
            abort(404)
        
        # Buscar fotos
        photos = db.execute("""
            SELECT id, filename, original_filename, file_size, uploaded_at 
            FROM photos 
            WHERE record_id = ? 
            ORDER BY uploaded_at ASC
        """, (record_id,)).fetchall()
        
        # Buscar mapas disponíveis (para admin)
        maps_for_admin = []
        if is_admin:
            maps_for_admin = db.execute(
                "SELECT * FROM work_maps ORDER BY uploaded_at DESC"
            ).fetchall()
    
    return render_template("view_record.html", 
                         rec=rec, photos=photos, maps_for_admin=maps_for_admin)

@app.route("/uploads/<path:filename>")
@login_required
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

@app.route("/record/<int:record_id>/delete", methods=["POST"])
@login_required
def delete_record(record_id):
    user_id = session["user_id"]
    is_admin = session.get("is_admin", False)
    
    with closing(get_db()) as db:
        # Verificar se o usuário pode deletar
        rec = db.execute("""
            SELECT id, device_name FROM records 
            WHERE id = ? AND (user_id = ? OR ?)
        """, (record_id, user_id, is_admin)).fetchone()
        
        if not rec:
            abort(404)
        
        # Buscar fotos para deletar arquivos
        photos = db.execute("SELECT filename FROM photos WHERE record_id = ?", (record_id,)).fetchall()
        
        # Deletar arquivos de foto
        for p in photos:
            fpath = os.path.join(UPLOAD_FOLDER, p["filename"])
            if os.path.exists(fpath):
                try:
                    os.remove(fpath)
                except Exception as e:
                    print(f"Erro ao deletar arquivo {p['filename']}: {e}")
        
        # Deletar do banco
        db.execute("DELETE FROM photos WHERE record_id = ?", (record_id,))
        db.execute("DELETE FROM records WHERE id = ?", (record_id,))
        db.commit()
        
        # Log da ação
        log_user_action(user_id, "RECORD_DELETED", "records", record_id,
                      {"device_name": rec["device_name"]}, None)
    
    flash("Registro apagado.", "info")
    return redirect(url_for("dashboard"))

# === ROTAS DE ADMINISTRAÇÃO ===
@app.route("/admin")
@admin_required
def admin_home():
    with closing(get_db()) as db:
        # Estatísticas gerais
        stats = db.execute("""
            SELECT 
                (SELECT COUNT(*) FROM users) as total_users,
                (SELECT COUNT(*) FROM records) as total_records,
                (SELECT SUM(fusion_count) FROM records) as total_fusions,
                (SELECT COUNT(*) FROM photos) as total_photos,
                (SELECT COUNT(*) FROM work_maps) as total_work_maps
        """).fetchone()
        
        # Atividade recente
        recent_activity = db.execute("""
            SELECT action, table_name, created_at, u.username
            FROM system_logs sl
            LEFT JOIN users u ON sl.user_id = u.id
            ORDER BY sl.created_at DESC
            LIMIT 10
        """).fetchall()
    
    return render_template("admin_home.html", stats=stats, recent_activity=recent_activity)

@app.route("/admin/users", methods=["GET", "POST"])
@admin_required
def admin_users():
    with closing(get_db()) as db:
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "").strip()
            is_admin = 1 if request.form.get("is_admin") == "on" else 0
            
            if not username or not password:
                flash("Preencha usuário e senha.", "error")
                return redirect(url_for("admin_users"))
            
            try:
                pw_hash = generate_password_hash(password)
                cursor = db.cursor()
                cursor.execute(
                    "INSERT INTO users (username, password_hash, is_admin) VALUES (?, ?, ?)", 
                    (username, pw_hash, is_admin)
                )
                user_id = cursor.lastrowid
                db.commit()
                
                # Log da ação
                log_user_action(session["user_id"], "USER_CREATED", "users", user_id,
                              None, {"username": username, "is_admin": is_admin})
                
                flash("Usuário criado com sucesso.", "success")
                
            except sqlite3.IntegrityError:
                flash("Nome de usuário já existe.", "error")
            
            return redirect(url_for("admin_users"))
        
        users = db.execute("""
            SELECT id, username, is_admin, created_at,
                   (SELECT COUNT(*) FROM records WHERE user_id = users.id) as record_count
            FROM users 
            ORDER BY username ASC
        """).fetchall()
    
    return render_template("admin_users.html", users=users)

@app.route("/admin/users/<int:user_id>/toggle_admin", methods=["POST"])
@admin_required
def admin_toggle_admin(user_id):
    with closing(get_db()) as db:
        row = db.execute("SELECT username, is_admin FROM users WHERE id = ?", (user_id,)).fetchone()
        if not row:
            flash("Usuário não encontrado.", "error")
            return redirect(url_for("admin_users"))
        
        new_val = 0 if row["is_admin"] else 1
        db.execute("UPDATE users SET is_admin = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", 
                  (new_val, user_id))
        db.commit()
        
        # Log da ação
        log_user_action(session["user_id"], "USER_ADMIN_TOGGLED", "users", user_id,
                      {"is_admin": row["is_admin"]}, {"is_admin": new_val})
        
        action = "promovido a" if new_val else "removido de"
        flash(f"Usuário {row['username']} {action} administrador.", "success")
    
    return redirect(url_for("admin_users"))

# === ROTAS DE BACKUP E MANUTENÇÃO ===
@app.route("/admin/backup")
@admin_required
def admin_backup():
    try:
        backup_path = db_manager.backup_database("manual")
        backup_name = os.path.basename(backup_path)
        
        # Log da ação
        log_user_action(session["user_id"], "BACKUP_CREATED", None, None,
                      None, {"backup_file": backup_name})
        
        flash(f"Backup criado: {backup_name}", "success")
        
    except Exception as e:
        flash(f"Falha ao criar backup: {e}", "error")
    
    return redirect(url_for("admin_home"))

# === ROTAS DE RELATÓRIOS ===
@app.route("/admin/reports", methods=["GET"])
@admin_required
def admin_reports():
    start_str = request.args.get("start", "").strip()
    end_str = request.args.get("end", "").strip()
    user_id = request.args.get("user_id", type=int)

    # Construir filtros
    clauses = []
    params = []
    
    if start_str:
        clauses.append("date(r.created_at) >= date(?)")
        params.append(start_str)
    if end_str:
        clauses.append("date(r.created_at) <= date(?)")
        params.append(end_str)
    if user_id:
        clauses.append("r.user_id = ?")
        params.append(user_id)
    
    where_sql = ("WHERE " + " AND ".join(clauses)) if clauses else ""

    with closing(get_db()) as db:
        # Registros detalhados
        rows = db.execute(f"""
            SELECT r.id, u.username, r.device_name, r.fusion_count, r.created_at, 
                   r.status, wm.title as work_map_title,
                   COUNT(p.id) as photo_count
            FROM records r 
            JOIN users u ON u.id = r.user_id 
            LEFT JOIN work_maps wm ON r.work_map_id = wm.id
            LEFT JOIN photos p ON p.record_id = r.id
            {where_sql} 
            GROUP BY r.id
            ORDER BY r.created_at DESC
        """, tuple(params)).fetchall()

        # Resumo por usuário
        users_summary = db.execute(f"""
            SELECT u.id, u.username, 
                   COUNT(DISTINCT r.device_name) AS devices, 
                   COUNT(r.id) AS registros, 
                   COALESCE(SUM(r.fusion_count), 0) AS fusoes
            FROM records r 
            JOIN users u ON u.id = r.user_id 
            {where_sql} 
            GROUP BY u.id, u.username 
            ORDER BY fusoes DESC, devices DESC
        """, tuple(params)).fetchall()

        # Lista de usuários para filtro
        users = db.execute("SELECT id, username FROM users ORDER BY username ASC").fetchall()

    return render_template("admin_reports.html",
                         rows=rows, users=users, 
                         users_summary=users_summary,
                         selected_user_id=user_id, start=start_str, end=end_str)

# === ROTAS DE API ===
@app.route("/api/stats")
@login_required
def api_stats():
    with closing(get_db()) as db:
        if session.get("is_admin"):
            # Stats gerais para admin
            stats = db.execute("""
                SELECT 
                    (SELECT COUNT(*) FROM users) as total_users,
                    (SELECT COUNT(*) FROM records) as total_records,
                    (SELECT SUM(fusion_count) FROM records) as total_fusions,
                    (SELECT COUNT(*) FROM photos) as total_photos
            """).fetchone()
        else:
            # Stats do usuário
            user_id = session["user_id"]
            stats = db.execute("""
                SELECT 
                    COUNT(*) as total_records,
                    SUM(fusion_count) as total_fusions,
                    COUNT(DISTINCT device_name) as unique_devices,
                    (SELECT COUNT(*) FROM photos p JOIN records r ON p.record_id = r.id 
                     WHERE r.user_id = ?) as total_photos
                FROM records WHERE user_id = ?
            """, (user_id, user_id)).fetchone()
    
    return jsonify(dict(stats))

# === ROTAS DE SAÚDE ===
@app.route("/healthz")
def healthz():
    try:
        stats = db_manager.get_database_stats()
        integrity_ok = db_manager.validate_data_integrity()
        
        return jsonify({
            "status": "healthy",
            "database": {
                "path": db_manager.db_path,
                "tables": {k: v for k, v in stats.items() 
                          if k not in ["database_size", "database_modified"]},
                "integrity": integrity_ok
            },
            "timestamp": datetime.utcnow().isoformat()
        })
    except Exception as e:
        return jsonify({
            "status": "error", 
            "error": str(e)
        }), 500

if __name__ == "__main__":
    print("🚀 Iniciando Splice Admin App...")
    print(f"   Banco de dados: {DB_PATH}")
    print(f"   Diretório de dados: {DATA_DIR}")
    print(f"   Upload folder: {UPLOAD_FOLDER}")
    
    # Verificar se há usuários
    with closing(get_db()) as db:
        user_count = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        admin_count = db.execute("SELECT COUNT(*) FROM users WHERE is_admin = 1").fetchone()[0]
        
        print(f"   Usuários cadastrados: {user_count}")
        print(f"   Administradores: {admin_count}")
    
    app.run(host="0.0.0.0", port=5000, debug=False)
