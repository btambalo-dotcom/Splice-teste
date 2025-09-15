
import os, pathlib
def ensure_persist(default_dir="/var/data", default_file="splice.db"):
    data_dir = os.getenv("DATA_DIR", default_dir)
    pathlib.Path(data_dir).mkdir(parents=True, exist_ok=True)
    db_file = os.getenv("DATABASE_FILE", default_file)
    db_path = os.path.join(data_dir, db_file)
    if not os.getenv("DATABASE_URL"):
        os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    return data_dir, db_file, db_path, os.environ["DATABASE_URL"]
