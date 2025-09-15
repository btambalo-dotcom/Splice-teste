
# Render Disk Persistence

This app is configured to store the SQLite database on the Render Disk mounted at **/var/data**.

## Notes
- Env var **DATA_DIR** controls the folder (default `/var/data`).
- The DB file is `splice_db.sqlite` in DATA_DIR.
- `init_db.py` is patched to NEVER drop the DB and to skip recreate if the file already exists.
- After you add a Render Disk in the dashboard, set **Mount Path** to `/var/data` and redeploy.
- Verify in logs that requests hit the app and data persists across deploys.
