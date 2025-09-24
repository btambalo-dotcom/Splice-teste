
Backup & Restore habilitado

Rotas:
  - GET  /admin/backup        -> Tela de upload/restauração
  - POST /admin/backup/upload -> Enviar arquivo .db/.sqlite/.sqlite3/.sql
  - POST /admin/backup/restore-> Restaurar o backup selecionado

Variáveis de ambiente (opcional):
  - SQLITE_PATH: caminho absoluto do arquivo SQLite do sistema, ex: /var/data/app.db
  - BACKUP_UPLOAD_FOLDER: pasta para armazenar backups (se não setado, usa <root>/backups)

Persistência (Render/DigitalOcean):
  - Monte um disco persistente e defina SQLITE_PATH para um caminho dentro dele.
  - Não inicialize o banco sobrescrevendo se o arquivo já existir.

Segurança:
  - Restrinja /admin/backup a usuários admin (adicione @login_required e verificação de perfil se já usa).
  - Limite de tamanho via env: MAX_CONTENT_LENGTH (ex: 64 * 1024 * 1024).
