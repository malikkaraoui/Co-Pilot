"""Service de recherche vehicule -- trouve un vehicule dans la base de reference.

Gere les variantes courantes de noms de marques et modeles
(ex. "Clio 5" -> "Clio V", "VW" -> "Volkswagen").
"""

import logging
import re
from functools import lru_cache

from app.models.vehicle import Vehicle
from app.services.vehicle_lookup_keys import (
    lookup_compact_key,
    lookup_keys,
    normalize_canonical_text,
    strip_accents,
)

logger = logging.getLogger(__name__)

# Modeles generiques LBC : le vendeur n'a pas precise le modele exact.
# Ces valeurs ne correspondent pas a un vrai vehicule et doivent etre ignorees.
GENERIC_MODELS: frozenset[str] = frozenset(
    {
        "autres",
        "autre",
        "other",
        "divers",
        "modele",  # placeholder "Marque / Modele"
        "marque",  # placeholder "Marque / Modele"
    }
)

# Marques generiques/placeholder vues dans certains scans (ex. formulaire incomplet).
# Ces valeurs ne correspondent pas a de vraies marques et doivent etre ignorees.
GENERIC_BRANDS: frozenset[str] = frozenset(
    {
        "marque",
        "autres",
        "autre",
        "other",
        "divers",
        "unknown",
        "n/a",
        "na",
    }
)

# Faux modeles par marque : gammes, carrosseries, ou noms de marque repetes.
# Cle = marque canonique (minuscules), valeur = set de faux modeles (minuscules, sans accents).
# Sources verifiees : structure BMW (Serie = gamme), VW (Multivan/Caravelle/Combi = gamme T),
# Mercedes (Benz = partie du nom de marque).
INVALID_MODELS_BY_BRAND: dict[str, frozenset[str]] = {
    # BMW: "Serie X" sont les noms officiels sur LBC et La Centrale.
    # Ils existent dans le referentiel vehicule comme modeles valides.
    # Pas de faux modeles connus pour BMW.
    "bmw": frozenset(),
    "volkswagen": frozenset(
        {
            "multivan",  # gamme T (T5/T6/T7)
            "caravelle",  # gamme T
            "combi",  # gamme T
            "vw",  # nom de marque repete en modele
            "volkswagen",
        }
    ),
    "mercedes": frozenset(
        {
            "benz",  # partie du nom de marque
            "mercedes",  # nom de marque repete
            "mercddes",  # faute de frappe courante
            "mersedes",  # faute de frappe courante
            "mercedes-benz",
        }
    ),
    "audi": frozenset(
        {
            "allroad",  # variante de carrosserie, pas un modele (A4 Allroad, A6 Allroad)
        }
    ),
    "land rover": frozenset(
        {
            "range",  # incomplet — le vrai modele est "Range Rover" ou "Range Rover Sport"
        }
    ),
}


def is_generic_model(model: str, make: str = "") -> bool:
    """True si le modele est un placeholder generique ou un faux modele pour cette marque.

    Verifie d'abord les generiques universels (Autres, Divers...),
    puis les faux modeles specifiques a la marque (Serie 3 pour BMW, etc.).
    """
    normalized = _strip_accents(model.strip().lower())
    if normalized in GENERIC_MODELS:
        return True

    if make:
        brand_key = _strip_accents(make.strip().lower())
        # Resoudre l'alias de marque pour matcher la cle du dictionnaire
        brand_canonical = BRAND_ALIASES.get(brand_key, brand_key)
        invalid_models = INVALID_MODELS_BY_BRAND.get(brand_canonical, frozenset())
        if normalized in invalid_models:
            return True

    return False


def is_generic_brand(brand: str) -> bool:
    """True si la marque est un placeholder generique (Marque/Autres/etc.)."""
    normalized = _strip_accents(brand.strip().lower())
    return normalized in GENERIC_BRANDS


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
    "vw": "volkswagen",
    "bmw": "bmw",
    "mercedes-benz": "mercedes",
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
    "grand c4 spacetourer": "c4 spacetourer",
    "c4 grand spacetourer": "c4 spacetourer",
    "c4 grand space tourer": "c4 spacetourer",
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
    "golf variant": "golf",
    "golf vairant": "golf",
    "golf alltrack": "golf",
    "golf variant alltrack": "golf",
    "golf vii variant": "golf",
    "golf viii variant": "golf",
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
    "transit": "transit",
    "transit custom": "transit custom",
    "transit connect": "transit connect",
    "transit courier": "transit courier",
    "fourgon": "transit",
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
    return strip_accents(text)


def _lookup_compact_key(text: str) -> str:
    """Clé compacte pour matcher des variantes comme `C-HR`, `C HR`, `CHR`."""
    return lookup_compact_key(text)


def _lookup_keys(text: str) -> tuple[str, ...]:
    """Retourne les clés lookup utiles pour résoudre un alias ou comparer deux valeurs."""
    return lookup_keys(text)


def _build_alias_lookup(aliases: dict[str, str]) -> dict[str, str]:
    """Construit un index d'alias robuste aux variantes typographiques."""
    lookup: dict[str, str] = {}
    for raw_key, canonical in aliases.items():
        for variant in (raw_key, canonical):
            for key in _lookup_keys(variant):
                lookup.setdefault(key, canonical)
    return lookup


def _resolve_alias(text: str, lookup: dict[str, str]) -> str | None:
    """Résout un alias à partir des différentes clés lookup dérivées du texte."""
    for key in _lookup_keys(text):
        canonical = lookup.get(key)
        if canonical:
            return canonical
    return None


def _match_key(text: str) -> str:
    """Clé de comparaison compacte, stable et accent-insensitive."""
    return _lookup_compact_key(text)


def brand_lookup_key(brand: str) -> str:
    """Clé persistable de marque pour matching exact robuste."""
    return _match_key(normalize_brand(brand))


def model_lookup_key(model: str) -> str:
    """Clé persistable de modèle pour matching exact robuste."""
    return _match_key(normalize_model(model))


def build_vehicle_lookup_keys(brand: str, model: str) -> tuple[str, str]:
    """Construit les lookup keys persistées d'un véhicule."""
    return brand_lookup_key(brand), model_lookup_key(model)


@lru_cache(maxsize=1)
def _brand_alias_lookup() -> dict[str, str]:
    return _build_alias_lookup(BRAND_ALIASES)


@lru_cache(maxsize=1)
def _model_alias_lookup() -> dict[str, str]:
    return _build_alias_lookup(MODEL_ALIASES)


def normalize_brand(brand: str) -> str:
    """Normalise le nom de marque : minuscule, sans accents, puis alias.

    C'est la forme canonique pour les COMPARAISONS (lowercase).
    Pour l'affichage, utiliser ``display_brand()``.
    """
    cleaned = normalize_canonical_text(brand)
    return _resolve_alias(brand, _brand_alias_lookup()) or cleaned


# Compat : ancien nom prive, utilise dans les tests et admin/routes
_normalize_brand = normalize_brand


def normalize_model(model: str) -> str:
    """Normalise le nom de modele : minuscule, sans accents, puis alias.

    C'est la forme canonique pour les COMPARAISONS (lowercase).
    Pour l'affichage, utiliser ``display_model()``.
    """
    cleaned = normalize_canonical_text(model)
    aliased = _resolve_alias(model, _model_alias_lookup())
    if aliased:
        return aliased

    # Heuristique légère: retirer un suffixe de génération en chiffres romains
    # (ex: "leon iv" -> "leon"), sans impacter les alias explicites ci-dessus.
    parts = cleaned.split()
    if len(parts) >= 2 and re.fullmatch(r"[ivx]{1,5}", parts[-1]):
        candidate = " ".join(parts[:-1]).strip()
        if candidate:
            return _resolve_alias(candidate, _model_alias_lookup()) or candidate

    return cleaned


# Compat : ancien nom prive
_normalize_model = normalize_model


# ── Formes d'affichage canoniques ────────────────────────────────
# Quand la conversion .title() ne suffit pas (sigles, casse mixte),
# on utilise ces dicts pour produire la bonne forme visuelle.

BRAND_DISPLAY: dict[str, str] = {
    "bmw": "BMW",
    "ds": "DS",
    "mg": "MG",
    "byd": "BYD",
    "gmc": "GMC",
    "nio": "NIO",
    "kia": "Kia",
    "mercedes": "Mercedes",
    "land rover": "Land Rover",
    "alfa romeo": "Alfa Romeo",
    "aston martin": "Aston Martin",
    "rolls royce": "Rolls Royce",
}

MODEL_DISPLAY: dict[str, str] = {
    "rs3": "RS3",
    "ds4": "DS4",
    "ds3": "DS3",
    "e-c3": "e-C3",
    "c4 spacetourer": "C4 SpaceTourer",
    "ds 3": "DS 3",
    "500x": "500x",
    "zs": "ZS",
    "cla": "CLA",
    "gla": "GLA",
    "glb": "GLB",
    "glc": "GLC",
    "gle": "GLE",
    "classe glc": "Classe GLC",
    "classe gla": "Classe GLA",
    "classe a": "Classe A",
    "classe b": "Classe B",
    "classe c": "Classe C",
    "classe e": "Classe E",
    "ix3": "iX3",
    "c-hr": "C-HR",
    "rav4": "RAV4",
    "id.3": "ID.3",
    "hr-v": "HR-V",
    "t-roc": "T-Roc",
    "t-cross": "T-Cross",
    "5 e-tech": "5 E-Tech",
    "clio v": "Clio V",
    "serie 1": "Serie 1",
    "serie 3": "Serie 3",
    "model 3": "Model 3",
    "model y": "Model Y",
    "3": "3",
    "4": "4",
    "7": "7",
    "9": "9",
    "3 crossback": "3 Crossback",
    "7 crossback": "7 Crossback",
    "range rover velar": "Range Rover Velar",
    "range rover evoque": "Range Rover Evoque",
    "range rover sport": "Range Rover Sport",
    "range rover": "Range Rover",
    "yaris cross": "Yaris Cross",
    "aygo x": "Aygo X",
    "c3 aircross": "C3 Aircross",
    "discovery sport": "Discovery Sport",
    "transit connect": "Transit Connect",
    "transit courier": "Transit Courier",
    "transit custom": "Transit Custom",
}


def display_brand(brand: str) -> str:
    """Forme d'affichage canonique d'une marque.

    Applique la normalisation (alias) puis met en forme :
    ``"land-rover"`` -> ``"Land Rover"``, ``"VW"`` -> ``"Volkswagen"``.
    """
    norm = normalize_brand(brand)
    if norm in BRAND_DISPLAY:
        return BRAND_DISPLAY[norm]
    return norm.title()


def display_model(model: str) -> str:
    """Forme d'affichage canonique d'un modele.

    Applique la normalisation (alias) puis met en forme :
    ``"chr"`` -> ``"C-HR"``, ``"id3"`` -> ``"ID.3"``.
    """
    norm = normalize_model(model)
    if norm in MODEL_DISPLAY:
        return MODEL_DISPLAY[norm]
    return norm.title()


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
    brand_norm = normalize_brand(make)
    model_norm = normalize_model(model)
    brand_key, model_key = build_vehicle_lookup_keys(make, model)

    vehicle = (
        Vehicle.query.filter(
            Vehicle.brand_lookup_key == brand_key,
            Vehicle.model_lookup_key == model_key,
        )
        .order_by(Vehicle.id.asc())
        .first()
    )

    if vehicle:
        logger.debug("Found vehicle: %s %s (id=%d)", vehicle.brand, vehicle.model, vehicle.id)
    else:
        brand_key = _match_key(brand_norm)
        model_key = _match_key(model_norm)
        for candidate in Vehicle.query.all():
            if _match_key(normalize_brand(candidate.brand)) != brand_key:
                continue
            if _match_key(normalize_model(candidate.model)) != model_key:
                continue

            logger.debug(
                "Found vehicle via resilient lookup: %s %s (id=%d)",
                candidate.brand,
                candidate.model,
                candidate.id,
            )
            return candidate

        logger.debug(
            "Vehicle not found: %s %s (normalized: %s %s)", make, model, brand_norm, model_norm
        )

    return vehicle
