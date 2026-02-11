"""Service de recherche vehicule -- trouve un vehicule dans la base de reference."""

import logging

from app.models.vehicle import Vehicle

logger = logging.getLogger(__name__)


def find_vehicle(make: str, model: str) -> Vehicle | None:
    """Recherche un vehicule par marque et modele, insensible a la casse.

    Gere les variations courantes (ex. "3008" correspond a "3008").

    Args:
        make: Marque du vehicule (ex. "Peugeot").
        model: Nom du modele (ex. "3008").

    Returns:
        Le Vehicle correspondant ou None.
    """
    make_lower = make.strip().lower()
    model_lower = model.strip().lower()

    vehicle = Vehicle.query.filter(
        Vehicle.brand.ilike(make_lower),
        Vehicle.model.ilike(f"%{model_lower}%"),
    ).first()

    if vehicle:
        logger.debug("Found vehicle: %s %s (id=%d)", vehicle.brand, vehicle.model, vehicle.id)
    else:
        logger.debug("Vehicle not found: %s %s", make, model)

    return vehicle
