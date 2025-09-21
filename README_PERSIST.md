# Persistência no DigitalOcean App Platform

- Monte um **Volume** em `/workspace/data`.
- Exporte estas variáveis:
  - `DATA_DIR=/workspace/data`
  - `DATABASE_FILE=splice.db`
  - `ADMIN_USERNAME=admin`
  - `ADMIN_PASSWORD=admin123`
  - `ADMIN_PASSWORD_FORCE=1` (depois que logar, troque para 0)
- Comandos úteis:
  - `python scripts/init_db.py`
  - `python scripts/reset_admin.py`
