"""Service de conversion de devises pour normaliser les prix en EUR.

Les taux sont configures statiquement (mise a jour manuelle).
Pour les besoins du projet, seul CHF→EUR est necessaire (AutoScout24.ch).
"""

import logging

logger = logging.getLogger(__name__)

# Taux de conversion vers EUR (1 unite de devise = X EUR).
# Source: BCE, mis a jour manuellement.
# CHF/EUR oscille entre 0.92 et 0.97 en 2025-2026.
EXCHANGE_RATES_TO_EUR: dict[str, float] = {
    "EUR": 1.0,
    "CHF": 0.94,
}


def convert_to_eur(amount: int | float | None, currency: str | None) -> tuple[int | None, bool]:
    """Convertit un montant dans une devise donnee en EUR.

    Returns:
        tuple (montant_eur, converted):
            - montant_eur: prix converti en EUR (arrondi), ou None si amount est None
            - converted: True si une conversion a ete appliquee, False sinon
    """
    if amount is None:
        return None, False

    if not currency or currency.upper() == "EUR":
        return int(amount), False

    key = currency.upper()
    rate = EXCHANGE_RATES_TO_EUR.get(key)

    if rate is None:
        logger.warning("Devise inconnue '%s', pas de conversion appliquee", currency)
        return int(amount), False

    converted = int(round(amount * rate))
    logger.info(
        "Conversion %s→EUR: %d %s × %.4f = %d EUR",
        key,
        amount,
        key,
        rate,
        converted,
    )
    return converted, True


def get_supported_currencies() -> list[str]:
    """Retourne la liste des devises supportees."""
    return list(EXCHANGE_RATES_TO_EUR.keys())


def get_rate(currency: str) -> float | None:
    """Retourne le taux de conversion pour une devise, ou None si inconnue."""
    return EXCHANGE_RATES_TO_EUR.get(currency.upper())
