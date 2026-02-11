---
stepsCompleted: ['step-01-init', 'step-02-context', 'step-03-starter', 'step-04-decisions', 'step-05-patterns', 'step-06-structure', 'step-07-validation', 'step-08-complete']
inputDocuments: ['_bmad-output/planning-artifacts/prd.md', '_bmad-output/planning-artifacts/product-brief-Co-Pilot-2026-02-09.md', 'docs/Critères_Evaluation_python_formation.pdf']
workflowType: 'architecture'
workflow_completed: true
project_name: 'Co-Pilot'
user_name: 'Malik'
date: '2026-02-09'
completedAt: '2026-02-09'
---

# Architecture Decision Document

_This document builds collaboratively through step-by-step discovery. Sections are appended as we work through each architectural decision together._

## Project Context Analysis

### Requirements Overview

**Functional Requirements:**

45 FRs organisees en 8 domaines de capacite :

| Domaine | FRs | Implication architecturale |
|---------|-----|---------------------------|
| Analyse d'annonce (core) | FR1-FR7 | Module d'extraction + moteur de scoring central |
| Scoring & Filtres | FR8-FR14 | Hierarchie OOP : classe abstraite + 9 sous-classes independantes |
| Interface Extension Chrome | FR15-FR21 | Content script + popup + communication REST |
| Referentiel vehicules | FR22-FR25 | Couche donnees SQLite + modele vehicule structure |
| Dashboard & Monitoring | FR26-FR30 | Flask MPA (Jinja2 + Bootstrap + Plotly) |
| Pipeline amont | FR31-FR35 | Modules d'ingestion : YouTube, Whisper, LLM, datasets |
| Degradation & Resilience | FR36-FR39 | Pattern graceful degradation transversal |
| Monetisation (Phase 2) | FR40-FR45 | Firebase Auth + Stripe + tokens navigateur |

**Non-Functional Requirements:**

25 NFRs en 6 categories. Les plus structurants pour l'architecture :

- NFR1 : Scan < 10s -- les filtres doivent tourner en parallele quand possible (NFR4)
- NFR3 : Extension n'ajoute pas > 500ms au chargement Leboncoin -- content script leger
- NFR8 : Validation/sanitization des donnees recues -- couche de validation API
- NFR24 : Migration SQLite vers PostgreSQL/Firestore possible -- couche d'abstraction DB
- NFR25 : Ajout de filtre = juste une nouvelle sous-classe -- pattern Strategy/Template Method

**Scale & Complexity:**

| Indicateur | Niveau | Detail |
|-----------|--------|--------|
| Domaine technique | Full-stack hybride | Extension Chrome + Backend Python + Data Pipeline |
| Complexite | Moyenne-haute | 3 sous-systemes distincts, 9 filtres OOP, 2 pipelines |
| Temps reel | Non | Request-response classique, pas de WebSocket |
| Multi-tenancy | Non (MVP) | Mono-utilisateur admin, users anonymes |
| Conformite reglementaire | Faible | RGPD basique (pas de donnees perso stockees) |
| Integrations externes | 3 | Leboncoin (DOM), API SIRET gouv.fr, YouTube (sous-titres) |
| Volume donnees | Faible (MVP) | 20 modeles, SQLite suffit |

- Primary domain: Full-stack hybride (Extension Chrome + Backend Python + Data Pipeline)
- Complexity level: Moyenne-haute
- Estimated architectural components: ~15 modules distincts

### Technical Constraints & Dependencies

1. **Deadline fixe 16 mars 2026** -- chaque decision architecturale doit privilegier la simplicite
2. **Solo dev + AI** -- pas de microservices, pas de sur-ingenierie, monolithe modulaire
3. **Grille jury** -- l'architecture doit demontrer OOP, heritage, modules externes, Flask UI + API, NumPy/Pandas, Docker, testing
4. **Extension Chrome** -- manifest V3, permissions minimales, communication HTTP standard
5. **Code existant** -- `lbc_extract.py` (extraction `__NEXT_DATA__`) a integrer
6. **Docker obligatoire** -- `docker-compose.yml` unique pour tout le stack

### Cross-Cutting Concerns Identified

1. **Degradation gracieuse** -- touche filtres, API, extension, messages UX. Doit etre un pattern architectural, pas du code ad hoc
2. **Extensibilite des filtres** -- le pattern OOP (abstract base + sous-classes) est au coeur du projet ET de la note jury
3. **Logging & monitoring** -- les erreurs/echecs remontent au dashboard, les stats d'usage alimentent la roadmap
4. **Dual interface** -- l'extension Chrome et le dashboard Flask consomment la meme API REST, mais avec des besoins differents
5. **Pipeline orchestration** -- pipeline amont (batch, offline) vs pipeline live (request-response, temps reel relatif) : deux modes d'execution distincts

### Architecture Direction

Un **monolithe modulaire Flask** avec separation claire en couches :
- Couche Extension (client JS autonome)
- Couche API REST (entree/sortie JSON)
- Couche Metier (filtres OOP, scoring, pipelines)
- Couche Donnees (SQLite avec abstraction)
- Couche Admin (MPA Jinja2/Plotly)

Pas de microservices. Pas de message queue. Pas d'over-engineering. Des modules Python bien decoupes dans un seul process Flask + Docker.

## Starter Template Evaluation

### Primary Technology Domain

Full-stack hybride Python : Backend Flask + Extension Chrome (vanilla JS) + Data Pipeline (NumPy/Pandas/Whisper).

### Technology Versions (verifiees fevrier 2026)

| Package | Version | Note |
|---------|---------|------|
| Python | 3.12.x | Choix stabilite -- compatibilite Whisper/NumPy garantie |
| Flask | 3.1.2 | Stable, application factory pattern confirme standard |
| SQLite | 3.50.4 | Bundle Python, zero config |
| pytest | 9.1 | |
| NumPy | 2.4.2 | |
| Pandas | 2.3.x | Pandas 3.0 a des breaking changes -- MVP sur 2.3.x |
| httpx | 0.28.1 | Client HTTP async/sync |
| BeautifulSoup4 | 4.14.3 | Parsing HTML |
| Plotly | 6.5.2 | Graphiques dashboard |
| Bootstrap | 5.3.8 | Via CDN pour dashboard |
| Whisper | v20250625 | Transcription locale |
| Docker Engine | 29.1.5 | |

### Starter Options Considered

| Starter | Approche | Verdict |
|---------|----------|---------|
| cookiecutter-flask | Full-featured (webpack, Factory-Boy) | Trop lourd -- pas de SPA, pas besoin de webpack |
| cookiecutter-flask-clean-architecture | Clean Architecture / Onion | Over-engineering pour MVP solo dev |
| cookiecutter-flask-openapi | API-first + SwaggerUI + JWT | Trop oriente API pure -- on a aussi le MPA |

### Selected Approach: Structure custom + Flask Application Factory

**Rationale:** Le projet est trop specifique (extension Chrome + MPA + pipelines data) pour rentrer dans un template generique. Structure custom appliquant les best practices Flask 2025-2026.

**Architectural Decisions Provided by Starter:**

**Language & Runtime:**
- Python 3.12.x (stable, images Docker officielles eprouvees)
- Flask 3.1.2 avec application factory pattern (`create_app()`)

**Code Organization:**
- Blueprints par fonctionnalite : `api/`, `admin/`, `pipeline/`
- Extensions Flask initialisees globalement, bindees via `init_app()` dans la factory
- Configuration par objets Python (classes `Config`, `DevConfig`, `TestConfig`)

**Styling Solution:**
- Extension Chrome : CSS simple inline / fichier CSS dedie
- Dashboard : Bootstrap 5.3.8 via CDN + templates Jinja2

**Build & Containerization:**
- `docker-compose.yml` unique
- Image Docker basee sur `python:3.12-slim`
- Volume persistant pour SQLite

**Testing Framework:**
- pytest 9.1 avec fixtures Flask (`app.test_client()`)
- Mocks pour APIs externes (SIRET, Leboncoin)

**Note:** L'initialisation du projet sera la premiere story d'implementation.

## Core Architectural Decisions

### Decision Priority Analysis

**Critical Decisions (Block Implementation):**

| # | Decision | Choix | Rationale | Affecte |
|---|----------|-------|-----------|---------|
| D1 | ORM | SQLAlchemy ORM | Criteres jury 02+08 (classes, modelisation donnees), NFR24 (migration DB) | Tous les modeles, API, pipelines |
| D2 | Validation donnees API | Pydantic | Moderne, type-safe, validation + serialisation | API REST, extension - backend |
| D3 | Auth admin MVP | Flask-Login (user admin en config) | Critere jury 08 (authentification), extensible Phase 2 | Dashboard admin |
| D4 | Format erreur API | Enveloppe uniforme `{success, error, message, data}` | Degradation gracieuse integree, lisible cote extension | API REST, extension Chrome |
| D5 | Logging | Python logging standard + ecriture DB | Critere jury 04 (built-ins), alimente le dashboard | Transversal |

**Important Decisions (Shape Architecture):**

| # | Decision | Choix | Rationale |
|---|----------|-------|-----------|
| D6 | CORS | Flask-CORS, whitelist extension uniquement | Securite API, seule l'extension peut appeler |
| D7 | Docker | Dockerfile simple + docker-compose.yml | Critere jury 09, pas besoin de multi-stage MVP |
| D8 | Configuration | Classes Python (Config, DevConfig, TestConfig) + .env | Pattern Flask standard, separation environnements |
| D9 | CI/CD | GitHub Actions (lint + pytest) | Critere jury 09 (DevOps), gratuit, integre |
| D10 | API versioning | Pas de versioning MVP (/api/analyze) | Un seul client (extension), on versionne en Phase 2 |

**Deferred Decisions (Post-MVP):**

| Decision | Raison du report | Phase |
|----------|------------------|-------|
| Firebase Auth | Pas de paiement MVP | Phase 2 |
| Stripe integration | Pas de monetisation MVP | Phase 2 |
| Rate limiting | Volume faible MVP | Phase 2 |
| API versioning | Un seul client MVP | Phase 2 |
| Migration PostgreSQL/Firestore | SQLite suffit MVP | Phase 2+ |

### Data Architecture

- **ORM** : SQLAlchemy ORM avec modeles Python mappes aux tables SQLite
- **Validation** : Pydantic schemas pour valider/serialiser les donnees API (entree et sortie)
- **Separation** : Modeles SQLAlchemy (persistance) + Schemas Pydantic (API) = deux couches distinctes
- **Migration DB** : SQLAlchemy abstrait le moteur -- migration SQLite vers PostgreSQL/Firestore par changement de connection string (NFR24)

### Authentication & Security

- **MVP** : Flask-Login avec un seul user admin defini dans la config (username + password hashe)
- **Dashboard** : decorateur `@login_required` sur toutes les vues admin
- **API** : pas d'auth sur /api/analyze (gratuit, anonyme) -- auth premium en Phase 2 via Firebase
- **CORS** : Flask-CORS configure pour n'accepter que l'origine de l'extension Chrome
- **Input validation** : Pydantic valide et sanitize toutes les donnees recues avant traitement (NFR8)
- **Erreurs** : aucune stacktrace exposee a l'utilisateur (NFR10), messages conviviaux uniquement

### API & Communication Patterns

- **Style** : REST JSON standard, pas de GraphQL
- **Versioning** : pas de version prefix MVP (/api/analyze, /api/health)
- **Format reponse** : enveloppe uniforme pour toutes les reponses :
  - Succes : `{"success": true, "error": null, "message": null, "data": {...}}`
  - Erreur : `{"success": false, "error": "CODE", "message": "texte UX", "data": null}`
- **Endpoints MVP** : POST /api/analyze (scan gratuit), GET /api/health (sante service)
- **CORS** : whitelist extension Chrome uniquement

### Frontend Architecture

- **Extension Chrome** : vanilla JS, pas de framework, content script + popup
- **Communication** : fetch() standard vers l'API REST backend
- **Stockage local** : chrome.storage.local pour preferences et tokens
- **Dashboard** : Jinja2 templates + Bootstrap 5.3.8 CDN + Plotly pour graphiques
- **Pas de SPA** : MPA traditionnel cote dashboard, injection DOM cote extension

### Infrastructure & Deployment

- **Docker** : Dockerfile simple (python:3.12-slim) + docker-compose.yml
- **Volume** : volume Docker persistant pour SQLite
- **Config** : classes Python (Config, DevConfig, TestConfig) + fichier .env
- **CI/CD** : GitHub Actions (lint flake8/ruff + pytest)
- **Deploiement MVP** : local Docker pour demo jury
- **Deploiement Phase 2** : VPS/cloud avec docker-compose

### Decision Impact Analysis

**Implementation Sequence:**
1. Flask factory + config + Docker -- fondation
2. SQLAlchemy models + DB init -- couche donnees
3. API blueprint + Pydantic schemas + CORS -- communication
4. Filtres OOP (abstract base + sous-classes) -- coeur metier
5. Dashboard blueprint + Flask-Login + Plotly -- admin
6. Extension Chrome + content script -- client
7. Pipelines amont -- enrichissement donnees
8. Tests pytest -- validation

**Cross-Component Dependencies:**
- SQLAlchemy ORM + Pydantic -- deux couches de modeles (DB models + API schemas), separation propre persistance/API
- Flask-Login -- necessite table User ou dict config, routes /login /logout, decorateur @login_required sur vues admin
- Python logging + DB -- LogHandler custom qui ecrit en table logs, dashboard lit cette table pour stats
- Flask-CORS -- origines autorisees dans config (CORS_ORIGINS), a mettre a jour quand extension publiee

## Implementation Patterns & Consistency Rules

### Naming Patterns

**Python (PEP 8 strict) :**

| Element | Convention | Exemple |
|---------|-----------|---------|
| Fichiers | snake_case.py | filter_price.py |
| Classes | PascalCase | PriceFilter, VehicleModel |
| Fonctions/methodes | snake_case | calculate_score(), run_filter() |
| Variables | snake_case | scan_result, filter_score |
| Constantes | UPPER_SNAKE_CASE | MAX_SCORE = 100, API_TIMEOUT = 5 |
| Modules/packages | snake_case | filters/, pipeline_youtube/ |
| Classe abstraite | Prefixe Base | BaseFilter |
| Sous-classes filtres | L{n}{Nom}Filter | L1ExtractionFilter, L4PriceFilter |

**JavaScript (extension Chrome) :**

| Element | Convention | Exemple |
|---------|-----------|---------|
| Fichiers | kebab-case.js | content-script.js, popup-ui.js |
| Fonctions | camelCase | analyzeAnnounce(), displayScore() |
| Variables | camelCase | scanResult, filterScore |
| Constantes | UPPER_SNAKE_CASE | API_BASE_URL, MAX_RETRY |
| Classes CSS | kebab-case avec prefixe | .copilot-gauge, .copilot-popup |

**Base de donnees (SQLAlchemy) :**

| Element | Convention | Exemple |
|---------|-----------|---------|
| Tables | snake_case, pluriel | vehicles, scan_logs, filter_results |
| Colonnes | snake_case | model_year, created_at, filter_score |
| Foreign keys | {table_singulier}_id | vehicle_id, scan_id |
| Index | ix_{table}_{colonne} | ix_vehicles_brand |

**API :**

| Element | Convention | Exemple |
|---------|-----------|---------|
| Endpoints | snake_case, pas de trailing slash | /api/analyze, /api/health |
| JSON fields | snake_case | {"filter_score": 85, "red_flags": [...]} |
| Error codes | UPPER_SNAKE_CASE | MODEL_NOT_FOUND, API_TIMEOUT |
| HTTP methods | Standard REST | POST pour actions, GET pour lectures |

### Structure Patterns

**Tests :** Repertoire tests/ separe, structure miroir du code source :

```
tests/
  test_filters/
    test_base_filter.py
    test_l1_extraction.py
    ...
  test_api/
    test_analyze.py
  test_models/
    test_vehicle.py
  conftest.py          # fixtures partagees
```

**Blueprints :** Organisation par fonctionnalite :

```
app/
  api/                 # Blueprint API REST
    routes.py
    schemas.py         # Pydantic schemas
  admin/               # Blueprint dashboard
    routes.py
    templates/
  filters/             # Coeur metier
    base.py            # BaseFilter (ABC)
    l1_extraction.py
    ...l9_score.py
    engine.py          # Orchestrateur des filtres
  models/              # SQLAlchemy models
    vehicle.py
    scan.py
  services/            # Logique metier
    scoring.py
    argus.py
  pipeline/            # Pipeline amont
    youtube.py
    whisper.py
    datasets.py
```

### Process Patterns

**Filtres -- Pattern de retour uniforme :**

Chaque filtre DOIT retourner un FilterResult :

```python
@dataclass
class FilterResult:
    filter_id: str          # "L1", "L2", ..., "L9"
    status: str             # "pass" | "warning" | "fail" | "skip"
    score: float            # 0.0 a 1.0 (contribution au score global)
    message: str            # Message UX lisible
    details: dict | None    # Donnees complementaires
```

**Error handling -- Hierarchie d'exceptions :**

```python
class CoPilotError(Exception):         # Base
class FilterError(CoPilotError):       # Erreur dans un filtre
class ExtractionError(CoPilotError):   # Erreur extraction Leboncoin
class ExternalAPIError(CoPilotError):  # API SIRET, etc.
class ValidationError(CoPilotError):   # Donnees invalides
```

Regle : jamais de `except Exception` nu. Toujours catcher un type specifique.

**Logging -- Convention par module :**

```python
import logging
logger = logging.getLogger(__name__)

logger.info("Scan started", extra={"annonce_id": "123"})
logger.warning("Price anomaly detected", extra={"delta": 22})
logger.error("SIRET API timeout", extra={"timeout": 5})
```

Niveaux : DEBUG (dev), INFO (flux normal), WARNING (anomalie non-bloquante), ERROR (echec recuperable), CRITICAL (jamais en prod).

**Degradation gracieuse -- Pattern systematique :**

```python
# Chaque filtre gere sa propre degradation
try:
    result = filter.run(data)
except FilterError:
    result = FilterResult(
        filter_id=filter.id,
        status="skip",
        score=0.0,
        message="Analyse partielle -- ce filtre n'a pas pu s'executer",
        details=None
    )
```

Jamais de crash silencieux. Toujours un FilterResult meme en echec.

### Format Patterns

| Format | Convention | Exemple |
|--------|-----------|---------|
| Dates JSON | ISO 8601 UTC | "2026-02-09T14:30:00Z" |
| Scores | Float 0.0 a 1.0 (interne), Int 0-100 (API) | 0.67 -> 67 |
| Booleens | true/false JSON natif | "is_professional": true |
| Null | null JSON, jamais string vide | "siret": null |
| HTTP status | 200 (succes), 400 (validation), 404 (not found), 500 (erreur serveur) | |

### Enforcement Guidelines

**Tout agent IA DOIT :**
1. Suivre PEP 8 pour Python, conventions JS standard pour l'extension
2. Retourner un FilterResult pour chaque filtre -- pas d'exception qui remonte
3. Utiliser l'enveloppe API {success, error, message, data} pour toutes les reponses
4. Logger via logging.getLogger(__name__) -- jamais de print()
5. Catcher des exceptions specifiques -- jamais de except Exception nu
6. Prefixer toutes les classes CSS extension avec copilot-
7. Ecrire au moins un test par filtre avec donnees valides, invalides, edge case

## Project Structure & Boundaries

### Complete Project Directory Structure

```
co-pilot/
├── README.md
├── .gitignore
├── .env.example
├── .env
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── requirements-dev.txt
├── wsgi.py                          # Point d'entree WSGI (gunicorn)
│
├── .github/
│   └── workflows/
│       └── ci.yml                   # GitHub Actions : lint + pytest
│
├── config.py                        # Config, DevConfig, TestConfig
│
├── app/
│   ├── __init__.py                  # create_app() factory
│   ├── extensions.py                # db, login_manager, cors init
│   │
│   ├── models/                      # SQLAlchemy ORM
│   │   ├── __init__.py
│   │   ├── vehicle.py               # Vehicle, VehicleSpec
│   │   ├── scan.py                  # ScanLog, ScanResult
│   │   ├── filter_result.py         # FilterResult (DB)
│   │   ├── argus.py                 # ArgusPrice (geolocalise)
│   │   ├── log.py                   # AppLog (pour dashboard)
│   │   └── user.py                  # User (admin Flask-Login)
│   │
│   ├── schemas/                     # Pydantic schemas (API)
│   │   ├── __init__.py
│   │   ├── analyze.py               # AnalyzeRequest, AnalyzeResponse
│   │   ├── vehicle.py               # VehicleSchema
│   │   ├── filter_result.py         # FilterResultSchema
│   │   └── common.py                # APIResponse envelope
│   │
│   ├── api/                         # Blueprint API REST
│   │   ├── __init__.py              # Blueprint registration
│   │   ├── routes.py                # POST /api/analyze, GET /api/health
│   │   └── errors.py                # Error handlers API (JSON)
│   │
│   ├── admin/                       # Blueprint dashboard MPA
│   │   ├── __init__.py              # Blueprint registration
│   │   ├── routes.py                # Pages dashboard
│   │   ├── auth.py                  # Login/logout routes
│   │   ├── templates/
│   │   │   ├── base.html            # Layout Bootstrap
│   │   │   ├── login.html
│   │   │   ├── dashboard.html       # Stats + Plotly
│   │   │   ├── scans.html           # Historique scans
│   │   │   ├── errors_log.html      # Logs erreurs
│   │   │   ├── vehicles.html        # Gestion referentiel
│   │   │   └── pipelines.html       # Etat pipelines
│   │   └── static/
│   │       └── css/
│   │           └── admin.css
│   │
│   ├── filters/                     # Coeur metier OOP
│   │   ├── __init__.py
│   │   ├── base.py                  # BaseFilter (ABC) + FilterResult dataclass
│   │   ├── engine.py                # FilterEngine (orchestrateur, parallele)
│   │   ├── l1_extraction.py         # L1ExtractionFilter
│   │   ├── l2_referentiel.py        # L2ReferentielFilter
│   │   ├── l3_coherence.py          # L3CoherenceFilter
│   │   ├── l4_price.py              # L4PriceFilter (argus)
│   │   ├── l5_visual.py             # L5VisualFilter (NumPy)
│   │   ├── l6_phone.py              # L6PhoneFilter
│   │   ├── l7_siret.py              # L7SiretFilter (API gouv)
│   │   ├── l8_reputation.py         # L8ReputationFilter
│   │   └── l9_score.py              # L9ScoreFilter (agregation)
│   │
│   ├── services/                    # Logique metier
│   │   ├── __init__.py
│   │   ├── scoring.py               # Calcul score global
│   │   ├── extraction.py            # Parsing __NEXT_DATA__
│   │   ├── argus.py                 # Service argus geolocalise
│   │   ├── siret.py                 # Client API SIRET gouv.fr
│   │   └── vehicle_lookup.py        # Recherche referentiel
│   │
│   ├── pipeline/                    # Pipeline amont (batch)
│   │   ├── __init__.py
│   │   ├── youtube.py               # Extraction sous-titres YouTube
│   │   ├── whisper.py               # Transcription audio locale
│   │   ├── llm_digest.py            # LLM -> fiches vehicules
│   │   ├── datasets.py              # Import car-list, CSVs, Teoalida
│   │   └── argus_collector.py       # Collecte argus Leboncoin
│   │
│   ├── errors.py                    # Hierarchie exceptions CoPilot
│   └── logging_config.py            # Config logging + DBHandler
│
├── extension/                       # Extension Chrome (separe)
│   ├── manifest.json                # Manifest V3
│   ├── content-script.js            # Injection page Leboncoin
│   ├── popup.html                   # Popup resultats
│   ├── popup.js                     # Logique popup
│   ├── styles.css                   # Styles .copilot-*
│   ├── icons/
│   │   ├── icon-16.png
│   │   ├── icon-48.png
│   │   └── icon-128.png
│   └── lib/
│       ├── api-client.js            # Communication REST backend
│       └── gauge.js                 # Jauge circulaire SVG
│
├── data/                            # Donnees statiques et datasets
│   ├── car-list.json                # Liste modeles
│   ├── youtube_channels.json        # Chaines YouTube cibles
│   └── seeds/                       # Donnees init SQLite
│       └── seed_vehicles.py
│
├── tests/
│   ├── conftest.py                  # Fixtures : app, client, db
│   ├── test_filters/
│   │   ├── test_base_filter.py
│   │   ├── test_l1_extraction.py
│   │   ├── test_l2_referentiel.py
│   │   ├── test_l3_coherence.py
│   │   ├── test_l4_price.py
│   │   ├── test_l5_visual.py
│   │   ├── test_l6_phone.py
│   │   ├── test_l7_siret.py
│   │   ├── test_l8_reputation.py
│   │   ├── test_l9_score.py
│   │   └── test_engine.py
│   ├── test_api/
│   │   ├── test_analyze.py
│   │   └── test_health.py
│   ├── test_models/
│   │   ├── test_vehicle.py
│   │   └── test_scan.py
│   ├── test_services/
│   │   ├── test_scoring.py
│   │   ├── test_extraction.py
│   │   └── test_siret.py
│   ├── mocks/
│   │   ├── mock_leboncoin.py        # Faux __NEXT_DATA__
│   │   ├── mock_siret.py            # Faux reponses API SIRET
│   │   └── sample_annonces.json     # 5 annonces test pre-validees
│   └── fixtures/
│       └── test_vehicles.json       # Donnees vehicules test
│
├── docs/                            # Documentation projet
│   └── Criteres_Evaluation_python_formation.pdf
│
└── scripts/                         # Scripts utilitaires
    ├── init_db.py                   # Creation tables + seed
    └── run_pipeline.py              # Lancement pipeline amont
```

### Requirements to Structure Mapping

| Domaine FR | Repertoire | Fichiers cles |
|-----------|-----------|--------------|
| FR1-FR7 (Analyse annonce) | app/services/extraction.py, app/api/routes.py | Extraction + endpoint |
| FR8-FR14 (Scoring & Filtres) | app/filters/ | base.py + l1 a l9 + engine.py |
| FR15-FR21 (Extension Chrome) | extension/ | content-script.js, popup.js, gauge.js |
| FR22-FR25 (Referentiel) | app/models/vehicle.py, app/services/vehicle_lookup.py | ORM + service |
| FR26-FR30 (Dashboard) | app/admin/ | Routes + templates Jinja2/Plotly |
| FR31-FR35 (Pipeline amont) | app/pipeline/ | YouTube, Whisper, LLM, datasets |
| FR36-FR39 (Degradation) | app/filters/base.py, app/errors.py | FilterResult "skip" + exceptions |
| FR40-FR45 (Monetisation P2) | (pas de fichiers MVP) | Architecture prete via blueprints |

### Architectural Boundaries

**Frontiere API :**

Extension Chrome --HTTP/JSON--> app/api/routes.py --> app/filters/engine.py --> app/services/ --> app/models/

L'extension ne touche JAMAIS les modeles ou la DB directement. Tout passe par l'API REST.

**Frontiere Admin :**

Navigateur --HTTP/HTML--> app/admin/routes.py --> app/models/ (lecture) --> app/admin/templates/ (rendu)

Le dashboard lit les donnees mais ne modifie pas la logique metier des filtres.

**Frontiere Pipeline :**

scripts/run_pipeline.py --> app/pipeline/*.py --> app/models/ (ecriture)

Le pipeline est batch -- il s'execute separement, pas dans le cycle request-response.

**Frontiere Extension :**

extension/ est un projet autonome. Zero import Python. Communication uniquement via REST API. Son propre manifest.json, ses propres fichiers JS/CSS/HTML.

### Data Flow

```
[Leboncoin DOM]
     | __NEXT_DATA__ JSON
     v
[Extension content-script.js] --POST /api/analyze-->
     |                                               |
     |                                    [app/api/routes.py]
     |                                         | Pydantic validate
     |                                         v
     |                                    [app/filters/engine.py]
     |                                         | run L1..L9 en parallele
     |                                         | chaque filtre -> FilterResult
     |                                         v
     |                                    [app/services/scoring.py]
     |                                         | score global 0-100
     |                                         v
     |                                    [app/models/scan.py]
     |                                         | persist ScanLog + resultats
     |                              <--JSON--  |
     v
[Extension popup.js] --> affiche jauge + details
```

### Integration Points

**Internal Communication:**
- API routes -> FilterEngine -> individual filters (via BaseFilter interface)
- FilterEngine -> Services (scoring, argus, siret, vehicle_lookup)
- Services -> Models (SQLAlchemy ORM)
- Admin routes -> Models (read-only queries)
- Pipeline scripts -> Models (write operations)

**External Integrations:**
- Extension Chrome <-> Backend Flask : REST API (HTTP/JSON)
- L7SiretFilter -> API SIRET gouv.fr : httpx GET avec timeout 5s
- Pipeline YouTube -> YouTube : extraction sous-titres
- Pipeline Whisper -> local : transcription audio
- Pipeline LLM -> LLM API : generation fiches vehicules

## Architecture Validation Results

### Coherence Validation

**Decision Compatibility:** PASS
- Flask 3.1.2 + SQLAlchemy ORM + Pydantic : stack classique, aucun conflit
- Flask-Login + Flask-CORS + Blueprints : extensions standard Flask
- Pydantic (API) vs SQLAlchemy (DB) : deux couches intentionnelles
- pytest + Flask test_client + mocks : coherent
- Docker python:3.12-slim + SQLite volume persistant : coherent

**Pattern Consistency:** PASS
- PEP 8 (Python) + camelCase (JS) : standard pour chaque langage
- FilterResult uniforme + API envelope : un langage interne, un langage API
- Naming conventions coherentes dans toutes les couches

**Structure Alignment:** PASS
- Blueprints (api/, admin/) alignes avec direction architecturale
- filters/ module separe avec hierarchie OOP
- pipeline/ separe du cycle request-response
- extension/ totalement autonome
- tests/ structure miroir

### Requirements Coverage Validation

**Functional Requirements:** 45/45 couverts

| FRs | Couvert par | Statut |
|-----|------------|--------|
| FR1-FR7 (Analyse annonce) | app/services/extraction.py + app/api/routes.py | OK |
| FR8-FR14 (Scoring & Filtres) | app/filters/ (9 filtres + engine) | OK |
| FR15-FR21 (Extension Chrome) | extension/ (content-script, popup, gauge) | OK |
| FR22-FR25 (Referentiel) | app/models/vehicle.py + app/services/vehicle_lookup.py | OK |
| FR26-FR30 (Dashboard) | app/admin/ (routes + templates Plotly) | OK |
| FR31-FR35 (Pipeline amont) | app/pipeline/ (YouTube, Whisper, LLM, datasets) | OK |
| FR36-FR39 (Degradation) | app/filters/base.py (FilterResult "skip") + app/errors.py | OK |
| FR40-FR45 (Monetisation P2) | Hors MVP -- architecture extensible via blueprints | OK (differe) |

**Non-Functional Requirements:** 25/25 couverts

| NFRs | Couvert par | Statut |
|------|------------|--------|
| NFR1-5 (Performance) | FilterEngine parallele (ThreadPoolExecutor), content script leger | OK |
| NFR6-10 (Securite) | Pas de donnees perso, Flask-Login, Pydantic validation | OK |
| NFR11-15 (Integration) | Timeouts services, monitoring __NEXT_DATA__, Whisper local | OK |
| NFR16-19 (Fiabilite) | FilterResult "skip", volumes Docker, messages degradation | OK |
| NFR20-23 (Testabilite) | pytest par filtre, conftest fixtures, mocks | OK |
| NFR24-25 (Evolutivite) | SQLAlchemy abstraction DB, BaseFilter + sous-classes | OK |

### Gap Analysis Results

**Gap 1 (resolu) : Parallelisation des filtres**
- Probleme : strategie de parallelisation non specifiee
- Resolution : concurrent.futures.ThreadPoolExecutor (Python standard, critere jury 04 built-ins)
- FilterEngine utilise ThreadPoolExecutor(max_workers=9) + as_completed()

**Gap 2 (resolu) : Integration lbc_extract.py existant**
- Probleme : code existant a integrer dans l'architecture
- Resolution : reecriture propre dans app/services/extraction.py en conservant la logique fonctionnelle (extraction __NEXT_DATA__)
- Le code original est un test fonctionnel -- la logique est bonne, le code sera reecrit avec nos patterns (classes, error handling, logging)

**Gaps critiques : 0**

### Architecture Completeness Checklist

- [x] Contexte projet analyse (complexite moyenne-haute)
- [x] 6 contraintes techniques identifiees
- [x] 5 preoccupations transversales mappees
- [x] 10 decisions architecturales documentees avec versions
- [x] 5 decisions differees post-MVP
- [x] Patterns de nommage (Python, JS, DB, API)
- [x] Patterns de processus (filtres, erreurs, logging, degradation)
- [x] Structure complete (~70 fichiers)
- [x] 4 frontieres architecturales definies
- [x] Flux de donnees bout en bout documente
- [x] Mapping FRs vers structure
- [x] 45/45 FRs couverts
- [x] 25/25 NFRs couverts
- [x] Grille jury alignee (10 criteres)
- [x] 2 gaps identifies et resolus

### Architecture Readiness Assessment

**Overall Status:** PRET POUR L'IMPLEMENTATION

**Confidence Level:** Haute

**Key Strengths:**
- Monolithe modulaire = simplicite maximale pour solo dev + deadline
- OOP filters avec heritage = coeur du projet ET critere jury
- Separation claire des couches (API, metier, donnees, admin, extension)
- Architecture extensible (nouveaux filtres, migration DB, blueprints)
- 100% couverture exigences (45 FRs + 25 NFRs)

**Areas for Future Enhancement:**
- Rate limiting API (Phase 2)
- Firebase Auth + Stripe integration (Phase 2)
- Migration SQLite vers PostgreSQL/Firestore (Phase 2+)
- API versioning (Phase 2)
- Monitoring avance (APM, alerting)

### Implementation Handoff

**AI Agent Guidelines:**
- Suivre toutes les decisions architecturales exactement comme documentees
- Utiliser les patterns d'implementation de maniere coherente dans tous les composants
- Respecter la structure projet et les frontieres
- Se referer a ce document pour toutes les questions architecturales

**First Implementation Priority:**
1. Flask factory + config + Docker (fondation)
2. SQLAlchemy models + DB init (couche donnees)
3. API blueprint + Pydantic schemas + CORS (communication)
4. Filtres OOP : BaseFilter ABC + premiers filtres (coeur metier)
