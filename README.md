# Co-Pilot -- Analyse de confiance pour annonces auto Leboncoin

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-3.x-000000?logo=flask&logoColor=white)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0-D71F00?logo=sqlalchemy&logoColor=white)
![Chrome Extension](https://img.shields.io/badge/Chrome-Manifest_V3-4285F4?logo=googlechrome&logoColor=white)
![Tests](https://img.shields.io/badge/tests-292%2B_passing-2EA44F)
![Ruff](https://img.shields.io/badge/lint-ruff-D7FF64?logo=ruff&logoColor=black)
![Docker](https://img.shields.io/badge/Docker-ready-2496ED?logo=docker&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-blue)

Co-Pilot est une extension Chrome couplée à une API Flask qui analyse les annonces de véhicules d'occasion sur Leboncoin et attribue un **score de confiance de 0 à 100**.

L'utilisateur navigue sur Leboncoin, clique sur "Analyser avec Co-Pilot", et obtient un verdict instantané avec le détail de 9 filtres indépendants.

## Fonctionnement

```text
Extension Chrome                API Flask (Python)
     |                               |
     |  1. Extrait __NEXT_DATA__     |
     |  2. POST /api/analyze ------> |
     |                               | 3. Extraction des données
     |                               | 4. Exécution des 9 filtres (parallèle)
     |                               | 5. Calcul du score global
     |  6. Affiche la popup  <------ |
     |     avec jauge + détails      |
```

## Argus Maison -- Cotation collaborative

L'**Argus Maison** est un système de cotation participatif intégré à Co-Pilot. Plutôt que de dépendre uniquement de données Argus importées (seeds), le système collecte les prix réels du marché directement depuis les annonces Leboncoin grâce aux utilisateurs de l'extension.

Chaque utilisateur qui analyse une annonce contribue automatiquement à enrichir la base de prix.

### Schéma du pipeline

```text
                        Extension Chrome
                              |
         1. Analyse d'une annonce Leboncoin
                              |
         2. GET /api/market-prices/next-job
                  (quel véhicule collecter ?)
                              |
                    +---------+---------+
                    |                   |
          Véhicule courant        Autre véhicule
          (toujours collecté)     (rotation, cooldown 24h)
                    |                   |
                    +---------+---------+
                              |
         3. Recherche Leboncoin (même marque/modèle/région)
            Parse __NEXT_DATA__ → extraction des prix
                              |
         4. POST /api/market-prices
            { make, model, year, region, prices: [...] }
                              |
                        API Flask
                              |
         5. Filtrage (prix < 500 EUR exclus)
            Calcul NumPy : min, median, mean, max, std
                              |
         6. Upsert MarketPrice en base
            (clé unique : marque + modèle + année + région)
                              |
                    Données disponibles
                      pour les filtres
                              |
              +---------------+---------------+
              |                               |
     Filtre L4 (Prix vs Argus)     Filtre L5 (Z-score)
              |                               |
     MarketPrice (n >= 5) ?        MarketPrice (n >= 5) ?
        OUI → prix réel              OUI → stats réelles
        NON → fallback ArgusPrice    NON → fallback ArgusPrice
```

### Strategie de fallback des prix

```text
MarketPrice crowdsourcé (>= 5 échantillons)
        |
        +-- NON --> MarketPrice année ±3 (même marque/modèle/région)
                          |
                          +-- NON --> ArgusPrice seed (import CSV)
                                            |
                                            +-- NON --> filtre skip
```

### Points clés

- **Fraîcheur** : cache 24h par véhicule/région, les données restent exploitables au-delà
- **Anti-abus** : cooldown 24h pour les véhicules tiers, le véhicule courant est toujours collecté
- **Matching robuste** : normalisation Unicode (NFKC), insensible à la casse et aux apostrophes
- **Transparence** : l'extension affiche un badge "Données simulées" quand L4/L5 utilisent le fallback ArgusPrice
- **Admin** : page `/admin/argus` avec stats, filtres par marque/région, tableau paginé des cotations

## Les 9 filtres

| ID  | Nom                    | Description                                                                 |
| --- | ---------------------- | --------------------------------------------------------------------------- |
| L1  | Complétude des données | Vérifie la présence des champs critiques (prix, marque, modèle, année, km)  |
| L2  | Modèle reconnu         | Recherche le véhicule dans le référentiel (20 modèles)                      |
| L3  | Cohérence km / année   | Détecte les kilométrages anormaux par rapport à l'âge                       |
| L4  | Prix vs Argus          | Compare le prix annoncé à l'argus géolocalisé par région                    |
| L5  | Analyse statistique    | Calcul de z-scores via NumPy pour détecter les outliers                     |
| L6  | Téléphone              | Détecte les indicatifs étrangers et formats suspects                        |
| L7  | SIRET vendeur          | Vérifie le SIRET via l'API publique gouv.fr                                 |
| L8  | Détection import       | Repère les signaux d'un véhicule importé                                    |
| L9  | Évaluation globale     | Synthèse des points forts / faibles de l'annonce                            |

## Stack technique

- **Backend** : Python 3.12, Flask 3.x, SQLAlchemy 2.x, Pydantic 2.x
- **Base de données** : SQLite (portable, persistée via Docker volume)
- **Extension** : Chrome Manifest V3, vanilla JS, CSS préfixé `.copilot-*`
- **Tests** : pytest, 226+ tests, couverture 86%+
- **Lint** : ruff
- **CI** : GitHub Actions (lint + tests)
- **Conteneurisation** : Docker + docker-compose

## Installation

### Prérequis

- Python 3.12+
- pip
- Chrome (pour l'extension)

### Backend

```bash
# Cloner le projet
git clone https://github.com/malikkaraoui/Co-Pilot.git
cd Co-Pilot

# Créer l'environnement virtuel
python -m venv .venv
source .venv/bin/activate  # macOS/Linux

# Installer les dépendances
pip install -r requirements.txt
pip install -r requirements-dev.txt  # pour les tests

# Initialiser la base de données + seeds
python scripts/init_db.py

# Lancer le serveur
flask run --port 5001
```

### Docker

```bash
docker-compose up --build
```

### Extension Chrome

1. Ouvrir Chrome > `chrome://extensions`
2. Activer le **Mode développeur**
3. Cliquer **"Charger l'extension non empaquetée"**
4. Sélectionner le dossier `extension/`

### Page de démo

Ouvrir `extension/demo.html` dans le navigateur pour tester sans Leboncoin (le serveur Flask doit tourner).

## Tests

```bash
# Lancer tous les tests
pytest

# Avec couverture
pytest --cov=app

# Linting
ruff check .
```

## Structure du projet

```text
Co-Pilot/
├── app/
│   ├── __init__.py          # Flask Application Factory
│   ├── api/                 # Blueprint API (routes, erreurs)
│   ├── admin/               # Blueprint admin (dashboard)
│   ├── filters/             # 9 filtres L1-L9 + BaseFilter + FilterEngine
│   ├── models/              # Modèles SQLAlchemy (Vehicle, ScanLog, MarketPrice…)
│   ├── schemas/             # Schémas Pydantic (validation)
│   ├── services/            # Logique métier (extraction, scoring, market_service…)
│   └── extensions.py        # Extensions Flask (db, cors, login)
├── extension/
│   ├── manifest.json        # Manifest V3
│   ├── content.js           # Script injecté sur Leboncoin
│   ├── content.css          # Styles de la popup
│   ├── popup/               # Popup de l'extension
│   └── demo.html            # Page de test
├── tests/                   # 226+ tests pytest
├── data/
│   ├── copilot.db           # Base SQLite (non versionné)
│   └── seeds/               # Scripts de peuplement
├── config.py                # Configuration par environnement
├── wsgi.py                  # Point d'entrée WSGI
├── Dockerfile
└── docker-compose.yml
```

## API

### POST /api/analyze

Analyse une annonce Leboncoin et retourne un score de confiance.

**Requête :**

```json
{
  "next_data": { "props": { "pageProps": { "ad": { ... } } } }
}
```

**Réponse :**

```json
{
  "success": true,
  "data": {
    "score": 78,
    "is_partial": false,
    "vehicle": { "make": "Peugeot", "model": "3008", "year": "2019" },
    "filters": [
      { "filter_id": "L1", "status": "pass", "score": 1.0, "message": "..." },
      { "filter_id": "L2", "status": "pass", "score": 1.0, "message": "..." }
    ]
  }
}
```

### POST /api/market-prices

Enregistre des prix collectés par l'extension pour alimenter l'Argus Maison.

**Requête :**

```json
{
  "make": "Peugeot",
  "model": "3008",
  "year": 2019,
  "region": "Île-de-France",
  "prices": [15200, 16800, 14500, 17000, 15900]
}
```

**Réponse :**

```json
{
  "success": true,
  "data": { "sample_count": 5, "price_median": 15900 }
}
```

### GET /api/market-prices/next-job

Retourne le prochain véhicule à collecter (smart job assignment).

### GET /api/health

Vérification de l'état du serveur.

## Auteur

**Malik Karaoui** -- Projet de certification Python SE (jury mars 2026)

## Licence

MIT
