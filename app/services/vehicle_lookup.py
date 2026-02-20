"""Service de recherche vehicule -- trouve un vehicule dans la base de reference.

Gere les variantes courantes de noms de marques et modeles
(ex. "Clio 5" -> "Clio V", "VW" -> "Volkswagen").
"""

import logging
import unicodedata

from app.models.vehicle import Vehicle

logger = logging.getLogger(__name__)

# Modeles generiques LBC : le vendeur n'a pas precise le modele exact.
# Ces valeurs ne correspondent pas a un vrai vehicule et doivent etre ignorees.
GENERIC_MODELS: frozenset[str] = frozenset(
    {
        "autres",
        "autre",
        "other",
        "divers",
    }
)


def is_generic_model(model: str) -> bool:
    """True si le modele est un placeholder generique LBC (ex. 'Autres')."""
    return _strip_accents(model.strip().lower()) in GENERIC_MODELS


# Alias de marques courantes -> nom canonique en base.
# IMPORTANT : cette table est la CLE de la reconnaissance vehicule.
# Chaque marque doit pointer vers son nom canonique en minuscules.
# LBC envoie des noms varies (tirets, espaces, casse differente).
BRAND_ALIASES: dict[str, str] = {
    # ── Marques francaises ──
    "peugeot": "peugeot",
    "renault": "renault",
    "citroen": "citroen",
    "citroën": "citroen",
    "ds": "ds",
    "ds automobiles": "ds",
    "dacia": "dacia",
    "alpine": "alpine",
    "bugatti": "bugatti",
    # ── Marques allemandes ──
    "volkswagen": "volkswagen",
    "vw": "volkswagen",
    "bmw": "bmw",
    "mercedes": "mercedes",
    "mercedes-benz": "mercedes",
    "merco": "mercedes",
    "merc": "mercedes",
    "mb": "mercedes",
    "audi": "audi",
    "porsche": "porsche",
    "opel": "opel",
    "smart": "smart",
    # ── Marques japonaises ──
    "toyota": "toyota",
    "honda": "honda",
    "nissan": "nissan",
    "mazda": "mazda",
    "suzuki": "suzuki",
    "mitsubishi": "mitsubishi",
    "subaru": "subaru",
    "lexus": "lexus",
    "infiniti": "infiniti",
    # ── Marques coreennes ──
    "hyundai": "hyundai",
    "hyunday": "hyundai",
    "hundai": "hyundai",
    "kia": "kia",
    "ssangyong": "ssangyong",
    "genesis": "genesis",
    # ── Marques italiennes ──
    "fiat": "fiat",
    "alfa romeo": "alfa romeo",
    "alfa-romeo": "alfa romeo",
    "alfaromeo": "alfa romeo",
    "alfa": "alfa romeo",
    "maserati": "maserati",
    "lamborghini": "lamborghini",
    "ferrari": "ferrari",
    "lancia": "lancia",
    "abarth": "abarth",
    # ── Marques britanniques ──
    "land rover": "land rover",
    "land-rover": "land rover",
    "landrover": "land rover",
    "jaguar": "jaguar",
    "mini": "mini",
    "bentley": "bentley",
    "aston martin": "aston martin",
    "aston-martin": "aston martin",
    "astonmartin": "aston martin",
    "rolls royce": "rolls royce",
    "rolls-royce": "rolls royce",
    "rollsroyce": "rolls royce",
    "mclaren": "mclaren",
    "lotus": "lotus",
    "mg": "mg",
    "mg motor": "mg",
    # ── Marques espagnoles ──
    "seat": "seat",
    "cupra": "cupra",
    # ── Marques tcheques ──
    "skoda": "skoda",
    "škoda": "skoda",
    # ── Marques americaines ──
    "ford": "ford",
    "jeep": "jeep",
    "tesla": "tesla",
    "chevrolet": "chevrolet",
    "dodge": "dodge",
    "chrysler": "chrysler",
    "cadillac": "cadillac",
    "lincoln": "lincoln",
    "gmc": "gmc",
    # ── Marques suedoises ──
    "volvo": "volvo",
    # ── Marques chinoises (croissance rapide en France) ──
    "byd": "byd",
    "aiways": "aiways",
    "nio": "nio",
    "xpeng": "xpeng",
    "leapmotor": "leapmotor",
    "seres": "seres",
    # ── Marques indiennes/autres ──
    "tata": "tata",
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
    # Mercedes -- nomenclature harmonisee 2015+
    # Berlines : Classe A/B/C/E
    "classe a": "classe a",
    "class a": "classe a",
    "a-class": "classe a",
    "a-klasse": "classe a",
    "classe b": "classe b",
    "class b": "classe b",
    "b-class": "classe b",
    "b-klasse": "classe b",
    "classe c": "classe c",
    "class c": "classe c",
    "c-class": "classe c",
    "c-klasse": "classe c",
    "classe e": "classe e",
    "class e": "classe e",
    "e-class": "classe e",
    "e-klasse": "classe e",
    # SUV : GLA/GLB/GLC/GLE
    "gla": "gla",
    "classe gla": "gla",
    "gla-class": "gla",
    "glb": "glb",
    "classe glb": "glb",
    "glb-class": "glb",
    "glc": "glc",
    "classe glc": "glc",
    "glc coupe": "glc",
    "glc-class": "glc",
    "gle": "gle",
    "classe gle": "gle",
    "gle coupe": "gle",
    "gle-class": "gle",
    # Coupe 4 portes
    "cla": "cla",
    "classe cla": "cla",
    "cla coupe": "cla",
    "cla-class": "cla",
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
    # DS (LBC envoie "DS 3", CSV a "3")
    "ds 3": "3",
    "ds3": "3",
    "ds 3 crossback": "3 crossback",
    "ds3 crossback": "3 crossback",
    "ds 4": "4",
    "ds4": "4",
    "ds 7": "7",
    "ds7": "7",
    "ds 7 crossback": "7 crossback",
    "ds7 crossback": "7 crossback",
    "ds 9": "9",
    "ds9": "9",
    # Land Rover
    "range rover velar": "range rover velar",
    "range rover evoque": "range rover evoque",
    "range rover sport": "range rover sport",
    "range rover": "range rover",
    "defender": "defender",
    "discovery": "discovery",
    "discovery sport": "discovery sport",
    # Honda
    "civic 11": "civic",
    "civic xi": "civic",
    "hr-v": "hr-v",
    "hrv": "hr-v",
    "jazz 4": "jazz",
    "jazz iv": "jazz",
    # Porsche
    "macan": "macan",
    "cayenne": "cayenne",
    "panamera": "panamera",
    "taycan": "taycan",
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
        Vehicle.model.ilike(model_norm),
    ).first()

    if vehicle:
        logger.debug("Found vehicle: %s %s (id=%d)", vehicle.brand, vehicle.model, vehicle.id)
    else:
        logger.debug(
            "Vehicle not found: %s %s (normalized: %s %s)", make, model, brand_norm, model_norm
        )

    return vehicle
