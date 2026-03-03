# Vehicore — Analyse de confiance pour annonces auto

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-3.1-000000?logo=flask&logoColor=white)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0-D71F00?logo=sqlalchemy&logoColor=white)
![Chrome Extension](https://img.shields.io/badge/Chrome-Manifest_V3-4285F4?logo=googlechrome&logoColor=white)
![Tests](https://img.shields.io/badge/tests-800_passing-2EA44F)
![Version](https://img.shields.io/badge/version-0.11.0-blue)
![Ruff](https://img.shields.io/badge/lint-ruff-D7FF64?logo=ruff&logoColor=black)
![Docker](https://img.shields.io/badge/Docker-ready-2496ED?logo=docker&logoColor=white)
![Render](https://img.shields.io/badge/deploy-Render-46E3B7?logo=render&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-blue)

**Vehicore** est une extension Chrome couplée à une API Flask qui analyse les annonces de véhicules d'occasion sur **Leboncoin** et **AutoScout24** (12 pays européens) et attribue un **score de confiance de 0 à 100**.

L'utilisateur navigue sur une annonce, clique sur "Analyser", et obtient un verdict instantané avec le détail de 10 filtres indépendants, un radar visuel, et des recommandations personnalisées.

## Points forts

- **Multi-plateforme** : Leboncoin (FR) + AutoScout24 (12 pays : CH, DE, FR, IT, BE, NL, AT, ES, PL, LU, SE, .com)
- **10 filtres indépendants** avec scoring pondéré et radar SVG interactif
- **Argus Maison collaboratif** : cotation participative en temps réel via les utilisateurs de l'extension
- **Auto-learning** : tokens de recherche LBC et slugs AS24 appris automatiquement pour chaque véhicule
- **Catalogue crowdsource** : les specs techniques (motorisation, boite, puissance) se construisent par repetition des observations sur les annonces
- **Email vendeur IA** : generation de mails personnalises via Gemini (adapte pro/particulier)
- **YouTube intégré** : vidéos de test et avis liées à chaque véhicule (sous-titres extractibles)
- **Détection intelligente** : non-véhicules, imports, republications, annonces sponsorisées off-brand
- **Dashboard admin complet** : pilotage, monitoring, gestion du référentiel, LLM, vidéos, erreurs

## Fonctionnement

```text
Extension Chrome                API Flask (Python)
     |                               |
     |  1. Extrait les données       |
     |     (LBC: __NEXT_DATA__,      |
     |      AS24: JSON-LD + DOM)     |
     |                               |
     |  2. POST /api/analyze ------> |
     |                               | 3. Extraction & normalisation
     |                               | 4. Exécution des 10 filtres
     |                               | 5. Scoring pondéré (L2/L4 critique)
     |  6. Affiche la popup  <------ |
     |     avec radar + détails      |
     |                               |
     |  7. Collecte prix marché ---> | 8. Upsert MarketPrice
     |     (véhicule courant +       |    (crowdsourcé, cache 24h)
     |      job bonus rotation)      | 9. Enrichit ObservedMotorization
     |                               |    (fuel+boite+CV → promotion auto
     |                               |     en VehicleSpec après 3 sources)
```

## Les 10 filtres

| ID  | Nom                      | Poids | Description                                                                |
| --- | ------------------------ | ----- | -------------------------------------------------------------------------- |
| L1  | Complétude des données   | 1.0   | Vérifie la présence des champs critiques (prix, marque, modèle, année, km)|
| L2  | Modèle reconnu           | 2.0   | Recherche le véhicule dans le référentiel (70+ véhicules, aliases)        |
| L3  | Cohérence km / année     | 1.0   | Détecte les kilométrages anormaux par rapport à l'âge                     |
| L4  | Prix vs Argus            | 2.0   | Compare le prix annoncé à l'argus géolocalisé + signal "anguille"        |
| L5  | Analyse statistique prix | 1.0   | Z-scores NumPy pour détecter les prix outliers                            |
| L6  | Téléphone                | 0.5   | Détecte les indicatifs étrangers et formats suspects                      |
| L7  | SIRET vendeur            | 1.0   | Vérifie le SIRET via l'API publique gouv.fr                               |
| L8  | Détection import         | 1.0   | Repère les signaux d'un véhicule importé (TVA, pays-aware)               |
| L9  | Évaluation globale       | 1.0   | Synthèse des points forts / faibles de l'annonce                          |
| L10 | Ancienneté annonce       | 1.0   | Durée de mise en vente et détection des republications                    |

## Argus Maison — Cotation collaborative

Plutôt que de dépendre uniquement de données Argus importées (seeds), le système collecte les prix réels du marché directement depuis les annonces grâce aux utilisateurs de l'extension.

```text
                        Extension Chrome
                              |
         1. Analyse d'une annonce (LBC ou AS24)
                              |
         2. GET /api/market-prices/next-job
                  (quel véhicule collecter ?)
                              |
                    +---------+---------+
                    |                   |
          Véhicule courant        Job bonus
          (toujours collecté)     (rotation, cooldown 24h)
                    |                   |
                    +---------+---------+
                              |
         3. Recherche sur la plateforme source
            LBC: parse __NEXT_DATA__
            AS24: parse JSON-LD + DOM
                              |
         4. POST /api/market-prices
            { make, model, year, region, prices, source }
                              |
         5. Filtrage + calcul NumPy (min, median, mean, max, std)
                              |
         6. Upsert MarketPrice (clé : marque + modèle + année + région)
```

**Stratégie de fallback** : MarketPrice crowdsourcé (≥ 5 échantillons) → MarketPrice année ±3 → ArgusPrice seed → filtre skip

**Auto-learning** : les tokens de recherche (LBC: accents, AS24: slugs) sont appris automatiquement depuis le DOM et persistes en base pour les futures recherches.

## Catalogue crowdsource — Construction par repetition

Le referentiel technique (motorisations, boites, puissances) se construit automatiquement a partir des annonces scannees :

```text
Annonce 1 (Diesel 130ch Manuelle)  ──┐
Annonce 2 (Diesel 130ch Manuelle)  ──┼──  3 sources distinctes
Annonce 3 (Diesel 130ch Manuelle)  ──┘         │
                                               ▼
                                    Promotion en VehicleSpec
                                    "Diesel 130ch Manuelle"
```

- Chaque scan individuel ET chaque collecte marche alimente les **ObservedMotorization**
- Deduplication par hash d'annonce (prix + annee + km)
- **Seuil de promotion : 3 sources distinctes** → creation automatique d'une fiche VehicleSpec
- Le vehicule passe de `enrichment_status=partial` a `complete` apres la premiere promotion
- Visible dans le dashboard admin (motorisations observees / promues / en attente)

## Email vendeur IA

Génération automatique de mails personnalisés via **Google Gemini** pour contacter le vendeur :

- Adapté au type de vendeur (professionnel / particulier)
- Basé sur les résultats des 10 filtres (points forts, alertes à questionner)
- Prompts versionnés et configurables depuis l'admin
- Suivi des coûts LLM avec graphiques Plotly

## YouTube intégré

Recherche automatique de vidéos YouTube (tests, avis) liées à chaque véhicule :

- Extraction des sous-titres via `youtube-transcript-api`
- Système de vidéo "featured" par véhicule
- Gestion complète depuis l'admin (archivage, extraction, recherche)

## Stack technique

- **Backend** : Python 3.12, Flask 3.1, SQLAlchemy 2.0, Pydantic 2.11
- **IA** : Google Gemini (génération email), yt-dlp + youtube-transcript-api (vidéos)
- **Base de données** : SQLite (persistée via Docker volume / Render disk)
- **Extension** : Chrome Manifest V3, vanilla JS, esbuild (bundling), CSS préfixé `.copilot-*`
- **Tests** : pytest (800 tests Python) + Vitest (tests JS)
- **Lint** : ruff
- **CI** : GitHub Actions (lint + tests)
- **Conteneurisation** : Docker + docker-compose
- **Déploiement** : Render (Starter, Frankfurt, HTTPS auto)

## Installation

### Prérequis

- Python 3.12+
- pip
- Node.js 20+ (pour le build de l'extension et les tests JS)
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

1. Builder l'extension : `npm run build` (ou utiliser `scripts/package-extension.sh`)
2. Ouvrir Chrome > `chrome://extensions`
3. Activer le **Mode développeur**
4. Cliquer **"Charger l'extension non empaquetée"**
5. Sélectionner le dossier `extension/`

## Tests

```bash
# Tests Python
pytest

# Avec couverture
pytest --cov=app

# Tests JS (extension)
npm test

# Linting
ruff check .
```

## Structure du projet

```text
Vehicore/
├── app/
│   ├── __init__.py              # Flask Application Factory
│   ├── api/                     # Blueprint API (routes, market_routes, erreurs)
│   ├── admin/                   # Blueprint admin (dashboard, templates)
│   ├── filters/                 # 10 filtres L1-L10 + BaseFilter + FilterEngine
│   ├── models/                  # SQLAlchemy (Vehicle, ScanLog, MarketPrice,
│   │                            #   ObservedMotorization, EmailDraft, YouTubeVideo…)
│   ├── schemas/                 # Schemas Pydantic (validation)
│   ├── services/                # Logique metier (extraction, scoring, market,
│   │                            #   motorization, email, gemini, youtube…)
│   └── extensions.py            # Extensions Flask (db, cors, login, limiter)
├── extension/
│   ├── manifest.json            # Manifest V3 (LBC + AS24 12 pays)
│   ├── content.js               # Script injecté (LBC + AS24)
│   ├── background.js            # Service worker
│   ├── build.js                 # esbuild config
│   ├── content.css              # Styles popup
│   └── popup/                   # Popup de l'extension
├── tests/                       # 800+ tests pytest
├── data/
│   ├── vehicore.db              # Base SQLite (non versionné)
│   └── seeds/                   # Scripts de peuplement (vehicles, argus,
│                                #   youtube, gemini prompts)
├── docs/                        # Documentation (deployment, privacy, specs…)
├── scripts/                     # Scripts utilitaires (init_db, packaging…)
├── config.py                    # Configuration par environnement
├── wsgi.py                      # Point d'entrée WSGI
├── Dockerfile                   # Image production (python:3.12-slim)
├── docker-compose.yml
└── render.yaml                  # IaC Render (service + disk + env vars)
```

## API

### POST /api/analyze

Analyse une annonce et retourne un score de confiance.

```json
// Requête
{
  "next_data": { "props": { "pageProps": { "ad": { "..." } } } },
  "url": "https://www.leboncoin.fr/voitures/..."
}

// Réponse
{
  "success": true,
  "data": {
    "score": 78,
    "is_partial": false,
    "vehicle": { "make": "Peugeot", "model": "3008", "year": "2019" },
    "filters": [
      { "filter_id": "L1", "status": "pass", "score": 1.0, "message": "..." }
    ],
    "featured_video": { "title": "...", "video_id": "..." },
    "scan_id": 42
  }
}
```

### POST /api/market-prices

Enregistre des prix collectés pour alimenter l'Argus Maison.

```json
// Requête
{
  "make": "Peugeot", "model": "3008", "year": 2019,
  "region": "Île-de-France", "prices": [15200, 16800, 14500],
  "source": "lbc"
}
```

### POST /api/email-draft

Génère un email personnalisé pour contacter le vendeur (via Gemini).

### GET /api/market-prices/next-job

Retourne le prochain véhicule à collecter (smart job assignment).

### GET /api/health

Vérification de l'état du serveur.

## Dashboard admin

Le panneau d'administration (`/admin`) offre :

- **Dashboard** : 7 stat cards (taux d'échec, warnings, erreurs, véhicules non reconnus…)
- **Referentiel vehicules** : gestion des 70+ vehicules, demandes utilisateurs, quick-add, auto-creation depuis CSV
- **Motorisations** : specs crowdsourcees, suivi des promotions, candidats proches du seuil
- **Argus** : cotations crowdsourcees, stats par marque/region
- **Filtres** : maturité de chaque filtre, badges OK/simulé
- **YouTube** : vidéos par véhicule, extraction de sous-titres, featured toggle
- **Email/LLM** : configuration Gemini, prompts versionnés, coûts, drafts
- **Pipelines** : historique des exécutions de seeds
- **Issues** : recherches échouées (LBC/AS24), diagnostic des tokens
- **Erreurs** : logs WARNING/ERROR persistés

## Sites supportés

| Site | Pays | Extraction | Collecte prix |
| --- | --- | --- | --- |
| Leboncoin | France | `__NEXT_DATA__` | `__NEXT_DATA__` + tokens auto-appris |
| AutoScout24 | CH, DE, FR, IT, BE, NL, AT, ES, PL, LU, SE, .com | JSON-LD + DOM | JSON-LD + slugs auto-appris |

## Auteur

**Malik Karaoui** — Projet de certification Python SE (jury mars 2026)

## Licence

MIT
