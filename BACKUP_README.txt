
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

- Rota para criar backup: GET/POST /admin/backup/create


=== Backup Completo (.zip) ===
- Endpoint: GET/POST /admin/backup/create_full
- Conteúdo: manifest.json + db/app.db + files/<pastas>
- Pastas incluídas: BACKUP_INCLUDE_DIRS (CSV), UPLOAD_FOLDER, MEDIA_ROOT, DATA_DIR, STATIC_UPLOADS
  e por padrão as existentes: uploads/, media/, static/uploads/

=== Restauração (sempre com safety antes) ===
- Antes de qualquer restauração, é criado automaticamente um backup de segurança (safety-YYYYMMDD-HHMMSS.zip).
- .zip: restaura DB e arquivos. Por padrão mescla arquivos; desmarque para substituir pastas.
- .db/.sqlite: restaura somente o banco (ainda assim gera safety completo antes).
- .sql: reconstrói o banco executando o SQL (gera safety antes).

=== Variáveis ===
- SQLITE_PATH: caminho do banco (ex: /var/data/app.db)
- BACKUP_UPLOAD_FOLDER: pasta dos backups (ex: /var/data/backups)
- BACKUP_INCLUDE_DIRS: CSV com pastas extras a incluir nos backups
- MAX_CONTENT_LENGTH: limite de upload em bytes (ex: 20971520)
- WEB_CONCURRENCY: 1 para SQLite
