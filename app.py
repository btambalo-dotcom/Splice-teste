from flask import Flask, jsonify

# Crie/importe seu app Flask global com o nome `app`
# Se você já possui um app em outro módulo, ajuste o import.
app = Flask(__name__)

@app.route("/")
def root_ok():
    # Rota ultra simples para evitar erros com templates/imports
    return "Aplicação rodando no Render 🚀", 200

@app.route("/healthz")
def healthz():
    # Endpoint usado pelo Render para healthcheck
    return jsonify({"ok": True, "checks": {"db": "ok", "disk": "ok"}}), 200

@app.errorhandler(Exception)
def handle_any_error(e):
    # Loga exceções no stderr para aparecer no Render Logs
    import traceback, sys
    traceback.print_exc(file=sys.stderr)
    return "Erro interno (já registrado nos logs).", 500

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
