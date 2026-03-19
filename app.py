from flask import Flask, render_template, request, redirect, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import os
import cloudinary
import cloudinary.uploader

app = Flask(__name__)

# -----------------------
# SECRET KEY
# -----------------------
app.secret_key = os.environ.get("SECRET_KEY", "devkey")

# -----------------------
# DATABASE CONFIG (SUPABASE)
# -----------------------
database_url = os.environ.get("DATABASE_URL")

if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

# fallback for local
app.config['SQLALCHEMY_DATABASE_URI'] = database_url or 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# -----------------------
# CLOUDINARY CONFIG (IMPORTANT)
# -----------------------
cloudinary.config(
    cloud_name=os.environ.get("CLOUDINARY_CLOUD_NAME"),
    api_key=os.environ.get("CLOUDINARY_API_KEY"),
    api_secret=os.environ.get("CLOUDINARY_API_SECRET")
)

# -----------------------
# MODELS
# -----------------------

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(200))
    role = db.Column(db.String(20))
    subject_id = db.Column(db.Integer, nullable=True)


class Subject(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))


class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200))
    body = db.Column(db.Text)
    tag = db.Column(db.String(100))
    subject_id = db.Column(db.Integer)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    user = db.relationship('User')


class Answer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.Text)
    post_id = db.Column(db.Integer)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    votes = db.Column(db.Integer, default=0)
    user = db.relationship('User')


class Material(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(300))
    subject_id = db.Column(db.Integer)


class Hackathon(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200))
    date = db.Column(db.String(50))
    time = db.Column(db.String(50))
    proof = db.Column(db.String(300))
    user_id = db.Column(db.Integer)


# -----------------------
# INIT DB
# -----------------------

with app.app_context():
    db.create_all()

    if Subject.query.count() == 0:
        subjects = [
            "Operating Systems",
            "Advanced IoT",
            "DBMS",
            "Data Mining",
            "DCCN",
            "Computer Organization and Architecture",
            "UHV"
        ]
        for s in subjects:
            db.session.add(Subject(name=s))
        db.session.commit()


# -----------------------
# ROUTES
# -----------------------

@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/home")
def dashboard():
    if "user_id" not in session:
        return redirect("/login")

    subjects = Subject.query.all()
    return render_template("dashboard.html", subjects=subjects)


@app.route("/register", methods=["GET", "POST"])
def register():
    subjects = Subject.query.all()

    if request.method == "POST":
        username = request.form.get("username")

        # ✅ FIX: prevent duplicate crash
        existing = User.query.filter_by(username=username).first()
        if existing:
            return "Username already exists"

        user = User(
            username=username,
            password=generate_password_hash(request.form.get("password")),
            role=request.form.get("role"),
            subject_id=request.form.get("subject_id") or None
        )

        db.session.add(user)
        db.session.commit()

        return redirect("/login")

    return render_template("register.html", subjects=subjects)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":

        user = User.query.filter_by(username=request.form.get("username")).first()

        if user and check_password_hash(user.password, request.form.get("password")):
            session["user_id"] = user.id
            session["username"] = user.username
            session["role"] = user.role
            session["subject_id"] = user.subject_id

            return redirect("/home")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


@app.route("/subject/<int:id>")
def subject(id):

    if session.get("role") == "teacher":
        if session.get("subject_id") != id:
            return "Access Denied"

    posts = Post.query.filter_by(subject_id=id).all()
    materials = Material.query.filter_by(subject_id=id).all()

    return render_template("subject.html", posts=posts, materials=materials, subject=id)


@app.route("/create/<int:subject>", methods=["GET", "POST"])
def create_post(subject):

    if request.method == "POST":
        post = Post(
            title=request.form.get("title"),
            body=request.form.get("body"),
            tag=request.form.get("tag"),
            subject_id=subject,
            user_id=session.get("user_id")
        )

        db.session.add(post)
        db.session.commit()

        return redirect(f"/subject/{subject}")

    return render_template("create_post.html", subject=subject)


@app.route("/post/<int:id>", methods=["GET", "POST"])
def post(id):

    post = Post.query.get(id)

    if request.method == "POST":
        ans = Answer(
            text=request.form.get("answer"),
            post_id=id,
            user_id=session.get("user_id")
        )
        db.session.add(ans)
        db.session.commit()

    answers = Answer.query.filter_by(post_id=id).all()

    return render_template("post.html", post=post, answers=answers)


@app.route("/vote/<int:id>/<action>")
def vote(id, action):
    ans = Answer.query.get(id)

    if action == "up":
        ans.votes += 1
    else:
        ans.votes -= 1

    db.session.commit()
    return redirect(request.referrer)


@app.route("/upload/<int:subject>", methods=["POST"])
def upload(subject):

    if session.get("role") != "teacher":
        return redirect(f"/subject/{subject}")

    file = request.files.get("file")

    if file:
        result = cloudinary.uploader.upload(file, resource_type="auto")
        file_url = result["secure_url"]

        material = Material(filename=file_url, subject_id=subject)

        db.session.add(material)
        db.session.commit()

    return redirect(f"/subject/{subject}")


@app.route("/hackathon", methods=["GET", "POST"])
def hackathon():

    if "user_id" not in session:
        return redirect("/login")

    if request.method == "POST":
        file = request.files.get("proof")

        result = cloudinary.uploader.upload(file, resource_type="auto")
        file_url = result["secure_url"]

        entry = Hackathon(
            name=request.form.get("name"),
            date=request.form.get("date"),
            time=request.form.get("time"),
            proof=file_url,
            user_id=session["user_id"]
        )

        db.session.add(entry)
        db.session.commit()

        return redirect("/hackathon")

    return render_template("hackathon.html")


@app.route("/hackathon_list")
def hackathon_list():

    if session.get("role") != "teacher":
        return "Access Denied"

    data = Hackathon.query.all()
    return render_template("hackathon_list.html", data=data)


@app.route("/profile", methods=["GET", "POST"])
def profile():
    if "user_id" not in session:
        return redirect("/login")

    user = User.query.get(session["user_id"])

    if request.method == "POST":
        user.username = request.form.get("username")
        new_password = request.form.get("password")

        if new_password:
            user.password = generate_password_hash(new_password)

        db.session.commit()
        session["username"] = user.username

        return redirect("/profile")

    return render_template("profile.html", user=user)


# -----------------------
# RUN
# -----------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
