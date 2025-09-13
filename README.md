# Splice Admin App (com Relatórios, Gráficos e XLSX)

Recursos:
- Login/senha e papéis (admin/usuário)
- Admin cria usuários, alterna admin, reseta senha
- Registros com dispositivo, nº de fusões e até 6 fotos
- Relatórios com filtro por datas e usuário
- Gráficos (Chart.js) de fusões por dia e por dispositivo
- Exportação CSV e XLSX dos relatórios
- Deploy via Render (Procfile, runtime, render.yaml)

## Rodar local
```bash
pip install -r requirements.txt
python app.py
# http://localhost:5000
```
Primeiro cadastro vira ADMIN.

## Render
- Start: `gunicorn app:app`
- Vars: `SECRET_KEY`, `MAX_CONTENT_LENGTH_MB=20`
- Disk: `/opt/render/project/src/static/uploads`
- Ou use `render.yaml` (Blueprint).
