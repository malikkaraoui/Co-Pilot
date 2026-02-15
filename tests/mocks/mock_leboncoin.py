"""Mock __NEXT_DATA__ payloads for testing."""

VALID_AD_NEXT_DATA = {
    "props": {
        "pageProps": {
            "ad": {
                "subject": "Peugeot 3008 1.6 BlueHDi 120ch Active",
                "price": [18500],
                "body": "Vehicule en excellent etat, revision faite.",
                "location": {
                    "city": "Lyon",
                    "zipcode": "69001",
                    "department_name": "Rhone",
                    "region_name": "Auvergne-Rhone-Alpes",
                    "lat": 45.764,
                    "lng": 4.8357,
                },
                "owner": {
                    "type": "private",
                    "name": "Jean",
                    "phone": "0612345678",
                },
                "attributes": [
                    {"key": "Marque", "value": "Peugeot"},
                    {"key": "Modèle", "value": "3008"},
                    {"key": "Année modèle", "value": "2019"},
                    {"key": "Kilométrage", "value": "75 000 km"},
                    {"key": "Énergie", "value": "Diesel"},
                    {"key": "Boîte de vitesse", "value": "Manuelle"},
                    {"key": "Nombre de portes", "value": "5"},
                    {"key": "Nombre de places", "value": "5"},
                    {"key": "Couleur", "value": "Gris"},
                    {"key": "Puissance fiscale", "value": "7 CV"},
                    {"key": "Puissance DIN", "value": "120 ch"},
                ],
            }
        }
    }
}

MINIMAL_AD_NEXT_DATA = {
    "props": {
        "pageProps": {
            "ad": {
                "subject": "Voiture occasion",
                "price": 5000,
                "attributes": [
                    {"key": "Marque", "value": "Renault"},
                    {"key": "Modèle", "value": "Clio"},
                ],
            }
        }
    }
}

MALFORMED_NEXT_DATA = {"props": {"pageProps": {"someOtherKey": "no ad here"}}}

EMPTY_NEXT_DATA = {}

# Annonce non-voiture (pneus dans equipement_auto)
NON_VEHICLE_AD_NEXT_DATA = {
    "props": {
        "pageProps": {
            "ad": {
                "list_id": 3144651429,
                "subject": "4 Pneus Bridgestone Turanza T005 225/45R17",
                "price": [280],
                "body": "Lot de 4 pneus Bridgestone en bon etat, 5mm de profil restant.",
                "location": {
                    "city": "Strasbourg",
                    "zipcode": "67000",
                    "department_name": "Bas-Rhin",
                    "region_name": "Grand Est",
                },
                "owner": {
                    "type": "private",
                    "name": "Marc",
                },
                "attributes": [
                    {"key": "Type", "value": "Pneus"},
                    {"key": "Marque pneu", "value": "Bridgestone"},
                ],
            }
        }
    }
}

# Voiture publiee dans la categorie equipement_auto (mal categorisee)
VEHICLE_IN_WRONG_CATEGORY_NEXT_DATA = {
    "props": {
        "pageProps": {
            "ad": {
                "list_id": 3144609125,
                "subject": "Renault Megane 1.5 dCi 110ch",
                "price": [8500],
                "body": "Megane en bon etat general.",
                "location": {
                    "city": "Marseille",
                    "zipcode": "13001",
                    "department_name": "Bouches-du-Rhone",
                    "region_name": "Provence-Alpes-Cote d'Azur",
                },
                "owner": {
                    "type": "private",
                    "name": "Sophie",
                    "phone": "0698765432",
                },
                "attributes": [
                    {"key": "Marque", "value": "Renault"},
                    {"key": "Modèle", "value": "Megane"},
                    {"key": "Année modèle", "value": "2018"},
                    {"key": "Kilométrage", "value": "95 000 km"},
                    {"key": "Énergie", "value": "Diesel"},
                ],
            }
        }
    }
}

# Annonce moto
MOTO_AD_NEXT_DATA = {
    "props": {
        "pageProps": {
            "ad": {
                "list_id": 3134260111,
                "subject": "Yamaha MT-07 2023 ABS",
                "price": [6500],
                "body": "Yamaha MT-07 en parfait etat, premiere main.",
                "location": {
                    "city": "Paris",
                    "zipcode": "75011",
                    "department_name": "Paris",
                    "region_name": "Ile-de-France",
                },
                "owner": {
                    "type": "private",
                    "name": "Lucas",
                    "phone": "0645789012",
                },
                "attributes": [
                    {"key": "Marque", "value": "Yamaha"},
                    {"key": "Modèle", "value": "MT-07"},
                    {"key": "Année modèle", "value": "2023"},
                    {"key": "Kilométrage", "value": "8 000 km"},
                    {"key": "Cylindrée", "value": "689 cm3"},
                ],
            }
        }
    }
}

AD_WITH_FOREIGN_PHONE = {
    "props": {
        "pageProps": {
            "ad": {
                "subject": "Golf 7 TDI 2017",
                "price": [13000],
                "owner": {
                    "type": "private",
                    "phone": "+48612345678",
                },
                "attributes": [
                    {"key": "Marque", "value": "Volkswagen"},
                    {"key": "Modèle", "value": "Golf"},
                    {"key": "Année modèle", "value": "2017"},
                    {"key": "Kilométrage", "value": "120 000 km"},
                    {"key": "Énergie", "value": "Diesel"},
                ],
            }
        }
    }
}
