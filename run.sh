#!/usr/bin/env bash
# Lance le serveur Flask OKazCar avec le venv du projet.
set -e
cd "$(dirname "$0")"
source .venv/bin/activate
flask run --port 5001
