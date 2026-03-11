"""Service de matching fiabilite moteur.

Expose get_engine_reliability() qui fait correspondre une string moteur
(ex: "1.5 BlueHDi 130") avec un enregistrement EngineReliability via
pattern matching substring (case-insensitive).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.engine_reliability import EngineReliability

logger = logging.getLogger(__name__)


def get_engine_reliability(
    engine_str: str,
    fuel_type: str | None = None,
) -> EngineReliability | None:
    """Retourne l'enregistrement de fiabilite correspondant a engine_str.

    Algorithme : pour chaque EngineReliability (filtre par fuel_type si fourni),
    teste si l'un des match_patterns est une sous-chaine de engine_str.
    Retourne le premier match (ordre : score DESC).

    Args:
        engine_str: valeur de VehicleSpec.engine, ex "1.5 BlueHDi 130 EAT8"
        fuel_type: "Diesel" ou "Essence" (optionnel, accelere la recherche)

    Returns:
        EngineReliability ou None si aucun match.
    """
    from app.models.engine_reliability import EngineReliability

    if not engine_str:
        return None

    engine_lower = engine_str.lower()

    query = EngineReliability.query.order_by(EngineReliability.score.desc())
    if fuel_type:
        query = query.filter(EngineReliability.fuel_type == fuel_type)

    for rel in query.all():
        for pattern in rel.patterns_list():
            if pattern.lower() in engine_lower:
                return rel

    return None


def get_reliability_for_specs(
    specs: list,
) -> dict[int, EngineReliability | None]:
    """Retourne un dict {spec.id: EngineReliability} pour une liste de VehicleSpec.

    Optimise : charge tous les EngineReliability une seule fois.
    """
    from app.models.engine_reliability import EngineReliability

    all_reliabilities = EngineReliability.query.order_by(EngineReliability.score.desc()).all()

    result: dict[int, "EngineReliability | None"] = {}
    for spec in specs:
        engine_str = (spec.engine or "").lower()
        fuel = spec.fuel_type or ""
        matched = None

        for rel in all_reliabilities:
            if fuel and rel.fuel_type != fuel:
                continue
            for pattern in rel.patterns_list():
                if pattern.lower() in engine_str:
                    matched = rel
                    break
            if matched:
                break

        result[spec.id] = matched

    return result
