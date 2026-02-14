"""Tests pour le service argus (Story 3.4)."""

from app.extensions import db
from app.models.argus import ArgusPrice
from app.models.vehicle import Vehicle
from app.services.argus import get_argus_price


class TestGetArgusPrice:
    """Tests pour la recuperation des prix argus geolocalisees."""

    def _seed(self):
        """Insere un vehicule avec des donnees argus dans 2 regions."""
        v = Vehicle.query.filter_by(brand="Peugeot", model="208").first()
        if not v:
            v = Vehicle(brand="Peugeot", model="208", generation="II")
            db.session.add(v)
            db.session.flush()
        a1 = ArgusPrice(
            vehicle_id=v.id,
            region="Ile-de-France",
            year=2021,
            mileage_bracket="20000-50000",
            price_low=13000,
            price_mid=15500,
            price_high=18000,
            source="seed_test",
        )
        a2 = ArgusPrice(
            vehicle_id=v.id,
            region="Auvergne-Rhone-Alpes",
            year=2021,
            mileage_bracket="20000-50000",
            price_low=12500,
            price_mid=15000,
            price_high=17500,
            source="seed_test",
        )
        db.session.add_all([a1, a2])
        db.session.commit()
        return v

    def test_found(self, app):
        """Argus trouve pour une region et annee existantes."""
        with app.app_context():
            v = self._seed()
            result = get_argus_price(v.id, "Ile-de-France", 2021)
            assert result is not None
            assert result.price_mid == 15500
            assert result.price_low == 13000
            assert result.price_high == 18000

    def test_different_region(self, app):
        """Argus dans une autre region retourne des prix differents."""
        with app.app_context():
            v = self._seed()
            result = get_argus_price(v.id, "Auvergne-Rhone-Alpes", 2021)
            assert result is not None
            assert result.price_mid == 15000

    def test_not_found_wrong_year(self, app):
        """Pas de donnees pour cette annee -- retourne None."""
        with app.app_context():
            v = self._seed()
            result = get_argus_price(v.id, "Ile-de-France", 2025)
            assert result is None

    def test_not_found_wrong_region(self, app):
        """Pas de donnees pour cette region -- retourne None."""
        with app.app_context():
            v = self._seed()
            result = get_argus_price(v.id, "Bretagne", 2021)
            assert result is None

    def test_not_found_wrong_vehicle(self, app):
        """Vehicle inexistant -- retourne None."""
        with app.app_context():
            result = get_argus_price(9999, "Ile-de-France", 2021)
            assert result is None
