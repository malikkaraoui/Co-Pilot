"""Tests for build_search_query."""

from app.services.youtube_service import build_search_query


class TestBuildSearchQuery:
    def test_full_query(self):
        """Build query with all parameters including generation and custom keywords."""
        q = build_search_query(
            make="Peugeot",
            model="308",
            generation="II",
            year=2019,
            fuel="diesel",
            hp="130",
            keywords="turbo embrayage",
        )
        assert '"Peugeot 308"' in q
        assert "II" in q
        assert "2019" in q
        assert "diesel" in q
        assert "130ch" in q
        assert "turbo embrayage" in q
        assert "fiabilite" not in q

    def test_minimal_query(self):
        """Build query with only make and model adds fiabilite keywords."""
        q = build_search_query(make="Renault", model="Clio")
        assert q == '"Renault Clio" fiabilite problemes defauts avis'

    def test_with_generation(self):
        """Generation is included in query."""
        q = build_search_query(
            make="Volkswagen", model="Golf", generation="VII/VIII", fuel="Diesel"
        )
        assert '"Volkswagen Golf"' in q
        assert "VII/VIII" in q
        assert "Diesel" in q
        assert "fiabilite" in q

    def test_with_year_and_fuel(self):
        """Year and fuel included, fiabilite keywords still added."""
        q = build_search_query(make="BMW", model="Serie 3", year=2020, fuel="diesel")
        assert '"BMW Serie 3"' in q
        assert "2020" in q
        assert "diesel" in q
        assert "fiabilite" in q

    def test_strips_whitespace(self):
        """Whitespace is stripped from inputs."""
        q = build_search_query(make="  Peugeot  ", model="  208  ")
        assert q == '"Peugeot 208" fiabilite problemes defauts avis'
