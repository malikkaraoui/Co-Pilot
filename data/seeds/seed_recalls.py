#!/usr/bin/env python3
"""Seed des rappels constructeur -- Takata airbag.

Les rappels constructeur sont utilises par le filtre L11 pour alerter
l'utilisateur si le vehicule analyse est potentiellement concerne
par un rappel de securite (ici les airbags Takata defectueux).

On ne couvre ici que les vehicules deja presents dans le catalogue OKazCar.
Les modeles hors catalogue sont ignores silencieusement.

Script idempotent : ne cree pas de doublons si relance.
Usage : python data/seeds/seed_recalls.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models.manufacturer_recall import ManufacturerRecall  # noqa: E402
from app.models.vehicle import Vehicle  # noqa: E402

# Source officielle du rappel
GOV_URL = "https://www.ecologie.gouv.fr/rappel-airbag-takata"
RECALL_TYPE = "takata_airbag"
DESCRIPTION = "Airbag Takata défectueux — gonfleur pouvant projeter des fragments métalliques"
SEVERITY = "critical"

# Liste des vehicules concernes par le rappel Takata
# (marque catalogue, modele catalogue, year_start, year_end)
# Seuls les vehicules du catalogue OKazCar sont inclus.
TAKATA_RECALLS = [
    ("Audi", "A3", 2006, 2013),
    ("BMW", "Serie 1", 2004, 2017),
    ("BMW", "Serie 3", 1997, 2018),
    ("BMW", "X1", 2009, 2016),
    ("Citroen", "C3", 2008, 2017),
    ("Citroen", "C4", 2010, 2018),
    ("Land Rover", "Discovery Sport", 2015, 2016),
    ("Mercedes", "Classe A", 2004, 2016),
    ("Mercedes", "Classe C", 2004, 2016),
    ("Mercedes", "Classe E", 2004, 2016),
    ("Opel", "Mokka", 2011, 2018),
    ("Seat", "Ibiza", 2016, 2017),
    ("Skoda", "Fabia", 2013, 2018),
    ("Skoda", "Octavia", 2013, 2018),
    ("Toyota", "Yaris", 2001, 2017),
    ("Toyota", "Corolla", 2001, 2010),
    ("Toyota", "RAV4", 2003, 2005),
    ("Volkswagen", "Golf", 2009, 2013),
    ("Volkswagen", "Polo", 2007, 2014),
    ("Volkswagen", "Tiguan", 2015, 2016),
]


def seed():
    """Insere les rappels Takata en base.

    Idempotent : dedup sur (vehicle_id, recall_type, year_start, year_end).
    """
    app = create_app()

    with app.app_context():
        db.create_all()

        created = 0
        skipped_no_vehicle = 0
        skipped_exists = 0

        for brand, model, year_start, year_end in TAKATA_RECALLS:
            vehicle = Vehicle.query.filter_by(brand=brand, model=model).first()
            if not vehicle:
                print(f"  [skip] {brand} {model} — pas dans le catalogue")
                skipped_no_vehicle += 1
                continue

            existing = ManufacturerRecall.query.filter_by(
                vehicle_id=vehicle.id,
                recall_type=RECALL_TYPE,
                year_start=year_start,
                year_end=year_end,
            ).first()
            if existing:
                print(f"  [skip] {brand} {model} ({year_start}-{year_end}) — deja en base")
                skipped_exists += 1
                continue

            recall = ManufacturerRecall(
                vehicle_id=vehicle.id,
                recall_type=RECALL_TYPE,
                year_start=year_start,
                year_end=year_end,
                description=DESCRIPTION,
                gov_url=GOV_URL,
                severity=SEVERITY,
            )
            db.session.add(recall)
            created += 1
            print(f"  [+] {brand} {model} ({year_start}-{year_end})")

        db.session.commit()

        total = ManufacturerRecall.query.count()
        print(
            f"\nResultat : {created} rappels crees, {skipped_no_vehicle} vehicules hors catalogue, {skipped_exists} doublons"
        )
        print(f"Total rappels en base : {total}")


if __name__ == "__main__":
    seed()
