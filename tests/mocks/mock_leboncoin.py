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

MALFORMED_NEXT_DATA = {
    "props": {
        "pageProps": {
            "someOtherKey": "no ad here"
        }
    }
}

EMPTY_NEXT_DATA = {}

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
