#!/bin/bash
set -e

PORT="${PORT:-5000}"

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
