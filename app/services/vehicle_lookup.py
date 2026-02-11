"""Service de recherche vehicule -- trouve un vehicule dans la base de reference.

Gere les variantes courantes de noms de marques et modeles
(ex. "Clio 5" -> "Clio V", "VW" -> "Volkswagen").
"""

import logging

from app.models.vehicle import Vehicle

logger = logging.getLogger(__name__)

# Alias de marques courantes -> nom canonique en base
BRAND_ALIASES: dict[str, str] = {
    "vw": "volkswagen",
    "citroën": "citroen",
    "bmw": "bmw",
    "merco": "mercedes",
    "merc": "mercedes",
}

# Alias de modeles courants -> nom canonique en base
MODEL_ALIASES: dict[str, str] = {
    "clio 5": "clio v",
    "clio5": "clio v",
    "serie 3": "serie 3",
    "série 3": "serie 3",
    "series 3": "serie 3",
    "3er": "serie 3",
    "golf 7": "golf",
    "golf 8": "golf",
    "golf vii": "golf",
    "golf viii": "golf",
    "yaris 4": "yaris",
    "yaris iv": "yaris",
    "500": "500",
    "fiat500": "500",
    "polo 6": "polo",
    "polo vi": "polo",
    "208 ii": "208",
    "2008 ii": "2008",
    "3008 ii": "3008",
    "308 iii": "308",
    "c3 iii": "c3",
    "c-hr": "c-hr",
    "chr": "c-hr",
    "sandero 3": "sandero",
    "sandero iii": "sandero",
    "duster 2": "duster",
    "duster ii": "duster",
}


def _normalize_brand(brand: str) -> str:
    """Normalise le nom de marque en appliquant les alias connus."""
    cleaned = brand.strip().lower()
    return BRAND_ALIASES.get(cleaned, cleaned)


def _normalize_model(model: str) -> str:
    """Normalise le nom de modele en appliquant les alias connus."""
    cleaned = model.strip().lower()
    return MODEL_ALIASES.get(cleaned, cleaned)


def find_vehicle(make: str, model: str) -> Vehicle | None:
    """Recherche un vehicule par marque et modele, insensible a la casse.

    Gere les variations courantes via les tables d'alias
    (ex. "VW" -> "Volkswagen", "Clio 5" -> "Clio V").

    Args:
        make: Marque du vehicule (ex. "Peugeot", "VW").
        model: Nom du modele (ex. "3008", "Clio 5").

    Returns:
        Le Vehicle correspondant ou None.
    """
    brand_norm = _normalize_brand(make)
    model_norm = _normalize_model(model)

    vehicle = Vehicle.query.filter(
        Vehicle.brand.ilike(brand_norm),
        Vehicle.model.ilike(f"%{model_norm}%"),
    ).first()

    if vehicle:
        logger.debug("Found vehicle: %s %s (id=%d)", vehicle.brand, vehicle.model, vehicle.id)
    else:
        logger.debug("Vehicle not found: %s %s (normalized: %s %s)",
                      make, model, brand_norm, model_norm)

    return vehicle
