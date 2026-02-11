#!/usr/bin/env python3
"""Initialize the database -- create all tables."""

import sys
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import *  # noqa: E402, F401, F403

app = create_app()

with app.app_context():
    db.create_all()
    print("Database tables created successfully.")
    for table in db.metadata.sorted_tables:
        print(f"  - {table.name}")
