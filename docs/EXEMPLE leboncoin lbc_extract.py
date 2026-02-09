#!/usr/bin/env python3
"""
Leboncoin ad -> extract structured fields from embedded __NEXT_DATA__ JSON.

Usage:
  python lbc_extract.py "https://www.leboncoin.fr/ad/voitures/3130994735"
"""

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import httpx
from bs4 import BeautifulSoup


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.6 Safari/605.1.15"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def fetch_html(url: str, timeout_s: int = 30) -> str:
    with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=timeout_s) as c:
        r = c.get(url)
        r.raise_for_status()
        return r.text


def extract_next_data(html: str) -> Dict[str, Any]:
    soup = BeautifulSoup(html, "lxml")
    tag = soup.find("script", {"id": "__NEXT_DATA__"})
    if not tag or not (tag.string or "").strip():
        raise RuntimeError("No __NEXT_DATA__ script tag found.")
    return json.loads(tag.string)


def deep_get(d: Dict[str, Any], path: str) -> Any:
    cur: Any = d
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def find_ad_payload(next_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Leboncoin pages typically expose the ad data in:
      props.pageProps.ad
    but keep it defensive.
    """
    ad = deep_get(next_data, "props.pageProps.ad")
    if isinstance(ad, dict):
        return ad

    # fallback: scan recursively for a dict that looks like an ad payload
    def walk(x: Any) -> Optional[Dict[str, Any]]:
        if isinstance(x, dict):
            if "attributes" in x and ("price" in x or "subject" in x or "title" in x):
                return x
            for v in x.values():
                hit = walk(v)
                if hit:
                    return hit
        elif isinstance(x, list):
            for v in x:
                hit = walk(v)
                if hit:
                    return hit
        return None

    return walk(next_data)


def normalize_attributes(ad: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert Leboncoin ad.attributes[] into a key->value dict.
    Handles either:
      {"key_label": "...", "value": "..."} or similar
    """
    out: Dict[str, Any] = {}

    attrs = ad.get("attributes") or []
    if not isinstance(attrs, list):
        attrs = []

    for a in attrs:
        if not isinstance(a, dict):
            continue
        key = (
            a.get("key")
            or a.get("key_label")
            or a.get("label")
            or a.get("name")
        )
        val = a.get("value") or a.get("value_label") or a.get("text") or a.get("value_text")
        if isinstance(key, str) and key.strip():
            out[key.strip()] = val

    return out


def coerce_int(x: Any) -> Optional[int]:
    if x is None:
        return None
    if isinstance(x, int):
        return x
    s = str(x)
    m = re.findall(r"\d+", s.replace(" ", ""))
    if not m:
        return None
    try:
        return int("".join(m))
    except ValueError:
        return None


def extract_fields(ad: Dict[str, Any]) -> Dict[str, Any]:
    attrs = normalize_attributes(ad)

    # common top-level
    title = ad.get("subject") or ad.get("title") or ad.get("headline")
    price = None
    if isinstance(ad.get("price"), (int, float)):
        price = int(ad["price"])
    elif isinstance(ad.get("price"), list) and ad["price"] and isinstance(ad["price"][0], (int, float)):
        price = int(ad["price"][0])

    # common labels found in attributes (French)
    make = attrs.get("Marque") or attrs.get("Constructeur") or attrs.get("brand")
    model = attrs.get("Modèle") or attrs.get("modele") or attrs.get("model")
    year_model = attrs.get("Année modèle") or attrs.get("Année") or attrs.get("year")
    mileage = attrs.get("Kilométrage") or attrs.get("kilometrage")
    fuel = attrs.get("Énergie") or attrs.get("Energie") or attrs.get("Carburant")
    gearbox = attrs.get("Boîte de vitesse") or attrs.get("Boite de vitesse") or attrs.get("Transmission")
    doors = attrs.get("Nombre de portes")
    seats = attrs.get("Nombre de place(s)") or attrs.get("Nombre de places")
    first_reg = attrs.get("Date de première mise en circulation") or attrs.get("Mise en circulation")
    color = attrs.get("Couleur")
    power_fiscal = attrs.get("Puissance fiscale")
    power_din = attrs.get("Puissance DIN")

    service_history = attrs.get("Historique et entretien")

    return {
        "title": title,
        "price_eur": price,
        "make": make,
        "model": model,
        "year_model": str(year_model) if year_model is not None else None,
        "mileage_km": coerce_int(mileage),
        "fuel": fuel,
        "gearbox": gearbox,
        "doors": coerce_int(doors),
        "seats": coerce_int(seats),
        "first_registration": first_reg,
        "color": color,
        "power_fiscal_cv": coerce_int(power_fiscal),
        "power_din_hp": coerce_int(power_din),
        "service_history": service_history,
        "raw_attributes": attrs,  # utile pour debug/coverage
    }


def main(url: str) -> Tuple[Path, Path]:
    outdir = Path("out")
    outdir.mkdir(exist_ok=True)

    html = fetch_html(url)
    html_path = outdir / f"raw_{re.sub(r'[^a-zA-Z0-9]+', '_', url).strip('_')}.html"
    html_path.write_text(html, encoding="utf-8")

    next_data = extract_next_data(html)
    next_path = outdir / f"nextdata_{re.sub(r'[^a-zA-Z0-9]+', '_', url).strip('_')}.json"
    next_path.write_text(json.dumps(next_data, ensure_ascii=False, indent=2), encoding="utf-8")

    ad = find_ad_payload(next_data)
    if not ad:
        raise RuntimeError("Could not locate ad payload in __NEXT_DATA__.")

    fields = extract_fields(ad)
    fields_path = outdir / "keyinfo_extracted.json"
    fields_path.write_text(json.dumps(fields, ensure_ascii=False, indent=2), encoding="utf-8")

    print("OK RAW :", html_path)
    print("OK NEXT:", next_path)
    print("OK OUT :", fields_path)
    print("FIELDS :", fields)
    return html_path, fields_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python lbc_extract.py <leboncoin_ad_url>")
        sys.exit(1)
    main(sys.argv[1])
