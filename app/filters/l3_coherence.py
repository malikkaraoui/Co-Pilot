"""Filtre L3 Coherence -- verifie la coherence croisee des donnees de l'annonce."""

import logging
import re
from datetime import datetime, timezone
from typing import Any

from app.filters.base import BaseFilter, FilterResult
from app.filters.vehicle_categories import (
    get_expected_km_per_year,
    get_vehicle_category,
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

    @staticmethod
    def _parse_fiscal_power_cv(raw: Any) -> int | None:
        """Extrait la puissance fiscale en CV depuis int/str (ex: "1", "1 Cv")."""
        if raw is None:
            return None
        if isinstance(raw, int):
            return raw
        if isinstance(raw, float):
            return int(raw)
        text = str(raw).strip()
        m = re.search(r"\d+", text)
        if not m:
            return None
        try:
            return int(m.group(0))
        except ValueError:
            return None

    @staticmethod
    def _parse_power_din_hp(raw: Any) -> int | None:
        """Extrait la puissance DIN en CV depuis int/str."""
        if raw is None:
            return None
        if isinstance(raw, (int, float)):
            return int(raw)
        text = str(raw).strip()
        m = re.search(r"\d+", text)
        if not m:
            return None
        try:
            return int(m.group(0))
        except ValueError:
            return None

    def run(self, data: dict[str, Any]) -> FilterResult:
        year_str = data.get("year_model")
        mileage = data.get("mileage_km")
        price = data.get("price_eur")
        make = data.get("make") or ""
        model = data.get("model") or ""
        fiscal_power_cv = self._parse_fiscal_power_cv(
            data.get("power_fiscal_cv", data.get("fiscal_hp"))
        )
        power_din_hp = self._parse_power_din_hp(
            data.get("power_din_hp") or data.get("power_hp") or data.get("horse_power_din")
        )

        if year_str is None or mileage is None:
            return self.skip("Année ou kilométrage non disponible")

        try:
            year = int(year_str)
        except (ValueError, TypeError):
            return self.skip("Année non valide")

        current_year = datetime.now(timezone.utc).year
        age = current_year - year

        if age < 0:
            return FilterResult(
                filter_id=self.filter_id,
                status="fail",
                score=0.0,
                message="L'année du modèle est dans le futur — donnée suspecte",
                details={"year": year, "current_year": current_year},
            )

        # km/an attendu adapte a la categorie du vehicule
        avg_km_per_year = get_expected_km_per_year(
            make, model, fiscal_hp=fiscal_power_cv, power_din_hp=power_din_hp
        )
        category = get_vehicle_category(
            make, model, fiscal_hp=fiscal_power_cv, power_din_hp=power_din_hp
        )

        # Donnee reelle LBC : vendeur pro = probable ex-flotte/LOA
        owner_type = data.get("owner_type")
        is_pro = owner_type == "pro"

        # Sportive/super-sportive : km faible = normal et positif
        # On utilise la catégorie (pas la puissance brute) pour ne pas classer
        # un Cayenne 440cv comme "sportive" alors qu'il est mappé suv_premium.
        vehicle_is_sportive = category == "sportive"

        warnings = []
        expected_km = age * avg_km_per_year
        km_per_year = mileage / max(age, 1)

        if expected_km > 0:
            km_ratio = mileage / expected_km
        else:
            km_ratio = 1.0 if mileage < 20000 else 2.0

        if km_ratio < (1 - KM_TOLERANCE_PCT):
            # Sportive avec km bas : c'est un bon signe, pas suspect
            if vehicle_is_sportive:
                warnings.append(
                    f"Kilométrage faible ({mileage:,} km pour {age} ans) "
                    f"— c'est plutôt bien pour une sportive de ce type, "
                    f"ces voitures roulent peu"
                )
            # Vehicule tres recent (<=1 an) avec km quasi-nul :
            # probable immatriculation constructeur pour gonfler les stats de vente,
            # pas un compteur trafique.
            elif age <= 1 and mileage < 1000:
                if is_pro:
                    warnings.append(
                        f"Véhicule quasi-neuf ({mileage:,} km) vendu par un pro "
                        f"— probable immatriculation constructeur (gonflement des "
                        f"statistiques de vente), n'a pas trouvé preneur"
                    )
                else:
                    warnings.append(
                        f"Véhicule quasi-neuf ({mileage:,} km, {age} an) "
                        f"— n'a pas trouvé preneur ou à peine utilisé"
                    )
            else:
                warnings.append(
                    f"Kilométrage bas pour l'année ({mileage:,} km pour {age} ans, "
                    f"attendu ~{expected_km:,} km)"
                )
        elif km_ratio > (1 + KM_TOLERANCE_PCT):
            # Vendeur pro + km eleve : probable deflottage (entretien suivi)
            if is_pro and km_ratio < 2.5:
                warnings.append(
                    f"Kilométrage élevé ({mileage:,} km) mais vendeur professionnel "
                    f"(probable déflottage, entretien suivi)"
                )
            else:
                warnings.append(
                    f"Kilométrage élevé ({mileage:,} km pour {age} ans, "
                    f"attendu ~{expected_km:,} km)"
                )

        # Verification basique du prix (pas de comparaison argus ici, c'est le L4)
        if price is not None:
            if price < 500:
                warnings.append(f"Prix anormalement bas ({price} EUR)")
            elif price > 100000:
                warnings.append(f"Prix très élevé ({price:,} EUR)")

        # Calcul du score
        # Vehicule recent quasi-neuf : cas normal, pas suspect
        is_recent_low_km = age <= 1 and mileage < 1000

        if not warnings:
            score = 1.0
            status = "pass"
            message = "Cohérence des données OK"
        elif len(warnings) == 1:
            if vehicle_is_sportive and "sportive" in warnings[0]:
                # Sportive avec km faible : bon signe, informatif
                score = 0.85
            elif is_recent_low_km and is_pro:
                # Immatriculation constructeur chez un pro : informatif, pas alarmant
                score = 0.7
            elif is_recent_low_km:
                # Particulier, vehicule quasi-neuf : leger
                score = 0.65
            elif is_pro and "professionnel" in warnings[0]:
                # Vendeur pro avec km eleve mais pas excessif : warning leger
                score = 0.6
            else:
                score = 0.5
            status = "warning"
            message = warnings[0]
        else:
            score = 0.2
            status = "fail"
            message = f"{len(warnings)} incohérences détectées"

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
                "fiscal_power_cv": fiscal_power_cv,
                "power_din_hp": power_din_hp,
                "is_voiture_sans_permis": category == "voiture_sans_permis",
                "is_sportive": vehicle_is_sportive,
                "is_pro": is_pro,
                "is_recent_low_km": is_recent_low_km,
                "avg_km_per_year": avg_km_per_year,
                "warnings": warnings,
            },
        )
