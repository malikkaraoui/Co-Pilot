"""Service de fiches modele -- recupere les informations de fiabilite et couts.

Point d'entree simple pour les callers (API, rapport PDF) qui veulent
les specs techniques d'un vehicule sans se soucier des jointures SQLAlchemy.
Sert surtout dans le rapport PDF pour afficher fiabilite et couts connus.
"""

import logging

from app.models.vehicle import VehicleSpec

logger = logging.getLogger(__name__)


def get_vehicle_specs(vehicle_id: int, fuel_type: str | None = None) -> list[VehicleSpec]:
    """Recupere les fiches techniques d'un vehicule.

    Filtre optionnellement par type de carburant pour ne retourner
    que les variantes pertinentes (ex: Diesel uniquement pour un scan diesel).

    Args:
        vehicle_id: ID du vehicule dans la base de reference.
        fuel_type: Filtre optionnel par type de carburant (ex. "Essence", "Diesel").

    Returns:
        Liste de VehicleSpec correspondantes (peut etre vide).
    """
    query = VehicleSpec.query.filter_by(vehicle_id=vehicle_id)
    if fuel_type:
        query = query.filter_by(fuel_type=fuel_type)

    specs = query.all()
    logger.debug("Found %d specs for vehicle_id=%d (fuel=%s)", len(specs), vehicle_id, fuel_type)
    return specs


def get_vehicle_fiche(make: str, model: str) -> dict | None:
    """Recupere la fiche complete d'un vehicule (specs + fiabilite).

    Combine les informations du vehicule et de ses specs pour
    construire une fiche lisible. Utilise par l'API /fiche pour
    l'affichage dans l'extension et le site.

    Args:
        make: Marque du vehicule.
        model: Nom du modele.

    Returns:
        Dictionnaire avec les infos ou None si vehicule introuvable.
    """
    from app.services.vehicle_lookup import find_vehicle

    vehicle = find_vehicle(make, model)
    if not vehicle:
        return None

    specs = get_vehicle_specs(vehicle.id)
    if not specs:
        # Vehicule connu mais pas encore de specs enrichies
        return {
            "vehicle": {
                "brand": vehicle.brand,
                "model": vehicle.model,
                "generation": vehicle.generation,
                "year_start": vehicle.year_start,
                "year_end": vehicle.year_end,
            },
            "specs": [],
        }

    return {
        "vehicle": {
            "brand": vehicle.brand,
            "model": vehicle.model,
            "generation": vehicle.generation,
            "year_start": vehicle.year_start,
            "year_end": vehicle.year_end,
        },
        "specs": [
            {
                "fuel_type": s.fuel_type,
                "transmission": s.transmission,
                "engine": s.engine,
                "power_hp": s.power_hp,
                "reliability_rating": s.reliability_rating,
                "known_issues": s.known_issues,
                "expected_costs": s.expected_costs,
            }
            for s in specs
        ],
    }
