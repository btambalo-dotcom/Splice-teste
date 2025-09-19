# Splice App — Deploy estável no DigitalOcean App Platform

## O que este pacote garante
- Persistência com **fallback automático**: usa `/var/data` quando o volume existir; caso contrário cai para `/tmp/data` sem quebrar o boot.
- SQLite com WAL e timeout.
- `Procfile` e `digitalocean-app-spec.yaml` prontos.
- Rota de health check: `/healthz`.

## Passos
1. Faça upload deste pacote no App Platform.
2. Em **Settings → Environment Variables**, defina:
   - `SECRET_KEY` (um valor forte)
3. Em **Web Service → Volumes**, crie um volume em `/var/data` (ex.: 1GB).
4. Deploy.

Se o volume não estiver montado ainda, o app vai iniciar usando `/tmp/data` (volátil), só para não derrubar o deploy.
