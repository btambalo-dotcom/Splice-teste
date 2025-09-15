import os
from pathlib import Path

DEFAULT_DATA_DIR = "/var/data"
DEFAULT_DB_FILE = "splice.db"

def get_settings():
    data_dir = os.getenv("DATA_DIR", DEFAULT_DATA_DIR)
    db_file = os.getenv("DATABASE_FILE", DEFAULT_DB_FILE)
    return data_dir, db_file

def ensure_dirs(data_dir: str):
    Path(data_dir).mkdir(parents=True, exist_ok=True)
    # optional persistent subfolders
    for d in ("workmaps", "backups", "uploads"):
        Path(data_dir, d).mkdir(parents=True, exist_ok=True)

def ensure_persist() -> str:
    """Ensure a persistent sqlite path on a Render Disk.
    Returns the absolute path to the DB file (string).
    """
    data_dir, db_file = get_settings()
    ensure_dirs(data_dir)
    db_path = os.path.join(data_dir, db_file)
    # Let sqlite create the file on first connect/commit
    return db_path
