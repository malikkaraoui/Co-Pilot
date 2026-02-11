"""Tests pour le service de lookup vehicule (Story 3.2)."""

from app.extensions import db
from app.models.vehicle import Vehicle
from app.services.vehicle_lookup import (
    _normalize_brand,
    _normalize_model,
    find_vehicle,
)


class TestNormalization:
    """Tests unitaires pour la normalisation des noms."""

    def test_brand_alias_vw(self):
        assert _normalize_brand("VW") == "volkswagen"

    def test_brand_alias_citroen_accent(self):
        assert _normalize_brand("Citroën") == "citroen"

    def test_brand_passthrough(self):
        assert _normalize_brand("Peugeot") == "peugeot"

    def test_brand_strips_whitespace(self):
        assert _normalize_brand("  Toyota  ") == "toyota"

    def test_model_alias_clio_5(self):
        assert _normalize_model("Clio 5") == "clio v"

    def test_model_alias_golf_vii(self):
        assert _normalize_model("Golf VII") == "golf"

    def test_model_alias_chr(self):
        assert _normalize_model("CHR") == "c-hr"

    def test_model_passthrough(self):
        assert _normalize_model("3008") == "3008"


class TestFindVehicle:
    """Tests d'integration avec la base de donnees."""

    def _seed_vehicles(self):
        """Insere quelques vehicules de test."""
        vehicles = [
            Vehicle(brand="Peugeot", model="3008", generation="II"),
            Vehicle(brand="Renault", model="Clio V", generation="V"),
            Vehicle(brand="Volkswagen", model="Golf", generation="VII/VIII"),
            Vehicle(brand="Toyota", model="C-HR", generation="I/II"),
            Vehicle(brand="BMW", model="Serie 3", generation="G20"),
        ]
        for v in vehicles:
            db.session.add(v)
        db.session.commit()

    def test_exact_match(self, app):
        """Recherche exacte par marque et modele."""
        with app.app_context():
            self._seed_vehicles()
            result = find_vehicle("Peugeot", "3008")
            assert result is not None
            assert result.brand == "Peugeot"
            assert result.model == "3008"

    def test_case_insensitive(self, app):
        """La recherche est insensible a la casse."""
        with app.app_context():
            self._seed_vehicles()
            result = find_vehicle("peugeot", "3008")
            assert result is not None
            assert result.brand == "Peugeot"

    def test_brand_alias_vw(self, app):
        """L'alias 'VW' trouve 'Volkswagen'."""
        with app.app_context():
            self._seed_vehicles()
            result = find_vehicle("VW", "Golf")
            assert result is not None
            assert result.brand == "Volkswagen"

    def test_model_alias_clio_5(self, app):
        """L'alias 'Clio 5' trouve 'Clio V'."""
        with app.app_context():
            self._seed_vehicles()
            result = find_vehicle("Renault", "Clio 5")
            assert result is not None
            assert "Clio" in result.model

    def test_model_alias_chr(self, app):
        """L'alias 'CHR' trouve 'C-HR'."""
        with app.app_context():
            self._seed_vehicles()
            result = find_vehicle("Toyota", "CHR")
            assert result is not None
            assert result.model == "C-HR"

    def test_not_found(self, app):
        """Un vehicule inexistant retourne None."""
        with app.app_context():
            self._seed_vehicles()
            result = find_vehicle("Tesla", "Model 3")
            assert result is None

    def test_unknown_brand_returns_none(self, app):
        """Une marque inconnue retourne None meme avec des donnees en base."""
        with app.app_context():
            self._seed_vehicles()
            result = find_vehicle("Lamborghini", "Urus")
            assert result is None
