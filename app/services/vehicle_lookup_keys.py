"""Outils purs de normalisation pour les lookup keys véhicule.

Ce module ne dépend pas des modèles SQLAlchemy.
Il sert de source de vérité partagée entre:
- le matching applicatif,
- les colonnes persistées de lookup,
- les fonctions SQLite custom.
"""

from __future__ import annotations

import re
import unicodedata

_DASH_TRANSLATION = str.maketrans(
    {
        "‐": "-",
        "‑": "-",
        "‒": "-",
        "–": "-",
        "—": "-",
        "―": "-",
    }
)
_APOSTROPHE_TRANSLATION = str.maketrans(
    {
        "’": "'",
        "‘": "'",
        "´": "'",
        "`": "'",
    }
)
_CANONICAL_SPACES_RE = re.compile(r"\s+")
_LOOKUP_SEPARATOR_RE = re.compile(r"[\s\-_/.,+'()]+")
_LOOKUP_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def strip_accents(text: str) -> str:
    """Supprime les accents et diacritiques."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalize_lookup_text(text: str) -> str:
    """Produit une forme stable pour les clés de lookup."""
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(_DASH_TRANSLATION)
    text = text.translate(_APOSTROPHE_TRANSLATION)
    text = strip_accents(text.casefold())
    text = _LOOKUP_SEPARATOR_RE.sub(" ", text)
    return " ".join(text.split())


def normalize_canonical_text(text: str) -> str:
    """Produit une forme canonique lisible en conservant les séparateurs utiles."""
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(_DASH_TRANSLATION)
    text = text.translate(_APOSTROPHE_TRANSLATION)
    text = strip_accents(text.casefold())
    text = _CANONICAL_SPACES_RE.sub(" ", text).strip()
    return text


def lookup_compact_key(text: str) -> str:
    """Clé compacte accent-insensitive pour le matching robuste."""
    normalized = normalize_lookup_text(text)
    return _LOOKUP_NON_ALNUM_RE.sub("", normalized)


def lookup_keys(text: str) -> tuple[str, ...]:
    """Retourne les variantes de clés utiles pour les alias."""
    normalized = normalize_lookup_text(text)
    compact = lookup_compact_key(normalized)
    if compact and compact != normalized:
        return normalized, compact
    return (normalized,)
