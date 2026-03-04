"""Tests for shared phone prefix parsing helpers."""

from app.filters.phone_prefixes import detect_phone_prefix_country, is_local_prefix


def test_detect_phone_prefix_country_longest_match_plus_437():
    country, prefix = detect_phone_prefix_country("+43720123456")
    assert country == "AT"
    assert prefix == "+43"


def test_detect_phone_prefix_country_luxembourg_00352():
    country, prefix = detect_phone_prefix_country("00352621123456")
    assert country == "LU"
    assert prefix == "+352"


def test_is_local_prefix_se():
    assert is_local_prefix("+46701234567", "SE") is True
