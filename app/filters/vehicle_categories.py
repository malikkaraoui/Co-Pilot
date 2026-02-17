"""Categories de vehicules et km attendus par categorie.

Savoir metier : une citadine fait moins de km/an qu'un SUV familial.
Un vehicule de flotte d'entreprise roule beaucoup plus mais est mieux suivi.
"""

# km/an moyens par categorie
KM_PER_YEAR = {
    "citadine": 10000,
    "compacte": 13000,
    "suv_compact": 15000,
    "suv_familial": 17000,
    "familiale": 17000,
    "berline": 18000,
    "electrique": 12000,
    "utilitaire": 20000,
}

# Mapping (marque, modele) -> categorie
# Normalise en minuscules pour le matching
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
}

# Vehicules typiques de flotte d'entreprise (km eleve mais bien suivi)
FLEET_VEHICLES: set[tuple[str, str]] = {
    ("peugeot", "208"),
    ("peugeot", "308"),
    ("peugeot", "3008"),
    ("peugeot", "5008"),
    ("renault", "clio v"),
    ("renault", "megane"),
    ("renault", "captur"),
    ("citroen", "c3"),
    ("citroen", "c4"),
    ("citroen", "c5 aircross"),
    ("dacia", "sandero"),
    ("dacia", "duster"),
    ("volkswagen", "golf"),
    ("volkswagen", "polo"),
    ("volkswagen", "tiguan"),
    ("ford", "fiesta"),
    ("ford", "puma"),
    ("ford", "kuga"),
    ("toyota", "yaris"),
    ("toyota", "corolla"),
    ("bmw", "serie 3"),
    ("mercedes", "classe a"),
    ("mercedes", "gla"),
    ("audi", "a3"),
    ("skoda", "octavia"),
    ("skoda", "fabia"),
}


def get_vehicle_category(make: str, model: str) -> str | None:
    """Retourne la categorie du vehicule ou None si inconnu."""
    key = (make.lower().strip(), model.lower().strip())
    return VEHICLE_CATEGORY.get(key)


def get_expected_km_per_year(make: str, model: str) -> int:
    """Retourne le km/an attendu pour ce vehicule selon sa categorie."""
    category = get_vehicle_category(make, model)
    if category:
        return KM_PER_YEAR[category]
    return 15000  # fallback moyen national


def is_fleet_vehicle(make: str, model: str) -> bool:
    """Retourne True si ce modele est typique des flottes d'entreprise."""
    key = (make.lower().strip(), model.lower().strip())
    return key in FLEET_VEHICLES
