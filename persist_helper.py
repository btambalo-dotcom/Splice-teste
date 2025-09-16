# -*- coding: utf-8 -*-
import os
import shutil
from pathlib import Path
import sqlite3

def ensure_persist():
    """
    Garante que o banco e pastas fiquem no DISK (/var/data por env).
    Retorna: DATA_DIR, DATABASE_FILE, DB_PATH, DATABASE_URL
    """
    DATA_DIR = os.getenv("DATA_DIR", "/var/data").rstrip("/")
    DATABASE_FILE = os.getenv("DATABASE_FILE", "splice.db")

    data_path = Path(DATA_DIR)
    data_path.mkdir(parents=True, exist_ok=True)

    DB_PATH = str(data_path / DATABASE_FILE)

    # Migrar banco antigo do diretório do código se existir
    old_db = Path(__file__).resolve().parent / DATABASE_FILE
    if old_db.exists() and not Path(DB_PATH).exists():
        try:
            shutil.move(str(old_db), DB_PATH)
        except Exception:
            Path(DB_PATH).touch()

    # Gera arquivo válido se não existir
    if not Path(DB_PATH).exists():
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("CREATE TABLE IF NOT EXISTS __init__(id INTEGER PRIMARY KEY)")
            conn.commit()
            conn.close()
        except Exception:
            Path(DB_PATH).touch()

    DATABASE_URL = f"sqlite:////{DB_PATH}"
    return DATA_DIR, DATABASE_FILE, DB_PATH, DATABASE_URL
