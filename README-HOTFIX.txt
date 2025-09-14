HOTFIX: Rota raiz estável para evitar erro 500 no Render

O que contém:
- app.py: cria a rota "/" que retorna um texto simples
- mantém /healthz para o healthcheck do Render
- adiciona um handler global de erros que imprime traceback nos logs

Como aplicar no Render:
1) No dashboard do Render, abra seu serviço → Deploys → "Add files via upload"
2) Faça upload DESSE ZIP e confirme (ele só substitui o app.py na raiz).
3) Confirme que o Start Command é `gunicorn app:app` (ou equivalente).
4) Teste:
   - / → deve mostrar "Aplicação rodando no Render 🚀"
   - /healthz → deve retornar {"ok": true, ...}

Se sua aplicação usa um `app.py` diferente (outro nome de arquivo ou o objeto Flask
está em outro módulo), ajuste o comando do gunicorn e/ou mova esse app.py.
