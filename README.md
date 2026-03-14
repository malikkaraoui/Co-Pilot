# OKazCar — Analyse de confiance pour annonces auto

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-3.1-000000?logo=flask&logoColor=white)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0-D71F00?logo=sqlalchemy&logoColor=white)
![Chrome Extension](https://img.shields.io/badge/Chrome-Manifest_V3-4285F4?logo=googlechrome&logoColor=white)
![Tests](https://img.shields.io/badge/tests-1381_passing-2EA44F)
![Version](https://img.shields.io/badge/version-1.2.0-blue)
![Ruff](https://img.shields.io/badge/lint-ruff-D7FF64?logo=ruff&logoColor=black)
![Docker](https://img.shields.io/badge/Docker-ready-2496ED?logo=docker&logoColor=white)
![Render](https://img.shields.io/badge/deploy-Render-46E3B7?logo=render&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-blue)

**OKazCar** est une extension Chrome couplée à une API Flask qui analyse les annonces de véhicules d'occasion sur **Leboncoin**, **AutoScout24**, **La Centrale** et **ParuVendu** (11 pays européens) et attribue un **score de confiance de 0 à 100**.

L'utilisateur navigue sur une annonce, clique sur "Analyser", et obtient un verdict instantané avec le détail de 11 filtres indépendants, et des recommandations personnalisées.

## Points forts

- **Multi-plateforme** : Leboncoin (FR) + AutoScout24 (12 pays) + La Centrale (FR) + ParuVendu (FR)
- **11 filtres indépendants** (L1-L11) avec scoring pondéré et exécution parallèle (ThreadPoolExecutor)
- **Argus Maison collaboratif** : cotation participative en temps réel via les utilisateurs de l'extension
- **Auto-learning** : tokens de recherche LBC et slugs AS24 appris automatiquement pour chaque véhicule
- **Catalogue crowdsource** : les specs techniques (motorisation, boite, puissance) se construisent par repetition des observations sur les annonces
- **Email vendeur IA** : generation de mails personnalises via Gemini 2.5 Flash (adapte pro/particulier)
- **Rapport PDF premium** : generation de rapports PDF avec branding OKazCar (WeasyPrint)
- **Pipeline RAG YouTube** : extraction sous-titres → digestion LLM (Gemini/Ollama) → syntheses vehicules
- **Rappels constructeur** : detection des rappels securite (Takata airbag, etc.)
- **Détection intelligente** : non-véhicules, imports, republications, annonces sponsorisées off-brand
- **Dashboard admin complet** : pilotage, monitoring, gestion du référentiel, LLM, vidéos, erreurs
- **1 381 tests automatisés** (922 pytest + 459 vitest) — CI/CD GitHub Actions

## Fonctionnement

```text
Extension Chrome (MV3)            API Flask (Python 3.12)
     |                                    |
     |  1. Extrait les données            |
     |     (LBC: __NEXT_DATA__,           |
     |      AS24: JSON-LD + DOM,          |
     |      LaC: API, PV: DOM)            |
     |                                    |
     |  2. POST /api/analyze ---------->  |
     |                                    | 3. Validation Pydantic
     |                                    | 4. Exécution 11 filtres (parallèle)
     |                                    | 5. Scoring pondéré (0-100)
     |  6. Affiche la popup  <----------  |
     |     avec score + détails           |
     |                                    |
     |  7. Collecte prix marché ------->  | 8. Upsert MarketPrice
     |     (véhicule courant +            |    (crowdsourcé, IQR Mean NumPy)
     |      job bonus rotation)           | 9. Enrichit ObservedMotorization
     |                                    |    (fuel+boite+CV → promotion auto
     |                                    |     en VehicleSpec après 3 sources)
```

## Les 11 filtres

| ID  | Nom                      | Poids | Description                                                                |
| --- | ------------------------ | ----- | -------------------------------------------------------------------------- |
| L1  | Complétude des données   | 1.0   | Vérifie la présence des champs critiques (prix, marque, modèle, année, km)|
| L2  | Modèle reconnu           | 2.0   | Recherche le véhicule dans le référentiel (1 961 véhicules, aliases)      |
| L3  | Cohérence km / année     | 1.5   | Détecte les kilométrages anormaux par rapport à l'âge                     |
| L4  | Prix vs marché           | 2.0   | Compare le prix à l'Argus Maison géolocalisé (cascade MarketPrice → Argus → LBC) |
| L5  | Analyse statistique prix | 1.5   | Z-scores NumPy pour détecter les prix outliers                            |
| L6  | Téléphone                | 0.5   | Détecte les indicatifs étrangers et formats suspects                      |
| L7  | SIRET vendeur            | 1.0   | Vérifie le SIRET via l'API publique gouv.fr (FR) / UID (CH)              |
| L8  | Détection import         | 1.0   | Repère les signaux d'un véhicule importé (TVA, pays-aware)               |
| L9  | Évaluation globale       | 1.5   | Synthèse bonus/pénalités de l'annonce                                     |
| L10 | Ancienneté annonce       | 1.0   | Durée de mise en vente et détection des republications                    |
| L11 | Rappels constructeur     | 1.0   | Détecte les rappels sécurité (ex. Takata airbag)                         |

## Architecture OOP des filtres

```python
class BaseFilter(ABC):
    filter_id: str
    @abstractmethod
    def run(self, data: dict) -> FilterResult: ...

@dataclass
class FilterResult:
    filter_id: str      # "L1" ... "L11"
    status: str         # "pass" | "warning" | "fail" | "skip" | "neutral"
    score: float        # 0.0 à 1.0
    message: str
    details: dict | None

class FilterEngine:
    """Exécute les 11 filtres en parallèle via ThreadPoolExecutor."""
    def run_all(self, data: dict) -> list[FilterResult]: ...
```

## Argus Maison — Cotation collaborative

Plutôt que de dépendre uniquement de données Argus importées, le système collecte les prix réels du marché directement depuis les annonces grâce aux utilisateurs de l'extension.

```text
                        Extension Chrome
                              |
         1. Analyse d'une annonce (LBC, AS24, LaC, PV)
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
                              |
         4. POST /api/market-prices
            { make, model, year, region, prices, source }
                              |
         5. Filtrage + calcul NumPy (IQR Mean, min, median, max, std)
                              |
         6. Upsert MarketPrice (clé unique multi-colonnes)
```

**Stratégie de fallback** : MarketPrice crowdsourcé (≥ seuil dynamique) → MarketPrice année ±3 → ArgusPrice seed → estimation LBC → filtre skip

## Pipeline RAG YouTube / LLM

Construction automatique du référentiel de connaissances véhicules :

```text
yt-dlp (recherche vidéos)
    → youtube-transcript-api (extraction sous-titres FR)
    → Filtrage chaînes de confiance (L'Argus, Caradisiac, Fiches Auto)
    → Digestion LLM (Gemini cloud OU Ollama local)
    → VehicleSynthesis (stockage DB)
```

## Email vendeur IA

Génération automatique de mails personnalisés via **Google Gemini 2.5 Flash** :

- Adapté au type de vendeur (professionnel / particulier)
- Basé sur les résultats des 11 filtres (points forts, alertes à questionner)
- Intègre les rappels constructeur (L11) si détectés
- Prompts versionnés et configurables depuis l'admin
- Suivi des coûts LLM avec graphiques Plotly

## Rapport PDF premium

Génération de rapports PDF complets avec branding OKazCar :

- Score circulaire + verdict
- Mini-cards résumé (prix, km, année, carburant)
- Fiches détaillées des 11 filtres
- Dimensions pneus + loi montagne
- Fiabilité moteur (étoiles)
- Email vendeur pré-rédigé
- Technologie : WeasyPrint (HTML/CSS → PDF)

## Stack technique

- **Backend** : Python 3.12, Flask 3.1, SQLAlchemy 2.0, Pydantic 2.11
- **IA** : Google Gemini 2.5 Flash (emails, synthèses), Ollama (LLM local)
- **Data** : NumPy (z-scores, IQR Mean), Pandas (enrichissement CSV), Plotly (visualisation)
- **Base de données** : SQLite (21 modèles, fonctions custom, disque persistant Render)
- **Extension** : Chrome Manifest V3, vanilla JS, esbuild, CSS préfixé `.okazcar-*`
- **Tests** : pytest (922 tests) + Vitest/jsdom (459 tests) = **1 381 tests**
- **Lint** : ruff (PEP 8 strict)
- **CI** : GitHub Actions (ruff + pytest + vitest à chaque push)
- **Conteneurisation** : Docker (python:3.12-slim) + docker-compose
- **Déploiement** : Render Starter (Frankfurt, HTTPS auto, no cold start)
- **Distribution** : Chrome Web Store (validée Google, pré-production)

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

1. Builder l'extension : `npm run build:ext`
2. Ouvrir Chrome > `chrome://extensions`
3. Activer le **Mode développeur**
4. Cliquer **"Charger l'extension non empaquetée"**
5. Sélectionner le dossier `extension/`

## Tests

```bash
# Vérification complète (ruff + pytest + vitest)
npm run verify

# Tests Python uniquement
pytest

# Avec couverture
pytest --cov=app

# Tests JS (extension)
npm run test:extension

# Linting
ruff check .
```

## Structure du projet

```text
Co-Pilot/
├── app/
│   ├── __init__.py              # Flask Application Factory
│   ├── api/                     # Blueprint API (routes, market_routes)
│   ├── admin/                   # Blueprint admin (dashboard, templates)
│   ├── filters/                 # 11 filtres L1-L11 + BaseFilter + FilterEngine
│   ├── models/                  # 21 modèles SQLAlchemy (Vehicle, ScanLog,
│   │                            #   MarketPrice, YouTubeVideo, User...)
│   ├── schemas/                 # Schemas Pydantic (validation API)
│   ├── services/                # 26 services métier (extraction, scoring,
│   │                            #   market, gemini, youtube, report...)
│   └── extensions.py            # Extensions Flask (db, cors, login, limiter)
├── extension/
│   ├── manifest.json            # Manifest V3 (4 sites, 11 pays)
│   ├── content.js               # Script injecté on-demand
│   ├── background.js            # Service worker
│   ├── extractors/              # 4 extracteurs (LBC, AS24, LaC, PV)
│   ├── ui/                      # Composants UI (popup, filtres, progress)
│   ├── popup/                   # Popup de l'extension
│   └── tests/                   # 459 tests Vitest
├── tests/                       # 922 tests pytest
├── data/
│   ├── okazcar.db               # Base SQLite (non versionné)
│   └── seeds/                   # Données d'initialisation (vehicles, argus,
│                                #   youtube, gemini prompts, recalls)
├── scripts/                     # Scripts utilitaires (init_db, packaging,
│                                #   publish_render_release, sync_render...)
├── config.py                    # Configuration par environnement (dev/test/prod)
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
  "url": "https://www.leboncoin.fr/voitures/...",
  "source": "leboncoin"
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
    "tire_sizes": { ... },
    "engine_reliability": { ... },
    "scan_id": 42
  }
}
```

### POST /api/market-prices

Enregistre des prix collectés pour alimenter l'Argus Maison.

### POST /api/report/pdf

Génère un rapport PDF premium pour un scan donné (scan_id).

### POST /api/email-draft

Génère un email personnalisé pour contacter le vendeur (via Gemini).

### GET /api/market-prices/next-job

Retourne le prochain véhicule à collecter (smart job assignment).

### GET /api/health

Vérification de l'état du serveur + version.

## Dashboard admin

Le panneau d'administration (`/admin`) offre :

- **Dashboard** : statistiques d'usage, taux d'échec, warnings, scans
- **Référentiel véhicules** : gestion des 1 961 véhicules, demandes utilisateurs, auto-création depuis CSV
- **Motorisations** : specs crowdsourcées, suivi des promotions, candidats proches du seuil
- **Argus** : cotations crowdsourcées, stats par marque/région
- **Filtres** : maturité de chaque filtre, badges OK/simulé
- **YouTube** : vidéos par véhicule, extraction de sous-titres, featured toggle
- **Email/LLM** : configuration Gemini, prompts versionnés, coûts, drafts
- **Pipelines** : historique des exécutions
- **Issues** : recherches échouées, diagnostic des tokens
- **Erreurs** : logs WARNING/ERROR persistés en base

## Sites supportés

| Site | Pays | Extraction |
| --- | --- | --- |
| Leboncoin | France | `__NEXT_DATA__` JSON |
| AutoScout24 | CH, DE, FR, IT, BE, NL, AT, ES, PL, LU, SE, .com | JSON-LD + DOM |
| La Centrale | France | API La Centrale |
| ParuVendu | France | DOM parsing |

## Déploiement

- **Backend** : Render Starter (Frankfurt, ~$1.59 USD/mois, no cold start, HTTPS auto)
- **Extension** : Chrome Web Store (validée Google, pré-production)
- **DB** : SQLite locale → GitHub Release → Render sync au démarrage
- **CI/CD** : GitHub Actions (lint + tests automatiques)

## Auteur

**Malik Karaoui** — Projet de certification Python Software Engineer (mars 2026)

## Licence

MIT
