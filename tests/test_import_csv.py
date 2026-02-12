"""Tests du script d'import CSV Kaggle."""

import csv
import tempfile
from pathlib import Path
from unittest.mock import patch

from app.models.vehicle import Vehicle, VehicleSpec

SAMPLE_CSV_ROWS = [
    {
        "id_trim": "1",
        "Make": "Peugeot",
        "Modle": "208",
        "Generation": "1 generation",
        "Year_from": "2012",
        "Year_to": "2019",
        "Series": "Hatchback 5-doors",
        "Trim": "1.2 VTi 82 MT",
        "Body_type": "Hatchback",
        "number_of_seats": "5",
        "length_mm": "3962",
        "width_mm": "1739",
        "height_mm": "1460",
        "curb_weight_kg": "1050",
        "capacity_cm3": "1199",
        "engine_hp": "82",
        "engine_type": "Gasoline",
        "transmission": "Manual",
        "maximum_torque_n_m": "118",
        "mixed_fuel_consumption_per_100_km_l": "5.2",
        "CO2_emissions_g/km": "104",
        "acceleration_0_100_km/h_s": "13.2",
        "max_speed_km_per_h": "175",
    },
    {
        "id_trim": "2",
        "Make": "Renault",
        "Modle": "Clio",
        "Generation": "4 generation",
        "Year_from": "2012",
        "Year_to": "2019",
        "Series": "Hatchback 5-doors",
        "Trim": "1.5 dCi 90 MT",
        "Body_type": "Hatchback",
        "number_of_seats": "5",
        "length_mm": "4062",
        "width_mm": "1732",
        "height_mm": "1448",
        "curb_weight_kg": "1150",
        "capacity_cm3": "1461",
        "engine_hp": "90",
        "engine_type": "Diesel",
        "transmission": "Automatic",
        "maximum_torque_n_m": "220",
        "mixed_fuel_consumption_per_100_km_l": "3.6",
        "CO2_emissions_g/km": "83",
        "acceleration_0_100_km/h_s": "12.1",
        "max_speed_km_per_h": "182",
    },
    {
        "id_trim": "3",
        "Make": "Lamborghini",
        "Modle": "Aventador",
        "Generation": "1 generation",
        "Year_from": "2011",
        "Year_to": "2022",
        "Series": "Coupe",
        "Trim": "LP 700-4",
        "Body_type": "Coupe",
        "number_of_seats": "2",
        "length_mm": "4780",
        "width_mm": "2030",
        "height_mm": "1136",
        "curb_weight_kg": "1575",
        "capacity_cm3": "6498",
        "engine_hp": "700",
        "engine_type": "Gasoline",
        "transmission": "Automatic",
        "maximum_torque_n_m": "690",
        "mixed_fuel_consumption_per_100_km_l": "16.0",
        "CO2_emissions_g/km": "370",
        "acceleration_0_100_km/h_s": "2.9",
        "max_speed_km_per_h": "350",
    },
    {
        "id_trim": "4",
        "Make": "Toyota",
        "Modle": "Yaris",
        "Generation": "3 generation",
        "Year_from": "2017",
        "Year_to": "2020",
        "Series": "Hatchback",
        "Trim": "1.5 Hybrid CVT",
        "Body_type": "Hatchback",
        "number_of_seats": "5",
        "length_mm": "3950",
        "width_mm": "1695",
        "height_mm": "1500",
        "curb_weight_kg": "1110",
        "capacity_cm3": "1497",
        "engine_hp": "100",
        "engine_type": "Hybrid",
        "transmission": "Automatic",
        "maximum_torque_n_m": "111",
        "mixed_fuel_consumption_per_100_km_l": "3.3",
        "CO2_emissions_g/km": "75",
        "acceleration_0_100_km/h_s": "11.8",
        "max_speed_km_per_h": "175",
    },
    {
        "id_trim": "5",
        "Make": "Peugeot",
        "Modle": "208",
        "Generation": "1 generation",
        "Year_from": "2012",
        "Year_to": "2019",
        "Series": "Hatchback 5-doors",
        "Trim": "1.6 BlueHDi 100 MT",
        "Body_type": "Hatchback",
        "number_of_seats": "5",
        "length_mm": "3962",
        "width_mm": "1739",
        "height_mm": "1460",
        "curb_weight_kg": "1100",
        "capacity_cm3": "1560",
        "engine_hp": "99",
        "engine_type": "Diesel",
        "transmission": "Manual",
        "maximum_torque_n_m": "254",
        "mixed_fuel_consumption_per_100_km_l": "3.1",
        "CO2_emissions_g/km": "79",
        "acceleration_0_100_km/h_s": "11.3",
        "max_speed_km_per_h": "188",
    },
]


def _write_sample_csv(path: Path, rows: list[dict] | None = None):
    """Ecrit un CSV sample dans un fichier temporaire."""
    if rows is None:
        rows = SAMPLE_CSV_ROWS
    fieldnames = rows[0].keys()
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


class TestImportCsv:
    """Tests du script d'import CSV."""

    def test_import_creates_vehicles_and_specs(self, app, db):
        """L'import cree les Vehicle et VehicleSpec."""
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        _write_sample_csv(tmp_path)

        from data.seeds.import_csv_specs import import_csv

        with patch("data.seeds.import_csv_specs.CSV_PATH", tmp_path):
            with patch("data.seeds.import_csv_specs.create_app", return_value=app):
                import_csv()

        with app.app_context():
            # Lamborghini filtree (pas dans TARGET_MAKES)
            assert Vehicle.query.filter_by(brand="Lamborghini").first() is None

            # Peugeot 208, Renault Clio, Toyota Yaris crees
            peugeot = Vehicle.query.filter_by(brand="Peugeot", model="208").first()
            assert peugeot is not None
            assert peugeot.generation == "1 generation"
            assert peugeot.year_start == 2012

            renault = Vehicle.query.filter_by(brand="Renault", model="Clio").first()
            assert renault is not None

            toyota = Vehicle.query.filter_by(brand="Toyota", model="Yaris").first()
            assert toyota is not None

            # 2 specs pour Peugeot 208 (VTi + BlueHDi)
            peugeot_specs = VehicleSpec.query.filter_by(vehicle_id=peugeot.id).all()
            assert len(peugeot_specs) == 2

        tmp_path.unlink(missing_ok=True)

    def test_import_is_idempotent(self, app, db):
        """Lancer l'import 2 fois ne cree pas de doublons."""
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        _write_sample_csv(tmp_path)

        from data.seeds.import_csv_specs import import_csv

        with patch("data.seeds.import_csv_specs.CSV_PATH", tmp_path):
            with patch("data.seeds.import_csv_specs.create_app", return_value=app):
                import_csv()
                import_csv()

        with app.app_context():
            peugeot = Vehicle.query.filter_by(brand="Peugeot", model="208").first()
            peugeot_specs = VehicleSpec.query.filter_by(vehicle_id=peugeot.id).all()
            # Toujours 2 specs, pas 4
            assert len(peugeot_specs) == 2

        tmp_path.unlink(missing_ok=True)

    def test_fuel_type_normalization(self, app, db):
        """Gasoline→Essence, Diesel→Diesel, Hybrid→Hybride."""
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        _write_sample_csv(tmp_path)

        from data.seeds.import_csv_specs import import_csv

        with patch("data.seeds.import_csv_specs.CSV_PATH", tmp_path):
            with patch("data.seeds.import_csv_specs.create_app", return_value=app):
                import_csv()

        with app.app_context():
            peugeot = Vehicle.query.filter_by(brand="Peugeot", model="208").first()
            specs = VehicleSpec.query.filter_by(vehicle_id=peugeot.id).all()
            fuel_types = {s.fuel_type for s in specs}
            assert "Essence" in fuel_types
            assert "Diesel" in fuel_types
            assert "Gasoline" not in fuel_types

            toyota = Vehicle.query.filter_by(brand="Toyota", model="Yaris").first()
            yaris_spec = VehicleSpec.query.filter_by(vehicle_id=toyota.id).first()
            assert yaris_spec.fuel_type == "Hybride"

        tmp_path.unlink(missing_ok=True)

    def test_transmission_normalization(self, app, db):
        """Manual→Manuelle, Automatic→Automatique."""
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        _write_sample_csv(tmp_path)

        from data.seeds.import_csv_specs import import_csv

        with patch("data.seeds.import_csv_specs.CSV_PATH", tmp_path):
            with patch("data.seeds.import_csv_specs.create_app", return_value=app):
                import_csv()

        with app.app_context():
            peugeot = Vehicle.query.filter_by(brand="Peugeot", model="208").first()
            specs = VehicleSpec.query.filter_by(vehicle_id=peugeot.id).all()
            transmissions = {s.transmission for s in specs}
            assert "Manuelle" in transmissions
            assert "Manual" not in transmissions

            renault = Vehicle.query.filter_by(brand="Renault", model="Clio").first()
            clio_spec = VehicleSpec.query.filter_by(vehicle_id=renault.id).first()
            assert clio_spec.transmission == "Automatique"

        tmp_path.unlink(missing_ok=True)

    def test_invalid_values_handled(self, app, db):
        """Les valeurs vides ou invalides deviennent None."""
        row = SAMPLE_CSV_ROWS[0].copy()
        row["engine_hp"] = ""
        row["curb_weight_kg"] = "n/a"
        row["mixed_fuel_consumption_per_100_km_l"] = ""
        row["Trim"] = "test_invalid"

        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        _write_sample_csv(tmp_path, [row])

        from data.seeds.import_csv_specs import import_csv

        with patch("data.seeds.import_csv_specs.CSV_PATH", tmp_path):
            with patch("data.seeds.import_csv_specs.create_app", return_value=app):
                import_csv()

        with app.app_context():
            peugeot = Vehicle.query.filter_by(brand="Peugeot", model="208").first()
            spec = VehicleSpec.query.filter_by(
                vehicle_id=peugeot.id, engine="test_invalid"
            ).first()
            assert spec is not None
            assert spec.power_hp is None
            assert spec.curb_weight_kg is None
            assert spec.mixed_consumption_l100km is None

        tmp_path.unlink(missing_ok=True)


class TestHelpers:
    """Tests des fonctions utilitaires."""

    def test_int_or_none(self):
        from data.seeds.import_csv_specs import int_or_none

        assert int_or_none("123") == 123
        assert int_or_none("123.7") == 123
        assert int_or_none("") is None
        assert int_or_none("n/a") is None
        assert int_or_none(None) is None

    def test_float_or_none(self):
        from data.seeds.import_csv_specs import float_or_none

        assert float_or_none("5.2") == 5.2
        assert float_or_none("100") == 100.0
        assert float_or_none("") is None
        assert float_or_none("n/a") is None
        assert float_or_none(None) is None

    def test_normalize_fuel(self):
        from data.seeds.import_csv_specs import normalize_fuel

        assert normalize_fuel("Gasoline") == "Essence"
        assert normalize_fuel("Diesel") == "Diesel"
        assert normalize_fuel("Hybrid") == "Hybride"
        assert normalize_fuel("Electric") == "Electrique"
        assert normalize_fuel("Plug-in Hybrid") == "Hybride rechargeable"
        assert normalize_fuel("Unknown") == "Unknown"
        assert normalize_fuel("") == ""

    def test_normalize_transmission(self):
        from data.seeds.import_csv_specs import normalize_transmission

        assert normalize_transmission("Manual") == "Manuelle"
        assert normalize_transmission("Automatic") == "Automatique"
        assert normalize_transmission("CVT") == "CVT"
        assert normalize_transmission("") == ""
