#!/bin/bash
set -e

PORT="${PORT:-5000}"
APP_ROOT="$(cd "$(dirname "$0")" && pwd)"
SYNC_SCRIPT="$APP_ROOT/scripts/sync_render_sqlite.py"

# Synchronisation optionnelle d'un snapshot SQLite canonique vers le disque Render.
# Le script ne fait rien si RENDER_DB_SYNC_URL n'est pas renseigne.
if [ -f "$SYNC_SCRIPT" ]; then
    python "$SYNC_SCRIPT"
else
    echo "[entrypoint] WARNING: script de synchro introuvable: $SYNC_SCRIPT"
    echo "[entrypoint] WARNING: synchro Render ignoree, demarrage de l'application quand meme"
fi

# Auto-seed si la DB est vide (premier deploy)
python -c "
from app import create_app
from app.extensions import db
from app.models.vehicle import Vehicle
app = create_app()
with app.app_context():
    db.create_all()
    if Vehicle.query.count() == 0:
        print('DB vide -- seed en cours...')
        import subprocess
        subprocess.run(['python', 'data/seeds/seed_vehicles.py'], check=True)
        subprocess.run(['python', 'data/seeds/seed_argus.py'], check=True)
        subprocess.run(['python', 'data/seeds/seed_gemini_prompt.py'], check=True)
        print('Seed termine.')
    else:
        print(f'DB existante ({Vehicle.query.count()} vehicules)')
"

exec gunicorn --bind "0.0.0.0:$PORT" --workers 2 --timeout 120 wsgi:app
