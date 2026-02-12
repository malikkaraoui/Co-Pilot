"""Scenarios de test realistes simulant de vraies annonces Leboncoin.

Chaque scenario reproduit un cas d'usage reel avec des donnees credibles.
Aucun appel reseau -- tout est en local (mocks JSON).
"""

# ── Scenario 1 : Annonce saine -- Peugeot 3008 particulier ──────────────
# Annonce complete, prix coherent, vendeur francais, pas de red flag.
SCENARIO_SAIN_3008 = {
    "name": "Peugeot 3008 sain (particulier)",
    "expected_score_range": (60, 100),
    "expected_status": {"L1": "pass", "L6": "pass", "L8": "pass"},
    "payload": {
        "props": {
            "pageProps": {
                "ad": {
                    "list_id": 3089201001,
                    "subject": "Peugeot 3008 1.6 BlueHDi 120ch Allure Business",
                    "price": [22500],
                    "body": (
                        "Vends ma Peugeot 3008 de 2019, premiere main, toujours entretenue "
                        "en concession Peugeot. Revision des 90 000 km faite en janvier 2026. "
                        "Distribution changee a 80 000 km. Pneus neufs. Pas de rayures. "
                        "Controle technique OK, sans reserves. Interieur non fumeur."
                    ),
                    "location": {
                        "city": "Lyon",
                        "zipcode": "69003",
                        "department_name": "Rhone",
                        "region_name": "Auvergne-Rhone-Alpes",
                        "lat": 45.76,
                        "lng": 4.85,
                    },
                    "owner": {
                        "type": "private",
                        "name": "Jean-Pierre",
                        "phone": "0678452311",
                    },
                    "attributes": [
                        {"key": "Marque", "value": "Peugeot"},
                        {"key": "Modèle", "value": "3008"},
                        {"key": "Année modèle", "value": "2019"},
                        {"key": "Kilométrage", "value": "92 000 km"},
                        {"key": "Énergie", "value": "Diesel"},
                        {"key": "Boîte de vitesse", "value": "Manuelle"},
                        {"key": "Nombre de portes", "value": "5"},
                        {"key": "Nombre de places", "value": "5"},
                        {"key": "Couleur", "value": "Gris Artense"},
                        {"key": "Puissance fiscale", "value": "7 CV"},
                        {"key": "Puissance DIN", "value": "120 ch"},
                    ],
                }
            }
        }
    },
}

# ── Scenario 2 : Annonce suspecte -- import possible ────────────────────
# Prix tres bas, telephone etranger, mots-cles import dans la description.
SCENARIO_SUSPECT_IMPORT = {
    "name": "Golf VII import suspect (telephone polonais)",
    "expected_score_range": (30, 70),
    "expected_status": {"L6": "warning", "L8": "fail"},
    "payload": {
        "props": {
            "pageProps": {
                "ad": {
                    "list_id": 3089201002,
                    "subject": "Golf 7 TDI 150 Carat 2017 IMPORT",
                    "price": [8500],
                    "body": (
                        "Volkswagen Golf 7 importee d'Allemagne, vehicule en bon etat, "
                        "quelques traces d'usure. Carte grise a faire. Vendu en l'etat. "
                        "Contact uniquement par telephone."
                    ),
                    "location": {
                        "city": "Strasbourg",
                        "zipcode": "67000",
                        "department_name": "Bas-Rhin",
                        "region_name": "Grand Est",
                    },
                    "owner": {
                        "type": "private",
                        "name": "Marek",
                        "phone": "+48612345678",
                    },
                    "attributes": [
                        {"key": "Marque", "value": "Volkswagen"},
                        {"key": "Modèle", "value": "Golf"},
                        {"key": "Année modèle", "value": "2017"},
                        {"key": "Kilométrage", "value": "195 000 km"},
                        {"key": "Énergie", "value": "Diesel"},
                        {"key": "Boîte de vitesse", "value": "Automatique"},
                        {"key": "Couleur", "value": "Noir"},
                    ],
                }
            }
        }
    },
}

# ── Scenario 3 : Annonce pro avec SIRET ─────────────────────────────────
# Vendeur professionnel, SIRET present, annonce complete.
SCENARIO_PRO_SIRET = {
    "name": "Renault Clio V pro (SIRET present)",
    "expected_score_range": (50, 100),
    "expected_status": {"L1": "pass", "L6": "pass"},
    "payload": {
        "props": {
            "pageProps": {
                "ad": {
                    "list_id": 3089201003,
                    "subject": "Renault Clio V 1.0 TCe 100ch Intens",
                    "price": [14900],
                    "body": (
                        "Clio V en excellent etat, premiere main, revision complete effectuee. "
                        "Garantie 12 mois incluse. Financement possible. "
                        "Vehicule visible en concession du lundi au samedi."
                    ),
                    "location": {
                        "city": "Toulouse",
                        "zipcode": "31000",
                        "department_name": "Haute-Garonne",
                        "region_name": "Occitanie",
                    },
                    "owner": {
                        "type": "pro",
                        "name": "AutoDistri31",
                        "siren": "44306184100025",
                        "phone": "0561234567",
                    },
                    "attributes": [
                        {"key": "Marque", "value": "Renault"},
                        {"key": "Modèle", "value": "Clio"},
                        {"key": "Année modèle", "value": "2021"},
                        {"key": "Kilométrage", "value": "35 000 km"},
                        {"key": "Énergie", "value": "Essence"},
                        {"key": "Boîte de vitesse", "value": "Manuelle"},
                        {"key": "Nombre de portes", "value": "5"},
                        {"key": "Nombre de places", "value": "5"},
                        {"key": "Couleur", "value": "Blanc Glacier"},
                        {"key": "Puissance fiscale", "value": "5 CV"},
                        {"key": "Puissance DIN", "value": "100 ch"},
                    ],
                }
            }
        }
    },
}

# ── Scenario 4 : Annonce incomplete / minimaliste ───────────────────────
# Tres peu de donnees, pas de telephone, description vide.
SCENARIO_INCOMPLET = {
    "name": "Dacia Sandero incomplet (donnees manquantes)",
    "expected_score_range": (20, 60),
    "expected_status": {"L1": "warning", "L6": "skip"},
    "payload": {
        "props": {
            "pageProps": {
                "ad": {
                    "list_id": 3089201004,
                    "subject": "Sandero",
                    "price": 6000,
                    "body": "",
                    "location": {},
                    "owner": {"type": "private"},
                    "attributes": [
                        {"key": "Marque", "value": "Dacia"},
                        {"key": "Modèle", "value": "Sandero"},
                        {"key": "Année modèle", "value": "2018"},
                        {"key": "Kilométrage", "value": "80 000 km"},
                    ],
                }
            }
        }
    },
}

# ── Scenario 5 : Kilometrage incoherent ─────────────────────────────────
# Voiture de 2023 avec 180 000 km = tres suspect.
SCENARIO_KM_INCOHERENT = {
    "name": "Toyota Yaris km incoherent (180k km en 3 ans)",
    "expected_score_range": (50, 90),
    "expected_status": {"L3": "warning"},
    "payload": {
        "props": {
            "pageProps": {
                "ad": {
                    "list_id": 3089201005,
                    "subject": "Toyota Yaris 1.5 Hybride 2023",
                    "price": [16000],
                    "body": (
                        "Yaris hybride, ideal pour la ville. Premiere main. "
                        "Carnet d'entretien a jour."
                    ),
                    "location": {
                        "city": "Paris",
                        "zipcode": "75011",
                        "department_name": "Paris",
                        "region_name": "Ile-de-France",
                    },
                    "owner": {
                        "type": "private",
                        "name": "Sophie",
                        "phone": "0745123456",
                    },
                    "attributes": [
                        {"key": "Marque", "value": "Toyota"},
                        {"key": "Modèle", "value": "Yaris"},
                        {"key": "Année modèle", "value": "2023"},
                        {"key": "Kilométrage", "value": "180 000 km"},
                        {"key": "Énergie", "value": "Hybride"},
                        {"key": "Boîte de vitesse", "value": "Automatique"},
                        {"key": "Nombre de portes", "value": "5"},
                        {"key": "Couleur", "value": "Blanc"},
                        {"key": "Puissance DIN", "value": "116 ch"},
                    ],
                }
            }
        }
    },
}

# ── Liste de tous les scenarios pour iteration ──────────────────────────
ALL_SCENARIOS = [
    SCENARIO_SAIN_3008,
    SCENARIO_SUSPECT_IMPORT,
    SCENARIO_PRO_SIRET,
    SCENARIO_INCOMPLET,
    SCENARIO_KM_INCOHERENT,
]
