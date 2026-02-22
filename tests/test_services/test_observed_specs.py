"""Tests for VehicleObservedSpec enrichment from market data."""

from app.extensions import db
from app.models.vehicle import Vehicle
from app.models.vehicle_observed_spec import VehicleObservedSpec
from app.services.market_service import store_market_prices


class TestObservedSpecEnrichment:
    def test_enriches_specs_from_price_details(self, app):
        with app.app_context():
            # Use a vehicle not in CSV to avoid auto_create_vehicle interference
            vehicle = Vehicle.query.filter_by(brand="Jeep", model="Renegade").first()
            if not vehicle:
                vehicle = Vehicle(
                    brand="Jeep",
                    model="Renegade",
                    year_start=2018,
                    year_end=2024,
                    enrichment_status="partial",
                )
                db.session.add(vehicle)
                db.session.commit()

            store_market_prices(
                make="Jeep",
                model="Renegade",
                year=2020,
                region="Île-de-France",
                prices=[14000, 15000, 16000, 17000, 18000],
                price_details=[
                    {
                        "price": 14000,
                        "year": 2020,
                        "km": 80000,
                        "fuel": "hybride rechargeable",
                        "gearbox": "automatique",
                        "horse_power": 190,
                    },
                    {
                        "price": 15000,
                        "year": 2020,
                        "km": 70000,
                        "fuel": "diesel",
                        "gearbox": "manuelle",
                        "horse_power": 130,
                    },
                    {
                        "price": 16000,
                        "year": 2020,
                        "km": 60000,
                        "fuel": "hybride rechargeable",
                        "gearbox": "automatique",
                        "horse_power": 190,
                    },
                    {
                        "price": 17000,
                        "year": 2020,
                        "km": 50000,
                        "fuel": "diesel",
                        "gearbox": "manuelle",
                        "horse_power": 130,
                    },
                    {"price": 18000, "year": 2020, "km": 40000, "fuel": "essence"},
                ],
            )

            specs = VehicleObservedSpec.query.filter_by(vehicle_id=vehicle.id).all()
            spec_map = {(s.spec_type, s.spec_value): s.count for s in specs}

            assert ("fuel", "hybride rechargeable") in spec_map
            assert spec_map[("fuel", "hybride rechargeable")] == 2
            assert ("fuel", "diesel") in spec_map
            assert ("gearbox", "automatique") in spec_map
            assert ("horse_power", "190") in spec_map

    def test_no_enrichment_without_vehicle(self, app):
        """If vehicle not in referential, no observed specs created."""
        with app.app_context():
            count_before = VehicleObservedSpec.query.count()
            store_market_prices(
                make="UnknownBrandXYZ",
                model="FakeCarABC",
                year=2020,
                region="Bretagne",
                prices=[10000, 11000, 12000, 13000, 14000],
                price_details=[
                    {"price": 10000, "fuel": "diesel"},
                    {"price": 11000, "fuel": "diesel"},
                    {"price": 12000, "fuel": "diesel"},
                    {"price": 13000, "fuel": "diesel"},
                    {"price": 14000, "fuel": "diesel"},
                ],
            )
            # No new specs should have been created
            assert VehicleObservedSpec.query.count() == count_before

    def test_increments_count_on_second_collection(self, app):
        """Collecting again should increment existing spec counts, not duplicate."""
        with app.app_context():
            # Use a unique brand to avoid pollution from other tests
            vehicle = Vehicle.query.filter_by(brand="Maserati", model="Levante").first()
            if not vehicle:
                vehicle = Vehicle(
                    brand="Maserati",
                    model="Levante",
                    year_start=2016,
                    year_end=2024,
                    enrichment_status="partial",
                )
                db.session.add(vehicle)
                db.session.commit()

            # First collection: 5 diesel
            store_market_prices(
                make="Maserati",
                model="Levante",
                year=2020,
                region="Île-de-France",
                prices=[34000, 35000, 36000, 37000, 38000],
                price_details=[
                    {"price": 34000, "fuel": "diesel", "gearbox": "automatique"},
                    {"price": 35000, "fuel": "diesel", "gearbox": "automatique"},
                    {"price": 36000, "fuel": "diesel", "gearbox": "automatique"},
                    {"price": 37000, "fuel": "diesel", "gearbox": "automatique"},
                    {"price": 38000, "fuel": "diesel", "gearbox": "automatique"},
                ],
            )

            diesel_after_first = VehicleObservedSpec.query.filter_by(
                vehicle_id=vehicle.id, spec_type="fuel", spec_value="diesel"
            ).first()
            assert diesel_after_first is not None
            assert diesel_after_first.count == 5

            # Second collection: 4 diesel + 1 essence
            store_market_prices(
                make="Maserati",
                model="Levante",
                year=2020,
                region="Bretagne",
                prices=[34500, 35500, 36500, 37500, 38500],
                price_details=[
                    {"price": 34500, "fuel": "diesel", "gearbox": "automatique"},
                    {"price": 35500, "fuel": "diesel", "gearbox": "automatique"},
                    {"price": 36500, "fuel": "diesel", "gearbox": "automatique"},
                    {"price": 37500, "fuel": "diesel", "gearbox": "automatique"},
                    {"price": 38500, "fuel": "essence", "gearbox": "manuelle"},
                ],
            )

            diesel_spec = VehicleObservedSpec.query.filter_by(
                vehicle_id=vehicle.id, spec_type="fuel", spec_value="diesel"
            ).first()
            assert diesel_spec is not None
            assert diesel_spec.count == 9  # 5 + 4

            essence_spec = VehicleObservedSpec.query.filter_by(
                vehicle_id=vehicle.id, spec_type="fuel", spec_value="essence"
            ).first()
            assert essence_spec is not None
            assert essence_spec.count == 1
