
from flask import Flask, render_template, request, redirect, url_for, session, send_from_directory, flash, Response
from werkzeug.utils import secure_filename
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
from datetime import datetime
import csv, io, os

app = Flask(__name__)
app.secret_key = "supersecretkey"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///splice.db"
app.config["UPLOAD_FOLDER"] = "static/uploads"
app.config["MAP_FOLDER"] = "static/maps"

db = SQLAlchemy(app)

# Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), default="user")

class Device(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    fusion_count = db.Column(db.Integer, default=0)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    photo = db.Column(db.String(200))
    released = db.Column(db.Boolean, default=False)

class WorkMap(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(200), nullable=False)
    assigned_users = db.Column(db.String(500))

# Helpers
def require_login():
    if "user_id" not in session:
        return False
    return True

def require_admin():
    return "role" in session and session["role"] == "admin"

# Rotas básicas
@app.route("/")
def index():
    if not require_login():
        return redirect(url_for("login"))
    devices = Device.query.order_by(Device.timestamp.desc()).all()
    return render_template("index.html", devices=devices)

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"].strip()
        user = User.query.filter_by(username=username, password=password).first()
        if user:
            session["user_id"] = user.id
            session["role"] = user.role
            return redirect(url_for("index"))
        else:
            flash("Credenciais inválidas")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/upload_device", methods=["GET", "POST"])
def upload_device():
    if not require_login():
        return redirect(url_for("login"))
    if request.method == "POST":
        name = request.form["name"].strip()
        fusion_count = int(request.form.get("fusion_count", 0))
        photo = request.files.get("photo")
        filename = None
        if photo and photo.filename:
            filename = secure_filename(photo.filename)
            photo.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
        device = Device(name=name, fusion_count=fusion_count, user_id=session["user_id"], photo=filename)
        db.session.add(device)
        db.session.commit()
        return redirect(url_for("index"))
    return render_template("upload_device.html")

@app.route("/release/<int:device_id>")
def release_device(device_id):
    if not require_login() or not require_admin():
        return redirect(url_for("login"))
    device = Device.query.get_or_404(device_id)
    device.released = True
    db.session.commit()
    return redirect(url_for("index"))

# Mapas de trabalho (PDF)
@app.route("/upload_map", methods=["GET", "POST"])
def upload_map():
    if not require_login() or not require_admin():
        return redirect(url_for("login"))
    if request.method == "POST":
        pdf = request.files.get("pdf")
        if pdf and pdf.filename:
            filename = secure_filename(pdf.filename)
            pdf.save(os.path.join(app.config["MAP_FOLDER"], filename))
            workmap = WorkMap(filename=filename, assigned_users="")
            db.session.add(workmap)
            db.session.commit()
            flash("Mapa enviado com sucesso")
            return redirect(url_for("maps"))
    return render_template("upload_map.html")

@app.route("/maps")
def maps():
    if not require_login():
        return redirect(url_for("login"))
    maps = WorkMap.query.order_by(WorkMap.id.desc()).all()
    return render_template("maps.html", maps=maps)

@app.route("/download_map/<int:map_id>")
def download_map(map_id):
    if not require_login():
        return redirect(url_for("login"))
    workmap = WorkMap.query.get_or_404(map_id)
    path = os.path.join(app.config["MAP_FOLDER"], workmap.filename)
    if not os.path.exists(path):
        flash("Arquivo não encontrado.")
        return redirect(url_for("maps"))
    return send_from_directory(app.config["MAP_FOLDER"], workmap.filename, as_attachment=True)

# Relatórios (admin)
@app.route("/reports", methods=["GET", "POST"])
def reports():
    if not require_login() or not require_admin():
        return redirect(url_for("login"))
    users = User.query.order_by(User.username.asc()).all()

    # filtros
    start = request.values.get("start", "")
    end = request.values.get("end", "")
    user_id = request.values.get("user_id", "")

    q = Device.query
    if start:
        try:
            dt = datetime.strptime(start, "%Y-%m-%d")
            q = q.filter(Device.timestamp >= dt)
        except ValueError:
            pass
    if end:
        try:
            dt = datetime.strptime(end, "%Y-%m-%d")
            # incluir o dia inteiro
            q = q.filter(Device.timestamp < dt.replace(hour=23, minute=59, second=59))
        except ValueError:
            pass
    if user_id:
        try:
            uid = int(user_id)
            q = q.filter(Device.user_id == uid)
        except ValueError:
            pass

    q = q.order_by(Device.timestamp.desc())
    records = q.all()

    # totais
    total_fusions = sum(r.fusion_count or 0 for r in records)
    total_devices = len(records)

    return render_template("admin_reports.html",
                           records=records,
                           users=users,
                           start=start, end=end, user_id=user_id,
                           total_fusions=total_fusions,
                           total_devices=total_devices)

@app.route("/reports/export")
def reports_export():
    if not require_login() or not require_admin():
        return redirect(url_for("login"))
    start = request.values.get("start", "")
    end = request.values.get("end", "")
    user_id = request.values.get("user_id", "")

    q = Device.query
    if start:
        try:
            dt = datetime.strptime(start, "%Y-%m-%d")
            q = q.filter(Device.timestamp >= dt)
        except ValueError:
            pass
    if end:
        try:
            dt = datetime.strptime(end, "%Y-%m-%d")
            q = q.filter(Device.timestamp < dt.replace(hour=23, minute=59, second=59))
        except ValueError:
            pass
    if user_id:
        try:
            uid = int(user_id)
            q = q.filter(Device.user_id == uid)
        except ValueError:
            pass

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Dispositivo", "Fusões", "Usuário", "Data/Hora", "Lançado"])
    for r in q.all():
        writer.writerow([r.id, r.name, r.fusion_count, r.user_id, r.timestamp.strftime("%Y-%m-%d %H:%M"), "sim" if r.released else "não"])

    csv_data = output.getvalue()
    output.close()
    return Response(csv_data, mimetype="text/csv",
                    headers={"Content-Disposition": "attachment;filename=relatorio.csv"})

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(host="0.0.0.0", port=5000)
