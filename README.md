# Splice Admin — Protótipo (PT-BR)

Funcionalidades:
- **Relatórios do Admin** com dispositivos clicáveis → página de **detalhes** com fotos e autor.
- Botão para **Marcar como Lançado** (somente Admin).
- **Upload de Mapas (PDF)** e **atribuição de acesso por usuário**.
- Ao **lançar dispositivo**, o usuário **precisa selecionar** um **Mapa** dentre os que têm acesso.
- **Download de PDF** apenas para usuários com acesso ou Admin.

## Como rodar (local)
```bash
pip install -r requirements.txt
python app.py
# abra http://127.0.0.1:5000
```

Credenciais de teste (seed):
- Admin: **admin@example.com** / **admin123**
- Técnico: **tech@example.com** / **tech123**

> Segurança: remova ou proteja a rota `/force_reset_admin` em produção.
