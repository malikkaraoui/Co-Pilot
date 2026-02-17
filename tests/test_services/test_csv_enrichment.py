"""Tests for CSV auto-enrichment service."""

import pytest

from app.services.csv_enrichment import CSV_PATH, lookup_specs


@pytest.mark.skipif(not CSV_PATH.exists(), reason="CSV Kaggle absent")
class TestCSVEnrichment:
    def test_lookup_known_model(self):
        """Peugeot 208 doit exister dans le CSV."""
        specs = lookup_specs("Peugeot", "208")
        assert len(specs) > 0
        first = specs[0]
        assert first.get("fuel_type") is not None
        assert first.get("power_hp") is not None or first.get("engine") is not None

    def test_lookup_audi_s3(self):
        """Audi S3 doit exister dans le CSV Kaggle."""
        specs = lookup_specs("Audi", "S3")
        assert len(specs) > 0
        # Au moins une spec avec des donnees utiles
        has_data = any(s.get("power_hp") for s in specs)
        assert has_data

    def test_lookup_unknown_model(self):
        """Modele inexistant retourne liste vide."""
        specs = lookup_specs("FakeMarque", "FakeModele")
        assert specs == []

    def test_lookup_case_insensitive(self):
        """Le lookup est insensible a la casse."""
        specs_lower = lookup_specs("peugeot", "208")
        specs_upper = lookup_specs("PEUGEOT", "208")
        assert len(specs_lower) == len(specs_upper)

    def test_spec_fields_valid(self):
        """Les specs retournees ont des champs valides."""
        specs = lookup_specs("Renault", "Clio V")
        if not specs:
            # Clio V n'est peut-etre pas dans le CSV (Clio sans V?)
            specs = lookup_specs("Renault", "Clio")
        assert len(specs) > 0
        for spec in specs:
            # Pas de champs vides string
            for key, val in spec.items():
                if isinstance(val, str):
                    assert val.strip() != "", f"Champ {key} est une string vide"

    def test_deduplication_trims(self):
        """Pas de doublons de trim."""
        specs = lookup_specs("Peugeot", "208")
        trims = [s["engine"] for s in specs if s.get("engine")]
        assert len(trims) == len(set(trims))
