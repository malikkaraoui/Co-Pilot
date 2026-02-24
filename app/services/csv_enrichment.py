"""Service d'enrichissement automatique depuis le CSV Kaggle (Car Dataset 1945-2020).

Lookup rapide par marque/modele : retourne les specs techniques disponibles
pour creer des VehicleSpec sans intervention manuelle.
"""

import csv
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

CSV_PATH = Path(__file__).resolve().parent.parent.parent / "docs" / "Car Dataset 1945-2020.csv"

FUEL_MAP = {
    "Gasoline": "Essence",
    "Diesel": "Diesel",
    "Hybrid": "Hybride",
    "Electric": "Electrique",
    "Plug-in Hybrid": "Hybride rechargeable",
}

TRANS_MAP = {
    "Manual": "Manuelle",
    "Automatic": "Automatique",
}

# Normalisation des noms vers le format CSV Kaggle.
# Nos noms canoniques (DB/LBC) different du CSV sur certaines marques/modeles.
CSV_BRAND_NORM: dict[str, str] = {
    "mercedes": "mercedes-benz",
    "land-rover": "land rover",
    "landrover": "land rover",
}

CSV_MODEL_NORM: dict[str, str] = {
    # Mercedes : LBC dit "Classe X", CSV dit "X-Class"
    "classe a": "a-class",
    "classe b": "b-class",
    "classe c": "c-class",
    "classe e": "e-class",
    "classe s": "s-class",
    "classe g": "g-class",
    "gla": "gla-class",
    "glb": "glb-class",
    "classe glc": "glc",
    "glc": "glc",  # CSV a "GLC" directement
    "classe gle": "gle",
    "gle": "gle",  # CSV a "GLE" directement
    "cla": "cla-class",
    # DS : LBC dit "DS 3", CSV dit "3"
    "ds 3": "3",
    "ds3": "3",
    "ds 3 crossback": "3 crossback",
    "ds3 crossback": "3 crossback",
    "ds 4": "4",
    "ds4": "4",
    "ds 7": "7",
    "ds7": "7",
    "ds 7 crossback": "7 crossback",
    "ds7 crossback": "7 crossback",
    "ds 9": "9",
    "ds9": "9",
}


def _int_or_none(val: str) -> int | None:
    if not val or not val.strip():
        return None
    try:
        return int(float(val.strip()))
    except (ValueError, OverflowError):
        return None


def _float_or_none(val: str) -> float | None:
    if not val or not val.strip():
        return None
    try:
        return float(val.strip())
    except (ValueError, OverflowError):
        return None


@lru_cache(maxsize=1)
def _load_csv_catalog() -> dict[tuple[str, str], dict]:
    """Charge le catalogue complet CSV avec métadonnées.

    Returns:
        {
            ("renault", "clio"): {
                "year_start": 2012,
                "year_end": 2024,
                "specs_count": 35
            },
            ...
        }
    """
    if not CSV_PATH.exists():
        return {}

    catalog: dict[tuple[str, str], dict] = {}

    with open(CSV_PATH, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            make = (row.get("Make") or "").strip().lower()
            model = (row.get("Modle") or "").strip().lower()

            if not make or not model:
                continue

            key = (make, model)
            year_from = _int_or_none(row.get("Year_from", ""))
            year_to = _int_or_none(row.get("Year_to", ""))

            if key not in catalog:
                catalog[key] = {
                    "year_start": year_from,
                    "year_end": year_to,
                    "specs_count": 0,
                }
            else:
                # Étendre la plage d'années si nécessaire
                if year_from and (
                    catalog[key]["year_start"] is None or year_from < catalog[key]["year_start"]
                ):
                    catalog[key]["year_start"] = year_from
                if year_to and (
                    catalog[key]["year_end"] is None or year_to > catalog[key]["year_end"]
                ):
                    catalog[key]["year_end"] = year_to

            catalog[key]["specs_count"] += 1

    logger.info("CSV catalog loaded: %d unique vehicles", len(catalog))
    return catalog


def _normalize_for_csv(brand: str, model: str) -> tuple[str, str]:
    """Normalise marque/modele vers le format CSV Kaggle."""
    b = brand.lower().strip()
    m = model.lower().strip()
    b = CSV_BRAND_NORM.get(b, b)
    m = CSV_MODEL_NORM.get(m, m)
    return b, m


def has_specs(brand: str, model: str) -> bool:
    """Verifie rapidement si un vehicule a des specs dans le CSV (O(1) apres chargement)."""
    b, m = _normalize_for_csv(brand, model)
    return (b, m) in _load_csv_catalog()


def lookup_specs(brand: str, model: str) -> list[dict[str, Any]]:
    """Cherche les specs d'un vehicule dans le CSV Kaggle.

    Args:
        brand: Marque (ex. "Audi").
        model: Modele (ex. "S3").

    Returns:
        Liste de dicts avec les specs trouvees (une par motorisation/trim).
        Liste vide si rien trouve ou si le CSV est absent.
    """
    if not CSV_PATH.exists():
        logger.warning("CSV introuvable : %s", CSV_PATH)
        return []

    brand_lower, model_lower = _normalize_for_csv(brand, model)
    results: list[dict[str, Any]] = []
    seen_trims: set[str] = set()

    with open(CSV_PATH, encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for row in reader:
            csv_make = (row.get("Make") or "").strip()
            csv_model = (row.get("Modle") or "").strip()

            if csv_make.lower() != brand_lower:
                continue
            if csv_model.lower() != model_lower:
                continue

            trim = (row.get("Trim") or "").strip()
            # Deduplication par trim (eviter 5 fois le meme moteur)
            if trim in seen_trims:
                continue
            seen_trims.add(trim)

            raw_fuel = (row.get("engine_type") or "").strip()
            raw_trans = (row.get("transmission") or "").strip()

            spec = {
                "fuel_type": FUEL_MAP.get(raw_fuel, raw_fuel) or None,
                "transmission": TRANS_MAP.get(raw_trans, raw_trans) or None,
                "engine": trim or None,
                "power_hp": _int_or_none(row.get("engine_hp", "")),
                "body_type": (row.get("Body_type") or "").strip() or None,
                "number_of_seats": _int_or_none(row.get("number_of_seats", "")),
                "capacity_cm3": _int_or_none(row.get("capacity_cm3", "")),
                "max_torque_nm": _int_or_none(row.get("maximum_torque_n_m", "")),
                "curb_weight_kg": _int_or_none(row.get("curb_weight_kg", "")),
                "length_mm": _int_or_none(row.get("length_mm", "")),
                "width_mm": _int_or_none(row.get("width_mm", "")),
                "height_mm": _int_or_none(row.get("height_mm", "")),
                "mixed_consumption_l100km": _float_or_none(
                    row.get("mixed_fuel_consumption_per_100_km_l", "")
                ),
                "co2_emissions_gkm": _int_or_none(row.get("CO2_emissions_g/km", "")),
                "acceleration_0_100s": _float_or_none(row.get("acceleration_0_100_km/h_s", "")),
                "max_speed_kmh": _int_or_none(row.get("max_speed_km_per_h", "")),
                # Metadata CSV
                "generation": (row.get("Generation") or "").strip() or None,
                "year_from": _int_or_none(row.get("Year_from", "")),
                "year_to": _int_or_none(row.get("Year_to", "")),
            }
            results.append(spec)

    logger.info(
        "CSV lookup %s %s: %d specs trouvees (%d trims uniques)",
        brand,
        model,
        len(results),
        len(seen_trims),
    )
    return results
