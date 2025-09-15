
import os, json

def persist_info():
    data_dir = os.getenv("DATA_DIR", "/var/data")
    db_file = os.getenv("DATABASE_FILE", "splice.db")
    db_path = os.path.join(data_dir, db_file)
    return {
        "DATA_DIR": data_dir,
        "DATABASE_FILE": db_file,
        "db_path": db_path,
        "DATABASE_URL": os.getenv("DATABASE_URL"),
        "dir_listing": sorted([p for p in os.listdir(data_dir)]) if os.path.isdir(data_dir) else []
    }
