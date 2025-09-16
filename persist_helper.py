# -*- coding: utf-8 -*-
import os
import sqlite3

def ensure_persist():
    """
    Garante persistência do banco em /var/data (ou DATA_DIR),
    cria pasta/arquivo se necessário e retorna exatamente 4 valores:
    (DATA_DIR, DATABASE_FILE, DB_PATH, DATABASE_URL)
    """
    DATA_DIR = os.getenv("DATA_DIR", "/var/data").rstrip("/")
    os.makedirs(DATA_DIR, exist_ok=True)

    DATABASE_FILE = os.getenv("DATABASE_FILE", "splice.db")
    DB_PATH = os.path.join(DATA_DIR, DATABASE_FILE)

    # Se o arquivo não existir, cria um SQLite válido e uma tabela dummy
    if not os.path.exists(DB_PATH):
        try:
            conn = sqlite3.connect(DB_PATH)
            # tabela simples para garantir arquivo válido
            conn.execute("CREATE TABLE IF NOT EXISTS __init__(id INTEGER PRIMARY KEY)")
            conn.commit()
            conn.close()
        except Exception:
            # Se der erro, ainda assim seguimos — o arquivo será criado depois pelo app
            pass

    DATABASE_URL = f"sqlite:///{DB_PATH}"
    # Retorna **exatamente 4 valores**, na ordem esperada
    return DATA_DIR, DATABASE_FILE, DB_PATH, DATABASE_URL
