
import os, io, zipfile, datetime
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, abort, send_from_directory, send_file, Response
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY","dev-secret")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///app.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = int(os.environ.get("MAX_CONTENT_LENGTH_MB","20")) * 1024 * 1024
app.config["DISABLE_REGISTER"] = os.environ.get("DISABLE_REGISTER","0") == "1"

db = SQLAlchemy(app)

# ---------- MODELOS ----------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    def set_password(self, pw): self.password_hash = generate_password_hash(pw)
    def check_password(self, pw): return check_password_hash(self.password_hash, pw)

class WorkMap(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    filename = db.Column(db.String(255), nullable=False)  # em static/maps

class MapAssignment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    map_id = db.Column(db.Integer, db.ForeignKey("work_map.id"), nullable=False)

class Record(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    device_name = db.Column(db.String(200), nullable=False)
    fusion_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    launched = db.Column(db.Boolean, default=False)
    map_id = db.Column(db.Integer, db.ForeignKey("work_map.id"))
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

class Photo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    record_id = db.Column(db.Integer, db.ForeignKey("record.id"), nullable=False)
    filename = db.Column(db.String(255), nullable=False)  # em static/uploads

# ---------- HELPERS ----------
def login_required(f):
    @wraps(f)
    def w(*a, **kw):
        if "user_id" not in session: return redirect(url_for("login"))
        return f(*a, **kw)
    return w

def admin_required(f):
    @wraps(f)
    def w(*a, **kw):
        if "user_id" not in session: return redirect(url_for("login"))
        u = db.session.get(User, session["user_id"])
        if not u or not u.is_admin: abort(403)
        return f(*a, **kw)
    return w

def allowed_image(fn):
    return "." in fn and fn.rsplit(".",1)[1].lower() in {"png","jpg","jpeg"}

def assigned_maps(user_id):
    ids = [a.map_id for a in MapAssignment.query.filter_by(user_id=user_id).all()]
    return WorkMap.query.filter(WorkMap.id.in_(ids)).all() if ids else []

def maps_dict():
    return {m.id: m.title for m in WorkMap.query.all()}

def filter_dates(q, start, end):
    if start:
        try:
            ds = datetime.datetime.strptime(start,"%Y-%m-%d")
            q = q.filter(Record.created_at >= ds)
        except: ...
    if end:
        try:
            de = datetime.datetime.strptime(end,"%Y-%m-%d") + datetime.timedelta(days=1)
            q = q.filter(Record.created_at < de)
        except: ...
    return q

@app.before_request
def ensure_db():
    db.create_all()

# ---------- AUTH ----------
@app.route("/register", methods=["GET","POST"])
def register():
    if app.config["DISABLE_REGISTER"]:
        abort(403)
    if User.query.count() > 0:  # só antes do primeiro usuário
        abort(403)
    if request.method == "POST":
        u = request.form.get("username","").strip()
        p = request.form.get("password","").strip()
        if not u or not p:
            flash("Preencha usuário e senha.","danger")
        elif User.query.filter_by(username=u).first():
            flash("Usuário já existe.","danger")
        else:
            user = User(username=u, is_admin=True); user.set_password(p)
            db.session.add(user); db.session.commit()
            flash("Administrador criado. Faça login.","success")
            return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        u = request.form.get("username","").strip()
        p = request.form.get("password","").strip()
        user = User.query.filter_by(username=u).first()
        if user and user.check_password(p):
            session["user_id"] = user.id
            return redirect(url_for("dashboard"))
        flash("Credenciais inválidas.","danger")
    return render_template("login.html")

@app.route("/logout")
def logout(): session.clear(); return redirect(url_for("login"))

# ---------- DASHBOARD ----------
@app.route("/")
@login_required
def dashboard():
    u = db.session.get(User, session["user_id"])
    return render_template("admin_home.html" if u.is_admin else "dashboard.html", user=u)

# ---------- ADMIN: USUÁRIOS ----------
@app.route("/admin/users", methods=["GET","POST"])
@admin_required
def admin_users():
    if request.method == "POST":
        u = request.form.get("username","").strip()
        p = request.form.get("password","").strip()
        is_admin = request.form.get("is_admin") == "1"
        if not u or not p:
            flash("Informe usuário e senha.","danger")
        elif User.query.filter_by(username=u).first():
            flash("Usuário já existe.","danger")
        else:
            user = User(username=u, is_admin=is_admin); user.set_password(p)
            db.session.add(user); db.session.commit()
            flash("Usuário criado.","success")
        return redirect(url_for("admin_users"))
    users = User.query.order_by(User.username.asc()).all()
    return render_template("admin_users.html", users=users)

# ---------- ADMIN: MAPAS PDF ----------
@app.route("/admin/maps", methods=["GET","POST"])
@admin_required
def admin_maps():
    if request.method == "POST":
        title = request.form.get("title","").strip()
        f = request.files.get("pdf")
        if not title or not f or not f.filename.lower().endswith(".pdf"):
            flash("Título e PDF são obrigatórios.","danger"); return redirect(url_for("admin_maps"))
        name = secure_filename(f.filename)
        dest = os.path.join(app.root_path,"static","maps",name)
        f.save(dest)
        m = WorkMap(title=title, filename=name); db.session.add(m); db.session.commit()
        flash("Mapa salvo.","success"); return redirect(url_for("admin_maps"))
    maps = WorkMap.query.order_by(WorkMap.id.desc()).all()
    users = User.query.order_by(User.username.asc()).all()
    return render_template("admin_maps.html", maps=maps, users=users)

@app.route("/admin/maps/assign", methods=["POST"])
@admin_required
def assign_map():
    map_id = request.form.get("map_id", type=int)
    user_ids = request.form.getlist("user_ids")
    if not map_id or not user_ids:
        flash("Selecione um mapa e pelo menos um usuário.","danger"); return redirect(url_for("admin_maps"))
    for uid in user_ids:
        uid = int(uid)
        if not MapAssignment.query.filter_by(user_id=uid, map_id=map_id).first():
            db.session.add(MapAssignment(user_id=uid, map_id=map_id))
    db.session.commit()
    flash("Atribuições salvas.","success"); return redirect(url_for("admin_maps"))

@app.route("/maps/<int:map_id>/download")
@login_required
def download_map(map_id):
    m = db.session.get(WorkMap, map_id) or abort(404)
    u = db.session.get(User, session["user_id"])
    allowed = u.is_admin or MapAssignment.query.filter_by(user_id=u.id, map_id=map_id).first()
    if not allowed: abort(403)
    return send_from_directory(os.path.join(app.root_path,"static","maps"), m.filename, as_attachment=True)

# ---------- REGISTROS ----------
@app.route("/new", methods=["GET","POST"])
@login_required
def new_record():
    u = db.session.get(User, session["user_id"])
    maps = assigned_maps(u.id)
    if request.method == "POST":
        device = request.form.get("device_name","").strip()
        fusion = int(request.form.get("fusion_count","0") or 0)
        map_id = request.form.get("map_id", type=int)
        if not device: flash("Informe o dispositivo.","danger"); return redirect(url_for("new_record"))
        if not maps: flash("Você não tem mapas atribuídos.","danger"); return redirect(url_for("new_record"))
        if not map_id or map_id not in [m.id for m in maps]: flash("Selecione um mapa válido.","danger"); return redirect(url_for("new_record"))
        rec = Record(device_name=device, fusion_count=fusion, user_id=u.id, map_id=map_id)
        db.session.add(rec); db.session.commit()
        photos = request.files.getlist("photos")[:6]
        for i,f in enumerate(photos):
            if f and allowed_image(f.filename):
                name = secure_filename(f"{rec.id}_{i}_{f.filename}")
                f.save(os.path.join(app.root_path,"static","uploads",name))
                db.session.add(Photo(record_id=rec.id, filename=name))
        db.session.commit()
        flash("Registro criado.","success"); return redirect(url_for("dashboard"))
    return render_template("new_record.html", assigned_maps=maps)

@app.route("/record/<int:rid>")
@login_required
def view_record(rid):
    rec = db.session.get(Record, rid) or abort(404)
    u = db.session.get(User, session["user_id"])
    if not u.is_admin and u.id != rec.user_id: abort(403)
    photos = Photo.query.filter_by(record_id=rec.id).all()
    wmap = db.session.get(WorkMap, rec.map_id) if rec.map_id else None
    return render_template("view_record.html", rec=rec, photos=photos, wmap=wmap)

@app.route("/record/<int:rid>/edit", methods=["GET","POST"])
@login_required
def edit_record(rid):
    rec = db.session.get(Record, rid) or abort(404)
    u = db.session.get(User, session["user_id"])
    if not u.is_admin and u.id != rec.user_id: abort(403)
    maps = assigned_maps(u.id) if not u.is_admin else WorkMap.query.all()
    if request.method == "POST":
        rec.device_name = request.form.get("device_name","").strip()
        rec.fusion_count = int(request.form.get("fusion_count","0") or 0)
        mid = request.form.get("map_id", type=int)
        if mid: rec.map_id = mid
        db.session.commit()
        flash("Registro atualizado.","success"); return redirect(url_for("view_record", rid=rec.id))
    return render_template("edit_record.html", rec=rec, assigned_maps=maps)

# ---------- RELATÓRIOS ----------
def query_records_for_admin(args):
    q = Record.query
    uid = args.get("user_id", type=int)
    if uid: q = q.filter(Record.user_id==uid)
    q = filter_dates(q, args.get("start"), args.get("end"))
    if args.get("launched_only")=="1" and args.get("not_launched_only")!="1":
        q = q.filter(Record.launched==True)
    if args.get("not_launched_only")=="1" and args.get("launched_only")!="1":
        q = q.filter(Record.launched==False)
    return q.order_by(Record.created_at.desc())

@app.route("/admin/reports")
@admin_required
def admin_reports():
    records = query_records_for_admin(request.args).all()
    users = User.query.order_by(User.username.asc()).all()
    return render_template("admin_reports.html", records=records, users=users, maps=maps_dict())

@app.route("/my/reports")
@login_required
def my_reports():
    uid = session["user_id"]
    q = Record.query.filter(Record.user_id==uid)
    q = filter_dates(q, request.args.get("start"), request.args.get("end"))
    if request.args.get("launched_only")=="1" and request.args.get("not_launched_only")!="1":
        q = q.filter(Record.launched==True)
    if request.args.get("not_launched_only")=="1" and request.args.get("launched_only")!="1":
        q = q.filter(Record.launched==False)
    return render_template("my_reports.html", records=q.order_by(Record.created_at.desc()).all(), maps=maps_dict())

@app.route("/admin/reports.csv")
@admin_required
def admin_reports_csv():
    rows = query_records_for_admin(request.args).all()
    def gen():
        yield "Usuario,Dispositivo,Fusoes,Data,Mapa,Lancado\n"
        for r in rows:
            u = db.session.get(User, r.user_id)
            m = db.session.get(WorkMap, r.map_id) if r.map_id else None
            yield f"{(u.username if u else '')},{r.device_name},{r.fusion_count},{r.created_at:%Y-%m-%d %H:%M},{(m.title if m else '')},{'SIM' if r.launched else 'NAO'}\n"
    return Response(gen(), mimetype="text/csv", headers={"Content-Disposition":"attachment;filename=relatorio_admin.csv"})

@app.route("/admin/reports_photos.zip")
@admin_required
def admin_reports_photos_zip():
    rows = query_records_for_admin(request.args).all()
    mem = io.BytesIO()
    with zipfile.ZipFile(mem,"w",zipfile.ZIP_DEFLATED) as z:
        for r in rows:
            user = db.session.get(User, r.user_id)
            folder = f\"{(user.username if user else 'user')}_{r.id}_{r.device_name}\".replace(' ','_')
            for p in Photo.query.filter_by(record_id=r.id).all():
                src = os.path.join(app.root_path,"static","uploads",p.filename)
                if os.path.exists(src):
                    z.write(src, arcname=f\"{folder}/{p.filename}\")
    mem.seek(0)
    return send_file(mem, mimetype="application/zip", as_attachment=True, download_name="fotos_filtradas.zip")

# ---------- ADMIN: DETALHE E LANÇADO ----------
@app.route("/admin/device/<int:rid>")
@admin_required
def admin_device_detail(rid):
    rec = db.session.get(Record, rid) or abort(404)
    user = db.session.get(User, rec.user_id)
    photos = Photo.query.filter_by(record_id=rec.id).all()
    wmap = db.session.get(WorkMap, rec.map_id) if rec.map_id else None
    return render_template("device_detail_admin.html", rec=rec, user=user, photos=photos, wmap=wmap)

@app.route("/admin/device/<int:rid>/toggle", methods=["POST"])
@admin_required
def admin_toggle_launched(rid):
    rec = db.session.get(Record, rid) or abort(404)
    rec.launched = not bool(rec.launched)
    db.session.commit()
    flash("Status atualizado.","success")
    return redirect(url_for("admin_device_detail", rid=rid))

if __name__ == "__main__":
    app.run(debug=True)
