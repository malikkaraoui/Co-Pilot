"""Tests pour le service de fiches modele (Story 3.3)."""

from app.extensions import db
from app.models.vehicle import Vehicle, VehicleSpec
from app.services.vehicle_specs import get_vehicle_fiche, get_vehicle_specs


class TestGetVehicleSpecs:
    """Tests pour la recuperation des specs par vehicle_id."""

    def _seed(self):
        """Insere un vehicule avec deux specs."""
        v = Vehicle(brand="Peugeot", model="208", generation="II")
        db.session.add(v)
        db.session.flush()
        s1 = VehicleSpec(
            vehicle_id=v.id,
            fuel_type="Essence",
            engine="1.2 PureTech",
            power_hp=100,
            reliability_rating=4.0,
            known_issues="Courroie distribution",
            expected_costs="600 EUR",
        )
        s2 = VehicleSpec(
            vehicle_id=v.id,
            fuel_type="Diesel",
            engine="1.5 BlueHDi",
            power_hp=100,
            reliability_rating=4.2,
            known_issues="FAP",
            expected_costs="800 EUR",
        )
        db.session.add_all([s1, s2])
        db.session.commit()
        return v

    def test_returns_all_specs(self, app):
        with app.app_context():
            v = self._seed()
            specs = get_vehicle_specs(v.id)
            assert len(specs) == 2

    def test_filter_by_fuel(self, app):
        with app.app_context():
            v = self._seed()
            specs = get_vehicle_specs(v.id, fuel_type="Essence")
            assert len(specs) == 1
            assert specs[0].fuel_type == "Essence"

    def test_empty_result(self, app):
        with app.app_context():
            specs = get_vehicle_specs(9999)
            assert specs == []


class TestGetVehicleFiche:
    """Tests pour la fiche complete (vehicule + specs)."""

    def _seed(self):
        # Utiliser un vehicule absent des seeds pour eviter les conflits
        v = Vehicle(brand="Volvo", model="XC40", generation="I")
        db.session.add(v)
        db.session.flush()
        s = VehicleSpec(
            vehicle_id=v.id,
            fuel_type="Hybride",
            engine="1.5 T5 Recharge",
            power_hp=262,
            reliability_rating=4.8,
            known_issues="Quasi aucun probleme",
            expected_costs="200 EUR/an",
        )
        db.session.add(s)
        db.session.commit()
        return v

    def test_fiche_complete(self, app):
        with app.app_context():
            self._seed()
            fiche = get_vehicle_fiche("Volvo", "XC40")
            assert fiche is not None
            assert fiche["vehicle"]["brand"] == "Volvo"
            assert fiche["vehicle"]["model"] == "XC40"
            assert len(fiche["specs"]) >= 1
            spec = fiche["specs"][0]
            assert spec["reliability_rating"] == 4.8
            assert "Quasi aucun probleme" in spec["known_issues"]
            assert spec["expected_costs"] == "200 EUR/an"

    def test_fiche_not_found(self, app):
        with app.app_context():
            fiche = get_vehicle_fiche("Tesla", "Model 3")
            assert fiche is None

    def test_fiche_without_specs(self, app):
        """Vehicule existe mais pas de specs -- retourne fiche avec liste vide."""
        with app.app_context():
            v = Vehicle(brand="Alfa Romeo", model="Giulia")
            db.session.add(v)
            db.session.commit()
            fiche = get_vehicle_fiche("Alfa Romeo", "Giulia")
            assert fiche is not None
            assert fiche["specs"] == []
