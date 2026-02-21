"""Tests pour le service de lookup vehicule (Story 3.2)."""

from app.extensions import db
from app.models.vehicle import Vehicle
from app.services.vehicle_lookup import (
    GENERIC_MODELS,
    _normalize_brand,
    _normalize_model,
    display_brand,
    display_model,
    find_vehicle,
    is_generic_model,
    normalize_brand,
    normalize_model,
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

    # Aliases nouvelles marques
    def test_brand_ds(self):
        assert _normalize_brand("DS") == "ds"

    def test_brand_ds_automobiles(self):
        assert _normalize_brand("DS Automobiles") == "ds"

    def test_brand_land_rover_hyphen(self):
        assert _normalize_brand("Land-Rover") == "land rover"

    def test_brand_landrover(self):
        assert _normalize_brand("LandRover") == "land rover"

    def test_brand_land_rover_space(self):
        assert _normalize_brand("Land Rover") == "land rover"

    def test_brand_honda(self):
        assert _normalize_brand("Honda") == "honda"

    def test_brand_porsche(self):
        assert _normalize_brand("Porsche") == "porsche"

    # Aliases DS modeles
    def test_model_ds3(self):
        assert _normalize_model("DS 3") == "3"

    def test_model_ds7_crossback(self):
        assert _normalize_model("DS 7 Crossback") == "7 crossback"

    # Generiques
    def test_generic_divers(self):
        assert is_generic_model("Divers")

    def test_generic_autres(self):
        assert is_generic_model("Autres")

    def test_not_generic(self):
        assert not is_generic_model("Civic")

    def test_generic_models_has_divers(self):
        assert "divers" in GENERIC_MODELS


class TestDisplayBrand:
    """Tests pour la forme d'affichage canonique des marques."""

    def test_land_rover_hyphen(self):
        assert display_brand("Land-Rover") == "Land Rover"

    def test_land_rover_space(self):
        assert display_brand("Land Rover") == "Land Rover"

    def test_bmw(self):
        assert display_brand("BMW") == "BMW"

    def test_bmw_lowercase(self):
        assert display_brand("bmw") == "BMW"

    def test_kia(self):
        assert display_brand("kia") == "Kia"

    def test_kia_uppercase(self):
        assert display_brand("KIA") == "Kia"

    def test_peugeot_uppercase(self):
        assert display_brand("PEUGEOT") == "Peugeot"

    def test_vw_alias(self):
        assert display_brand("VW") == "Volkswagen"

    def test_mercedes_benz(self):
        assert display_brand("Mercedes-Benz") == "Mercedes"

    def test_alfa_romeo(self):
        assert display_brand("alfa-romeo") == "Alfa Romeo"


class TestDisplayModel:
    """Tests pour la forme d'affichage canonique des modeles."""

    def test_transit_lowercase(self):
        assert display_model("transit") == "Transit"

    def test_transit_uppercase(self):
        assert display_model("TRANSIT") == "Transit"

    def test_fourgon_to_transit(self):
        assert display_model("fourgon") == "Transit"

    def test_transit_connect(self):
        assert display_model("Transit Connect") == "Transit Connect"

    def test_chr(self):
        assert display_model("chr") == "C-HR"

    def test_id3(self):
        assert display_model("id3") == "ID.3"

    def test_rav4(self):
        assert display_model("rav4") == "RAV4"

    def test_cla(self):
        assert display_model("cla") == "CLA"

    def test_clio_5(self):
        assert display_model("Clio 5") == "Clio V"

    def test_range_rover_velar(self):
        assert display_model("Range Rover Velar") == "Range Rover Velar"

    def test_simple_model_title(self):
        assert display_model("sandero") == "Sandero"


class TestNormalizePublicAPI:
    """Verifie que normalize_brand/normalize_model sont bien publiques."""

    def test_normalize_brand_is_same(self):
        assert normalize_brand("VW") == _normalize_brand("VW")

    def test_normalize_model_is_same(self):
        assert normalize_model("Clio 5") == _normalize_model("Clio 5")


class TestFindVehicle:
    """Tests d'integration avec la base de donnees."""

    def _seed_vehicles(self):
        """Insere quelques vehicules de test (lookup-or-create pour eviter les doublons)."""
        specs = [
            ("Peugeot", "3008", "II"),
            ("Renault", "Clio V", "V"),
            ("Volkswagen", "Golf", "VII/VIII"),
            ("Toyota", "C-HR", "I/II"),
            ("BMW", "Serie 3", "G20"),
        ]
        for brand, model, gen in specs:
            existing = Vehicle.query.filter_by(brand=brand, model=model).first()
            if not existing:
                db.session.add(Vehicle(brand=brand, model=model, generation=gen))
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

    def test_quickadd_display_brand_matches_find_vehicle(self, app):
        """Un vehicule ajoute via display_brand() est retrouve par find_vehicle()."""
        with app.app_context():
            brand_clean = display_brand("Land-Rover")
            model_clean = display_model("Defender")
            v = Vehicle(brand=brand_clean, model=model_clean)
            db.session.add(v)
            db.session.commit()
            assert find_vehicle("Land-Rover", "Defender") is not None
            assert find_vehicle("LAND-ROVER", "defender") is not None
            assert find_vehicle("Land Rover", "Defender") is not None
