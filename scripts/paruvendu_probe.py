#!/usr/bin/env python3
"""Sonde exploratoire pour ParuVendu -- analyse de faisabilite d'extraction.

Script de R&D utilise pour :
- decoder les tokens de l'URL de recherche ParuVendu (marque, modele, energie...)
- extraire quelques liens d'annonces depuis la page de resultats
- inspecter les pages de detail pour reperer les donnees structurees (JSON-LD, regex)
- produire un rapport JSON compact pour concevoir un futur extracteur

Pas utilise en production, c'est un outil de reverse-engineering.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

DEFAULT_SEARCH_URL = (
    "https://www.paruvendu.fr/a/voiture-occasion/audi/a5/"
    "?r=VVO00000&r2=VVOAU000&md=VVOAUA5&nrj=DI&a0=2017&a1=2024"
    "&km0=22888&km1=111111&tr=AU&pf0=5&pf1=9"
)

# User-Agent classique pour ne pas se faire bloquer par le WAF ParuVendu
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/135.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}

# Hypotheses sur la signification des parametres URL ParuVendu
# Documentees par observation, pas par une API officielle
QUERY_HINTS = {
    "r": "rubrique racine (voiture d'occasion)",
    "r2": "token marque probable",
    "md": "token modèle probable",
    "nrj": "énergie (ex: DI=diesel)",
    "a0": "année minimale",
    "a1": "année maximale",
    "km0": "kilométrage minimal",
    "km1": "kilométrage maximal",
    "tr": "transmission (ex: AU=automatique)",
    "pf0": "puissance fiscale minimale",
    "pf1": "puissance fiscale maximale",
    "ray": "rayon de recherche",
    "p": "pagination",
}

# Regex d'extraction brute depuis le texte de la page detail
# Fallback quand le JSON-LD ne contient pas le champ
DETAIL_PATTERNS = {
    "price_eur": r"Prix\s*([\d\s]+)\s*€",
    "make": r"Marque\s*([A-ZÀ-ÿ0-9\- ]+)",
    "model": r"Modèle\s*([A-ZÀ-ÿ0-9\- ]+)",
    "version": r"Version\s*(.+?)\s*Carrosserie",
    "body_type": r"Carrosserie\s*([A-ZÀ-ÿ0-9\- ]+)",
    "year_month": r"Année\s*([A-ZÀ-ÿéûîôç]+\s*\d{4}|\d{4})",
    "mileage_km": r"Kilométrage\s*([\d\s]+)\s*km",
    "fuel": r"Energie\s*([A-ZÀ-ÿ\- ]+)",
    "transmission": r"Transmission\s*([A-ZÀ-ÿ\- ]+)",
    "doors": r"Nb de portes\s*([A-ZÀ-ÿ0-9\- ]+)",
    "fiscal_hp": r"Puissance fiscale\s*([\d\s]+)\s*CV",
    "seats": r"Nombre de places\s*([\d\s]+)\s*places",
    "color": r"Couleur\s*([A-ZÀ-ÿ0-9\- ]+)",
    "actual_hp": r"Puissance réelle\s*([\d\s]+)",
    "critair": r"Vignette Crit'Air\s*([0-9]+)",
    "mechanical_warranty": r"Garantie mécanique\s*([\d\s]+)\s*mois",
    "seller_member_since": r"membre depuis\s*([\d\s]+)\s*ans",
    "reference": r"Réf\. annonce\s*:\s*([^\n]+?)\s*-\s*Le",
    "photos_count": r"([\d]+)\s*photos disponibles",
}


@dataclass
class ListingSummary:
    """Resume d'une page de resultats de recherche ParuVendu."""

    url: str
    title: str | None = None
    result_count: int | None = None
    inferred_filters: dict[str, Any] = field(default_factory=dict)
    query_tokens: dict[str, dict[str, Any]] = field(default_factory=dict)
    ad_links: list[str] = field(default_factory=list)
    jsonld_types: list[str] = field(default_factory=list)


@dataclass
class AdSummary:
    """Resume d'une page de detail d'annonce ParuVendu."""

    url: str
    title: str | None = None
    location: str | None = None
    seller_type: str | None = None
    extracted_fields: dict[str, Any] = field(default_factory=dict)
    structured_fields: dict[str, Any] = field(default_factory=dict)
    jsonld_types: list[str] = field(default_factory=list)
    native_cote_links: list[str] = field(default_factory=list)
    fiche_links: list[str] = field(default_factory=list)
    has_phone_cta: bool = False
    has_message_cta: bool = False


class ProbeError(RuntimeError):
    """Raised when a page cannot be probed."""


def fetch_html(client: httpx.Client, url: str) -> str:
    """Telecharge le HTML d'une page avec gestion des redirections."""
    response = client.get(url, follow_redirects=True, timeout=30.0)
    response.raise_for_status()
    return response.text


def normalize_space(text: str) -> str:
    """Condense les espaces multiples en un seul espace."""
    return re.sub(r"\s+", " ", text or "").strip()


def text_of(soup: BeautifulSoup) -> str:
    return normalize_space(soup.get_text(" ", strip=True))


def parse_jsonld_types(soup: BeautifulSoup) -> list[str]:
    """Extrait les @type de tous les blocs JSON-LD de la page."""
    types: list[str] = []
    for item in iter_jsonld_items(soup):
        if isinstance(item, dict):
            json_type = item.get("@type")
            if isinstance(json_type, list):
                types.extend(str(v) for v in json_type)
            elif json_type:
                types.append(str(json_type))
    return sorted(set(types))


def iter_jsonld_items(soup: BeautifulSoup):
    """Iterateur sur les objets JSON-LD de la page (peut y en avoir plusieurs)."""
    for node in soup.select('script[type="application/ld+json"]'):
        raw = node.string or node.get_text(strip=True)
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        items = payload if isinstance(payload, list) else [payload]
        for item in items:
            if isinstance(item, dict):
                yield item


def find_jsonld_vehicle(soup: BeautifulSoup) -> dict[str, Any]:
    """Cherche un objet JSON-LD de @type Vehicle dans la page."""
    for item in iter_jsonld_items(soup):
        json_type = item.get("@type")
        if json_type == "Vehicle" or (isinstance(json_type, list) and "Vehicle" in json_type):
            return item
    return {}


def extract_jsonld_vehicle_fields(vehicle: dict[str, Any]) -> dict[str, Any]:
    """Extrait les champs utiles du JSON-LD Vehicle en un dict plat et propre."""
    if not vehicle:
        return {}

    def pick(obj: Any, *path: str) -> Any:
        current = obj
        for key in path:
            if not isinstance(current, dict):
                return None
            current = current.get(key)
        return current

    def stringify(value: Any) -> Any:
        if isinstance(value, dict):
            return value.get("name") or value.get("value") or value.get("@id")
        return value

    offers = vehicle.get("offers") if isinstance(vehicle.get("offers"), dict) else {}
    brand = stringify(vehicle.get("brand"))
    mileage = stringify(vehicle.get("mileageFromOdometer"))
    seller = vehicle.get("seller") if isinstance(vehicle.get("seller"), dict) else {}
    address = seller.get("address") if isinstance(seller.get("address"), dict) else {}

    result = {
        "name": vehicle.get("name"),
        "brand": brand,
        "model": vehicle.get("model"),
        "version": vehicle.get("vehicleConfiguration") or vehicle.get("description"),
        "body_type": vehicle.get("bodyType"),
        "fuel_type": vehicle.get("fuelType"),
        "transmission": vehicle.get("vehicleTransmission"),
        "color": vehicle.get("color"),
        "price_eur": stringify(offers.get("price")),
        "price_currency": offers.get("priceCurrency"),
        "mileage": mileage,
        "first_registration": vehicle.get("dateVehicleFirstRegistered"),
        "production_date": vehicle.get("productionDate"),
        "seller_name": seller.get("name"),
        "seller_city": address.get("addressLocality"),
        "seller_postal_code": address.get("postalCode"),
        "images_count": len(vehicle.get("image", []))
        if isinstance(vehicle.get("image"), list)
        else None,
        "url": vehicle.get("url"),
    }
    return {
        key: normalize_space(str(value)) for key, value in result.items() if value not in (None, "")
    }


def infer_query_tokens(url: str) -> dict[str, dict[str, Any]]:
    """Decode les parametres URL et ajoute nos hypotheses sur leur role."""
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    result: dict[str, dict[str, Any]] = {}
    for key, values in query.items():
        value = values[-1] if values else ""
        result[key] = {
            "value": value,
            "hint": QUERY_HINTS.get(key, "à qualifier"),
        }
    return result


def infer_filters_from_text(text: str) -> dict[str, Any]:
    """Tente de deviner les filtres actifs depuis le texte visible de la page."""
    filters: dict[str, Any] = {}
    match = re.search(r"(\d[\d\s]*)\s+annonces\s+(.+?)\s+occasion", text, flags=re.IGNORECASE)
    if match:
        filters["visible_results_phrase"] = normalize_space(match.group(0))
    patterns = {
        "year_min": r"Année min\s*(\d{4})",
        "year_max": r"Année max\s*(\d{4})",
        "km_min": r"de\s*([\d\s]+)\s*km",
        "km_max": r"jusqu[’']à\s*([\d\s]+)\s*km",
        "fiscal_min": r"(\d+)\s*CV min",
        "fiscal_max": r"(\d+)\s*CV max",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            filters[key] = normalize_space(match.group(1))
    for label in [
        "Diesel",
        "Essence",
        "Hybride",
        "Electrique",
        "Automatique",
        "Manuelle",
        "Audi",
        "A5",
    ]:
        if re.search(rf"\b{re.escape(label)}\b", text, flags=re.IGNORECASE):
            filters.setdefault("detected_labels", []).append(label)
    return filters


def extract_listing_links(soup: BeautifulSoup, base_url: str, max_ads: int) -> list[str]:
    """Recupere les URLs d'annonces individuelles depuis la page de resultats."""
    links: list[str] = []
    seen: set[str] = set()
    for node in soup.select("a[href]"):
        href = node.get("href", "")
        if not href:
            continue
        absolute = urljoin(base_url, href)
        if re.search(r"/a/voiture-occasion/[^/]+/[^/]+/\d+A1KVVO", absolute):
            if absolute not in seen:
                links.append(absolute)
                seen.add(absolute)
        if len(links) >= max_ads:
            break
    return links


def parse_listing(url: str, html: str, max_ads: int) -> ListingSummary:
    """Parse une page de resultats de recherche ParuVendu."""
    soup = BeautifulSoup(html, "lxml")
    text = text_of(soup)
    result_count = None
    match = re.search(r"([\d\s]+)\s+annonces", text, flags=re.IGNORECASE)
    if match:
        result_count = int(re.sub(r"\D", "", match.group(1)))
    title = None
    if soup.title and soup.title.string:
        title = normalize_space(soup.title.string)
    h1 = soup.find(["h1", "h2"])
    if h1:
        title = normalize_space(h1.get_text(" ", strip=True)) or title

    return ListingSummary(
        url=url,
        title=title,
        result_count=result_count,
        inferred_filters=infer_filters_from_text(text),
        query_tokens=infer_query_tokens(url),
        ad_links=extract_listing_links(soup, url, max_ads=max_ads),
        jsonld_types=parse_jsonld_types(soup),
    )


def extract_with_patterns(text: str) -> dict[str, Any]:
    """Extrait les champs vehicule par regex depuis le texte brut de la page."""
    extracted: dict[str, Any] = {}
    for key, pattern in DETAIL_PATTERNS.items():
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            extracted[key] = normalize_space(match.group(1))
    return extracted


def parse_ad(url: str, html: str) -> AdSummary:
    """Parse une page de detail d'annonce ParuVendu.

    Combine l'extraction JSON-LD (donnees structurees) et regex (texte brut)
    pour maximiser la couverture des champs.
    """
    soup = BeautifulSoup(html, "lxml")
    text = text_of(soup)
    vehicle_jsonld = find_jsonld_vehicle(soup)

    title = None
    if soup.title and soup.title.string:
        title = normalize_space(soup.title.string)
    h1 = soup.find("h1")
    if h1:
        title = normalize_space(h1.get_text(" ", strip=True)) or title

    location = None
    for heading in soup.find_all(["h2", "h3"]):
        candidate = normalize_space(heading.get_text(" ", strip=True))
        if re.search(r"\(\d{5}\)|\b\d{5}\b", candidate):
            location = candidate
            break

    # Detection du type de vendeur par mots-cles dans le texte
    seller_type = None
    if "Vendeur particulier" in text or "Contacter le vendeur particulier" in text:
        seller_type = "particulier"
    elif "Professionnel" in text or "concessionnaire" in text.lower():
        seller_type = "professionnel"

    # ParuVendu inclut parfois des liens vers sa propre cote et ses fiches techniques
    native_cote_links = []
    fiche_links = []
    for node in soup.select("a[href]"):
        href = urljoin(url, node.get("href", ""))
        if "/cote-auto-gratuite/" in href and href not in native_cote_links:
            native_cote_links.append(href)
        if "/fiches-techniques-auto/" in href and href not in fiche_links:
            fiche_links.append(href)

    has_phone_cta = bool(
        re.search(r"Voir le numéro|Contacter par téléphone", text, flags=re.IGNORECASE)
    )
    has_message_cta = bool(
        re.search(r"Envoyer un message|Contacter le vendeur", text, flags=re.IGNORECASE)
    )

    return AdSummary(
        url=url,
        title=title,
        location=location,
        seller_type=seller_type,
        extracted_fields=extract_with_patterns(text),
        structured_fields=extract_jsonld_vehicle_fields(vehicle_jsonld),
        jsonld_types=parse_jsonld_types(soup),
        native_cote_links=native_cote_links,
        fiche_links=fiche_links,
        has_phone_cta=has_phone_cta,
        has_message_cta=has_message_cta,
    )


def build_report(search_url: str, max_ads: int) -> dict[str, Any]:
    """Genere le rapport complet : listing + N annonces detail + analyse."""
    with httpx.Client(headers=HEADERS) as client:
        listing_html = fetch_html(client, search_url)
        listing = parse_listing(search_url, listing_html, max_ads=max_ads)
        if not listing.ad_links:
            raise ProbeError("Aucune annonce détectée dans la page de résultats.")
        ads = []
        for ad_url in listing.ad_links:
            ad_html = fetch_html(client, ad_url)
            ads.append(parse_ad(ad_url, ad_html))

    return {
        "listing": asdict(listing),
        "ads": [asdict(ad) for ad in ads],
        "analysis": {
            "token_hypotheses": {
                "r2": "semble porter le token marque (ex: VVOAU000 pour Audi)",
                "md": "semble porter le token modèle (ex: VVOAUA5 pour Audi A5)",
                "nrj": "code énergie court (DI observé pour diesel)",
                "tr": "code transmission court (AU observé pour automatique)",
                "a0/a1": "bornes année",
                "km0/km1": "bornes kilométrage",
                "pf0/pf1": "bornes puissance fiscale",
                "p": "pagination résultats",
            },
            "extraction_feasibility": {
                "listing_cards_have_text": True,
                "detail_pages_have_structured_sections": True,
                "detail_pages_link_native_cote": True,
                "seller_type_detectable": True,
                "detail_pages_expose_jsonld_vehicle": True,
                "detail_pages_likely_need_dom_or_text_parsing": True,
            },
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--url", default=DEFAULT_SEARCH_URL, help="URL de listing ParuVendu à sonder"
    )
    parser.add_argument(
        "--max-ads", type=int, default=2, help="Nombre maximum d'annonces détail à inspecter"
    )
    parser.add_argument("--pretty", action="store_true", help="Affiche le JSON avec indentation")
    args = parser.parse_args()

    report = build_report(args.url, max_ads=args.max_ads)
    if args.pretty:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
