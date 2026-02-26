"""Service d'extraction des donnees structurees d'une annonce Leboncoin.

Analyse le payload JSON __NEXT_DATA__ et extrait les champs de l'annonce vehicule.
Base sur le script original lbc_extract.py, reecrit selon les patterns Co-Pilot.
"""

import logging
import re
from datetime import datetime, timezone
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
    """Localise le payload de l'annonce dans __NEXT_DATA__.

    Utilise le chemin standard Next.js en priorite, puis un fallback
    restrictif qui exige list_id pour eviter de matcher des annonces
    provenant de listes de resultats ou de recommandations.
    """
    ad = _deep_get(next_data, "props.pageProps.ad")
    if isinstance(ad, dict):
        return ad

    # Fallback : recherche recursive d'un dict qui ressemble a une annonce.
    # On exige list_id (identifiant unique d'annonce Leboncoin) pour eviter
    # de matcher des annonces issues de listes / recommandations.
    def _walk(node: Any) -> dict | None:
        if isinstance(node, dict):
            has_attributes = "attributes" in node
            has_identity = "list_id" in node or "ad_id" in node
            has_content = "price" in node or "subject" in node
            if has_attributes and has_identity and has_content:
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

    result = _walk(next_data)
    if result:
        logger.info("Ad payload found via fallback walker (list_id=%s)", result.get("list_id"))
    return result


def _normalize_attributes(ad: dict) -> dict[str, Any]:
    """Convertit ad.attributes[] de Leboncoin en dictionnaire plat cle->valeur.

    Stocke chaque attribut sous sa cle machine (``key``, ex. ``vehicule_color``)
    ET sous son label francais (``key_label``, ex. ``Couleur vehicule``) quand
    il est disponible.  Prefere ``value_label`` (texte lisible) a ``value``
    (parfois un code encode, ex. fuel=8 pour Hybride Rechargeable).
    """
    out: dict[str, Any] = {}
    attrs = ad.get("attributes") or []
    if not isinstance(attrs, list):
        return out

    for attr in attrs:
        if not isinstance(attr, dict):
            continue
        key = attr.get("key") or attr.get("key_label") or attr.get("label") or attr.get("name")
        # Preferer value_label (lisible) a value (parfois encode)
        val = (
            attr.get("value_label")
            or attr.get("value")
            or attr.get("text")
            or attr.get("value_text")
        )
        if isinstance(key, str) and key.strip():
            out[key.strip()] = val
            # Stocker aussi sous key_label pour que les lookups par nom francais marchent.
            # IMPORTANT : first-wins -- si un key_label est deja present (ex: deux attributs
            # avec key_label="Modèle"), on garde la premiere valeur pour eviter qu'un
            # attribut secondaire (ex: modele detaille "A6 Allroad") ecrase le modele
            # de base ("A6") utilise par le reste du pipeline.
            key_label = attr.get("key_label")
            if key_label and isinstance(key_label, str) and key_label.strip() != key.strip():
                lbl = key_label.strip()
                if lbl not in out:
                    out[lbl] = val

    return out


# Modeles generiques LBC : le vendeur n'a pas choisi de modele specifique,
# ou LBC ne connait pas encore ce modele dans sa liste.
_GENERIC_MODELS = frozenset({"autres", "autre", "other", "divers"})

# Mots parasites a retirer du titre lors de l'extraction du modele
_TITLE_NOISE = frozenset(
    {
        "neuf",
        "neuve",
        "occasion",
        "tbe",
        "garantie",
        "garantié",
        "full",
        "options",
        "option",
        "pack",
        "premium",
        "edition",
        "limited",
        "sport",
        "line",
        "style",
        "business",
        "confort",
        "first",
        "life",
        "zen",
        "intens",
        "intense",
        "initiale",
        "paris",
        "riviera",
        "alpine",
        "esprit",
        "techno",
        "evolution",
        "iconic",
        "rs",
        "gt",
        "gtline",
        "gt-line",
    }
)


def _extract_model_from_title(title: str, make: str) -> str | None:
    """Tente d'extraire le nom du modele depuis le titre de l'annonce.

    Quand LBC met 'Autres' comme modele, le vrai nom est souvent dans le titre :
    'Renault Symbioz Esprit Alpine 2025' → 'Symbioz'
    'Peugeot E-5008 GT 2025' → 'E-5008'

    Retourne le premier mot significatif apres la marque, ou None.
    """
    if not title or not make:
        return None

    # Retirer la marque du debut du titre (case-insensitive)
    cleaned = title.strip()
    make_lower = make.strip().lower()
    if cleaned.lower().startswith(make_lower):
        cleaned = cleaned[len(make_lower) :].strip()

    # Retirer l'annee (4 chiffres)
    cleaned = re.sub(r"\b(19|20)\d{2}\b", "", cleaned).strip()

    # Prendre le premier mot non-parasite, non-numerique
    for word in cleaned.split():
        word_clean = word.strip(" ,-./()").strip()
        if not word_clean:
            continue
        if word_clean.lower() in _TITLE_NOISE:
            continue
        if word_clean.isdigit():
            continue
        return word_clean

    return None


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


def _parse_date_str(raw: str) -> datetime | None:
    """Parse une date ISO 8601 LBC en datetime UTC."""
    try:
        cleaned = raw.replace("T", " ").split("+")[0].strip()
        return datetime.strptime(cleaned[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _extract_publication_dates(ad: dict) -> dict:
    """Extrait les dates de publication et calcule l'anciennete.

    LBC fournit deux dates :
    - ``first_publication_date`` : date de premiere mise en ligne (la vraie anciennete)
    - ``index_date`` : date de derniere republication (ce que LBC affiche a l'utilisateur)

    Un vendeur peut republier son annonce pour apparaitre "frais". Co-Pilot
    utilise first_publication_date pour calculer la vraie duree en vente.
    """
    now = datetime.now(timezone.utc)

    first_pub = ad.get("first_publication_date")
    index_date = ad.get("index_date")

    # Premiere publication (la vraie anciennete)
    first_dt = _parse_date_str(first_pub) if isinstance(first_pub, str) else None
    days_online = max((now - first_dt).days, 0) if first_dt else None

    # Derniere republication (ce que LBC montre)
    index_dt = _parse_date_str(index_date) if isinstance(index_date, str) else None
    days_since_refresh = max((now - index_dt).days, 0) if index_dt else None

    # Detecter si l'annonce a ete republiee (dates differentes)
    republished = False
    if first_dt and index_dt and (index_dt - first_dt).days > 1:
        republished = True

    return {
        "publication_date": first_pub,
        "days_online": days_online,
        "index_date": index_date if index_date != first_pub else None,
        "days_since_refresh": days_since_refresh if republished else None,
        "republished": republished,
    }


def _extract_price(ad: dict) -> int | None:
    """Extrait le prix depuis les donnees de premier niveau de l'annonce."""
    price = ad.get("price")
    if isinstance(price, (int, float)):
        return int(price)
    if isinstance(price, list) and price and isinstance(price[0], (int, float)):
        return int(price[0])
    return None


def _normalize_region(region: str | None) -> str | None:
    """Normalise les noms de regions LBC vers les noms post-reforme 2016.

    LBC envoie parfois les anciens noms (ex. 'Aquitaine' au lieu de
    'Nouvelle-Aquitaine'), ce qui casse le matching argus et market price.
    """
    if not region:
        return None
    _OLD_TO_NEW: dict[str, str] = {
        "aquitaine": "Nouvelle-Aquitaine",
        "limousin": "Nouvelle-Aquitaine",
        "poitou-charentes": "Nouvelle-Aquitaine",
        "alsace": "Grand Est",
        "lorraine": "Grand Est",
        "champagne-ardenne": "Grand Est",
        "nord-pas-de-calais": "Hauts-de-France",
        "picardie": "Hauts-de-France",
        "languedoc-roussillon": "Occitanie",
        "midi-pyrenees": "Occitanie",
        "midi-pyrénées": "Occitanie",
        "bourgogne": "Bourgogne-Franche-Comte",
        "franche-comte": "Bourgogne-Franche-Comte",
        "franche-comté": "Bourgogne-Franche-Comte",
        "haute-normandie": "Normandie",
        "basse-normandie": "Normandie",
        "auvergne": "Auvergne-Rhone-Alpes",
        "rhone-alpes": "Auvergne-Rhone-Alpes",
        "rhône-alpes": "Auvergne-Rhone-Alpes",
        "provence-alpes-cote d'azur": "Provence-Alpes-Cote d'Azur",
        "paca": "Provence-Alpes-Cote d'Azur",
    }
    return _OLD_TO_NEW.get(region.strip().lower(), region)


def _extract_location(ad: dict) -> dict[str, Any]:
    """Extrait les informations de localisation de l'annonce."""
    location = ad.get("location") or {}
    raw_region = location.get("region_name") or location.get("region")
    return {
        "city": location.get("city"),
        "zipcode": location.get("zipcode"),
        "department": location.get("department_name"),
        "region": _normalize_region(raw_region),
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


def _extract_lbc_estimation(ad: dict) -> dict | None:
    """Extrait l'estimation de prix LeBonCoin (fourchette argus affichee sur la page).

    LBC peut fournir un champ price_rating/estimation dans l'objet ad avec
    les bornes low/high de la fourchette. Retourne None si absent.
    """
    for key in ("price_rating", "estimation", "price_tips", "price_estimate"):
        rating = ad.get(key)
        if isinstance(rating, dict):
            low = rating.get("low") or rating.get("price_low") or rating.get("min")
            high = rating.get("high") or rating.get("price_high") or rating.get("max")
            if low and high:
                try:
                    return {"low": int(low), "high": int(high)}
                except (ValueError, TypeError):
                    continue
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

    # Images : LBC utilise un dict {nb_images, urls, urls_thumb, urls_large}
    images_data = ad.get("images") or {}
    if isinstance(images_data, dict):
        image_count = images_data.get("nb_images") or len(images_data.get("urls") or [])
    elif isinstance(images_data, list):
        image_count = len(images_data)
    else:
        image_count = 0

    # Telephone : LBC ne fournit pas le numero dans __NEXT_DATA__,
    # seulement has_phone (bool). On l'extrait pour L9.
    has_phone = bool(ad.get("has_phone"))

    # Options payantes LBC (urgent, a la une, boost)
    options = ad.get("options") or ad.get("ad_options") or {}
    has_urgent = bool(options.get("urgent") or options.get("is_urgent") or ad.get("urgent"))
    has_highlight = bool(
        options.get("highlight") or options.get("is_highlight") or ad.get("highlight")
    )
    has_boost = bool(options.get("boost") or options.get("is_boost") or ad.get("boost"))

    # Dates de publication (premiere + derniere republication)
    pub_dates = _extract_publication_dates(ad)

    # Priorite : cle machine d'abord (coherent avec extractVehicleFromNextData cote extension)
    # Cela evite les incoherences quand LBC envoie deux attributs avec le meme key_label.
    make = attrs.get("brand") or attrs.get("Marque")
    model_raw = attrs.get("model") or attrs.get("Modèle") or attrs.get("modele")

    # Fallback : si LBC renvoie un modele generique ("Autres"), on tente
    # d'extraire le vrai nom depuis le titre de l'annonce.
    if model_raw and model_raw.strip().lower() in _GENERIC_MODELS and title and make:
        extracted = _extract_model_from_title(title, make)
        if extracted:
            logger.info(
                "Generic model '%s' replaced by '%s' (from title '%s')", model_raw, extracted, title
            )
            model_raw = extracted

    # Normalisation canonique : forme d'affichage coherente pour toute la chaine
    # (ScanLog, filtres, reponse API). Evite les doublons "transit"/"TRANSIT"/"Transit".
    from app.services.vehicle_lookup import display_brand, display_model

    if make:
        make = display_brand(make)
    if model_raw:
        model_raw = display_model(model_raw)

    result = {
        "title": title,
        "price_eur": price,
        "make": make,
        "model": model_raw,
        "year_model": str(y)
        if (
            y := (
                attrs.get("Année modèle")
                or attrs.get("Année")
                or attrs.get("year")
                or attrs.get("regdate")
            )
        )
        is not None
        else None,
        "mileage_km": _coerce_int(
            attrs.get("Kilométrage") or attrs.get("kilometrage") or attrs.get("mileage")
        ),
        "fuel": (
            attrs.get("Énergie")
            or attrs.get("Energie")
            or attrs.get("Carburant")
            or attrs.get("fuel")
        ),
        "gearbox": (
            attrs.get("Boîte de vitesse")
            or attrs.get("Boite de vitesse")
            or attrs.get("Transmission")
            or attrs.get("gearbox")
        ),
        "doors": _coerce_int(attrs.get("Nombre de portes")),
        "seats": _coerce_int(attrs.get("Nombre de place(s)") or attrs.get("Nombre de places")),
        "first_registration": (
            attrs.get("Date de première mise en circulation") or attrs.get("Mise en circulation")
        ),
        "color": attrs.get("Couleur") or attrs.get("vehicule_color") or attrs.get("color"),
        "power_fiscal_cv": _coerce_int(attrs.get("Puissance fiscale")),
        "power_din_hp": _coerce_int(attrs.get("Puissance DIN")),
        "location": location,
        "phone": phone,
        "description": description,
        "owner_type": owner_type,
        "owner_name": owner_name,
        "siret": siret,
        "raw_attributes": attrs,
        "image_count": image_count,
        "has_phone": has_phone,
        "has_urgent": has_urgent,
        "has_highlight": has_highlight,
        "has_boost": has_boost,
        "publication_date": pub_dates["publication_date"],
        "days_online": pub_dates["days_online"],
        "index_date": pub_dates["index_date"],
        "days_since_refresh": pub_dates["days_since_refresh"],
        "republished": pub_dates["republished"],
        "lbc_estimation": _extract_lbc_estimation(ad),
    }

    logger.info(
        "Extracted ad: %s %s %s - %s EUR",
        result.get("make"),
        result.get("model"),
        result.get("year_model"),
        result.get("price_eur"),
    )
    return result
