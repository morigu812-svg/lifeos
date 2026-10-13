import os
import json
import sqlite3
from io import BytesIO
from datetime import date, datetime
from functools import wraps
from urllib.parse import urlparse

from flask import Flask, flash, redirect, render_template, request, session, url_for, send_file
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "local-dev-key-change-me")
DB_PATH = os.environ.get("LIFEOS_DB_PATH", "lifeos.db")

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
            description TEXT NOT NULL DEFAULT '', repo_url TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL)""")
        columns = {row["name"] for row in db.execute("PRAGMA table_info(sites)").fetchall()}
        if "repo_url" not in columns:
            db.execute("ALTER TABLE sites ADD COLUMN repo_url TEXT NOT NULL DEFAULT ''")


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
        flash("パスワードが違います。もう一度お試しください。", "error")
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
        sites = db.execute("SELECT * FROM sites ORDER BY id DESC").fetchall()
    total = len(tasks)
    completed = sum(1 for t in tasks if t["done"])
    return render_template("index.html", tasks=tasks, sites=sites,
        note=note["content"] if note else "", today=today,
        total_tasks=total, completed_tasks=completed,
        active_tasks=total-completed)


@app.post("/tasks/add")
@login_required
def add_task():
    title = request.form.get("title", "").strip()
    if not title:
        flash("タスク名を入力してください。", "error")
    elif len(title) > 120:
        flash("タスク名は120文字以内で入力してください。", "error")
    else:
        with get_db() as db:
            db.execute("INSERT INTO tasks (title, created_at) VALUES (?, ?)",
                       (title, date.today().isoformat()))
        flash("タスクを追加しました。", "success")
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
    flash("タスクを削除しました。", "success")
    return redirect(url_for("index") + "#tasks")


@app.post("/notes/save")
@login_required
def save_note():
    content = request.form.get("content", "")
    if len(content) > 5000:
        flash("ノートは5,000文字以内で入力してください。", "error")
        return redirect(url_for("index") + "#notes")
    with get_db() as db:
        db.execute("""INSERT INTO notes (note_date, content) VALUES (?, ?)
            ON CONFLICT(note_date) DO UPDATE SET content = excluded.content""",
            (date.today().isoformat(), content))
    flash("今日のノートを保存しました。", "success")
    return redirect(url_for("index") + "#notes")


@app.post("/sites/add")
@login_required
def add_site():
    name = request.form.get("name", "").strip()
    url = request.form.get("url", "").strip()
    repo_url = request.form.get("repo_url", "").strip()
    category = request.form.get("category", "その他").strip()[:40] or "その他"
    description = request.form.get("description", "").strip()[:500]
    parsed = urlparse(url)
    if not name or len(name) > 100:
        flash("サイト名を1〜100文字で入力してください。", "error")
        return redirect(url_for("index") + "#sites")
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        flash("サイトURLは https:// または http:// から入力してください。", "error")
        return redirect(url_for("index") + "#sites")
    if repo_url:
        repo = urlparse(repo_url)
        if repo.scheme not in ("http", "https") or repo.netloc.lower() not in ("github.com", "www.github.com") or len(repo.path.strip("/").split("/")) < 2:
            flash("GitHubリポジトリURLを確認してください（例：https://github.com/ユーザー名/リポジトリ名）。", "error")
            return redirect(url_for("index") + "#sites")
    with get_db() as db:
        db.execute("""INSERT INTO sites (name, url, category, description, repo_url, created_at)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (name, url, category, description, repo_url, datetime.now().isoformat(timespec="seconds")))
    flash("サイトを登録しました。", "success")
    return redirect(url_for("index") + "#sites")


@app.post("/sites/<int:site_id>/delete")
@login_required
def delete_site(site_id):
    with get_db() as db:
        db.execute("DELETE FROM sites WHERE id = ?", (site_id,))
    flash("サイト情報を削除したで。", "success")
    return redirect(url_for("index") + "#sites")


@app.get("/backup/export")
@login_required
def export_backup():
    """Download all user data as a portable JSON backup."""
    with get_db() as db:
        tasks = [dict(row) for row in db.execute(
            "SELECT id, title, done, created_at FROM tasks ORDER BY id"
        ).fetchall()]
        notes = [dict(row) for row in db.execute(
            "SELECT note_date, content FROM notes ORDER BY note_date"
        ).fetchall()]
        sites = [dict(row) for row in db.execute(
            "SELECT id, name, url, category, description, repo_url, created_at FROM sites ORDER BY id"
        ).fetchall()]

    payload = {
        "app": "LifeOS",
        "format_version": 1,
        "exported_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "data": {"tasks": tasks, "notes": notes, "sites": sites},
    }
    content = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    return send_file(
        BytesIO(content),
        mimetype="application/json",
        as_attachment=True,
        download_name=f"lifeos-backup-{date.today().isoformat()}.json",
    )


@app.post("/backup/import")
@login_required
def import_backup():
    """Restore a LifeOS JSON backup, replacing current tasks, notes and sites."""
    uploaded = request.files.get("backup_file")
    if not uploaded or not uploaded.filename:
        flash("復元するバックアップファイルを選択してください。", "error")
        return redirect(url_for("index") + "#data-management")

    raw = uploaded.read(2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024:
        flash("バックアップは2MB以下のファイルを選択してください。", "error")
        return redirect(url_for("index") + "#data-management")

    try:
        payload = json.loads(raw.decode("utf-8"))
        data = payload["data"]
        if payload.get("app") != "LifeOS" or payload.get("format_version") != 1:
            raise ValueError("unsupported format")
        tasks, notes, sites = data["tasks"], data["notes"], data["sites"]
        if not all(isinstance(items, list) for items in (tasks, notes, sites)):
            raise ValueError("invalid lists")

        for task in tasks:
            if not isinstance(task, dict) or not isinstance(task.get("title"), str) or not task["title"].strip():
                raise ValueError("invalid task")
            if not isinstance(task.get("done"), int) or task["done"] not in (0, 1):
                raise ValueError("invalid task status")
            if not isinstance(task.get("created_at"), str):
                raise ValueError("invalid task date")
            if "id" in task and (not isinstance(task["id"], int) or task["id"] < 1):
                raise ValueError("invalid task id")
        for note in notes:
            if not isinstance(note, dict) or not isinstance(note.get("note_date"), str) or not isinstance(note.get("content"), str):
                raise ValueError("invalid note")
        for site in sites:
            if not isinstance(site, dict):
                raise ValueError("invalid site")
            for field in ("name", "url", "category", "description", "repo_url", "created_at"):
                if not isinstance(site.get(field, "" if field in ("description", "repo_url") else None), str):
                    raise ValueError("invalid site field")
            parsed = urlparse(site["url"])
            if not site["name"].strip() or parsed.scheme not in ("http", "https") or not parsed.netloc:
                raise ValueError("invalid site URL")
            if "id" in site and (not isinstance(site["id"], int) or site["id"] < 1):
                raise ValueError("invalid site id")
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        flash("ファイルを読み取れませんでした。LifeOSから書き出したJSONバックアップを選択してください。", "error")
        return redirect(url_for("index") + "#data-management")

    try:
        with get_db() as db:
            db.execute("DELETE FROM tasks")
            db.execute("DELETE FROM notes")
            db.execute("DELETE FROM sites")
            for task in tasks:
                if "id" in task:
                    db.execute(
                        "INSERT INTO tasks (id, title, done, created_at) VALUES (?, ?, ?, ?)",
                        (task["id"], task["title"], task["done"], task["created_at"]),
                    )
                else:
                    db.execute(
                        "INSERT INTO tasks (title, done, created_at) VALUES (?, ?, ?)",
                        (task["title"], task["done"], task["created_at"]),
                    )
            for note in notes:
                db.execute(
                    "INSERT INTO notes (note_date, content) VALUES (?, ?)",
                    (note["note_date"], note["content"]),
                )
            for site in sites:
                values = (site["name"], site["url"], site.get("category", "その他"),
                          site.get("description", ""), site.get("repo_url", ""), site["created_at"])
                if "id" in site:
                    db.execute(
                        "INSERT INTO sites (id, name, url, category, description, repo_url, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (site["id"], *values),
                    )
                else:
                    db.execute(
                        "INSERT INTO sites (name, url, category, description, repo_url, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                        values,
                    )
    except sqlite3.Error:
        flash("復元に失敗しました。データを確認して、もう一度お試しください。", "error")
        return redirect(url_for("index") + "#data-management")

    flash("バックアップから復元しました。現在のタスク・ノート・サイト情報は、バックアップの内容に置き換わりました。", "success")
    return redirect(url_for("index") + "#data-management")


@app.get("/health")
def health():
    return {"status": "ok"}


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
