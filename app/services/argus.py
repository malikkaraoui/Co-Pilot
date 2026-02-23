"""Service Argus -- recupere les references de prix geolocalisees."""

import logging

from app.models.argus import ArgusPrice

logger = logging.getLogger(__name__)


def get_argus_price(vehicle_id: int, region: str, year: int) -> ArgusPrice | None:
    """Recherche le prix argus d'un vehicule pour une region et une annee donnees.

    Args:
        vehicle_id: ID du vehicule dans la base de reference.
        region: Nom de la region (ex. "Auvergne-Rhone-Alpes").
        year: Annee du modele.

    Returns:
        L'ArgusPrice correspondant ou None.
    """
    result = ArgusPrice.query.filter_by(
        vehicle_id=vehicle_id,
        region=region,
        year=year,
    ).first()

    if result:
        logger.debug(
            "Argus found: %s %d -> %d/%d/%d",
            region,
            year,
            result.price_low,
            result.price_mid,
            result.price_high,
        )
    else:
        logger.debug("No argus data for vehicle_id=%d region=%s year=%d", vehicle_id, region, year)
    return result
