"""Service d'enrichissement automatique depuis le CSV Kaggle (Car Dataset 1945-2020).

Lookup rapide par marque/modele : retourne les specs techniques disponibles
pour creer des VehicleSpec sans intervention manuelle.
"""

import csv
import logging
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

    brand_lower = brand.lower().strip()
    model_lower = model.lower().strip()
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
