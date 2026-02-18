"""Filtre L2 Referentiel -- verifie si le modele du vehicule existe dans la base de reference."""

import logging
from typing import Any

from app.filters.base import BaseFilter, FilterResult

logger = logging.getLogger(__name__)


class L2ReferentielFilter(BaseFilter):
    """Verifie si la marque/modele du vehicule est connu dans la base de reference Co-Pilot."""

    filter_id = "L2"

    def run(self, data: dict[str, Any]) -> FilterResult:
        make = data.get("make")
        model = data.get("model")

        if not make or not model:
            return self.skip("Marque ou modèle non disponible dans l'annonce")

        # Import local pour eviter les imports circulaires et permettre l'usage hors contexte app dans les tests
        from app.services.vehicle_lookup import find_vehicle, is_generic_model

        # "Autres" = fallback LBC quand le vendeur ne precise pas le modele
        if is_generic_model(model):
            return self.skip(f"Modèle non précisé par le vendeur ({make} {model})")

        vehicle = find_vehicle(make, model)

        if vehicle:
            logger.info("L2: model found -- %s %s", make, model)
            return FilterResult(
                filter_id=self.filter_id,
                status="pass",
                score=1.0,
                message=f"Modèle reconnu : {vehicle.brand} {vehicle.model}",
                details={
                    "vehicle_id": vehicle.id,
                    "brand": vehicle.brand,
                    "model": vehicle.model,
                    "generation": vehicle.generation,
                },
            )

        logger.info("L2: model not found -- %s %s", make, model)
        return FilterResult(
            filter_id=self.filter_id,
            status="warning",
            score=0.3,
            message=(
                f"On ne connaît pas encore le {make} {model} "
                "— on prépare le garage pour l'expertiser très prochainement !"
            ),
            details={"brand": make, "model": model, "recognized": False},
        )
