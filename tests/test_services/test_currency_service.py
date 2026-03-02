"""Tests for currency conversion service."""

import pytest

from app.services.currency_service import convert_to_eur, get_rate, get_supported_currencies


class TestConvertToEur:
    def test_chf_converts_to_eur(self):
        amount, converted = convert_to_eur(43900, "CHF")
        assert converted is True
        assert amount == round(43900 * 0.94)

    def test_eur_returns_unchanged(self):
        amount, converted = convert_to_eur(15000, "EUR")
        assert converted is False
        assert amount == 15000

    def test_none_currency_returns_unchanged(self):
        amount, converted = convert_to_eur(15000, None)
        assert converted is False
        assert amount == 15000

    def test_empty_currency_returns_unchanged(self):
        amount, converted = convert_to_eur(15000, "")
        assert converted is False
        assert amount == 15000

    def test_none_amount_returns_none(self):
        amount, converted = convert_to_eur(None, "CHF")
        assert amount is None
        assert converted is False

    def test_unknown_currency_returns_unchanged(self):
        amount, converted = convert_to_eur(10000, "GBP")
        assert converted is False
        assert amount == 10000

    def test_case_insensitive_currency(self):
        amount1, conv1 = convert_to_eur(10000, "chf")
        amount2, conv2 = convert_to_eur(10000, "CHF")
        assert amount1 == amount2
        assert conv1 is True
        assert conv2 is True

    def test_float_amount_rounds(self):
        amount, converted = convert_to_eur(100.5, "CHF")
        assert converted is True
        assert isinstance(amount, int)
        assert amount == round(100.5 * 0.94)


class TestGetRate:
    def test_chf_rate(self):
        rate = get_rate("CHF")
        assert rate == pytest.approx(0.94)

    def test_eur_rate(self):
        assert get_rate("EUR") == 1.0

    def test_unknown_rate(self):
        assert get_rate("GBP") is None

    def test_case_insensitive(self):
        assert get_rate("chf") == get_rate("CHF")


class TestGetSupportedCurrencies:
    def test_returns_eur_and_chf(self):
        currencies = get_supported_currencies()
        assert "EUR" in currencies
        assert "CHF" in currencies
