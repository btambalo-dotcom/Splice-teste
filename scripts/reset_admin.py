import os, sqlite3
from pathlib import Path
from werkzeug.security import generate_password_hash

DATA_DIR = Path(os.getenv("DATA_DIR", "/workspace/data"))
DB_FILE  = os.getenv("DATABASE_FILE", "splice.db")
DB_PATH  = DATA_DIR/DB_FILE

def run(password="admin123"):
    conn = sqlite3.connect(DB_PATH.as_posix())
    cur  = conn.cursor()
    cur.execute("UPDATE users SET password_hash=? WHERE username='admin'",
                (generate_password_hash(password),))
    if cur.rowcount == 0:
        cur.execute("INSERT INTO users(username,password_hash,is_admin) VALUES(?,?,1)",
                    ("admin", generate_password_hash(password)))
    conn.commit(); conn.close()
    print("Admin resetado")

if __name__ == "__main__":
    run()
