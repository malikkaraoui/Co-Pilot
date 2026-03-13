"""Categories de vehicules et km attendus par categorie.

Savoir metier : une citadine fait moins de km/an qu'un SUV familial.
Sources km/an : moyennes nationales INSEE / SDES (enquete mobilite).

Sportives/super-sportives : ~5 000 km/an.
Ces vehicules sont utilises en loisir, pas au quotidien.
Un km faible est normal et meme souhaitable.

Ce module est utilise par L3 (coherence km) pour adapter les attentes
de kilometrage a la categorie du vehicule. Ca evite de lever des faux
positifs du type "Porsche 911 avec 20 000 km en 4 ans = suspect".
"""

# km/an moyens par categorie
# Ces valeurs sont des medianes observees, pas des bornes strictes.
# L3 applique une tolerance de 50% autour de ces valeurs.
KM_PER_YEAR = {
    "citadine": 10000,
    "compacte": 13000,
    "suv_compact": 15000,
    "suv_familial": 17000,
    "familiale": 17000,
    "berline": 18000,
    "electrique": 12000,
    "utilitaire": 20000,
    "voiture_sans_permis": 6000,
    "sportive": 5000,
    # SUVs premium / grands routiers : concus pour avaler les km
    # Cayenne, Touareg, X5, X6, Q7, GLE... font 20-25 000 km/an sans probleme
    "suv_premium": 22000,
}

# Seuils de puissance pour considerer un vehicule comme sportive/super-sportive.
# >400 CV DIN ou >45 CV fiscaux : ces voitures roulent peu (loisir, circuit).
SPORTIVE_DIN_HP_THRESHOLD = 400
SPORTIVE_FISCAL_HP_THRESHOLD = 45

# Marques typiques de voitures sans permis (quadricycles legers).
# Detection par marque car la puissance fiscale n'est pas toujours renseignee.
VSP_BRANDS: frozenset[str] = frozenset(
    {
        "aixam",
        "ligier",
        "microcar",
        "chatenet",
        "bellier",
        "casalini",
    }
)

# Mapping (marque, modele) -> categorie
# Normalise en minuscules pour le matching.
# C'est la source de verite pour la categorisation : un Cayenne reste un SUV
# meme s'il a 400+ CV, car il est mappe explicitement ici.
VEHICLE_CATEGORY: dict[tuple[str, str], str] = {
    # --- Citadines ---
    ("peugeot", "208"): "citadine",
    ("renault", "clio v"): "citadine",
    ("citroen", "c3"): "citadine",
    ("dacia", "sandero"): "citadine",
    ("volkswagen", "polo"): "citadine",
    ("toyota", "yaris"): "citadine",
    ("fiat", "500"): "citadine",
    ("ford", "fiesta"): "citadine",
    ("opel", "corsa"): "citadine",
    ("mini", "cooper"): "citadine",
    ("suzuki", "swift"): "citadine",
    ("toyota", "aygo x"): "citadine",
    ("skoda", "fabia"): "citadine",
    ("seat", "ibiza"): "citadine",
    ("kia", "picanto"): "citadine",
    ("mg", "3"): "citadine",
    ("renault", "5 e-tech"): "electrique",
    ("citroen", "e-c3"): "electrique",
    ("dacia", "spring"): "electrique",
    # --- Compactes ---
    ("peugeot", "308"): "compacte",
    ("renault", "megane"): "compacte",
    ("volkswagen", "golf"): "compacte",
    ("citroen", "c4"): "compacte",
    ("bmw", "serie 1"): "compacte",
    ("audi", "a3"): "compacte",
    ("mercedes", "classe a"): "compacte",
    ("skoda", "octavia"): "compacte",
    ("ford", "puma"): "compacte",
    # --- SUV compacts ---
    ("peugeot", "2008"): "suv_compact",
    ("renault", "captur"): "suv_compact",
    ("citroen", "c3 aircross"): "suv_compact",
    ("dacia", "duster"): "suv_compact",
    ("volkswagen", "t-roc"): "suv_compact",
    ("volkswagen", "t-cross"): "suv_compact",
    ("volkswagen", "taigo"): "suv_compact",
    ("hyundai", "kona"): "suv_compact",
    ("nissan", "juke"): "suv_compact",
    ("opel", "mokka"): "suv_compact",
    ("skoda", "kamiq"): "suv_compact",
    ("seat", "arona"): "suv_compact",
    ("mg", "zs"): "suv_compact",
    ("toyota", "yaris cross"): "suv_compact",
    ("jeep", "avenger"): "suv_compact",
    ("toyota", "c-hr"): "suv_compact",
    # --- SUV familiaux ---
    ("peugeot", "3008"): "suv_familial",
    ("peugeot", "5008"): "suv_familial",
    ("peugeot", "408"): "suv_familial",
    ("citroen", "c5 aircross"): "suv_familial",
    ("volkswagen", "tiguan"): "suv_familial",
    ("hyundai", "tucson"): "suv_familial",
    ("nissan", "qashqai"): "suv_familial",
    ("ford", "kuga"): "suv_familial",
    ("bmw", "x1"): "suv_familial",
    ("mercedes", "gla"): "suv_familial",
    ("kia", "sportage"): "suv_familial",
    ("toyota", "rav4"): "suv_familial",
    ("cupra", "formentor"): "suv_familial",
    ("renault", "austral"): "suv_familial",
    ("dacia", "bigster"): "suv_familial",
    ("kia", "niro"): "suv_familial",
    # --- Familiales / monospaces ---
    ("renault", "scenic"): "familiale",
    ("renault", "espace"): "familiale",
    ("dacia", "jogger"): "familiale",
    ("renault", "symbioz"): "familiale",
    # --- Berlines ---
    ("bmw", "serie 3"): "berline",
    ("tesla", "model 3"): "berline",
    ("tesla", "model y"): "berline",
    ("toyota", "corolla"): "compacte",
    # --- Electriques pures ---
    ("volkswagen", "id.3"): "electrique",
    ("fiat", "600"): "suv_compact",
    # --- Utilitaires ---
    ("ford", "transit"): "utilitaire",
    ("ford", "transit custom"): "utilitaire",
    ("ford", "transit connect"): "utilitaire",
    ("ford", "transit courier"): "utilitaire",
    # --- SUVs premium / grands routiers ---
    ("porsche", "cayenne"): "suv_premium",
    ("porsche", "macan"): "suv_familial",
    ("volkswagen", "touareg"): "suv_premium",
    ("bmw", "x5"): "suv_premium",
    ("bmw", "x6"): "suv_premium",
    ("bmw", "x7"): "suv_premium",
    ("audi", "q7"): "suv_premium",
    ("audi", "q8"): "suv_premium",
    ("mercedes", "gle"): "suv_premium",
    ("mercedes", "gls"): "suv_premium",
    ("mercedes", "glc"): "suv_familial",
    ("land rover", "range rover"): "suv_premium",
    ("land rover", "discovery"): "suv_premium",
    ("volvo", "xc90"): "suv_premium",
    ("lexus", "rx"): "suv_premium",
    ("lexus", "nx"): "suv_familial",
}


def is_voiture_sans_permis(make: str, fiscal_hp: int | None = None) -> bool:
    """Detecte les voitures sans permis via marque connue ou puissance fiscale typique.

    Heuristique metier:
    - marques VSP connues (Aixam, Ligier, ...)
    - puissance fiscale <= 1 CV (signal fort vu sur les annonces VSP)
    """
    brand = (make or "").lower().strip()
    if brand in VSP_BRANDS:
        return True
    if fiscal_hp is not None and fiscal_hp <= 1:
        return True
    return False


def is_sportive(
    power_din_hp: int | None = None,
    fiscal_hp: int | None = None,
) -> bool:
    """Detecte les sportives/super-sportives via puissance.

    Seuils : >400 CV DIN ou >45 CV fiscaux.
    Ces vehicules roulent peu (loisir, circuit, collection).
    Un km faible est normal et meme souhaitable.

    Note : cette fonction est un FALLBACK. Si le vehicule est dans
    VEHICLE_CATEGORY, c'est la categorie mappee qui prime.
    """
    if power_din_hp is not None and power_din_hp > SPORTIVE_DIN_HP_THRESHOLD:
        return True
    if fiscal_hp is not None and fiscal_hp > SPORTIVE_FISCAL_HP_THRESHOLD:
        return True
    return False


def get_vehicle_category(
    make: str,
    model: str,
    fiscal_hp: int | None = None,
    power_din_hp: int | None = None,
) -> str | None:
    """Retourne la categorie du vehicule ou None si inconnu.

    Ordre de priorite :
    1. VSP (marque ou puissance fiscale <= 1 CV)
    2. Mapping statique (Cayenne -> suv_premium, pas sportive, meme a 400 CV)
    3. Detection sportive par puissance (fallback pour vehicules non mappes)

    Le mapping statique est prioritaire car il encode du savoir metier :
    un Cayenne est un SUV qui fait du km, pas une sportive de circuit.
    """
    if is_voiture_sans_permis(make, fiscal_hp):
        return "voiture_sans_permis"

    # Mapping statique en priorite : un Cayenne reste un SUV meme a 400+ CV
    key = (make.lower().strip(), model.lower().strip())
    if key in VEHICLE_CATEGORY:
        return VEHICLE_CATEGORY[key]

    # Fallback : detection sportive par puissance pour les vehicules non mappes
    if is_sportive(power_din_hp=power_din_hp, fiscal_hp=fiscal_hp):
        return "sportive"

    return None


def get_expected_km_per_year(
    make: str,
    model: str,
    fiscal_hp: int | None = None,
    power_din_hp: int | None = None,
) -> int:
    """Retourne le km/an attendu pour ce vehicule selon sa categorie.

    Si le vehicule n'est pas dans une categorie connue, on retourne
    15 000 km/an (moyenne nationale francaise).
    """
    category = get_vehicle_category(make, model, fiscal_hp=fiscal_hp, power_din_hp=power_din_hp)
    if category:
        return KM_PER_YEAR[category]
    return 15000  # fallback moyen national
