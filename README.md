
# Splice App — FULL (DigitalOcean App Platform)

Aplicação Flask completa e funcional com:
- Autenticação (registro/login, admin)
- CRUD básico de registros + upload de fotos
- Workmaps (upload/listagem)
- Admin: usuários, registros, fotos, export CSV, backups zip
- Persistência com **SQLite** em **/workspace/data** (monte um **Volume** aqui)
- `Procfile` para Gunicorn, rota `/healthz`, rota `/debug/env`

## Variáveis de ambiente
- `SECRET_KEY` — gere um valor forte
- `DATA_DIR` — `/workspace/data` (recomendado)
- `DATABASE_FILE` — `splice.db` (opcional)

## Deploy (DO App Platform)
- **Run Command**: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120`
- **Build Command**: deixe vazio
- **Volume**: adicione um Volume montado em `/workspace/data`

Credenciais iniciais: `admin / admin` (altere após login).
