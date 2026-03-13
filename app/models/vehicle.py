"""Modeles Vehicle et VehicleSpec.

Vehicle est la table centrale du systeme : chaque vehicule connu (marque + modele)
a une fiche ici. VehicleSpec detaille les motorisations possibles avec les specs
techniques et les infos de fiabilite.

Les lookup keys sont des versions normalisees de brand/model pour le matching
flou avec les annonces (pas de casse, pas d'accents, pas de tirets).
Les tokens LBC/AS24 sont appris automatiquement depuis le DOM des annonces
pour construire les URLs de recherche correctes sur chaque site.
"""

from datetime import datetime, timezone

from sqlalchemy import event

from app.extensions import db


class Vehicle(db.Model):
    """Vehicule connu dans la base de reference (144+ modeles, objectif 200+).

    La contrainte d'unicite sur (brand, model) evite les doublons.
    L'index composite sur les lookup keys accelere le matching
    qui est execute a chaque scan (chemin critique).
    """

    __tablename__ = "vehicles"
    __table_args__ = (
        db.UniqueConstraint("brand", "model", name="uq_vehicle_brand_model"),
        db.Index("ix_vehicle_lookup_keys", "brand_lookup_key", "model_lookup_key"),
    )

    id = db.Column(db.Integer, primary_key=True)
    brand = db.Column(db.String(80), nullable=False, index=True)
    model = db.Column(db.String(120), nullable=False, index=True)
    # Cles de recherche normalisees pour le matching flou avec les annonces
    brand_lookup_key = db.Column(db.String(80), nullable=True, index=True)
    model_lookup_key = db.Column(db.String(120), nullable=True, index=True)
    generation = db.Column(db.String(80))
    year_start = db.Column(db.Integer)
    year_end = db.Column(db.Integer)
    enrichment_status = db.Column(
        db.String(20), nullable=False, default="complete", server_default="complete"
    )
    # Override admin : seuil minimum d'annonces pour l'argus (NULL = dynamique auto)
    argus_min_samples = db.Column(db.Integer, nullable=True)
    # Tokens LBC pour les URLs de recherche (auto-appris depuis le DOM des annonces).
    # Necessaire car __NEXT_DATA__ peut renvoyer "Serie 3" sans accent alors que
    # LBC exige "Série 3" dans u_car_model. Stockes une fois, reutilises partout.
    site_brand_token = db.Column(db.String(120), nullable=True)
    site_model_token = db.Column(db.String(200), nullable=True)
    # Slugs AutoScout24 pour les URLs de recherche (auto-appris depuis le RSC).
    # Ex: "vw" pour Volkswagen, "tiguan" pour Tiguan.
    as24_slug_make = db.Column(db.String(80), nullable=True)
    as24_slug_model = db.Column(db.String(80), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    specs = db.relationship("VehicleSpec", backref="vehicle", lazy="select")

    def sync_lookup_keys(self) -> None:
        """Synchronise les lookup keys persistées à partir de la marque/modèle.

        Appele automatiquement avant chaque insert/update via l'event listener.
        Les lookup keys sont recalculees a chaque fois pour rester en phase
        avec les eventuelles corrections de brand/model.
        """
        from app.services.vehicle_lookup import build_vehicle_lookup_keys

        self.brand_lookup_key, self.model_lookup_key = build_vehicle_lookup_keys(
            self.brand or "",
            self.model or "",
        )

    def __repr__(self):
        return f"<Vehicle {self.brand} {self.model}>"


class VehicleSpec(db.Model):
    """Specifications techniques et informations de fiabilite pour un vehicule.

    Chaque VehicleSpec represente une motorisation (fuel + transmission + puissance).
    Un Vehicle peut avoir plusieurs specs (ex: Golf diesel manuelle 115ch,
    Golf essence auto 150ch, etc). Les champs de fiabilite (reliability_rating,
    known_issues, expected_costs) sont remplis manuellement ou via seed.
    """

    __tablename__ = "vehicle_specs"

    id = db.Column(db.Integer, primary_key=True)
    vehicle_id = db.Column(db.Integer, db.ForeignKey("vehicles.id"), nullable=False)
    fuel_type = db.Column(db.String(40))
    transmission = db.Column(db.String(40))
    engine = db.Column(db.String(80))
    power_hp = db.Column(db.Integer)
    body_type = db.Column(db.String(40))
    number_of_seats = db.Column(db.Integer)
    capacity_cm3 = db.Column(db.Integer)
    max_torque_nm = db.Column(db.Integer)
    curb_weight_kg = db.Column(db.Integer)
    length_mm = db.Column(db.Integer)
    width_mm = db.Column(db.Integer)
    height_mm = db.Column(db.Integer)
    mixed_consumption_l100km = db.Column(db.Float)
    co2_emissions_gkm = db.Column(db.Integer)
    acceleration_0_100s = db.Column(db.Float)
    max_speed_kmh = db.Column(db.Integer)
    reliability_rating = db.Column(db.Float)
    known_issues = db.Column(db.Text)
    expected_costs = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<VehicleSpec {self.vehicle_id} {self.fuel_type}>"


# Hook SQLAlchemy pour recalculer les lookup keys a chaque modification de Vehicle.
# Sans ca, un changement de brand/model via le dashboard admin ne serait pas
# repercute dans les lookup keys et le matching serait casse.
@event.listens_for(Vehicle, "before_insert")
@event.listens_for(Vehicle, "before_update")
def _sync_vehicle_lookup_keys(_mapper, _connection, target: Vehicle) -> None:
    """Maintient les lookup keys persistées à jour."""
    target.sync_lookup_keys()
