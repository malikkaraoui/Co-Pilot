"""Service d'extraction des donnees structurees d'une annonce Leboncoin.

Analyse le payload JSON __NEXT_DATA__ et extrait les champs de l'annonce vehicule.
Base sur le script original lbc_extract.py, reecrit selon les patterns Co-Pilot.
"""

import logging
import re
from typing import Any

from app.errors import ExtractionError

logger = logging.getLogger(__name__)


def _deep_get(data: dict, path: str) -> Any:
    """Parcourt un dictionnaire imbrique via un chemin separe par des points."""
    current: Any = data
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


def _find_ad_payload(next_data: dict) -> dict | None:
    """Localise le payload de l'annonce dans __NEXT_DATA__."""
    ad = _deep_get(next_data, "props.pageProps.ad")
    if isinstance(ad, dict):
        return ad

    # Fallback : recherche recursive d'un dict qui ressemble a une annonce
    def _walk(node: Any) -> dict | None:
        if isinstance(node, dict):
            if "attributes" in node and ("price" in node or "subject" in node):
                return node
            for value in node.values():
                hit = _walk(value)
                if hit:
                    return hit
        elif isinstance(node, list):
            for item in node:
                hit = _walk(item)
                if hit:
                    return hit
        return None

    return _walk(next_data)


def _normalize_attributes(ad: dict) -> dict[str, Any]:
    """Convertit ad.attributes[] de Leboncoin en dictionnaire plat cle->valeur."""
    out: dict[str, Any] = {}
    attrs = ad.get("attributes") or []
    if not isinstance(attrs, list):
        return out

    for attr in attrs:
        if not isinstance(attr, dict):
            continue
        key = (
            attr.get("key")
            or attr.get("key_label")
            or attr.get("label")
            or attr.get("name")
        )
        val = (
            attr.get("value")
            or attr.get("value_label")
            or attr.get("text")
            or attr.get("value_text")
        )
        if isinstance(key, str) and key.strip():
            out[key.strip()] = val

    return out


def _coerce_int(value: Any) -> int | None:
    """Tente de convertir un entier depuis differents formats."""
    if value is None:
        return None
    if isinstance(value, int):
        return value
    digits = re.findall(r"\d+", str(value).replace(" ", ""))
    if not digits:
        return None
    try:
        return int("".join(digits))
    except ValueError:
        return None


def _extract_price(ad: dict) -> int | None:
    """Extrait le prix depuis les donnees de premier niveau de l'annonce."""
    price = ad.get("price")
    if isinstance(price, (int, float)):
        return int(price)
    if isinstance(price, list) and price and isinstance(price[0], (int, float)):
        return int(price[0])
    return None


def _extract_location(ad: dict) -> dict[str, Any]:
    """Extrait les informations de localisation de l'annonce."""
    location = ad.get("location") or {}
    return {
        "city": location.get("city"),
        "zipcode": location.get("zipcode"),
        "department": location.get("department_name"),
        "region": location.get("region_name"),
        "lat": location.get("lat"),
        "lng": location.get("lng"),
    }


def _extract_phone(ad: dict) -> str | None:
    """Extrait le numero de telephone si disponible."""
    phone = ad.get("phone")
    if isinstance(phone, str) and phone.strip():
        return phone.strip()
    owner = ad.get("owner") or {}
    phone = owner.get("phone")
    if isinstance(phone, str) and phone.strip():
        return phone.strip()
    return None


def extract_ad_data(next_data: dict) -> dict[str, Any]:
    """Extrait les donnees structurees du vehicule depuis un payload __NEXT_DATA__ Leboncoin.

    Args:
        next_data: L'objet JSON __NEXT_DATA__ analyse.

    Returns:
        Un dictionnaire plat avec les champs vehicule normalises.

    Raises:
        ExtractionError: Si le payload de l'annonce est introuvable ou malformate.
    """
    if not isinstance(next_data, dict):
        raise ExtractionError("next_data must be a dict")

    ad = _find_ad_payload(next_data)
    if not ad:
        raise ExtractionError("Could not locate ad payload in __NEXT_DATA__")

    attrs = _normalize_attributes(ad)
    logger.debug("Normalized %d attributes from ad", len(attrs))

    title = ad.get("subject") or ad.get("title") or ad.get("headline")
    price = _extract_price(ad)
    location = _extract_location(ad)
    phone = _extract_phone(ad)
    description = ad.get("body") or ad.get("description") or ""

    # Informations du proprietaire
    owner = ad.get("owner") or {}
    owner_type = owner.get("type")
    owner_name = owner.get("name")
    siret = owner.get("siren") or owner.get("siret")

    result = {
        "title": title,
        "price_eur": price,
        "make": attrs.get("Marque") or attrs.get("brand"),
        "model": (
            attrs.get("Modèle")
            or attrs.get("modele")
            or attrs.get("model")
        ),
        "year_model": str(y) if (y := (
            attrs.get("Année modèle")
            or attrs.get("Année")
            or attrs.get("year")
        )) is not None else None,
        "mileage_km": _coerce_int(
            attrs.get("Kilométrage") or attrs.get("kilometrage")
        ),
        "fuel": (
            attrs.get("Énergie")
            or attrs.get("Energie")
            or attrs.get("Carburant")
        ),
        "gearbox": (
            attrs.get("Boîte de vitesse")
            or attrs.get("Boite de vitesse")
            or attrs.get("Transmission")
        ),
        "doors": _coerce_int(attrs.get("Nombre de portes")),
        "seats": _coerce_int(
            attrs.get("Nombre de place(s)") or attrs.get("Nombre de places")
        ),
        "first_registration": (
            attrs.get("Date de première mise en circulation")
            or attrs.get("Mise en circulation")
        ),
        "color": attrs.get("Couleur"),
        "power_fiscal_cv": _coerce_int(attrs.get("Puissance fiscale")),
        "power_din_hp": _coerce_int(attrs.get("Puissance DIN")),
        "location": location,
        "phone": phone,
        "description": description,
        "owner_type": owner_type,
        "owner_name": owner_name,
        "siret": siret,
        "raw_attributes": attrs,
    }

    logger.info(
        "Extracted ad: %s %s %s - %s EUR",
        result.get("make"),
        result.get("model"),
        result.get("year_model"),
        result.get("price_eur"),
    )
    return result
