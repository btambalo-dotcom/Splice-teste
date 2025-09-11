
import os, datetime, io, zipfile
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, abort, send_from_directory, Response, send_file
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///app.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = int(os.environ.get("MAX_CONTENT_LENGTH_MB", "20")) * 1024 * 1024

db = SQLAlchemy(app)

# ---- Models ----
class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)

    def set_password(self, pw): self.password_hash = generate_password_hash(pw)
    def check_password(self, pw): return check_password_hash(self.password_hash, pw)

class WorkMap(db.Model):
    __tablename__ = "work_maps"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    filename = db.Column(db.String(255), nullable=False)  # static/maps

class MapAssignment(db.Model):
    __tablename__ = "map_assignments"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    map_id = db.Column(db.Integer, db.ForeignKey("work_maps.id"), nullable=False)

class Record(db.Model):
    __tablename__ = "records"
    id = db.Column(db.Integer, primary_key=True)
    device_name = db.Column(db.String(200), nullable=False)
    fusion_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    launched = db.Column(db.Boolean, default=False)
    map_id = db.Column(db.Integer, db.ForeignKey("work_maps.id"))
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

class Photo(db.Model):
    __tablename__ = "photos"
    id = db.Column(db.Integer, primary_key=True)
    record_id = db.Column(db.Integer, db.ForeignKey("records.id"), nullable=False)
    filename = db.Column(db.String(255), nullable=False)  # static/uploads

# ---- Helpers & decorators ----
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

def allowed_file(name): return "." in name and name.rsplit(".",1)[1].lower() in {"png","jpg","jpeg"}

def get_assigned_maps(user_id):
    ids = [m.map_id for m in MapAssignment.query.filter_by(user_id=user_id).all()]
    return WorkMap.query.filter(WorkMap.id.in_(ids)).all() if ids else []

@app.before_request
def _bootstrap():
    db.create_all()

# ---- Auth ----
@app.route("/register", methods=["GET","POST"])
def register():
    if User.query.count() > 0:
        abort(403)
    if request.method == "POST":
        u = request.form["username"].strip()
        p = request.form["password"].strip()
        if not u or not p:
            flash("Preencha usuário e senha.", "danger")
        elif User.query.filter_by(username=u).first():
            flash("Usuário já existe.", "danger")
        else:
            user = User(username=u, is_admin=True)
            user.set_password(p)
            db.session.add(user); db.session.commit()
            flash("Admin criado. Faça login.", "success")
            return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        u = request.form["username"].strip()
        p = request.form["password"].strip()
        user = User.query.filter_by(username=u).first()
        if user and user.check_password(p):
            session["user_id"] = user.id
            return redirect(url_for("dashboard"))
        flash("Credenciais inválidas.", "danger")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ---- Dashboard ----
@app.route("/")
@login_required
def dashboard():
    user = db.session.get(User, session["user_id"])
    if user.is_admin:
        return render_template("admin_home.html", user=user)
    else:
        return render_template("dashboard.html", user=user)

# ---- Admin: users ----
@app.route("/admin/users", methods=["GET","POST"])
@admin_required
def admin_users():
    if request.method == "POST":
        u = request.form.get("username","").strip()
        p = request.form.get("password","").strip()
        is_admin = True if request.form.get("is_admin") == "1" else False
        if not u or not p:
            flash("Informe usuário e senha.", "danger")
        elif User.query.filter_by(username=u).first():
            flash("Usuário já existe.", "danger")
        else:
            user = User(username=u, is_admin=is_admin)
            user.set_password(p)
            db.session.add(user); db.session.commit()
            flash("Usuário criado.", "success")
        return redirect(url_for("admin_users"))
    users = User.query.order_by(User.username.asc()).all()
    return render_template("admin_users.html", users=users)

# ---- Maps (admin) ----
@app.route("/admin/maps", methods=["GET","POST"])
@admin_required
def admin_maps():
    if request.method == "POST":
        title = request.form.get("title","").strip()
        f = request.files.get("pdf")
        if not title or not f or not f.filename.lower().endswith(".pdf"):
            flash("Informe título e PDF.", "danger")
            return redirect(url_for("admin_maps"))
        name = secure_filename(f.filename)
        f.save(os.path.join(app.root_path,"static","maps",name))
        wm = WorkMap(title=title, filename=name)
        db.session.add(wm); db.session.commit()
        flash("Mapa salvo.", "success")
        return redirect(url_for("admin_maps"))
    maps = WorkMap.query.order_by(WorkMap.id.desc()).all()
    users = User.query.order_by(User.username.asc()).all()
    return render_template("admin_maps.html", maps=maps, users=users)

@app.route("/admin/maps/assign", methods=["POST"])
@admin_required
def admin_map_assign():
    map_id = request.form.get("map_id", type=int)
    user_ids = request.form.getlist("user_ids")
    if not map_id or not user_ids:
        flash("Selecione um mapa e ao menos um usuário.", "danger")
        return redirect(url_for("admin_maps"))
    for uid in user_ids:
        uid = int(uid)
        if not MapAssignment.query.filter_by(user_id=uid, map_id=map_id).first():
            db.session.add(MapAssignment(user_id=uid, map_id=map_id))
    db.session.commit()
    flash("Atribuições salvas.", "success")
    return redirect(url_for("admin_maps"))

@app.route("/maps/<int:map_id>/download")
@login_required
def download_map(map_id):
    m = db.session.get(WorkMap, map_id) or abort(404)
    user = db.session.get(User, session["user_id"])
    allowed = user.is_admin or MapAssignment.query.filter_by(user_id=user.id, map_id=map_id).first()
    if not allowed: abort(403)
    return send_from_directory(os.path.join(app.root_path,"static","maps"), m.filename, as_attachment=True)

# ---- New record (user) ----
@app.route("/new", methods=["GET","POST"])
@login_required
def new_record():
    user = db.session.get(User, session["user_id"])
    assigned = get_assigned_maps(user.id)
    if request.method == "POST":
        device_name = request.form.get("device_name","").strip()
        fusion_count = int(request.form.get("fusion_count","0") or 0)
        map_id = request.form.get("map_id", type=int)
        if not device_name:
            flash("Informe o nome do dispositivo.", "danger"); return redirect(url_for("new_record"))
        if not assigned:
            flash("Nenhum mapa atribuído. Fale com o administrador.", "danger"); return redirect(url_for("new_record"))
        if not map_id or map_id not in [m.id for m in assigned]:
            flash("Selecione um mapa válido.", "danger"); return redirect(url_for("new_record"))
        rec = Record(device_name=device_name, fusion_count=fusion_count, user_id=user.id, map_id=map_id)
        db.session.add(rec); db.session.commit()
        files = request.files.getlist("photos")
        for i,f in enumerate(files[:6]):
            if f and allowed_file(f.filename):
                fname = secure_filename(f"{rec.id}_{i}_{f.filename}")
                f.save(os.path.join(app.root_path,"static","uploads",fname))
                db.session.add(Photo(record_id=rec.id, filename=fname))
        db.session.commit()
        flash("Registro criado.", "success")
        return redirect(url_for("dashboard"))
    return render_template("new_record.html", assigned_maps=assigned)

# ---- Viewing & editing records (user) ----
@app.route("/record/<int:rid>")
@login_required
def view_record(rid):
    rec = db.session.get(Record, rid) or abort(404)
    user = db.session.get(User, session["user_id"])
    if user.id != rec.user_id and not user.is_admin: abort(403)
    photos = Photo.query.filter_by(record_id=rec.id).all()
    wmap = db.session.get(WorkMap, rec.map_id) if rec.map_id else None
    return render_template("view_record.html", rec=rec, photos=photos, wmap=wmap)

@app.route("/record/<int:rid>/edit", methods=["GET","POST"])
@login_required
def edit_record(rid):
    rec = db.session.get(Record, rid) or abort(404)
    user = db.session.get(User, session["user_id"])
    if user.id != rec.user_id and not user.is_admin: abort(403)
    assigned = get_assigned_maps(user.id) if not user.is_admin else WorkMap.query.all()
    if request.method == "POST":
        rec.device_name = request.form.get("device_name","").strip()
        rec.fusion_count = int(request.form.get("fusion_count","0") or 0)
        mid = request.form.get("map_id", type=int)
        if mid: rec.map_id = mid
        db.session.commit()
        flash("Registro atualizado.", "success")
        return redirect(url_for("view_record", rid=rec.id))
    return render_template("edit_record.html", rec=rec, assigned_maps=assigned)

# ---- Admin device detail & launched toggle ----
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
    flash("Status de lançado atualizado.", "success")
    return redirect(url_for("admin_device_detail", rid=rid))

# ---- Reports ----
def _apply_date_filters(q, start, end):
    if start:
        try:
            ds = datetime.datetime.strptime(start, "%Y-%m-%d")
            q = q.filter(Record.created_at >= ds)
        except: pass
    if end:
        try:
            de = datetime.datetime.strptime(end, "%Y-%m-%d") + datetime.timedelta(days=1)
            q = q.filter(Record.created_at < de)
        except: pass
    return q

@app.route("/admin/reports")
@admin_required
def admin_reports():
    launched_only = request.args.get("launched_only") == "1"
    not_launched_only = request.args.get("not_launched_only") == "1"
    user_id = request.args.get("user_id", type=int)
    start = request.args.get("start"); end = request.args.get("end")

    q = Record.query
    if user_id: q = q.filter(Record.user_id==user_id)
    q = _apply_date_filters(q, start, end)
    if launched_only and not not_launched_only:
        q = q.filter(Record.launched == True)
    elif not_launched_only and not launched_only:
        q = q.filter(Record.launched == False)
    records = q.order_by(Record.created_at.desc()).all()
    users = User.query.order_by(User.username.asc()).all()
    maps = get_maps_dict()
    return render_template("admin_reports.html", records=records, users=users, maps=maps)


@app.route("/my/reports")
@login_required
def my_reports():
    launched_only = request.args.get("launched_only") == "1"
    not_launched_only = request.args.get("not_launched_only") == "1"
    start = request.args.get("start"); end = request.args.get("end")
    uid = session["user_id"]
    q = Record.query.filter(Record.user_id==uid)
    q = _apply_date_filters(q, start, end)
    if launched_only and not not_launched_only:
        q = q.filter(Record.launched == True)
    elif not_launched_only and not launched_only:
        q = q.filter(Record.launched == False)
    records = q.order_by(Record.created_at.desc()).all()
    maps = get_maps_dict()
    return render_template("my_reports.html", records=records, maps=maps)


# ---- CSV ----
@app.route("/admin/reports.csv")
@admin_required
def admin_reports_csv():
    launched_only = request.args.get("launched_only") == "1"
    user_id = request.args.get("user_id", type=int)
    start = request.args.get("start"); end = request.args.get("end")
    q = Record.query
    if user_id: q = q.filter(Record.user_id==user_id)
    q = _apply_date_filters(q, start, end)
    if launched_only: q = q.filter(Record.launched == True)
    rows = q.order_by(Record.created_at.desc()).all()

    def gen():
        yield "Usuario,Dispositivo,Fusoes,Data,Mapa,Lancado\n"
        for r in rows:
            u = db.session.get(User, r.user_id)
            m = db.session.get(WorkMap, r.map_id) if r.map_id else None
            yield f"{(u.username if u else '')},{r.device_name},{r.fusion_count},{r.created_at:%Y-%m-%d %H:%M},{(m.title if m else '')},{'SIM' if r.launched else 'NAO'}\n"
    return Response(gen(), mimetype="text/csv", headers={"Content-Disposition":"attachment;filename=relatorio_admin.csv"})

@app.route("/my/reports.csv")
@login_required
def my_reports_csv():
    launched_only = request.args.get("launched_only") == "1"
    start = request.args.get("start"); end = request.args.get("end")
    uid = session["user_id"]
    q = Record.query.filter(Record.user_id==uid)
    q = _apply_date_filters(q, start, end)
    if launched_only: q = q.filter(Record.launched == True)
    rows = q.order_by(Record.created_at.desc()).all()

    def gen():
        yield "Dispositivo,Fusoes,Data,Mapa,Lancado\n"
        for r in rows:
            m = db.session.get(WorkMap, r.map_id) if r.map_id else None
            yield f"{r.device_name},{r.fusion_count},{r.created_at:%Y-%m-%d %H:%M},{(m.title if m else '')},{'SIM' if r.launched else 'NAO'}\n"
    return Response(gen(), mimetype="text/csv", headers={"Content-Disposition":"attachment;filename=meu_relatorio.csv"})

# ---- Admin reset (env-gated) ----
@app.route("/force_reset_admin")
def force_reset_admin():
    if os.environ.get("FORCE_RESET_ADMIN") != "1":
        abort(404)
    expected = os.environ.get("RESET_ADMIN_TOKEN","")
    token = request.args.get("token","")
    if not expected or token != expected:
        return "Token inválido.", 403
    new_pw = os.environ.get("NEW_ADMIN_PASSWORD","admin123")
    admin = User.query.filter_by(is_admin=True).order_by(User.id.asc()).first()
    if not admin:
        admin = User(username="admin", is_admin=True)
        admin.set_password(new_pw); db.session.add(admin); db.session.commit()
        return "Admin criado.", 200
    admin.set_password(new_pw); db.session.commit()
    return "Senha redefinida.", 200

if __name__ == "__main__":
    app.run(debug=True)


def get_maps_dict():
    return {m.id: m.title for m in WorkMap.query.all()}

@app.route("/admin/reports_photos.zip")
@admin_required
def admin_reports_photos_zip():
    launched_only = request.args.get("launched_only") == "1"
    not_launched_only = request.args.get("not_launched_only") == "1"
    user_id = request.args.get("user_id", type=int)
    start = request.args.get("start"); end = request.args.get("end")

    q = Record.query
    if user_id: q = q.filter(Record.user_id==user_id)
    q = _apply_date_filters(q, start, end)
    if launched_only and not not_launched_only:
        q = q.filter(Record.launched == True)
    elif not_launched_only and not launched_only:
        q = q.filter(Record.launched == False)
    recs = q.order_by(Record.created_at.desc()).all()

    mem = io.BytesIO()
    with zipfile.ZipFile(mem, "w", zipfile.ZIP_DEFLATED) as z:
        for r in recs:
            user = db.session.get(User, r.user_id)
            folder = f"{(user.username if user else 'user')}_{r.id}_{r.device_name}".replace(' ', '_')
            photos = Photo.query.filter_by(record_id=r.id).all()
            for p in photos:
                src = os.path.join(app.root_path, "static", "uploads", p.filename)
                if os.path.exists(src):
                    z.write(src, arcname=f"{folder}/{p.filename}")
    mem.seek(0)
    return send_file(mem, mimetype="application/zip", as_attachment=True, download_name="fotos_filtradas.zip")
