import os
import sqlite3
import uuid
from datetime import date, datetime
from functools import wraps
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, abort, flash, redirect, render_template, request, send_from_directory, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "local-dev-key-change-me")
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024
DB_PATH = os.environ.get("LIFEOS_DB_PATH", "lifeos.db")
UPLOAD_DIR = Path(os.environ.get("LIFEOS_UPLOAD_DIR", "site_backups"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

password_hash = os.environ.get("LIFEOS_PASSWORD_HASH")
plain_password = os.environ.get("LIFEOS_PASSWORD")
APP_PASSWORD_HASH = password_hash or (generate_password_hash(plain_password) if plain_password else None)


def get_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db


def init_db():
    with get_db() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,
            done INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL)""")
        db.execute("""CREATE TABLE IF NOT EXISTS notes (
            note_date TEXT PRIMARY KEY, content TEXT NOT NULL DEFAULT '')""")
        db.execute("""CREATE TABLE IF NOT EXISTS habits (
            id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL UNIQUE)""")
        db.execute("""CREATE TABLE IF NOT EXISTS habit_checks (
            habit_id INTEGER NOT NULL, check_date TEXT NOT NULL,
            PRIMARY KEY (habit_id, check_date),
            FOREIGN KEY (habit_id) REFERENCES habits(id))""")
        db.execute("""CREATE TABLE IF NOT EXISTS sites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, url TEXT NOT NULL, category TEXT NOT NULL DEFAULT 'その他',
            description TEXT NOT NULL DEFAULT '', backup_name TEXT,
            backup_original_name TEXT, created_at TEXT NOT NULL)""")
        for title in ("勉強する", "コードを書く", "机を整理する"):
            db.execute("INSERT OR IGNORE INTO habits (title) VALUES (?)", (title,))


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not APP_PASSWORD_HASH:
            return render_template("setup.html"), 503
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


@app.route("/login", methods=["GET", "POST"])
def login():
    if not APP_PASSWORD_HASH:
        return render_template("setup.html"), 503
    if request.method == "POST":
        password = request.form.get("password", "")
        if check_password_hash(APP_PASSWORD_HASH, password):
            session.clear()
            session["logged_in"] = True
            return redirect(url_for("index"))
        flash("パスワードが違います。もう一度試してな。", "error")
    return render_template("login.html")


@app.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.get("/")
@login_required
def index():
    today = date.today().isoformat()
    with get_db() as db:
        tasks = db.execute("SELECT * FROM tasks ORDER BY done ASC, id DESC").fetchall()
        note = db.execute("SELECT content FROM notes WHERE note_date = ?", (today,)).fetchone()
        habits = db.execute("""SELECT habits.id, habits.title,
            CASE WHEN habit_checks.habit_id IS NULL THEN 0 ELSE 1 END AS checked
            FROM habits LEFT JOIN habit_checks
            ON habits.id = habit_checks.habit_id AND habit_checks.check_date = ?
            ORDER BY habits.id""", (today,)).fetchall()
        sites = db.execute("SELECT * FROM sites ORDER BY id DESC").fetchall()
    total = len(tasks)
    completed = sum(1 for t in tasks if t["done"])
    checked = sum(1 for h in habits if h["checked"])
    return render_template("index.html", tasks=tasks, habits=habits, sites=sites,
        note=note["content"] if note else "", today=today,
        total_tasks=total, completed_tasks=completed,
        active_tasks=total-completed, checked_habits=checked)


@app.post("/tasks/add")
@login_required
def add_task():
    title = request.form.get("title", "").strip()
    if not title:
        flash("タスク名を入力してな。", "error")
    elif len(title) > 120:
        flash("タスク名は120文字以内にしてな。", "error")
    else:
        with get_db() as db:
            db.execute("INSERT INTO tasks (title, created_at) VALUES (?, ?)",
                       (title, date.today().isoformat()))
        flash("タスクを追加したで。", "success")
    return redirect(url_for("index") + "#tasks")


@app.post("/tasks/<int:task_id>/toggle")
@login_required
def toggle_task(task_id):
    with get_db() as db:
        db.execute("UPDATE tasks SET done = CASE WHEN done = 0 THEN 1 ELSE 0 END WHERE id = ?", (task_id,))
    return redirect(url_for("index") + "#tasks")


@app.post("/tasks/<int:task_id>/delete")
@login_required
def delete_task(task_id):
    with get_db() as db:
        db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    flash("タスクを削除したで。", "success")
    return redirect(url_for("index") + "#tasks")


@app.post("/notes/save")
@login_required
def save_note():
    content = request.form.get("content", "")
    if len(content) > 5000:
        flash("ノートは5000文字以内にしてな。", "error")
        return redirect(url_for("index") + "#notes")
    with get_db() as db:
        db.execute("""INSERT INTO notes (note_date, content) VALUES (?, ?)
            ON CONFLICT(note_date) DO UPDATE SET content = excluded.content""",
            (date.today().isoformat(), content))
    flash("今日のノートを保存したで。", "success")
    return redirect(url_for("index") + "#notes")


@app.post("/habits/<int:habit_id>/toggle")
@login_required
def toggle_habit(habit_id):
    today = date.today().isoformat()
    with get_db() as db:
        exists = db.execute("SELECT 1 FROM habits WHERE id = ?", (habit_id,)).fetchone()
        if exists:
            checked = db.execute("SELECT 1 FROM habit_checks WHERE habit_id = ? AND check_date = ?", (habit_id, today)).fetchone()
            if checked:
                db.execute("DELETE FROM habit_checks WHERE habit_id = ? AND check_date = ?", (habit_id, today))
            else:
                db.execute("INSERT INTO habit_checks (habit_id, check_date) VALUES (?, ?)", (habit_id, today))
    return redirect(url_for("index") + "#habits")


@app.post("/sites/add")
@login_required
def add_site():
    name = request.form.get("name", "").strip()
    url = request.form.get("url", "").strip()
    category = request.form.get("category", "その他").strip()[:40] or "その他"
    description = request.form.get("description", "").strip()[:500]
    parsed = urlparse(url)
    if not name or len(name) > 100:
        flash("サイト名を1〜100文字で入力してな。", "error")
        return redirect(url_for("index") + "#sites")
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        flash("URLは https:// または http:// から入力してな。", "error")
        return redirect(url_for("index") + "#sites")
    backup = request.files.get("backup")
    stored_name = None
    original_name = None
    if backup and backup.filename:
        original_name = secure_filename(backup.filename) or "site-backup.zip"
        if Path(original_name).suffix.lower() != ".zip":
            flash("バックアップはZIP形式でアップロードしてな。HTML・CSS・画像などをまとめたZIPに対応してるで。", "error")
            return redirect(url_for("index") + "#sites")
        stored_name = f"{uuid.uuid4().hex}.zip"
        backup.save(UPLOAD_DIR / stored_name)
    with get_db() as db:
        db.execute("""INSERT INTO sites (name, url, category, description, backup_name, backup_original_name, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (name, url, category, description, stored_name, original_name, datetime.now().isoformat(timespec="seconds")))
    flash("サイトを登録したで。" + (" ZIPバックアップも保存したで。" if stored_name else ""), "success")
    return redirect(url_for("index") + "#sites")


@app.get("/sites/<int:site_id>/backup")
@login_required
def download_site_backup(site_id):
    with get_db() as db:
        site = db.execute("SELECT backup_name, backup_original_name FROM sites WHERE id = ?", (site_id,)).fetchone()
    if not site or not site["backup_name"]:
        abort(404)
    path = UPLOAD_DIR / site["backup_name"]
    if not path.is_file():
        flash("バックアップファイルが見つからへん。Renderの保存領域がリセットされた可能性があるで。", "error")
        return redirect(url_for("index") + "#sites")
    return send_from_directory(UPLOAD_DIR, site["backup_name"], as_attachment=True,
                               download_name=site["backup_original_name"] or "site-backup.zip")


@app.post("/sites/<int:site_id>/delete")
@login_required
def delete_site(site_id):
    with get_db() as db:
        site = db.execute("SELECT backup_name FROM sites WHERE id = ?", (site_id,)).fetchone()
        if site:
            db.execute("DELETE FROM sites WHERE id = ?", (site_id,))
    if site and site["backup_name"]:
        try:
            (UPLOAD_DIR / site["backup_name"]).unlink(missing_ok=True)
        except OSError:
            pass
    flash("サイト情報を削除したで。", "success")
    return redirect(url_for("index") + "#sites")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.errorhandler(413)
def too_large(_error):
    flash("ZIPファイルは50MB以下にしてな。", "error")
    return redirect(url_for("index") + "#sites")


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
