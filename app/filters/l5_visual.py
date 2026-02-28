"""Filtre L5 Visuel / NumPy -- analyse statistique des prix par z-scores par rapport a la reference."""

import logging
from typing import Any

import numpy as np

from app.filters.base import BaseFilter, FilterResult

logger = logging.getLogger(__name__)


class L5VisualFilter(BaseFilter):
    """Analyse statistique des prix par z-scores NumPy par rapport aux donnees de reference."""

    filter_id = "L5"

    # Seuil minimum de samples pour utiliser les donnees MarketPrice
    MARKET_MIN_SAMPLES = 3

    # Tranches de puissance DIN (ch) -- meme logique que getHorsePowerRange() en JS
    HP_RANGES: list[tuple[int, str]] = [
        (80, "min-90"),
        (110, "70-120"),
        (140, "100-150"),
        (180, "130-190"),
        (250, "170-260"),
        (350, "240-360"),
    ]
    HP_RANGE_MAX = "340-max"

    @classmethod
    def _get_hp_range(cls, hp: int | None) -> str | None:
        """Calcule la tranche de puissance DIN pour filtrer les comparables."""
        if not hp or hp <= 0:
            return None
        for threshold, range_label in cls.HP_RANGES:
            if hp < threshold:
                return range_label
        return cls.HP_RANGE_MAX

    @staticmethod
    def _records_to_array(records: list, min_count: int = 3) -> np.ndarray | None:
        """Extrait les prix (min/median/max) d'une liste de MarketPrice et retourne un ndarray."""
        prices = []
        for r in records:
            prices.extend([r.price_min, r.price_median, r.price_max])
        ref = np.array([p for p in prices if p], dtype=float)
        return ref if len(ref) >= min_count else None

    @classmethod
    def _collect_market_prices(cls, data: dict[str, Any], min_samples: int) -> np.ndarray | None:
        """Collecte les prix de reference depuis MarketPrice avec filtrage hp_range.

        Cascade de precision :
        1. fuel + hp_range exact
        2. fuel + hp_range=NULL (generique)
        3. fuel + any hp_range
        4. sans fuel + hp_range exact
        5. sans fuel + hp_range=NULL
        6. sans fuel + any hp_range
        """
        from sqlalchemy import func

        from app.models.market_price import MarketPrice
        from app.services.market_service import market_text_key, market_text_key_expr

        make = data.get("make", "")
        model = data.get("model", "")
        year_str = data.get("year_model")
        location = data.get("location") or {}
        region = location.get("region")

        if not (make and model and year_str and region):
            return None

        try:
            int(year_str)
        except (ValueError, TypeError):
            return None

        base_filters = [
            market_text_key_expr(MarketPrice.make) == market_text_key(make),
            market_text_key_expr(MarketPrice.model) == market_text_key(model),
            MarketPrice.sample_count >= min_samples,
        ]

        fuel = (data.get("fuel") or "").strip().lower() or None
        hp = data.get("power_din_hp") or data.get("power_hp") or data.get("horse_power_din")
        hp_range = cls._get_hp_range(int(hp) if hp else None)

        def _query(extra_filters: list) -> list:
            return MarketPrice.query.filter(*base_filters, *extra_filters).all()

        def _try_hp_cascade(extra_filters: list) -> np.ndarray | None:
            """Tente hp_range exact → hp_range=NULL → any hp_range."""
            if hp_range:
                ref = cls._records_to_array(
                    _query([*extra_filters, func.lower(MarketPrice.hp_range) == hp_range.lower()])
                )
                if ref is not None:
                    return ref
            # Fallback hp_range=NULL (generique)
            ref = cls._records_to_array(_query([*extra_filters, MarketPrice.hp_range.is_(None)]))
            if ref is not None:
                return ref
            # Dernier fallback : any hp_range
            return cls._records_to_array(_query(extra_filters))

        # 1. Avec fuel (plus precis)
        if fuel:
            ref = _try_hp_cascade([func.lower(MarketPrice.fuel) == fuel])
            if ref is not None:
                return ref

        # 2. Sans fuel
        return _try_hp_cascade([])

    @staticmethod
    def _collect_argus_prices(vehicle_id: int) -> np.ndarray:
        """Collecte les prix de reference depuis ArgusPrice (seed)."""
        from app.models.argus import ArgusPrice

        argus_records = ArgusPrice.query.filter_by(vehicle_id=vehicle_id).all()
        return np.array([r.price_mid for r in argus_records if r.price_mid], dtype=float)

    def run(self, data: dict[str, Any]) -> FilterResult:
        price = data.get("price_eur")
        mileage = data.get("mileage_km")

        if price is None:
            return self.skip("Prix non disponible pour l'analyse statistique")

        make = data.get("make")
        model = data.get("model")

        if not make or not model:
            return self.skip("Marque ou modèle non disponible")

        # 1. MarketPrice (crowdsource) : pas besoin du referentiel vehicule
        market_ref = self._collect_market_prices(data, self.MARKET_MIN_SAMPLES)
        if market_ref is not None:
            ref_prices = market_ref
            source = "marche_leboncoin"
        else:
            # 2. Fallback ArgusPrice (seed) : necessite le vehicule dans le referentiel
            from app.services.vehicle_lookup import find_vehicle

            vehicle = find_vehicle(make, model)
            if not vehicle:
                return self.skip("Modèle non reconnu — analyse statistique impossible")
            ref_prices = self._collect_argus_prices(vehicle.id)
            source = "argus_seed"

        if len(ref_prices) < 3:
            return self.skip("Pas assez de prix de référence")

        anomalies = []
        z_scores = {}

        # Malus diesel urbain : un diesel en zone agglo dense a des km plus usants
        # Le FAP doit monter a 800°C (>100 km/h, >2500 tr/min, 30 min) pour se regenerer.
        # En ville, ca n'arrive jamais → encrassement FAP, injecteurs, vanne EGR.
        diesel_urban_warning = None
        fuel = (data.get("fuel") or "").lower()
        location = data.get("location") or {}
        region = location.get("region") or ""
        is_diesel = "diesel" in fuel
        agglo_regions = {
            "Île-de-France",
            "Ile-de-France",
            "Auvergne-Rhône-Alpes",
            "Auvergne-Rhone-Alpes",
            "Provence-Alpes-Côte d'Azur",
            "Provence-Alpes-Cote d'Azur",
        }
        is_urban = any(r.lower() in region.lower() for r in agglo_regions)

        if is_diesel and is_urban and mileage is not None and mileage > 30000:
            diesel_urban_warning = (
                "Diesel en zone urbaine dense — usure FAP/injecteurs "
                "potentiellement plus élevée à kilométrage égal"
            )
            anomalies.append(diesel_urban_warning)

        # Z-score du prix
        if price is not None:
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
        hp = data.get("power_din_hp") or data.get("power_hp") or data.get("horse_power_din")
        hp_range_used = self._get_hp_range(int(hp) if hp else None)
        stats = {
            "ref_count": len(ref_prices),
            "ref_mean": round(float(np.mean(ref_prices))),
            "ref_std": round(float(np.std(ref_prices))),
            "ref_median": round(float(np.median(ref_prices))),
            "z_scores": z_scores,
            "anomalies": anomalies,
            "source": source,
            "diesel_urban": diesel_urban_warning is not None,
            "hp_range": hp_range_used,
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
