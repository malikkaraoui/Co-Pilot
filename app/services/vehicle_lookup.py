"""Service de recherche vehicule -- trouve un vehicule dans la base de reference.

Gere les variantes courantes de noms de marques et modeles
(ex. "Clio 5" -> "Clio V", "VW" -> "Volkswagen").
"""

import logging
import unicodedata

from app.models.vehicle import Vehicle

logger = logging.getLogger(__name__)

# Alias de marques courantes -> nom canonique en base
BRAND_ALIASES: dict[str, str] = {
    "vw": "volkswagen",
    "bmw": "bmw",
    "merco": "mercedes",
    "merc": "mercedes",
    "mercedes-benz": "mercedes",
    "mb": "mercedes",
    "mg motor": "mg",
    "hyunday": "hyundai",
    "hundai": "hyundai",
    "seat": "seat",
    "cupra": "cupra",
    "skoda": "skoda",
    "jeep": "jeep",
}

# Alias de modeles courants -> nom canonique en base
MODEL_ALIASES: dict[str, str] = {
    # Renault
    "clio 5": "clio v",
    "clio5": "clio v",
    "clio v": "clio v",
    "renault 5": "5 e-tech",
    "r5": "5 e-tech",
    "r5 e-tech": "5 e-tech",
    "captur 2": "captur",
    "captur ii": "captur",
    "megane 4": "megane",
    "megane iv": "megane",
    "scenic 4": "scenic",
    "scenic iv": "scenic",
    # Peugeot
    "208 ii": "208",
    "2008 ii": "2008",
    "3008 ii": "3008",
    "308 iii": "308",
    "5008 ii": "5008",
    # Citroen
    "c3 iii": "c3",
    "c3 aircross": "c3 aircross",
    "ec3": "e-c3",
    "e c3": "e-c3",
    "c4 iii": "c4",
    "e-c4": "c4",
    # Dacia
    "sandero 3": "sandero",
    "sandero iii": "sandero",
    "duster 2": "duster",
    "duster ii": "duster",
    "duster 3": "duster",
    # Volkswagen
    "golf 7": "golf",
    "golf 8": "golf",
    "golf vii": "golf",
    "golf viii": "golf",
    "polo 6": "polo",
    "polo vi": "polo",
    "t-roc": "t-roc",
    "troc": "t-roc",
    "t roc": "t-roc",
    "t-cross": "t-cross",
    "tcross": "t-cross",
    "t cross": "t-cross",
    "tiguan 2": "tiguan",
    "tiguan ii": "tiguan",
    # Toyota
    "yaris 4": "yaris",
    "yaris iv": "yaris",
    "yaris cross": "yaris cross",
    "c-hr": "c-hr",
    "chr": "c-hr",
    "aygo x": "aygo x",
    "aygox": "aygo x",
    # BMW
    "serie 3": "serie 3",
    "series 3": "serie 3",
    "3er": "serie 3",
    "serie 1": "serie 1",
    "series 1": "serie 1",
    "1er": "serie 1",
    "x1": "x1",
    "ix1": "x1",
    # Fiat
    "500": "500",
    "fiat500": "500",
    # Ford
    "fiesta 7": "fiesta",
    "kuga 3": "kuga",
    "kuga iii": "kuga",
    # Nissan
    "qashqai 3": "qashqai",
    "qashqai iii": "qashqai",
    "juke 2": "juke",
    "juke ii": "juke",
    # Hyundai
    "tucson 4": "tucson",
    "tucson iv": "tucson",
    "kona 2": "kona",
    # Mercedes
    "gla": "gla",
    "classe a": "classe a",
    "class a": "classe a",
    "a-class": "classe a",
    "a-klasse": "classe a",
    # Audi
    "a3": "a3",
    "a3 sportback": "a3",
    # Skoda
    "fabia 4": "fabia",
    "fabia iv": "fabia",
    "octavia 4": "octavia",
    "octavia iv": "octavia",
    # Mini
    "cooper": "cooper",
    "mini cooper": "cooper",
    "cooper s": "cooper",
    "cooper se": "cooper",
    # Kia
    "sportage 5": "sportage",
    "sportage v": "sportage",
    # MG
    "zs": "zs",
    "zs ev": "zs",
    "mg3": "3",
    # Opel
    "corsa f": "corsa",
    "corsa-e": "corsa",
    # Suzuki
    "swift 4": "swift",
    "swift iv": "swift",
    # Tesla
    "model y": "model y",
    "model3": "model 3",
    "modely": "model y",
    # Toyota (nouveaux)
    "corolla 12": "corolla",
    "corolla xii": "corolla",
    "rav4": "rav4",
    "rav 4": "rav4",
    "rav4 5": "rav4",
    # Seat
    "ibiza 5": "ibiza",
    "ibiza v": "ibiza",
    "arona": "arona",
    # Cupra
    "formentor": "formentor",
    # Dacia
    "spring": "spring",
    "spring electric": "spring",
    # Kia (nouveaux)
    "niro 2": "niro",
    "niro ii": "niro",
    "niro hev": "niro",
    "niro phev": "niro",
    "picanto 3": "picanto",
    "picanto iii": "picanto",
    # Opel
    "mokka 2": "mokka",
    "mokka ii": "mokka",
    "mokka-e": "mokka",
    # Volkswagen (nouveaux)
    "id.3": "id.3",
    "id3": "id.3",
    "id 3": "id.3",
    "taigo": "taigo",
    # Skoda (nouveau)
    "kamiq": "kamiq",
    # Peugeot (nouveau)
    "408": "408",
    # Renault (nouveau)
    "espace 6": "espace",
    "espace vi": "espace",
    # Jeep
    "avenger": "avenger",
    # Fiat (nouveau)
    "fiat 600": "600",
    "600e": "600",
    "600 hybrid": "600",
}


def _strip_accents(text: str) -> str:
    """Supprime les accents et diacritiques (ex. Citroën -> Citroen, Škoda -> Skoda)."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _normalize_brand(brand: str) -> str:
    """Normalise le nom de marque : minuscule, sans accents, puis alias."""
    cleaned = _strip_accents(brand.strip().lower())
    return BRAND_ALIASES.get(cleaned, cleaned)


def _normalize_model(model: str) -> str:
    """Normalise le nom de modele : minuscule, sans accents, puis alias."""
    cleaned = _strip_accents(model.strip().lower())
    return MODEL_ALIASES.get(cleaned, cleaned)


def find_vehicle(make: str, model: str) -> Vehicle | None:
    """Recherche un vehicule par marque et modele, insensible a la casse.

    Gere les variations courantes via les tables d'alias
    (ex. "VW" -> "Volkswagen", "Clio 5" -> "Clio V").

    Args:
        make: Marque du vehicule (ex. "Peugeot", "VW").
        model: Nom du modele (ex. "3008", "Clio 5").

    Returns:
        Le Vehicle correspondant ou None.
    """
    brand_norm = _normalize_brand(make)
    model_norm = _normalize_model(model)

    vehicle = Vehicle.query.filter(
        Vehicle.brand.ilike(brand_norm),
        Vehicle.model.ilike(f"%{model_norm}%"),
    ).first()

    if vehicle:
        logger.debug("Found vehicle: %s %s (id=%d)", vehicle.brand, vehicle.model, vehicle.id)
    else:
        logger.debug(
            "Vehicle not found: %s %s (normalized: %s %s)", make, model, brand_norm, model_norm
        )

    return vehicle
