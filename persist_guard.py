# -*- coding: utf-8 -*-
import os, re, shutil, datetime
from pathlib import Path
import sqlite3

DATA_DIR = os.getenv("DATA_DIR", "/var/data")
DB_FILE  = os.getenv("DATABASE_FILE", "splice.db")
DB_PATH  = str(Path(DATA_DIR) / DB_FILE)

Path(DATA_DIR).mkdir(parents=True, exist_ok=True)
Path(os.path.join(DATA_DIR, "backups")).mkdir(parents=True, exist_ok=True)

# Backup on boot (best effort)
try:
    if os.path.exists(DB_PATH):
        ts = datetime.datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        bkp = os.path.join(DATA_DIR, "backups", f"splice-{ts}.db")
        shutil.copy2(DB_PATH, bkp)
except Exception:
    pass

# Guard against destructive SQL
_DANGEROUS = re.compile(r"\b(DROP\s+TABLE|DROP\s+SCHEMA|TRUNCATE|DELETE\s+FROM\s+\w+\s*;?)", re.I)
_ALLOW_DROP = os.getenv("ALLOW_DESTRUCTIVE_SQL", "0") == "1"

class GuardedConnection(sqlite3.Connection):
    def execute(self, sql, *args, **kwargs):
        if not _ALLOW_DROP and isinstance(sql, str) and _DANGEROUS.search(sql):
            raise RuntimeError("Comando SQL destrutivo bloqueado em produção.")
        return super().execute(sql, *args, **kwargs)

    def executescript(self, script, *args, **kwargs):
        if not _ALLOW_DROP and isinstance(script, str) and _DANGEROUS.search(script):
            raise RuntimeError("Script SQL destrutivo bloqueado em produção.")
        return super().executescript(script, *args, **kwargs)

sqlite3.connect = lambda *a, **kw: GuardedConnection(*a, **kw)

# === SQL guard via Connection subclass (compatível com Python 3.11+) ===
import re as _re
_DANGEROUS = _re.compile(r"\b(DROP\s+TABLE|DROP\s+SCHEMA|TRUNCATE|DELETE\s+FROM\s+\w+\s*;?)", _re.I)

class GuardedConnection(sqlite3.Connection):
    def execute(self, sql, *a, **k):
        if isinstance(sql, str) and _DANGEROUS.search(sql):
            raise RuntimeError("Comando SQL destrutivo bloqueado em produção.")
        return super().execute(sql, *a, **k)

    def executescript(self, script, *a, **k):
        if isinstance(script, str) and _DANGEROUS.search(script):
            raise RuntimeError("Script SQL destrutivo bloqueado em produção.")
        return super().executescript(script, *a, **k)

# Monkeypatch leve: usa factory=GuardedConnection (não reatribui atributos read-only)
_orig_connect = sqlite3.connect
def _guarded_connect(*a, **k):
    k.setdefault("factory", GuardedConnection)
    return _orig_connect(*a, **k)
sqlite3.connect = _guarded_connect
