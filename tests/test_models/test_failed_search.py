"""Tests pour le modele FailedSearch et son workflow de statut."""

import json

from app.models.failed_search import FailedSearch


class TestFailedSearchModel:
    """Tests du modele FailedSearch."""

    def test_default_status_is_new(self, db):
        fs = FailedSearch(make="BMW", model="320", year=2021, region="Zurich")
        db.session.add(fs)
        db.session.commit()
        assert fs.status == "new"
        assert fs.severity == "medium"
        assert fs.resolved is False

    def test_set_status_updates_fields(self, db):
        fs = FailedSearch(make="VW", model="Golf", year=2022, region="Geneve")
        db.session.add(fs)
        db.session.commit()

        fs.set_status("investigating", "Investigation en cours")
        db.session.commit()

        assert fs.status == "investigating"
        assert fs.resolved is False
        assert fs.status_changed_at is not None
        notes = fs.get_notes()
        assert len(notes) == 1
        assert "investigating" in notes[0]["action"]

    def test_set_status_resolved_syncs_legacy(self, db):
        fs = FailedSearch(make="AUDI", model="A3", year=2020, region="Berne")
        db.session.add(fs)
        db.session.commit()

        fs.set_status("resolved", "Tokens corriges")
        db.session.commit()

        assert fs.status == "resolved"
        assert fs.resolved is True
        assert fs.resolved_at is not None

    def test_set_status_wont_fix_syncs_legacy(self, db):
        fs = FailedSearch(make="SEAT", model="Ibiza", year=2019, region="Vaud")
        db.session.add(fs)
        db.session.commit()

        fs.set_status("wont_fix", "Vehicule trop rare")
        db.session.commit()

        assert fs.resolved is True

    def test_add_note_persists(self, db):
        fs = FailedSearch(make="PEUGEOT", model="208", year=2021, region="Ile-de-France")
        db.session.add(fs)
        db.session.commit()

        fs.add_note("comment", "Verifier les tokens LBC")
        fs.add_note("comment", "Essayer le fallback")
        db.session.commit()

        notes = fs.get_notes()
        assert len(notes) == 2
        assert notes[0]["message"] == "Verifier les tokens LBC"
        assert notes[1]["message"] == "Essayer le fallback"

    def test_get_search_log_returns_none_when_empty(self):
        fs = FailedSearch(make="BMW", model="X1", year=2023, region="Zurich")
        assert fs.get_search_log() is None

    def test_get_search_log_parses_json(self, db):
        log = [{"step": 1, "precision": 5, "ads_found": 0}]
        fs = FailedSearch(
            make="BMW",
            model="X1",
            year=2023,
            region="Zurich",
            search_log=json.dumps(log),
        )
        db.session.add(fs)
        db.session.commit()

        assert fs.get_search_log() == log

    def test_country_defaults_to_fr(self, db):
        fs = FailedSearch(make="RENAULT", model="Clio", year=2022, region="Bretagne")
        db.session.add(fs)
        db.session.commit()

        assert fs.country == "FR"

    def test_country_ch(self, db):
        fs = FailedSearch(
            make="VW",
            model="Golf",
            year=2022,
            region="Geneve",
            country="CH",
        )
        db.session.add(fs)
        db.session.commit()

        assert fs.country == "CH"


class TestComputeSeverity:
    """Tests du calcul auto de severite."""

    def test_low_for_single_occurrence(self):
        assert FailedSearch.compute_severity(1) == "low"

    def test_medium_for_two_occurrences(self):
        assert FailedSearch.compute_severity(2) == "medium"

    def test_high_for_three_occurrences(self):
        assert FailedSearch.compute_severity(3) == "high"

    def test_high_for_fallback_source(self):
        assert FailedSearch.compute_severity(1, "fallback") == "high"

    def test_critical_for_five_occurrences(self):
        assert FailedSearch.compute_severity(5) == "critical"

    def test_critical_for_ten_occurrences(self):
        assert FailedSearch.compute_severity(10) == "critical"
