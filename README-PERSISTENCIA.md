# Persistência de dados no Render

- O disco persistente está montado em **/var/data**.
- O banco SQLite fica em **/var/data/splice.db**.
- Variáveis obrigatórias já estão configuradas no `render.yaml`:
  - `DATA_DIR=/var/data`
  - `DATABASE_FILE=splice.db`
  - `WEB_CONCURRENCY=1`
- Endpoints de verificação:
  - `GET /healthz` → `{"ok": true, "checks": {"db":"ok","disk":"ok"}}`
  - `GET /db.json` → JSON com as infos do SQLite.