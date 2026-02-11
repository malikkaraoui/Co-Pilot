"""Filtre L3 Coherence -- verifie la coherence croisee des donnees de l'annonce."""

import logging
from datetime import datetime, timezone
from typing import Any

from app.filters.base import BaseFilter, FilterResult

logger = logging.getLogger(__name__)

AVG_KM_PER_YEAR = 15000
KM_TOLERANCE_PCT = 0.50  # 50% tolerance on expected km


class L3CoherenceFilter(BaseFilter):
    """Verifie la coherence entre l'annee, le kilometrage et le prix de l'annonce."""

    filter_id = "L3"

    def run(self, data: dict[str, Any]) -> FilterResult:
        year_str = data.get("year_model")
        mileage = data.get("mileage_km")
        price = data.get("price_eur")

        if not year_str or not mileage:
            return self.skip("Annee ou kilometrage non disponible")

        try:
            year = int(year_str)
        except (ValueError, TypeError):
            return self.skip("Annee non valide")

        current_year = datetime.now(timezone.utc).year
        age = current_year - year

        if age < 0:
            return FilterResult(
                filter_id=self.filter_id,
                status="fail",
                score=0.0,
                message="L'annee du modele est dans le futur -- donnee suspecte",
                details={"year": year, "current_year": current_year},
            )

        # Coherence du kilometrage
        warnings = []
        expected_km = age * AVG_KM_PER_YEAR
        km_per_year = mileage / max(age, 1)

        if expected_km > 0:
            km_ratio = mileage / expected_km
        else:
            km_ratio = 1.0 if mileage < 20000 else 2.0

        if km_ratio < (1 - KM_TOLERANCE_PCT):
            warnings.append(
                f"Kilometrage bas pour l'annee ({mileage:,} km pour {age} ans, "
                f"attendu ~{expected_km:,} km)"
            )
        elif km_ratio > (1 + KM_TOLERANCE_PCT):
            warnings.append(
                f"Kilometrage eleve ({mileage:,} km pour {age} ans, "
                f"attendu ~{expected_km:,} km)"
            )

        # Verification basique du prix (pas de comparaison argus ici, c'est le L4)
        if price is not None:
            if price < 500:
                warnings.append(f"Prix anormalement bas ({price} EUR)")
            elif price > 100000:
                warnings.append(f"Prix tres eleve ({price:,} EUR)")

        # Calcul du score
        if not warnings:
            score = 1.0
            status = "pass"
            message = "Coherence des donnees OK"
        elif len(warnings) == 1:
            score = 0.5
            status = "warning"
            message = warnings[0]
        else:
            score = 0.2
            status = "fail"
            message = f"{len(warnings)} incoherences detectees"

        return FilterResult(
            filter_id=self.filter_id,
            status=status,
            score=score,
            message=message,
            details={
                "year": year,
                "age": age,
                "mileage_km": mileage,
                "km_per_year": round(km_per_year),
                "expected_km": expected_km,
                "km_ratio": round(km_ratio, 2),
                "warnings": warnings,
            },
        )
