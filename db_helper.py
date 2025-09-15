
import os, pathlib

def resolve_db_url(default_dir="/var/data", default_file="splice.db"):
    data_dir = os.getenv("DATA_DIR", default_dir)
    pathlib.Path(data_dir).mkdir(parents=True, exist_ok=True)
    db_file = os.getenv("DATABASE_FILE", default_file)
    url = os.getenv("DATABASE_URL", "").strip()
    if url:
        # normalize to absolute if provided as relative sqlite
        if url.startswith("sqlite:///") and not url.startswith("sqlite:////"):
            tail = url.split("sqlite:///")[1]
            tail = tail.split("/")[-1] if "/" in tail else tail
            url = f"sqlite:////{os.path.join(data_dir, tail)}"
        return url
    return f"sqlite:////{os.path.join(data_dir, db_file)}"

def resolve_db_path(default_dir="/var/data", default_file="splice.db"):
    data_dir = os.getenv("DATA_DIR", default_dir)
    pathlib.Path(data_dir).mkdir(parents=True, exist_ok=True)
    db_file = os.getenv("DATABASE_FILE", default_file)
    return os.path.join(data_dir, db_file)
