#!/usr/bin/env python3
"""Import des specs vehicules depuis Car Dataset 1945-2020.csv (Kaggle, CC0).

Script idempotent : ne cree pas de doublons si relance.
Approche hybride : ce script importe les specs techniques du CSV,
le seed_vehicles.py conserve les donnees de fiabilite.

Usage : python data/seeds/import_csv_specs.py
"""

import csv
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models.vehicle import Vehicle, VehicleSpec  # noqa: E402
from app.services.pipeline_tracker import track_pipeline  # noqa: E402

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

CSV_PATH = Path(__file__).resolve().parent.parent.parent / "docs" / "Car Dataset 1945-2020.csv"

# Marques du marche francais a importer
TARGET_MAKES = {
    "Peugeot",
    "Renault",
    "Citroen",
    "Dacia",
    "Volkswagen",
    "Toyota",
    "Hyundai",
    "Kia",
    "BMW",
    "Mercedes-Benz",
    "Audi",
    "Ford",
    "Opel",
    "Fiat",
    "Nissan",
    "Skoda",
    "MINI",
    "Suzuki",
    "MG",
    "SEAT",
    "Volvo",
    "Mazda",
    "Honda",
    "Mitsubishi",
    "Alfa Romeo",
}

# Normalisation des types de carburant
FUEL_MAP = {
    "Gasoline": "Essence",
    "Diesel": "Diesel",
    "Hybrid": "Hybride",
    "Electric": "Electrique",
    "Plug-in Hybrid": "Hybride rechargeable",
}

# Normalisation des transmissions
TRANS_MAP = {
    "Manual": "Manuelle",
    "Automatic": "Automatique",
}


def int_or_none(val: str) -> int | None:
    """Convertit une chaine en int ou retourne None."""
    if not val or not val.strip():
        return None
    try:
        return int(float(val.strip()))
    except (ValueError, OverflowError):
        return None


def float_or_none(val: str) -> float | None:
    """Convertit une chaine en float ou retourne None."""
    if not val or not val.strip():
        return None
    try:
        return float(val.strip())
    except (ValueError, OverflowError):
        return None


def normalize_fuel(raw: str) -> str:
    """Normalise le type de carburant CSV → francais."""
    return FUEL_MAP.get(raw.strip(), raw.strip()) if raw else ""


def normalize_transmission(raw: str) -> str:
    """Normalise la transmission CSV → francais."""
    return TRANS_MAP.get(raw.strip(), raw.strip()) if raw else ""


def import_csv():
    """Importe les vehicules et specs depuis le CSV Kaggle."""
    if not CSV_PATH.exists():
        logger.error("Fichier CSV introuvable : %s", CSV_PATH)
        sys.exit(1)

    app = create_app()

    with app.app_context():
        db.create_all()

        with track_pipeline("import_csv_specs") as tracker:
            # Cache des vehicules existants : (brand, model, generation) → Vehicle
            vehicle_cache: dict[tuple[str, str, str], Vehicle] = {}
            for v in Vehicle.query.all():
                key = (v.brand, v.model, v.generation or "")
                vehicle_cache[key] = v

            # Cache des specs existantes pour idempotence
            existing_specs: set[tuple[int, str]] = set()
            for s in VehicleSpec.query.all():
                existing_specs.add((s.vehicle_id, s.engine or ""))

            created_vehicles = 0
            created_specs = 0
            skipped_specs = 0
            brand_counts: dict[str, int] = {}

            with open(CSV_PATH, encoding="utf-8") as f:
                reader = csv.DictReader(f)

                for row in reader:
                    make = row.get("Make", "").strip()
                    if make not in TARGET_MAKES:
                        continue

                    model = row.get("Modle", "").strip()
                    generation = row.get("Generation", "").strip()
                    trim = row.get("Trim", "").strip()

                    if not model:
                        continue

                    # Creer ou reutiliser le Vehicle
                    vkey = (make, model, generation)
                    if vkey not in vehicle_cache:
                        vehicle = Vehicle(
                            brand=make,
                            model=model,
                            generation=generation,
                            year_start=int_or_none(row.get("Year_from", "")),
                            year_end=int_or_none(row.get("Year_to", "")),
                        )
                        db.session.add(vehicle)
                        db.session.flush()
                        vehicle_cache[vkey] = vehicle
                        created_vehicles += 1
                    else:
                        vehicle = vehicle_cache[vkey]

                    # Verifier idempotence
                    spec_key = (vehicle.id, trim)
                    if spec_key in existing_specs:
                        skipped_specs += 1
                        continue

                    spec = VehicleSpec(
                        vehicle_id=vehicle.id,
                        fuel_type=normalize_fuel(row.get("engine_type", "")),
                        transmission=normalize_transmission(row.get("transmission", "")),
                        engine=trim,
                        power_hp=int_or_none(row.get("engine_hp", "")),
                        body_type=row.get("Body_type", "").strip() or None,
                        number_of_seats=int_or_none(row.get("number_of_seats", "")),
                        capacity_cm3=int_or_none(row.get("capacity_cm3", "")),
                        max_torque_nm=int_or_none(row.get("maximum_torque_n_m", "")),
                        curb_weight_kg=int_or_none(row.get("curb_weight_kg", "")),
                        length_mm=int_or_none(row.get("length_mm", "")),
                        width_mm=int_or_none(row.get("width_mm", "")),
                        height_mm=int_or_none(row.get("height_mm", "")),
                        mixed_consumption_l100km=float_or_none(
                            row.get("mixed_fuel_consumption_per_100_km_l", "")
                        ),
                        co2_emissions_gkm=int_or_none(row.get("CO2_emissions_g/km", "")),
                        acceleration_0_100s=float_or_none(row.get("acceleration_0_100_km/h_s", "")),
                        max_speed_kmh=int_or_none(row.get("max_speed_km_per_h", "")),
                    )
                    db.session.add(spec)
                    existing_specs.add(spec_key)
                    created_specs += 1
                    brand_counts[make] = brand_counts.get(make, 0) + 1

            db.session.commit()
            tracker.count = created_specs

        # Log recap
        logger.info("=== Import termine ===")
        logger.info("Vehicules crees : %d", created_vehicles)
        logger.info("Specs creees : %d", created_specs)
        logger.info("Specs ignorees (doublons) : %d", skipped_specs)
        logger.info("--- Par marque ---")
        for brand in sorted(brand_counts, key=brand_counts.get, reverse=True):
            logger.info("  %s : %d fiches", brand, brand_counts[brand])

        total_v = Vehicle.query.count()
        total_s = VehicleSpec.query.count()
        logger.info("Total en base : %d vehicules, %d specs", total_v, total_s)


if __name__ == "__main__":
    import_csv()
