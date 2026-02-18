"""Filtre L4 Prix / Argus -- compare le prix de l'annonce aux donnees argus geolocalisees."""

import logging
from typing import Any

from app.filters.base import BaseFilter, FilterResult

logger = logging.getLogger(__name__)


class L4PriceFilter(BaseFilter):
    """Compare le prix de l'annonce a la reference argus pour la region."""

    filter_id = "L4"

    # Seuil minimum de prix pour utiliser les donnees MarketPrice
    MARKET_MIN_SAMPLES = 3

    def run(self, data: dict[str, Any]) -> FilterResult:
        price = data.get("price_eur")
        if price is None:
            return self.skip("Prix non disponible dans l'annonce")

        # Import local pour eviter les imports circulaires
        from app.services.argus import get_argus_price
        from app.services.market_service import get_market_stats
        from app.services.vehicle_lookup import find_vehicle

        make = data.get("make")
        model = data.get("model")
        year_str = data.get("year_model")
        location = data.get("location") or {}
        region = location.get("region")

        if not make or not model or not year_str:
            return self.skip("Données insuffisantes pour la comparaison argus")

        try:
            year = int(year_str)
        except (ValueError, TypeError):
            return self.skip("Année non valide")

        if not region:
            return self.skip("Région non disponible dans l'annonce")

        fuel = (data.get("fuel") or "").strip() or None
        ref_price = None
        source = None
        details: dict[str, Any] = {"price_annonce": price, "region": region}

        # 1. MarketPrice (crowdsource) : pas besoin du referentiel vehicule,
        #    la recherche se fait par make/model/year/region/fuel en texte.
        logger.info(
            "L4 lookup: make=%r model=%r year=%d region=%r fuel=%r",
            make,
            model,
            year,
            region,
            fuel,
        )
        market = get_market_stats(make, model, year, region, fuel=fuel)
        if market and market.sample_count >= self.MARKET_MIN_SAMPLES:
            ref_price = market.price_median
            source = "marche_leboncoin"
            details["price_reference"] = market.price_median
            details["sample_count"] = market.sample_count
            details["source"] = source

        # 2. Fallback ArgusPrice (seed) : necessite le vehicule dans le referentiel
        if ref_price is None:
            vehicle = find_vehicle(make, model)
            if vehicle:
                argus = get_argus_price(vehicle.id, region, year)
                if argus and argus.price_mid:
                    ref_price = argus.price_mid
                    source = "argus_seed"
                    details["price_argus_mid"] = argus.price_mid
                    details["price_argus_low"] = argus.price_low
                    details["price_argus_high"] = argus.price_high
                    details["source"] = source

        if ref_price is None:
            if market and market.sample_count < self.MARKET_MIN_SAMPLES:
                logger.info(
                    "L4 insufficient samples: %s %s %d %s (n=%d, min=%d)",
                    make,
                    model,
                    year,
                    region,
                    market.sample_count,
                    self.MARKET_MIN_SAMPLES,
                )
                return self.skip(
                    f"Données insuffisantes ({market.sample_count} annonces, minimum {self.MARKET_MIN_SAMPLES})"
                )
            logger.info(
                "L4 no ref: market=%s, tried make=%r model=%r year=%d region=%r",
                market,
                make,
                model,
                year,
                region,
            )
            return self.skip("Pas de données de référence pour ce modèle dans cette région")

        # Comparaison
        delta = price - ref_price
        delta_pct = (delta / ref_price) * 100
        details["delta_eur"] = delta
        details["delta_pct"] = round(delta_pct, 1)

        if abs(delta_pct) <= 10:
            status = "pass"
            score = 1.0
            message = f"Prix en ligne avec la référence ({delta_pct:+.0f}%)"
        elif abs(delta_pct) <= 25:
            status = "warning"
            score = 0.5
            direction = "au-dessus" if delta_pct > 0 else "en dessous"
            message = f"Prix {abs(delta_pct):.0f}% {direction} de la référence"
        else:
            status = "fail"
            score = 0.1
            direction = "au-dessus" if delta_pct > 0 else "en dessous"
            message = f"Prix {abs(delta_pct):.0f}% {direction} de la référence — anomalie prix"

        # Signal "anguille sous roche" : prix en dessous de la reference MAIS
        # l'annonce est en ligne depuis >30 jours. Si c'etait vraiment une bonne
        # affaire, elle serait partie. Les acheteurs n'ont pas franchi le pas.
        days_online = data.get("days_online")
        if days_online is not None and days_online > 30 and delta_pct < -10:
            details["stale_below_market"] = True
            details["days_online"] = days_online
            if status == "pass":
                status = "warning"
                score = 0.5
            message += (
                f" — en ligne depuis {days_online} jours, les acheteurs n'ont pas franchi le pas"
            )

        return FilterResult(
            filter_id=self.filter_id,
            status=status,
            score=score,
            message=message,
            details=details,
        )
