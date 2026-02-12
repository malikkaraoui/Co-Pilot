#!/usr/bin/env python3
"""Seed des donnees argus geolocalisees -- prix de reference pour 5+ modeles dans 3 regions.

Script idempotent : ne cree pas de doublons si relance.
Usage : python data/seeds/seed_argus.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models.argus import ArgusPrice  # noqa: E402
from app.models.vehicle import Vehicle  # noqa: E402
from app.services.pipeline_tracker import track_pipeline  # noqa: E402

# Regions de reference (3 regions representatives)
REGIONS = ["Ile-de-France", "Auvergne-Rhone-Alpes", "Nouvelle-Aquitaine"]

# Donnees ARGUS par modele, année et region
# Format: (marque, modele, année, region, price_low, price_mid, price_high, mileage_bracket)
ARGUS_DATA = [
    # Peugeot 208 -- citadine tres vendue
    ("Peugeot", "208", 2020, "Ile-de-France", 11000, 13500, 16000, "30000-60000"),
    ("Peugeot", "208", 2020, "Auvergne-Rhone-Alpes", 10500, 13000, 15500, "30000-60000"),
    ("Peugeot", "208", 2020, "Nouvelle-Aquitaine", 10000, 12500, 15000, "30000-60000"),
    ("Peugeot", "208", 2021, "Ile-de-France", 13000, 15500, 18000, "20000-50000"),
    ("Peugeot", "208", 2021, "Auvergne-Rhone-Alpes", 12500, 15000, 17500, "20000-50000"),
    ("Peugeot", "208", 2021, "Nouvelle-Aquitaine", 12000, 14500, 17000, "20000-50000"),
    ("Peugeot", "208", 2022, "Ile-de-France", 15000, 17500, 20000, "10000-40000"),
    ("Peugeot", "208", 2022, "Auvergne-Rhone-Alpes", 14500, 17000, 19500, "10000-40000"),
    ("Peugeot", "208", 2022, "Nouvelle-Aquitaine", 14000, 16500, 19000, "10000-40000"),
    # Peugeot 3008 -- SUV familial
    ("Peugeot", "3008", 2019, "Ile-de-France", 17000, 20000, 23000, "40000-80000"),
    ("Peugeot", "3008", 2019, "Auvergne-Rhone-Alpes", 16500, 19500, 22500, "40000-80000"),
    ("Peugeot", "3008", 2019, "Nouvelle-Aquitaine", 16000, 19000, 22000, "40000-80000"),
    ("Peugeot", "3008", 2021, "Ile-de-France", 22000, 25000, 28000, "20000-50000"),
    ("Peugeot", "3008", 2021, "Auvergne-Rhone-Alpes", 21500, 24500, 27500, "20000-50000"),
    ("Peugeot", "3008", 2021, "Nouvelle-Aquitaine", 21000, 24000, 27000, "20000-50000"),
    # Renault Clio V -- citadine populaire
    ("Renault", "Clio V", 2020, "Ile-de-France", 10000, 12500, 15000, "30000-60000"),
    ("Renault", "Clio V", 2020, "Auvergne-Rhone-Alpes", 9500, 12000, 14500, "30000-60000"),
    ("Renault", "Clio V", 2020, "Nouvelle-Aquitaine", 9000, 11500, 14000, "30000-60000"),
    ("Renault", "Clio V", 2022, "Ile-de-France", 13000, 15000, 17000, "10000-40000"),
    ("Renault", "Clio V", 2022, "Auvergne-Rhone-Alpes", 12500, 14500, 16500, "10000-40000"),
    ("Renault", "Clio V", 2022, "Nouvelle-Aquitaine", 12000, 14000, 16000, "10000-40000"),
    # Dacia Sandero -- budget
    ("Dacia", "Sandero", 2021, "Ile-de-France", 9000, 11000, 13000, "20000-50000"),
    ("Dacia", "Sandero", 2021, "Auvergne-Rhone-Alpes", 8500, 10500, 12500, "20000-50000"),
    ("Dacia", "Sandero", 2021, "Nouvelle-Aquitaine", 8000, 10000, 12000, "20000-50000"),
    ("Dacia", "Sandero", 2023, "Ile-de-France", 11000, 13000, 15000, "5000-30000"),
    ("Dacia", "Sandero", 2023, "Auvergne-Rhone-Alpes", 10500, 12500, 14500, "5000-30000"),
    ("Dacia", "Sandero", 2023, "Nouvelle-Aquitaine", 10000, 12000, 14000, "5000-30000"),
    # Volkswagen Golf -- reference segment C
    ("Volkswagen", "Golf", 2019, "Ile-de-France", 16000, 19000, 22000, "40000-80000"),
    ("Volkswagen", "Golf", 2019, "Auvergne-Rhone-Alpes", 15500, 18500, 21500, "40000-80000"),
    ("Volkswagen", "Golf", 2019, "Nouvelle-Aquitaine", 15000, 18000, 21000, "40000-80000"),
    ("Volkswagen", "Golf", 2021, "Ile-de-France", 20000, 23000, 26000, "20000-50000"),
    ("Volkswagen", "Golf", 2021, "Auvergne-Rhone-Alpes", 19500, 22500, 25500, "20000-50000"),
    ("Volkswagen", "Golf", 2021, "Nouvelle-Aquitaine", 19000, 22000, 25000, "20000-50000"),
    # Toyota Yaris -- hybride fiable
    ("Toyota", "Yaris", 2021, "Ile-de-France", 14000, 16500, 19000, "20000-40000"),
    ("Toyota", "Yaris", 2021, "Auvergne-Rhone-Alpes", 13500, 16000, 18500, "20000-40000"),
    ("Toyota", "Yaris", 2021, "Nouvelle-Aquitaine", 13000, 15500, 18000, "20000-40000"),
    ("Toyota", "Yaris", 2023, "Ile-de-France", 17000, 19500, 22000, "5000-25000"),
    ("Toyota", "Yaris", 2023, "Auvergne-Rhone-Alpes", 16500, 19000, 21500, "5000-25000"),
    ("Toyota", "Yaris", 2023, "Nouvelle-Aquitaine", 16000, 18500, 21000, "5000-25000"),
]


def seed():
    """Insere les donnees argus en base. Idempotent."""
    app = create_app()

    with app.app_context():
        db.create_all()

        with track_pipeline("argus_geolocalise") as tracker:
            created = 0

            for brand, model_name, year, region, p_low, p_mid, p_high, mileage in ARGUS_DATA:
                vehicle = Vehicle.query.filter_by(brand=brand, model=model_name).first()
                if not vehicle:
                    print(
                        f"  [!] Vehicule introuvable: {brand} {model_name} -- lancer seed_vehicles.py d'abord"
                    )
                    continue

                existing = ArgusPrice.query.filter_by(
                    vehicle_id=vehicle.id, region=region, year=year
                ).first()
                if existing:
                    print(f"  [skip] Argus {brand} {model_name} {year} {region} existe deja")
                    continue

                entry = ArgusPrice(
                    vehicle_id=vehicle.id,
                    region=region,
                    year=year,
                    mileage_bracket=mileage,
                    price_low=p_low,
                    price_mid=p_mid,
                    price_high=p_high,
                    source="seed_manual",
                )
                db.session.add(entry)
                created += 1
                print(f"  [+] Argus {brand} {model_name} {year} {region}: {p_low}/{p_mid}/{p_high}")

            db.session.commit()
            tracker.count = created

        total = ArgusPrice.query.count()
        print(f"\nResultat : {created} entrees argus creees")
        print(f"Total en base : {total} entrees argus")


if __name__ == "__main__":
    seed()
