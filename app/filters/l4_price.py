"""Filtre L4 Prix / Argus -- compare le prix de l'annonce aux donnees argus geolocalisees."""

import logging
from typing import Any

from app.filters.base import BaseFilter, FilterResult

logger = logging.getLogger(__name__)


class L4PriceFilter(BaseFilter):
    """Compare le prix de l'annonce a la reference argus pour la region."""

    filter_id = "L4"

    def run(self, data: dict[str, Any]) -> FilterResult:
        price = data.get("price_eur")
        if not price:
            return self.skip("Prix non disponible dans l'annonce")

        # Import local pour eviter les imports circulaires
        from app.services.argus import get_argus_price
        from app.services.vehicle_lookup import find_vehicle

        make = data.get("make")
        model = data.get("model")
        year_str = data.get("year_model")
        location = data.get("location") or {}
        region = location.get("region")

        if not make or not model or not year_str:
            return self.skip("Donnees insuffisantes pour la comparaison argus")

        try:
            year = int(year_str)
        except (ValueError, TypeError):
            return self.skip("Annee non valide")

        vehicle = find_vehicle(make, model)
        if not vehicle:
            return self.skip("Modele non reconnu -- comparaison argus impossible")

        if not region:
            return self.skip("Region non disponible dans l'annonce")

        argus = get_argus_price(vehicle.id, region, year)
        if not argus or not argus.price_mid:
            return self.skip("Pas de donnees argus pour ce modele dans cette region")

        # Comparaison
        delta = price - argus.price_mid
        delta_pct = (delta / argus.price_mid) * 100

        if abs(delta_pct) <= 10:
            status = "pass"
            score = 1.0
            message = f"Prix en ligne avec l'argus ({delta_pct:+.0f}%)"
        elif abs(delta_pct) <= 25:
            status = "warning"
            score = 0.5
            direction = "au-dessus" if delta_pct > 0 else "en dessous"
            message = f"Prix {abs(delta_pct):.0f}% {direction} de l'argus local"
        else:
            status = "fail"
            score = 0.1
            direction = "au-dessus" if delta_pct > 0 else "en dessous"
            message = f"Prix {abs(delta_pct):.0f}% {direction} de l'argus -- anomalie prix"

        return FilterResult(
            filter_id=self.filter_id,
            status=status,
            score=score,
            message=message,
            details={
                "price_annonce": price,
                "price_argus_mid": argus.price_mid,
                "price_argus_low": argus.price_low,
                "price_argus_high": argus.price_high,
                "delta_eur": delta,
                "delta_pct": round(delta_pct, 1),
                "region": region,
            },
        )
