"""Tests for Vehicle and VehicleSpec models."""

from app.models.vehicle import Vehicle, VehicleSpec


def test_create_vehicle(db):
    v = Vehicle(brand="Peugeot", model="3008", year_start=2016, year_end=2023)
    db.session.add(v)
    db.session.commit()

    saved = Vehicle.query.filter_by(brand="Peugeot", model="3008").first()
    assert saved is not None
    assert saved.brand == "Peugeot"
    assert saved.model == "3008"


def test_vehicle_spec_relationship(db):
    v = Vehicle(brand="Renault", model="Clio V", year_start=2019)
    db.session.add(v)
    db.session.flush()

    spec = VehicleSpec(
        vehicle_id=v.id,
        fuel_type="Essence",
        transmission="Manuelle",
        power_hp=100,
    )
    db.session.add(spec)
    db.session.commit()

    assert len(v.specs) == 1
    assert v.specs[0].fuel_type == "Essence"
