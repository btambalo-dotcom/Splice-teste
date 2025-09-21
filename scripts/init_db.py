import os, sqlite3, datetime
from pathlib import Path
from werkzeug.security import generate_password_hash

DATA_DIR = Path(os.getenv("DATA_DIR", "/workspace/data"))
DB_FILE  = os.getenv("DATABASE_FILE", "splice.db")
DB_PATH  = DATA_DIR/DB_FILE

def ensure_dirs():
    (DATA_DIR/"uploads").mkdir(parents=True, exist_ok=True)
    (DATA_DIR/"workmaps").mkdir(parents=True, exist_ok=True)
    (DATA_DIR/"backup").mkdir(parents=True, exist_ok=True)

def run():
    ensure_dirs()
    conn = sqlite3.connect(DB_PATH.as_posix())
    cur  = conn.cursor()
    cur.executescript("""
    PRAGMA foreign_keys=ON;
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        is_admin INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS records(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        body  TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS photos(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        record_id INTEGER NOT NULL,
        filename TEXT NOT NULL,
        uploaded_at TEXT NOT NULL,
        FOREIGN KEY(record_id) REFERENCES records(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS devices(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        serial TEXT UNIQUE NOT NULL,
        launched INTEGER NOT NULL DEFAULT 0,
        owner_id INTEGER,
        created_at TEXT NOT NULL,
        FOREIGN KEY(owner_id) REFERENCES users(id) ON DELETE SET NULL
    );
    CREATE TABLE IF NOT EXISTS workmaps(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT NOT NULL,
        owner_id INTEGER NOT NULL,
        uploaded_at TEXT NOT NULL,
        FOREIGN KEY(owner_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)
    # garante admin
    cur.execute("SELECT id FROM users WHERE username='admin'")
    row = cur.fetchone()
    if not row:
        cur.execute("INSERT INTO users(username,password_hash,is_admin) VALUES(?,?,1)",
                    ("admin", generate_password_hash("admin123")))
    conn.commit(); conn.close()
    print(f"DB ok -> {DB_PATH}")

if __name__ == "__main__":
    run()
