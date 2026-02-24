"""Tests for build_search_query."""

from app.services.youtube_service import build_search_query


class TestBuildSearchQuery:
    def test_full_query(self):
        """Build query with all parameters."""
        q = build_search_query(
            make="Peugeot",
            model="308",
            year=2019,
            fuel="diesel",
            hp="130",
            keywords="fiabilite problemes",
        )
        assert "Peugeot" in q
        assert "308" in q
        assert "2019" in q
        assert "diesel" in q
        assert "130ch" in q
        assert "fiabilite problemes" in q

    def test_minimal_query(self):
        """Build query with only make and model adds default keywords."""
        q = build_search_query(make="Renault", model="Clio")
        assert q == "Renault Clio essai test avis"

    def test_with_year_only(self):
        """Year is included, no default keywords when specifics provided."""
        q = build_search_query(make="BMW", model="Serie 3", year=2020)
        assert "2020" in q
        assert "BMW" in q
        assert "essai" not in q

    def test_strips_whitespace(self):
        """Whitespace is stripped from inputs."""
        q = build_search_query(make="  Peugeot  ", model="  208  ")
        assert q == "Peugeot 208 essai test avis"
