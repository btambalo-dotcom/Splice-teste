# -*- coding: utf-8 -*-
import os, re, datetime, shutil, sqlite3
from pathlib import Path

# Defaults for DigitalOcean volume
DATA_DIR = os.getenv("DATA_DIR", "/var/data")
DB_FILE  = os.getenv("DATABASE_FILE", "splice.db")
DB_PATH  = str(Path(DATA_DIR) / DB_FILE)

Path(DATA_DIR).mkdir(parents=True, exist_ok=True)
Path(os.path.join(DATA_DIR, "backups")).mkdir(parents=True, exist_ok=True)

# Best-effort boot backup
try:
    if os.path.exists(DB_PATH):
        ts = datetime.datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        shutil.copy2(DB_PATH, os.path.join(DATA_DIR, "backups", f"boot-{ts}.db"))
except Exception:
    pass

# Guard against destructive SQL (allow DELETE ... WHERE)
_DANGEROUS = re.compile(r"\b(DROP\s+TABLE|DROP\s+SCHEMA|TRUNCATE)\b", re.I)
_ALLOW_DROP = os.getenv("ALLOW_DESTRUCTIVE_SQL", "0") == "1"
_orig_connect = sqlite3.connect

def _connect_guard(*args, **kwargs):
    conn = _orig_connect(*args, **kwargs)
    if _ALLOW_DROP:
        return conn
    orig_execute = conn.execute
    orig_executescript = conn.executescript
    def safe_execute(sql, *a, **k):
        if isinstance(sql, str) and _DANGEROUS.search(sql):
            raise RuntimeError("Comando SQL destrutivo bloqueado em produção.")
        return orig_execute(sql, *a, **k)
    def safe_executescript(script, *a, **k):
        if isinstance(script, str) and _DANGEROUS.search(script):
            raise RuntimeError("Script SQL destrutivo bloqueado em produção.")
        return orig_executescript(script, *a, **k)
    conn.execute = safe_execute
    conn.executescript = safe_executescript
    return conn

sqlite3.connect = _connect_guard
