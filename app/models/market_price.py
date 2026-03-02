"""Modele MarketPrice -- cache des prix du marche collectes par crowdsourcing."""

import json
from datetime import datetime, timezone

from app.extensions import db


class MarketPrice(db.Model):
    """Prix du marche collectes depuis les annonces LeBonCoin par les utilisateurs de l'extension."""

    __tablename__ = "market_prices"

    id = db.Column(db.Integer, primary_key=True)
    make = db.Column(db.String(80), nullable=False, index=True)
    model = db.Column(db.String(80), nullable=False, index=True)
    year = db.Column(db.Integer, nullable=False)
    region = db.Column(db.String(80), nullable=False)
    fuel = db.Column(db.String(30), nullable=True)  # essence, diesel, electrique, hybride
    country = db.Column(db.String(5), nullable=True, default="FR")  # ISO 2 lettres (FR, CH, DE...)

    price_min = db.Column(db.Integer)
    price_median = db.Column(db.Integer)
    price_mean = db.Column(db.Integer)
    price_max = db.Column(db.Integer)
    price_std = db.Column(db.Float)

    # IQR Mean (moyenne interquartile) : moyenne des prix entre Q1 et Q3 (50% central).
    # Estimateur plus robuste que la mediane (sensible aux variations reelles)
    # et que la moyenne (resistante aux outliers). Utilise comme prix de reference L4.
    price_iqr_mean = db.Column(db.Integer, nullable=True)
    # Percentiles P25 (bonne affaire) et P75 (cher) pour fourchette de prix
    price_p25 = db.Column(db.Integer, nullable=True)
    price_p75 = db.Column(db.Integer, nullable=True)

    sample_count = db.Column(db.Integer, default=0)

    # Precision de la collecte (1 a 5) : 5=geo+filtres complets, 1=national+filtres minimaux
    precision = db.Column(db.Integer, nullable=True)

    # Tranche de puissance DIN (ex: "120-150") pour distinguer les motorisations
    hp_range = db.Column(db.String(20), nullable=True)
    # Chevaux fiscaux (puissance administrative)
    fiscal_hp = db.Column(db.Integer, nullable=True)

    # Estimation LBC (fourchette basse/haute affichee par LeBonCoin)
    lbc_estimate_low = db.Column(db.Integer, nullable=True)
    lbc_estimate_high = db.Column(db.Integer, nullable=True)

    # Details du calcul (JSON) pour transparence dans le dashboard
    # Format: {"raw_prices": [...], "kept_prices": [...], "excluded_prices": [...],
    #          "iqr_low": N, "iqr_high": N, "method": "iqr"}
    calculation_details = db.Column(db.Text, nullable=True)

    collected_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    refresh_after = db.Column(db.DateTime, nullable=False)

    __table_args__ = (
        db.UniqueConstraint(
            "make",
            "model",
            "year",
            "region",
            "fuel",
            "hp_range",
            "country",
            name="uq_market_price_vehicle_region_fuel_hp_country",
        ),
    )

    def get_calculation_details(self) -> dict | None:
        """Retourne les details du calcul en dict, ou None."""
        if not self.calculation_details:
            return None
        return json.loads(self.calculation_details)

    def __repr__(self):
        return f"<MarketPrice {self.make} {self.model} {self.year} {self.region}>"
