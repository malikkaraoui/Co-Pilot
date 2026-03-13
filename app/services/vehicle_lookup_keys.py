"""Outils purs de normalisation pour les lookup keys véhicule.

Ce module ne dépend pas des modèles SQLAlchemy.
Il sert de source de vérité partagée entre:
- le matching applicatif,
- les colonnes persistées de lookup,
- les fonctions SQLite custom.

L'idee c'est qu'on normalise de la meme facon partout : a l'ecriture en base
ET a la lecture/comparaison. Comme ca, "Citroen" == "citroen" == "CITROEN"
peu importe d'ou vient la donnee (LBC, AS24, CSV, saisie manuelle).
"""

from __future__ import annotations

import re
import unicodedata

# Tables de remplacement pour homogeneiser les tirets et apostrophes Unicode.
# LBC et AS24 utilisent des variantes typographiques differentes,
# on ramene tout vers les formes ASCII standard.
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
    """Supprime les accents et diacritiques.

    Decompose en NFKD puis retire les caracteres combining (accents).
    """
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalize_lookup_text(text: str) -> str:
    """Produit une forme stable pour les cles de lookup.

    Pipeline : NFKC -> tirets/apostrophes uniformes -> sans accents -> lowercase
    -> separateurs unifies en espaces -> trim.
    C'est la forme "lisible" de la cle, avec des espaces entre les mots.
    """
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(_DASH_TRANSLATION)
    text = text.translate(_APOSTROPHE_TRANSLATION)
    text = strip_accents(text.casefold())
    text = _LOOKUP_SEPARATOR_RE.sub(" ", text)
    return " ".join(text.split())


def normalize_canonical_text(text: str) -> str:
    """Produit une forme canonique lisible en conservant les separateurs utiles.

    Similaire a normalize_lookup_text mais garde les tirets (ex: "T-Roc" reste "t-roc").
    Utilisee pour l'affichage et les aliases ou le tiret est significatif.
    """
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(_DASH_TRANSLATION)
    text = text.translate(_APOSTROPHE_TRANSLATION)
    text = strip_accents(text.casefold())
    text = _CANONICAL_SPACES_RE.sub(" ", text).strip()
    return text


def lookup_compact_key(text: str) -> str:
    """Cle compacte accent-insensitive pour le matching robuste.

    Retire TOUT sauf les lettres et chiffres.
    Ex: "C-HR" -> "chr", "ID.3" -> "id3", "Serie 3" -> "serie3".
    C'est la cle la plus aggressive : elle matche les variantes
    "C-HR" / "CHR" / "C HR" comme identiques.
    """
    normalized = normalize_lookup_text(text)
    return _LOOKUP_NON_ALNUM_RE.sub("", normalized)


def lookup_keys(text: str) -> tuple[str, ...]:
    """Retourne les variantes de cles utiles pour les alias.

    Genere la forme "avec espaces" et la forme "compacte" pour
    maximiser les chances de matcher un alias dans la table.
    Si les deux formes sont identiques, on n'en retourne qu'une.
    """
    normalized = normalize_lookup_text(text)
    compact = lookup_compact_key(normalized)
    if compact and compact != normalized:
        return normalized, compact
    return (normalized,)
