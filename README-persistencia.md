# Persistência de banco no Render (Disk)

Este pacote foi ajustado para salvar o SQLite dentro do Disk do Render.

## Como funciona
- A aplicação monta `DATA_DIR` (padrão `/var/data`).
- O arquivo do banco será `/var/data/splice.db` por padrão.
- Você pode trocar o nome do arquivo do banco via variável `DATABASE_FILE` (ex: `DATABASE_FILE=mydata.db`).

## Variáveis de Ambiente recomendadas
- `DATA_DIR=/var/data`
- `DATABASE_FILE=splice.db`  (opcional)
- `WEB_CONCURRENCY=1`        (em serviços pequenos)
- `SECRET_KEY=...`           (se sua app usa sessões)

## Importante
- **Não use** caminhos relativos dentro do container para o banco (como `sqlite:///splice.db`). Agora a app usa `DATABASE_URL` calculada dinamicamente:
  `sqlite:////var/data/splice.db`

## Arquivos modificados
- ['/mnt/data/_build_persist/app.py']