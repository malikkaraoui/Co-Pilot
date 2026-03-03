"""Tests pour le service de motorisations observees -- tracking + promotion."""

import json

import pytest

from app.extensions import db
from app.models.observed_motorization import ObservedMotorization
from app.models.vehicle import Vehicle, VehicleSpec
from app.services.motorization_service import (
    PROMOTION_THRESHOLD,
    _ad_hash,
    build_engine_name,
    capitalize_fuel,
    capitalize_transmission,
    enrich_observed_motorizations,
)


@pytest.fixture()
def _test_vehicle(app):
    """Cree un vehicule de test unique et nettoie les motorisations avant chaque test."""
    with app.app_context():
        v = Vehicle.query.filter_by(brand="TestMoto", model="Phantom").first()
        if not v:
            v = Vehicle(
                brand="TestMoto",
                model="Phantom",
                year_start=2020,
                enrichment_status="partial",
            )
            db.session.add(v)
            db.session.commit()
        else:
            # Reset enrichment_status pour les tests qui le verifient
            v.enrichment_status = "partial"
            db.session.commit()

        # Nettoyer les motorisations et specs de test precedents
        ObservedMotorization.query.filter_by(vehicle_id=v.id).delete()
        VehicleSpec.query.filter_by(vehicle_id=v.id).delete()
        db.session.commit()
        return v.id


def _make_detail(
    price=15000, year=2020, km=80000, fuel="diesel", gearbox="manuelle", hp=130, seats=5
):
    """Helper pour creer un detail d'annonce."""
    return {
        "price": price,
        "year": year,
        "km": km,
        "fuel": fuel,
        "gearbox": gearbox,
        "horse_power": hp,
        "seats": seats,
    }


class TestHelpers:
    """Tests des fonctions utilitaires."""

    def test_capitalize_fuel(self):
        assert capitalize_fuel("essence") == "Essence"
        assert capitalize_fuel("diesel") == "Diesel"
        assert capitalize_fuel("hybride rechargeable") == "Hybride rechargeable"
        assert capitalize_fuel("electrique") == "Electrique"
        assert capitalize_fuel("électrique") == "Electrique"
        assert capitalize_fuel("gpl") == "GPL"

    def test_capitalize_transmission(self):
        assert capitalize_transmission("manuelle") == "Manuelle"
        assert capitalize_transmission("automatique") == "Automatique"
        assert capitalize_transmission("manual") == "Manuelle"
        assert capitalize_transmission("automatic") == "Automatique"

    def test_build_engine_name(self):
        assert build_engine_name("diesel", "manuelle", 130) == "Diesel 130ch Manuelle"
        assert (
            build_engine_name("hybride rechargeable", "automatique", 225)
            == "Hybride rechargeable 225ch Automatique"
        )
        assert build_engine_name("essence", "automatique", 110) == "Essence 110ch Automatique"

    def test_ad_hash_deterministic(self):
        d = {"price": 15000, "year": 2020, "km": 80000}
        assert _ad_hash(d) == _ad_hash(d)
        assert len(_ad_hash(d)) == 12

    def test_ad_hash_different_ads(self):
        d1 = {"price": 15000, "year": 2020, "km": 80000}
        d2 = {"price": 16000, "year": 2020, "km": 75000}
        assert _ad_hash(d1) != _ad_hash(d2)


class TestEnrichObservedMotorizations:
    """Tests de l'enrichissement des motorisations observees."""

    @pytest.mark.usefixtures("_test_vehicle")
    def test_creates_motorization_from_complete_detail(self, app, _test_vehicle):
        """Un detail complet (fuel+gearbox+hp) cree un ObservedMotorization."""
        vid = _test_vehicle
        with app.app_context():
            enrich_observed_motorizations(vid, [_make_detail()])
            moto = ObservedMotorization.query.filter_by(
                vehicle_id=vid, fuel="diesel", transmission="manuelle", power_din_hp=130
            ).first()
            assert moto is not None
            assert moto.count == 1
            assert moto.distinct_sources == 1
            assert moto.seats == 5
            assert not moto.promoted

    @pytest.mark.usefixtures("_test_vehicle")
    def test_skips_incomplete_details(self, app, _test_vehicle):
        """Details sans fuel ou sans gearbox sont ignores."""
        vid = _test_vehicle
        with app.app_context():
            # Sans gearbox
            enrich_observed_motorizations(vid, [{"fuel": "diesel", "horse_power": 130, "price": 1}])
            # Sans fuel
            enrich_observed_motorizations(
                vid, [{"gearbox": "auto", "horse_power": 130, "price": 2}]
            )
            # Sans hp
            enrich_observed_motorizations(vid, [{"fuel": "diesel", "gearbox": "auto", "price": 3}])
            count = ObservedMotorization.query.filter_by(vehicle_id=vid).count()
            assert count == 0

    @pytest.mark.usefixtures("_test_vehicle")
    def test_increments_count_on_repeat(self, app, _test_vehicle):
        """Deuxieme collecte incremente count et distinct_sources."""
        vid = _test_vehicle
        with app.app_context():
            enrich_observed_motorizations(vid, [_make_detail(price=15000, km=80000)])
            enrich_observed_motorizations(vid, [_make_detail(price=16000, km=70000)])

            moto = ObservedMotorization.query.filter_by(
                vehicle_id=vid, fuel="diesel", transmission="manuelle", power_din_hp=130
            ).first()
            assert moto.count == 2
            assert moto.distinct_sources == 2

    @pytest.mark.usefixtures("_test_vehicle")
    def test_deduplicates_same_ad(self, app, _test_vehicle):
        """Meme annonce (meme hash) ne compte qu'une fois dans distinct_sources."""
        vid = _test_vehicle
        with app.app_context():
            same_ad = _make_detail(price=15000, year=2020, km=80000)
            # Envoyer la meme annonce 2 fois
            enrich_observed_motorizations(vid, [same_ad])
            enrich_observed_motorizations(vid, [same_ad])

            moto = ObservedMotorization.query.filter_by(
                vehicle_id=vid, fuel="diesel", transmission="manuelle", power_din_hp=130
            ).first()
            assert moto.count == 2  # Total occurrences
            assert moto.distinct_sources == 1  # Mais une seule source unique

    @pytest.mark.usefixtures("_test_vehicle")
    def test_promotes_at_threshold(self, app, _test_vehicle):
        """A PROMOTION_THRESHOLD sources distinctes, cree un VehicleSpec."""
        vid = _test_vehicle
        with app.app_context():
            # Envoyer N annonces distinctes
            for i in range(PROMOTION_THRESHOLD):
                enrich_observed_motorizations(
                    vid, [_make_detail(price=15000 + i * 1000, km=80000 - i * 5000)]
                )

            moto = ObservedMotorization.query.filter_by(
                vehicle_id=vid, fuel="diesel", transmission="manuelle", power_din_hp=130
            ).first()
            assert moto.promoted is True
            assert moto.promoted_at is not None

            # Verifier le VehicleSpec cree
            spec = VehicleSpec.query.filter_by(
                vehicle_id=vid,
                fuel_type="Diesel",
                transmission="Manuelle",
                power_hp=130,
            ).first()
            assert spec is not None
            assert spec.engine == "Diesel 130ch Manuelle"
            assert spec.number_of_seats == 5

    @pytest.mark.usefixtures("_test_vehicle")
    def test_no_duplicate_vehiclespec(self, app, _test_vehicle):
        """Ne cree pas de doublon VehicleSpec si deja promu."""
        vid = _test_vehicle
        with app.app_context():
            # Promouvoir
            for i in range(PROMOTION_THRESHOLD):
                enrich_observed_motorizations(
                    vid, [_make_detail(price=20000 + i * 1000, km=60000 - i * 5000)]
                )

            spec_count_after = VehicleSpec.query.filter_by(
                vehicle_id=vid,
                fuel_type="Diesel",
                transmission="Manuelle",
                power_hp=130,
            ).count()
            assert spec_count_after == 1

            # Envoyer plus de donnees — pas de nouveau spec
            enrich_observed_motorizations(vid, [_make_detail(price=30000, km=10000)])
            spec_count_still = VehicleSpec.query.filter_by(
                vehicle_id=vid,
                fuel_type="Diesel",
                transmission="Manuelle",
                power_hp=130,
            ).count()
            assert spec_count_still == 1

    @pytest.mark.usefixtures("_test_vehicle")
    def test_updates_enrichment_status(self, app, _test_vehicle):
        """Apres promotion, enrichment_status passe a 'complete'."""
        vid = _test_vehicle
        with app.app_context():
            vehicle = db.session.get(Vehicle, vid)
            assert vehicle.enrichment_status == "partial"

            for i in range(PROMOTION_THRESHOLD):
                enrich_observed_motorizations(
                    vid, [_make_detail(price=25000 + i * 1000, km=50000 - i * 5000)]
                )

            db.session.refresh(vehicle)
            assert vehicle.enrichment_status == "complete"

    @pytest.mark.usefixtures("_test_vehicle")
    def test_multiple_motorizations(self, app, _test_vehicle):
        """Deux motorisations differentes creent deux ObservedMotorization."""
        vid = _test_vehicle
        with app.app_context():
            enrich_observed_motorizations(
                vid,
                [
                    _make_detail(fuel="diesel", gearbox="manuelle", hp=130, price=15000, km=80000),
                    _make_detail(
                        fuel="essence", gearbox="automatique", hp=150, price=18000, km=60000
                    ),
                ],
            )
            count = ObservedMotorization.query.filter_by(vehicle_id=vid).count()
            assert count == 2

    @pytest.mark.usefixtures("_test_vehicle")
    def test_batch_same_combo(self, app, _test_vehicle):
        """Un batch avec 3 annonces identiques en combo mais prix/km differents."""
        vid = _test_vehicle
        with app.app_context():
            details = [
                _make_detail(price=15000, km=80000),
                _make_detail(price=16000, km=75000),
                _make_detail(price=17000, km=70000),
            ]
            promoted = enrich_observed_motorizations(vid, details)

            moto = ObservedMotorization.query.filter_by(
                vehicle_id=vid, fuel="diesel", transmission="manuelle", power_din_hp=130
            ).first()
            assert moto.count == 3
            assert moto.distinct_sources == 3
            # 3 sources distinctes = seuil atteint
            assert moto.promoted is True
            assert len(promoted) == 1

    @pytest.mark.usefixtures("_test_vehicle")
    def test_source_ids_stored_as_json(self, app, _test_vehicle):
        """source_ids est un JSON array valide."""
        vid = _test_vehicle
        with app.app_context():
            enrich_observed_motorizations(vid, [_make_detail()])
            moto = ObservedMotorization.query.filter_by(vehicle_id=vid).first()
            hashes = json.loads(moto.source_ids)
            assert isinstance(hashes, list)
            assert len(hashes) == 1
