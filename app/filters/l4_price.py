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
        if price is None:
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

        # Source de prix : MarketPrice (crowdsource) en priorite, sinon ArgusPrice (seed)
        from app.services.market_service import get_market_stats

        ref_price = None
        source = None
        details: dict[str, Any] = {"price_annonce": price, "region": region}

        logger.info("L4 lookup: make=%r model=%r year=%d region=%r", make, model, year, region)
        market = get_market_stats(make, model, year, region)
        if market and market.sample_count >= 5:
            ref_price = market.price_median
            source = "marche_leboncoin"
            details["price_reference"] = market.price_median
            details["sample_count"] = market.sample_count
            details["source"] = source
        else:
            argus = get_argus_price(vehicle.id, region, year)
            if argus and argus.price_mid:
                ref_price = argus.price_mid
                source = "argus_seed"
                details["price_argus_mid"] = argus.price_mid
                details["price_argus_low"] = argus.price_low
                details["price_argus_high"] = argus.price_high
                details["source"] = source

        if ref_price is None:
            if market and market.sample_count < 5:
                logger.info(
                    "L4 insufficient samples: %s %s %d %s (n=%d, min=5)",
                    make,
                    model,
                    year,
                    region,
                    market.sample_count,
                )
                return self.skip(
                    f"Donnees insuffisantes ({market.sample_count} annonces, minimum 5)"
                )
            logger.info(
                "L4 no ref: market=%s, tried make=%r model=%r year=%d region=%r",
                market,
                make,
                model,
                year,
                region,
            )
            return self.skip("Pas de donnees de reference pour ce modele dans cette region")

        # Comparaison
        delta = price - ref_price
        delta_pct = (delta / ref_price) * 100
        details["delta_eur"] = delta
        details["delta_pct"] = round(delta_pct, 1)

        if abs(delta_pct) <= 10:
            status = "pass"
            score = 1.0
            message = f"Prix en ligne avec la reference ({delta_pct:+.0f}%)"
        elif abs(delta_pct) <= 25:
            status = "warning"
            score = 0.5
            direction = "au-dessus" if delta_pct > 0 else "en dessous"
            message = f"Prix {abs(delta_pct):.0f}% {direction} de la reference"
        else:
            status = "fail"
            score = 0.1
            direction = "au-dessus" if delta_pct > 0 else "en dessous"
            message = f"Prix {abs(delta_pct):.0f}% {direction} de la reference -- anomalie prix"

        return FilterResult(
            filter_id=self.filter_id,
            status=status,
            score=score,
            message=message,
            details=details,
        )
