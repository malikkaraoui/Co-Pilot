"""Filtre L5 Visuel / NumPy -- analyse statistique des donnees de l'annonce par rapport a la reference."""

import logging
from typing import Any

import numpy as np

from app.filters.base import BaseFilter, FilterResult

logger = logging.getLogger(__name__)


class L5VisualFilter(BaseFilter):
    """Analyse statistique prix/kilometrage par z-scores NumPy par rapport aux donnees de reference."""

    filter_id = "L5"

    def run(self, data: dict[str, Any]) -> FilterResult:
        price = data.get("price_eur")
        mileage = data.get("mileage_km")

        if not price and not mileage:
            return self.skip("Ni prix ni kilometrage disponibles")

        # Recuperation des donnees de reference pour ce type de vehicule
        from app.services.vehicle_lookup import find_vehicle

        make = data.get("make")
        model = data.get("model")

        if not make or not model:
            return self.skip("Marque ou modele non disponible")

        vehicle = find_vehicle(make, model)
        if not vehicle:
            return self.skip("Modele non reconnu -- analyse statistique impossible")

        # Collecter les prix de reference depuis argus_prices pour ce vehicule
        from app.models.argus import ArgusPrice

        argus_records = ArgusPrice.query.filter_by(vehicle_id=vehicle.id).all()

        if len(argus_records) < 3:
            return self.skip("Pas assez de donnees de reference pour l'analyse statistique")

        # Construction des tableaux de reference avec NumPy
        ref_prices = np.array([r.price_mid for r in argus_records if r.price_mid], dtype=float)

        if len(ref_prices) < 3:
            return self.skip("Pas assez de prix de reference")

        anomalies = []
        z_scores = {}

        # Z-score du prix
        if price:
            price_mean = np.mean(ref_prices)
            price_std = np.std(ref_prices)
            if price_std > 0:
                z_price = float((price - price_mean) / price_std)
                z_scores["price"] = round(z_price, 2)
                if abs(z_price) > 3:
                    anomalies.append(f"Prix outlier (z={z_price:.1f})")
                elif abs(z_price) > 2:
                    anomalies.append(f"Prix en marge (z={z_price:.1f})")

        # Statistiques recapitulatives
        stats = {
            "ref_count": len(ref_prices),
            "ref_mean": round(float(np.mean(ref_prices))),
            "ref_std": round(float(np.std(ref_prices))),
            "ref_median": round(float(np.median(ref_prices))),
            "z_scores": z_scores,
            "anomalies": anomalies,
        }

        if not anomalies:
            return FilterResult(
                filter_id=self.filter_id,
                status="pass",
                score=1.0,
                message="Valeurs dans la norme statistique",
                details=stats,
            )

        has_outlier = any("outlier" in a for a in anomalies)
        if has_outlier:
            return FilterResult(
                filter_id=self.filter_id,
                status="fail",
                score=0.2,
                message=anomalies[0],
                details=stats,
            )

        return FilterResult(
            filter_id=self.filter_id,
            status="warning",
            score=0.5,
            message=anomalies[0],
            details=stats,
        )
