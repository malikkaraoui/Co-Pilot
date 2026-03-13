"""Table partagee d'indicatifs telephoniques et helpers de parsing pour L6/L8.

Source unique de verite pour :
- Le mapping pays <-> indicatif telephonique
- Les drapeaux et noms de pays pour l'affichage
- L'extraction robuste de prefixe depuis un numero brut

Le point cle : on utilise le longest-prefix match pour eviter les bugs
de type "+437..." qui matchait "+43" (Autriche) au lieu de ne pas matcher
du tout. Maintenant on compare tous les candidats et on prend le plus long.
"""

from __future__ import annotations

import re

# Tableau indicatifs par pays/site (TLD principal AutoScout24/LBC).
# Note: certains indicatifs officiels ont 3 chiffres (ex: +352 Luxembourg).
# C'est pour ca qu'on ne peut pas juste faire startswith("+XX") :
# il faut comparer toutes les longueurs de prefixes.
PHONE_DIAL_TABLE: dict[str, dict[str, str | tuple[str, ...]]] = {
    "FR": {
        "name": "France",
        "flag": "\U0001f1eb\U0001f1f7",
        "tld": "fr",
        "prefixes": ("+33", "0033"),
    },
    "CH": {
        "name": "Suisse",
        "flag": "\U0001f1e8\U0001f1ed",
        "tld": "ch",
        "prefixes": ("+41", "0041"),
    },
    "DE": {
        "name": "Allemagne",
        "flag": "\U0001f1e9\U0001f1ea",
        "tld": "de",
        "prefixes": ("+49", "0049"),
    },
    "AT": {
        "name": "Autriche",
        "flag": "\U0001f1e6\U0001f1f9",
        "tld": "at",
        "prefixes": ("+43", "0043"),
    },
    "IT": {
        "name": "Italie",
        "flag": "\U0001f1ee\U0001f1f9",
        "tld": "it",
        "prefixes": ("+39", "0039"),
    },
    "NL": {
        "name": "Pays-Bas",
        "flag": "\U0001f1f3\U0001f1f1",
        "tld": "nl",
        "prefixes": ("+31", "0031"),
    },
    "BE": {
        "name": "Belgique",
        "flag": "\U0001f1e7\U0001f1ea",
        "tld": "be",
        "prefixes": ("+32", "0032"),
    },
    "LU": {
        "name": "Luxembourg",
        "flag": "\U0001f1f1\U0001f1fa",
        "tld": "lu",
        "prefixes": ("+352", "00352"),
    },
    "ES": {
        "name": "Espagne",
        "flag": "\U0001f1ea\U0001f1f8",
        "tld": "es",
        "prefixes": ("+34", "0034"),
    },
    "PL": {
        "name": "Pologne",
        "flag": "\U0001f1f5\U0001f1f1",
        "tld": "pl",
        "prefixes": ("+48", "0048"),
    },
    "SE": {
        "name": "Suède",
        "flag": "\U0001f1f8\U0001f1ea",
        "tld": "se",
        "prefixes": ("+46", "0046"),
    },
}


def get_country_prefixes(country: str) -> tuple[str, ...]:
    """Retourne les indicatifs telephoniques connus pour un code pays."""
    row = PHONE_DIAL_TABLE.get((country or "").upper(), {})
    prefixes = row.get("prefixes")
    if isinstance(prefixes, tuple):
        return prefixes
    return ()


def get_country_flag(country: str) -> str:
    """Retourne l'emoji drapeau du pays (ou chaine vide si inconnu)."""
    row = PHONE_DIAL_TABLE.get((country or "").upper(), {})
    flag = row.get("flag")
    return str(flag) if flag else ""


def get_country_name(country: str) -> str:
    """Retourne le nom du pays en francais (ou le code pays en majuscules si inconnu)."""
    row = PHONE_DIAL_TABLE.get((country or "").upper(), {})
    name = row.get("name")
    return str(name) if name else (country or "").upper()


def detect_phone_prefix_country(cleaned_phone: str) -> tuple[str | None, str | None]:
    """Detecte le pays d'un numero a partir de son indicatif, via longest-prefix match.

    Resout l'ambiguite entre indicatifs de longueurs differentes :
    +43 (Autriche) vs +352 (Luxembourg) vs +33 (France).

    Returns:
        (country_code, canonical_plus_prefix) ou (None, None) si non reconnu.

    Example:
        +43720123456 -> ("AT", "+43")
        +352621123456 -> ("LU", "+352")
    """
    if not cleaned_phone:
        return None, None

    # Normaliser : retirer les espaces/tirets/points/parentheses
    normalized = re.sub(r"[\s\-.()]", "", str(cleaned_phone).strip())
    normalized = normalized.replace("(0)", "")
    # Convertir le format 00XX en +XX pour simplifier le matching
    if normalized.startswith("00") and len(normalized) > 4:
        normalized = "+" + normalized[2:]
    if not normalized.startswith("+"):
        return None, None

    # Collecter tous les candidats et prendre le plus long
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
    """True si le numero commence par un indicatif local du pays donne.

    Utilise par L6 pour distinguer un numero local d'un numero etranger.
    """
    ctry, _ = detect_phone_prefix_country(cleaned_phone)
    return bool(ctry and ctry == (country or "").upper())
