"""Filtre L3 Coherence -- verifie la coherence croisee des donnees de l'annonce."""

import logging
from datetime import datetime, timezone
from typing import Any

from app.filters.base import BaseFilter, FilterResult
from app.filters.vehicle_categories import (
    get_expected_km_per_year,
    get_vehicle_category,
    is_fleet_vehicle,
)

logger = logging.getLogger(__name__)

KM_TOLERANCE_PCT = 0.50  # 50% tolerance on expected km


class L3CoherenceFilter(BaseFilter):
    """Verifie la coherence entre l'annee, le kilometrage et le prix de l'annonce.

    Adapte les attentes km/an selon la categorie du vehicule :
    - Citadine : ~10 000 km/an
    - Compacte : ~13 000 km/an
    - SUV familial : ~17 000 km/an
    - Berline routiere : ~18 000 km/an
    - Electrique : ~12 000 km/an
    """

    filter_id = "L3"

    def run(self, data: dict[str, Any]) -> FilterResult:
        year_str = data.get("year_model")
        mileage = data.get("mileage_km")
        price = data.get("price_eur")
        make = data.get("make") or ""
        model = data.get("model") or ""

        if year_str is None or mileage is None:
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

        # km/an attendu adapte a la categorie du vehicule
        avg_km_per_year = get_expected_km_per_year(make, model)
        category = get_vehicle_category(make, model)
        fleet = is_fleet_vehicle(make, model)

        warnings = []
        expected_km = age * avg_km_per_year
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
            # Km eleve mais vehicule de flotte : nuancer le message
            if fleet and km_ratio < 2.5:
                warnings.append(
                    f"Kilometrage eleve ({mileage:,} km) mais modele courant en flotte "
                    f"d'entreprise (entretien suivi)"
                )
            else:
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
            # Vehicule de flotte avec km eleve mais pas excessif : warning leger
            if fleet and "flotte" in warnings[0]:
                score = 0.6
            else:
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
                "category": category,
                "is_fleet": fleet,
                "avg_km_per_year": avg_km_per_year,
                "warnings": warnings,
            },
        )
