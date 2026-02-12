# Co-Pilot -- Analyse de confiance pour annonces auto Leboncoin

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
- **Tests** : pytest, 114+ tests, couverture 86%+
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
│   ├── models/              # Modèles SQLAlchemy (Vehicle, ScanLog, etc.)
│   ├── schemas/             # Schémas Pydantic (validation)
│   ├── services/            # Logique métier (extraction, scoring, lookup)
│   └── extensions.py        # Extensions Flask (db, cors, login)
├── extension/
│   ├── manifest.json        # Manifest V3
│   ├── content.js           # Script injecté sur Leboncoin
│   ├── content.css          # Styles de la popup
│   ├── popup/               # Popup de l'extension
│   └── demo.html            # Page de test
├── tests/                   # 114+ tests pytest
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

### GET /api/health

Vérification de l'état du serveur.

## Auteur

**Malik Karaoui** -- Projet de certification Python SE (jury mars 2026)

## Licence

MIT
