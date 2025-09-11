
# Splice Admin Pro (Render Ready)

**Build:** `pip install -r requirements.txt`  
**Start:** `gunicorn app:app`

Env vars:
- `SECRET_KEY` (obrigatória)
- `MAX_CONTENT_LENGTH_MB` (opcional, ex.: 20)
- (reset admin opcional) `FORCE_RESET_ADMIN=1`, `RESET_ADMIN_TOKEN=...`, `NEW_ADMIN_PASSWORD=...`

Rotas úteis:
- `/register` — cria o admin no primeiro acesso
- `/login` — autenticação
- `/admin/users` — gestão de usuários (apenas admin)
- `/admin/maps` — upload/atribuição de mapas PDF
- `/new` — novo registro (usuário escolhe um mapa atribuído)
- `/admin/reports` — relatórios + CSV + ZIP de fotos (respeita filtros)
- `/my/reports` — relatórios do usuário + CSV
- `/force_reset_admin?token=XYZ` — reset de senha (se env vars definidas)
