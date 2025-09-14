web: gunicorn app:app -w 1 -k sync -b 0.0.0.0:$PORT --timeout 120 --graceful-timeout 30 --log-level info --access-logfile - --error-logfile -
