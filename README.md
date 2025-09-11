# Splice Admin Pro — Completo

Recursos:
- Login/senha e papéis (admin/usuário). Primeiro cadastro vira admin; depois só admin cria usuários.
- Usuário: cria registros (dispositivo, nº de fusões, até 6 fotos), **edita** seus registros (não pode apagar).
- **Meu Relatório** com filtros (data + dispositivo), gráficos (por dia, acumulado, por dispositivo), CSV/XLSX, e download de fotos (ZIP).
- Página **do dispositivo** do usuário com totais, lista, fotos com **ampliação (lightbox)**.
- Admin: criar/trocar admin/reset senha, registros com filtro, relatórios completos (totais por dispositivo e por usuário), gráficos + export CSV/XLSX, download de fotos por dispositivos.
- Reset de admin via token opcional (`/force_reset_admin?token=...`).

## Rodar local
```bash
pip install -r requirements.txt
python app.py
# http://localhost:5000
```

## Deploy Render
- Start: `gunicorn app:app`
- Build: `pip install -r requirements.txt`
- Env Vars: `SECRET_KEY`, `MAX_CONTENT_LENGTH_MB=20`
  - (opcional) `FORCE_RESET_ADMIN=1`, `RESET_ADMIN_TOKEN=seu_token`, `NEW_ADMIN_PASSWORD=nova123`
- Disk: monte `/opt/render/project/src/static/uploads`

## Rotas
- `/register`, `/login`, `/logout`
- `/` (dashboard), `/new`, `/record/<id>`, `/record/<id>/edit`, `/uploads/<file>`
- `/my/reports`, `/my/reports_data.json`, `/my/reports.csv`, `/my/reports.xlsx`, `/my/photos.zip`
- `/my/device/<device_name>`
- `/admin`, `/admin/users`, `/admin/users/<id>/reset`, `/admin/users/<id>/toggle_admin`
- `/admin/records`, `/admin/export.csv`
- `/admin/reports`, `/admin/reports_data.json`, `/admin/reports.csv`, `/admin/reports.xlsx`, `/admin/reports_users.csv`
- `/admin/photos`, `/admin/photos.zip` (POST)
- `/force_reset_admin?token=...` (se habilitado)
