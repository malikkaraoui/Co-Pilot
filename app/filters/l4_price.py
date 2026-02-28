"""Filtre L4 Prix / Argus -- compare le prix de l'annonce aux donnees argus geolocalisees."""

import logging
from typing import Any

from app.filters.base import BaseFilter, FilterResult

logger = logging.getLogger(__name__)


class L4PriceFilter(BaseFilter):
    """Compare le prix de l'annonce a la reference argus pour la region."""

    filter_id = "L4"

    # Seuil par defaut (fallback si pas de specs en base)
    MARKET_MIN_SAMPLES = 3

    def _get_min_samples(self, data: dict[str, Any]) -> int:
        """Seuil dynamique base sur la puissance du vehicule."""
        # Si l'annonce indique la puissance, l'utiliser directement
        power = data.get("power_din_hp") or data.get("power_hp") or data.get("horse_power_din")
        if power:
            try:
                hp = int(power)
                if hp > 420:
                    return 2  # Ultra-niche : 2 annonces suffisent
                if hp > 300:
                    return 3  # Niche sportive
            except (ValueError, TypeError):
                pass
        return self.MARKET_MIN_SAMPLES

    def run(self, data: dict[str, Any]) -> FilterResult:
        price = data.get("price_eur")
        if price is None:
            return self.skip("Prix non disponible dans l'annonce")

        # Import local pour eviter les imports circulaires
        from app.services.argus import get_argus_price
        from app.services.market_service import get_market_stats, normalize_market_text
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
        details: dict[str, Any] = {
            "price_annonce": price,
            "region": region,
            "lookup_make": make,
            "lookup_model": model,
            "lookup_year": year,
            "lookup_region_key": normalize_market_text(region).lower(),
            "lookup_fuel_input": fuel,
            "lookup_fuel_key": normalize_market_text(fuel).lower() if fuel else None,
        }

        # Transparence cascade : quels tiers ont ete essayes et avec quel resultat
        cascade_tried: list[str] = []

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
        min_samples = self._get_min_samples(data)
        details["lookup_min_samples"] = min_samples
        country = (data.get("country") or "FR").upper()
        market = get_market_stats(make, model, year, region, fuel=fuel, country=country)
        cascade_tried.append("market_price")
        if market and market.sample_count >= min_samples:
            # IQR Mean = moyenne des 50% centraux du marche (plus robuste que la mediane)
            ref_price = market.price_iqr_mean or market.price_median
            source = "marche_leboncoin"
            details["price_reference"] = ref_price
            details["price_iqr_mean"] = market.price_iqr_mean
            details["price_median"] = market.price_median
            details["price_p25"] = market.price_p25
            details["price_p75"] = market.price_p75
            details["sample_count"] = market.sample_count
            details["source"] = source
            details["cascade_market_price_result"] = "found"
            if market.precision is not None:
                details["precision"] = market.precision
        elif market and market.sample_count > 0:
            details["cascade_market_price_result"] = "insufficient"
        else:
            details["cascade_market_price_result"] = "not_found"

        # 2. Fallback ArgusPrice (seed) : necessite le vehicule dans le referentiel
        if ref_price is None:
            cascade_tried.append("argus_seed")
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
                    details["cascade_argus_seed_result"] = "found"
                else:
                    details["cascade_argus_seed_result"] = "not_found"
            else:
                details["cascade_argus_seed_result"] = "not_found"

        # 3. Fallback LBC Estimation (fourchette affichee par LBC -- scoring leger)
        if ref_price is None:
            lbc_est = data.get("lbc_estimation")
            if lbc_est and isinstance(lbc_est, dict):
                lbc_low = lbc_est.get("low")
                lbc_high = lbc_est.get("high")
                if (
                    lbc_low
                    and lbc_high
                    and isinstance(lbc_low, (int, float))
                    and isinstance(lbc_high, (int, float))
                ):
                    cascade_tried.append("lbc_estimation")
                    ref_price = (lbc_low + lbc_high) / 2
                    source = "estimation_lbc"
                    details["lbc_estimation_low"] = lbc_low
                    details["lbc_estimation_high"] = lbc_high
                    details["price_reference"] = ref_price
                    details["source"] = source
                    details["cascade_lbc_estimation_result"] = "found"
                    logger.info(
                        "L4 using LBC estimation: low=%d high=%d mid=%.0f",
                        lbc_low,
                        lbc_high,
                        ref_price,
                    )
                else:
                    cascade_tried.append("lbc_estimation")
                    details["cascade_lbc_estimation_result"] = "invalid"
            else:
                cascade_tried.append("lbc_estimation")
                details["cascade_lbc_estimation_result"] = "not_found"

        details["cascade_tried"] = cascade_tried

        if ref_price is None:
            if market and market.sample_count < min_samples:
                logger.info(
                    "L4 insufficient samples: %s %s %d %s (n=%d, min=%d)",
                    make,
                    model,
                    year,
                    region,
                    market.sample_count,
                    min_samples,
                )
                return self.skip(
                    f"Données insuffisantes ({market.sample_count} annonces, minimum {min_samples})",
                    details=details,
                )
            logger.info(
                "L4 no ref: market=%s, tried make=%r model=%r year=%d region=%r",
                market,
                make,
                model,
                year,
                region,
            )
            return self.skip(
                "Pas de données de référence pour ce modèle dans cette région",
                details=details,
            )

        # Comparaison
        delta = price - ref_price
        delta_pct = (delta / ref_price) * 100

        # Scoring attenue pour estimation LBC (fourchette large, moins fiable)
        if source == "estimation_lbc":
            details["delta_pct_raw"] = round(delta_pct, 1)
            delta_pct = delta_pct * 0.5
            details["delta_pct_attenuated"] = True

        details["delta_eur"] = delta
        details["delta_pct"] = round(delta_pct, 1)

        # Prefix du message selon la source
        msg_prefix = ""
        if source == "estimation_lbc":
            msg_prefix = "Estimation LeBonCoin — "

        if abs(delta_pct) <= 10:
            status = "pass"
            score = 1.0
            message = f"{msg_prefix}Prix en ligne avec la référence ({delta_pct:+.0f}%)"
        elif abs(delta_pct) <= 25:
            status = "warning"
            score = 0.5
            direction = "au-dessus" if delta_pct > 0 else "en dessous"
            message = f"{msg_prefix}Prix {abs(delta_pct):.0f}% {direction} de la référence"
        else:
            status = "fail"
            score = 0.1
            direction = "au-dessus" if delta_pct > 0 else "en dessous"
            message = f"{msg_prefix}Prix {abs(delta_pct):.0f}% {direction} de la référence — anomalie prix"

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
