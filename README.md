# Splice Admin Pro

**Build:** `pip install -r requirements.txt`  
**Start:** `gunicorn app:app`

Env:
- `SECRET_KEY` obrigatório
- `MAX_CONTENT_LENGTH_MB` opcional (padrão 20)

Rotas principais:
- `/register` (somente enquanto não há usuários) → cria o admin
- `/login` / `/logout`
- `/admin/users` (somente admin) → cria usuários
- `/admin/maps` (somente admin) → upload PDF + atribuição de usuários
- `/new` (usuário) → novo registro (exige escolher mapa atribuído) + até 6 fotos
- `/admin/reports` (admin) → filtros, CSV, ZIP de fotos, link p/ detalhe
- `/my/reports` (usuário) → filtros + CSV
- `/admin/device/<id>` (admin) → fotos, autor, mapa, **botão LANÇADO**

Reset admin (opcional):
- Defina `FORCE_RESET_ADMIN=1`, `RESET_ADMIN_TOKEN=XYZ`, `NEW_ADMIN_PASSWORD=<nova>` e acesse `/force_reset_admin?token=XYZ`. Depois remova as variáveis.
