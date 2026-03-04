"""Shared phone prefix table and parsing helpers for L6/L8 filters.

Single source of truth for:
- country <-> dial code mapping
- country flags / display labels
- robust prefix extraction from phone strings (no greedy +437 bugs)
"""

from __future__ import annotations

import re

# Tableau indicatifs par pays/site (TLD principal AutoScout24/LBC).
# Note: certains indicatifs officiels ont 3 chiffres (ex: +352 Luxembourg).
PHONE_DIAL_TABLE: dict[str, dict[str, str | tuple[str, ...]]] = {
    "FR": {"name": "France", "flag": "🇫🇷", "tld": "fr", "prefixes": ("+33", "0033")},
    "CH": {"name": "Suisse", "flag": "🇨🇭", "tld": "ch", "prefixes": ("+41", "0041")},
    "DE": {"name": "Allemagne", "flag": "🇩🇪", "tld": "de", "prefixes": ("+49", "0049")},
    "AT": {"name": "Autriche", "flag": "🇦🇹", "tld": "at", "prefixes": ("+43", "0043")},
    "IT": {"name": "Italie", "flag": "🇮🇹", "tld": "it", "prefixes": ("+39", "0039")},
    "NL": {"name": "Pays-Bas", "flag": "🇳🇱", "tld": "nl", "prefixes": ("+31", "0031")},
    "BE": {"name": "Belgique", "flag": "🇧🇪", "tld": "be", "prefixes": ("+32", "0032")},
    "LU": {"name": "Luxembourg", "flag": "🇱🇺", "tld": "lu", "prefixes": ("+352", "00352")},
    "ES": {"name": "Espagne", "flag": "🇪🇸", "tld": "es", "prefixes": ("+34", "0034")},
    "PL": {"name": "Pologne", "flag": "🇵🇱", "tld": "pl", "prefixes": ("+48", "0048")},
    "SE": {"name": "Suède", "flag": "🇸🇪", "tld": "se", "prefixes": ("+46", "0046")},
}


def get_country_prefixes(country: str) -> tuple[str, ...]:
    """Return known dial prefixes for a country code."""
    row = PHONE_DIAL_TABLE.get((country or "").upper(), {})
    prefixes = row.get("prefixes")
    if isinstance(prefixes, tuple):
        return prefixes
    return ()


def get_country_flag(country: str) -> str:
    row = PHONE_DIAL_TABLE.get((country or "").upper(), {})
    flag = row.get("flag")
    return str(flag) if flag else ""


def get_country_name(country: str) -> str:
    row = PHONE_DIAL_TABLE.get((country or "").upper(), {})
    name = row.get("name")
    return str(name) if name else (country or "").upper()


def detect_phone_prefix_country(cleaned_phone: str) -> tuple[str | None, str | None]:
    """Detect phone prefix country from known prefixes using longest-prefix match.

    Returns:
        (country_code, canonical_plus_prefix)

    Example:
        +43720123456 -> ("AT", "+43")
    """
    if not cleaned_phone:
        return None, None

    normalized = re.sub(r"[\s\-.()]", "", str(cleaned_phone).strip())
    normalized = normalized.replace("(0)", "")
    if normalized.startswith("00") and len(normalized) > 4:
        normalized = "+" + normalized[2:]
    if not normalized.startswith("+"):
        return None, None

    candidates: list[tuple[int, str, str]] = []
    for ctry, row in PHONE_DIAL_TABLE.items():
        prefixes = row.get("prefixes")
        if not isinstance(prefixes, tuple):
            continue
        for p in prefixes:
            if normalized.startswith(p):
                plus = p if p.startswith("+") else "+" + p[2:]
                candidates.append((len(p), ctry, plus))

    if not candidates:
        return None, None

    # Longest-prefix wins to avoid ambiguous matches.
    _, ctry, plus = max(candidates, key=lambda x: x[0])
    return ctry, plus


def is_local_prefix(cleaned_phone: str, country: str) -> bool:
    """True if phone starts with known local country prefix."""
    ctry, _ = detect_phone_prefix_country(cleaned_phone)
    return bool(ctry and ctry == (country or "").upper())
