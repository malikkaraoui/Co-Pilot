---
stepsCompleted: [1, 2, 3]
inputDocuments:
  - '_bmad-output/planning-artifacts/prd.md'
  - '_bmad-output/planning-artifacts/architecture.md'
---

# Co-Pilot - Epic Breakdown

## Overview

This document provides the complete epic and story breakdown for Co-Pilot, decomposing the requirements from the PRD and Architecture requirements into implementable stories.

## Requirements Inventory

### Functional Requirements

- FR1: L'utilisateur peut declencher une analyse sur n'importe quelle page annonce Leboncoin
- FR2: Le systeme peut extraire les donnees structurees d'une annonce Leboncoin (prix, marque, modele, annee, kilometrage, carburant, boite, etc.)
- FR3: Le systeme peut calculer un score global sur 100 a partir de la convergence des filtres individuels
- FR4: L'utilisateur peut consulter le detail de chaque filtre avec son verdict individuel (vert/orange/rouge)
- FR5: L'utilisateur peut identifier les red flags et warnings sans connaissance automobile prealable
- FR6: Le systeme peut comparer le prix annonce a l'argus geolocalise de la region de l'annonce
- FR7: Le systeme peut verifier la coherence des donnees de l'annonce (km vs annee, prix vs modele, etc.)
- FR8: Le systeme peut executer 9 filtres independants (L1-L9) sur une annonce
- FR9: Le systeme peut verifier si le modele vehicule est present dans le referentiel
- FR10: Le systeme peut analyser le numero de telephone de l'annonce (indicatif etranger, format suspect)
- FR11: Le systeme peut verifier un numero SIRET via l'API publique gouv.fr
- FR12: Le systeme peut detecter les signaux d'import (historique incomplet, anomalie prix)
- FR13: Le systeme peut effectuer une analyse visuelle des donnees avec NumPy
- FR14: Le systeme peut produire un score partiel quand certains filtres ne sont pas applicables (modele non reconnu)
- FR15: L'utilisateur peut voir un bouton d'action injecte sur les pages annonces Leboncoin
- FR16: L'utilisateur peut voir une animation d'attente pendant le traitement de l'analyse
- FR17: L'utilisateur peut voir le score global dans une jauge circulaire
- FR18: L'utilisateur peut scroller dans la fenetre contextuelle pour voir les resultats detailles
- FR19: L'utilisateur peut deplier la fenetre contextuelle pour plus de details
- FR20: L'utilisateur peut voir le contenu premium floute derriere un effet liquid glass avec invitation a debloquer
- FR21: Le systeme peut afficher un message de degradation gracieuse humoristique en cas d'erreur
- FR22: Le systeme peut stocker et interroger un referentiel de specifications vehicules (20 modeles MVP)
- FR23: Le systeme peut fournir une fiche modele avec informations de fiabilite, problemes connus, et couts a prevoir
- FR24: Le systeme peut associer les donnees d'une annonce au bon modele dans le referentiel
- FR25: Le systeme peut stocker des donnees argus geolocalisees par region
- FR26: L'administrateur peut consulter les statistiques d'utilisation (scans gratuits, conversions premium, echecs)
- FR27: L'administrateur peut voir les modeles vehicules les plus demandes mais non reconnus
- FR28: L'administrateur peut monitorer l'etat des pipelines amont (YouTube, argus, imports)
- FR29: L'administrateur peut visualiser les donnees sous forme de graphiques interactifs
- FR30: L'administrateur peut consulter les logs d'erreurs et d'echecs
- FR31: Le systeme peut importer et normaliser des datasets vehicules (car-list.json, CSVs, Teoalida)
- FR32: Le systeme peut extraire les sous-titres de videos YouTube de chaines automobiles
- FR33: Le systeme peut transcrire des fichiers audio via Whisper en local
- FR34: Le systeme peut generer des fiches vehicules structurees a partir de transcriptions via LLM
- FR35: Le systeme peut collecter des donnees argus geolocalisees depuis Leboncoin
- FR36: Le systeme peut fonctionner en mode degrade quand un modele n'est pas reconnu (filtres universels uniquement)
- FR37: Le systeme peut remonter les echecs et erreurs au dashboard pour alimenter la roadmap
- FR38: Le systeme peut afficher des messages d'erreur conviviaux avec humour automobile sans exposer de details techniques
- FR39: Le systeme peut fonctionner dans un environnement Docker conteneurise
- FR40: L'utilisateur peut s'authentifier via email ou compte Google (Firebase Auth) [Phase 2]
- FR41: L'utilisateur peut acheter une analyse premium via paiement one-shot (Stripe checkout session) [Phase 2]
- FR42: Le systeme peut gerer l'acces premium via token stocke dans le navigateur [Phase 2]
- FR43: L'utilisateur peut telecharger le rapport d'analyse premium au format PDF [Phase 2]
- FR44: L'utilisateur peut recevoir le rapport d'analyse premium par email [Phase 2]
- FR45: Le rapport premium presente les memes donnees d'analyse dans un format structure et lisible [Phase 2]

### NonFunctional Requirements

- NFR1: L'analyse gratuite (scan) repond en moins de 10 secondes dans des conditions normales
- NFR2: Le dashboard admin charge en moins de 3 secondes
- NFR3: L'extension Chrome n'impacte pas le temps de chargement des pages Leboncoin de plus de 500ms
- NFR4: Les filtres s'executent en parallele quand ils sont independants pour minimiser le temps total
- NFR5: L'animation d'attente demarre en moins de 200ms apres le clic utilisateur (feedback immediat)
- NFR6: L'API REST n'expose aucune donnee personnelle utilisateur dans les reponses
- NFR7: L'authentification premium repose sur Firebase Auth (tokens securises, pas de credentials en clair) [Phase 2]
- NFR8: L'API valide et sanitize toutes les donnees recues de l'extension avant traitement
- NFR9: Le dashboard admin est protege par authentification (acces Malik uniquement)
- NFR10: Aucune stacktrace ou erreur technique n'est exposee a l'utilisateur final
- NFR11: Le systeme gere gracieusement l'indisponibilite de l'API SIRET gouv.fr (timeout + fallback)
- NFR12: Le systeme detecte les changements de structure du JSON __NEXT_DATA__ de Leboncoin et alerte l'admin
- NFR13: Les appels API externes (SIRET) ont un timeout de 5 secondes maximum
- NFR14: Le pipeline Whisper fonctionne entierement en local sans dependance reseau
- NFR15: Firebase Auth + Stripe checkout s'integrent via webhooks et Firebase Functions [Phase 2]
- NFR16: Le systeme affiche un score partiel plutot qu'une erreur quand des filtres echouent individuellement
- NFR17: Le backend supporte un redemarrage Docker sans perte de donnees (SQLite persistant)
- NFR18: L'extension fonctionne meme si le backend est temporairement injoignable (message de degradation)
- NFR19: Le systeme dispose de 5 annonces de test pre-validees pour les demos
- NFR20: Chaque filtre (L1-L9) dispose d'au moins un test unitaire avec donnees valides, invalides, et edge cases
- NFR21: La suite de tests peut s'executer avec pytest en moins de 60 secondes
- NFR22: Les tests sont reproductibles sans dependance a des services externes (mocks pour APIs)
- NFR23: Le code maintient une couverture de test suffisante pour demontrer la rigueur au jury
- NFR24: La base de donnees peut migrer de SQLite vers Firestore ou PostgreSQL sans refonte de l'architecture
- NFR25: L'ajout d'un nouveau filtre ne necessite que la creation d'une nouvelle sous-classe (pattern extensible)

### Additional Requirements

**Architecture technique :**
- Structure custom + Flask Application Factory (create_app()) -- pas de starter template
- Blueprints par fonctionnalite : api/, admin/, pipeline/
- SQLAlchemy ORM : modeles Vehicle, VehicleSpec, ScanLog, ScanResult, FilterResult, ArgusPrice, AppLog, User
- Pydantic schemas : AnalyzeRequest, AnalyzeResponse, VehicleSchema, FilterResultSchema, APIResponse envelope
- FilterResult dataclass uniforme : filter_id, status, score, message, details
- Hierarchie exceptions : CoPilotError -> FilterError, ExtractionError, ExternalAPIError, ValidationError
- FilterEngine avec ThreadPoolExecutor(max_workers=9) pour parallelisation
- Flask-Login pour admin (user admin en config)
- Flask-CORS whitelist extension uniquement
- Docker : Dockerfile python:3.12-slim + docker-compose.yml + volume SQLite persistant
- GitHub Actions CI : lint (ruff/flake8) + pytest
- Python logging standard + DBHandler custom pour alimenter le dashboard
- Configuration par classes Python (Config, DevConfig, TestConfig) + fichier .env
- Extension Chrome : Manifest V3, vanilla JS, CSS prefixe copilot-
- Sequence d'implementation : Flask factory -> Models -> API -> Filtres -> Dashboard -> Extension -> Pipeline -> Tests

### FR Coverage Map

| FR | Epic | Description |
|----|------|-------------|
| FR1 | Epic 1 | Declencher analyse sur page Leboncoin |
| FR2 | Epic 1 | Extraire donnees structurees annonce |
| FR3 | Epic 1 | Calculer score global sur 100 |
| FR4 | Epic 2 | Detail chaque filtre (vert/orange/rouge) |
| FR5 | Epic 2 | Red flags lisibles sans expertise |
| FR6 | Epic 2 | Comparaison prix/argus geolocalise |
| FR7 | Epic 2 | Verification coherence donnees |
| FR8 | Epic 1 | Executer 9 filtres independants |
| FR9 | Epic 2 | Verifier modele dans referentiel |
| FR10 | Epic 2 | Analyse numero telephone |
| FR11 | Epic 2 | Verification SIRET via API gouv |
| FR12 | Epic 2 | Detection signaux import |
| FR13 | Epic 2 | Analyse visuelle NumPy |
| FR14 | Epic 1 | Score partiel (modele non reconnu) |
| FR15 | Epic 4 | Bouton injecte sur Leboncoin |
| FR16 | Epic 4 | Animation d'attente |
| FR17 | Epic 4 | Jauge circulaire score |
| FR18 | Epic 4 | Scroll fenetre contextuelle |
| FR19 | Epic 4 | Deplier fenetre details |
| FR20 | Epic 4 | Liquid glass paywall |
| FR21 | Epic 4 | Message degradation humoristique (extension) |
| FR22 | Epic 3 | Referentiel 20 modeles |
| FR23 | Epic 3 | Fiche modele fiabilite/couts |
| FR24 | Epic 3 | Association annonce-modele |
| FR25 | Epic 3 | Argus geolocalise par region |
| FR26 | Epic 5 | Stats utilisation |
| FR27 | Epic 5 | Modeles non reconnus |
| FR28 | Epic 5 | Monitoring pipelines |
| FR29 | Epic 5 | Graphiques interactifs Plotly |
| FR30 | Epic 5 | Logs erreurs |
| FR31 | Epic 6 | Import datasets vehicules |
| FR32 | Epic 6 | Extraction sous-titres YouTube |
| FR33 | Epic 6 | Transcription Whisper local |
| FR34 | Epic 6 | Fiches vehicules via LLM |
| FR35 | Epic 6 | Collecte argus Leboncoin |
| FR36 | Epic 2 | Mode degrade (filtres universels) |
| FR37 | Epic 5 | Remontee echecs au dashboard |
| FR38 | Epic 2 | Messages erreur conviviaux |
| FR39 | Epic 1 | Docker conteneurise |
| FR40 | Epic 7 | Auth Firebase [Phase 2] |
| FR41 | Epic 7 | Stripe paiement [Phase 2] |
| FR42 | Epic 7 | Token premium navigateur [Phase 2] |
| FR43 | Epic 7 | PDF rapport premium [Phase 2] |
| FR44 | Epic 7 | Email rapport premium [Phase 2] |
| FR45 | Epic 7 | Rapport premium structure [Phase 2] |

## Epic List

### Epic 1: Fondation & Analyse Core
L'utilisateur peut soumettre les donnees d'une annonce Leboncoin et recevoir un score de confiance avec les resultats des filtres individuels.
**FRs covered:** FR1, FR2, FR3, FR8, FR14, FR39

### Epic 2: Les 9 Filtres d'Intelligence
Les 9 filtres specialises (coherence, prix/argus, telephone, SIRET, visuel NumPy, import, referentiel) tournent et convergent en un verdict detaille avec degradation gracieuse integree.
**FRs covered:** FR4, FR5, FR6, FR7, FR9, FR10, FR11, FR12, FR13, FR36, FR38

### Epic 3: Referentiel Vehicules & Argus
Le systeme connait 20 modeles vehicules avec fiches fiabilite, problemes connus, couts a prevoir et donnees argus geolocalisees par region.
**FRs covered:** FR22, FR23, FR24, FR25

### Epic 4: Experience Utilisateur Extension Chrome
L'utilisateur voit un bouton sur Leboncoin, clique, voit la jauge circulaire, scrolle les details et decouvre le paywall liquid glass.
**FRs covered:** FR15, FR16, FR17, FR18, FR19, FR20, FR21

### Epic 5: Dashboard de Pilotage Admin
Malik peut monitorer les stats (scans, conversions, echecs), voir les modeles demandes, suivre les pipelines, visualiser des graphiques Plotly et consulter les logs.
**FRs covered:** FR26, FR27, FR28, FR29, FR30, FR37

### Epic 6: Pipeline d'Enrichissement Donnees
Le systeme ingere YouTube → Whisper → LLM → fiches vehicules, importe les datasets et collecte l'argus geolocalise.
**FRs covered:** FR31, FR32, FR33, FR34, FR35

### Epic 7: Monetisation Premium [Phase 2]
L'utilisateur s'authentifie, paie 9,90€ et accede au rapport detaille (PDF, email).
**FRs covered:** FR40, FR41, FR42, FR43, FR44, FR45

## Epic 1 : Fondation & Analyse Core

L'utilisateur peut soumettre les donnees d'une annonce Leboncoin et recevoir un score de confiance avec les resultats des filtres individuels.

### Story 1.1 : Initialisation du projet Flask + Docker

En tant que developpeur,
Je veux un projet Flask fonctionnel conteneurise avec configuration par environnement,
Afin d'avoir une fondation stable et reproductible pour tous les composants.

**Criteres d'acceptation :**

**Etant donne** le depot git clone
**Quand** je lance `docker-compose up`
**Alors** le serveur Flask demarre sur le port configure
**Et** GET /api/health retourne `{"success": true, "data": {"status": "ok"}}`
**Et** les fichiers config.py, .env.example, Dockerfile, docker-compose.yml, requirements.txt existent
**Et** `create_app()` factory est fonctionnelle avec Config, DevConfig, TestConfig
**Et** GitHub Actions CI (lint + pytest) est configure

### Story 1.2 : Modeles de donnees core

En tant que developpeur,
Je veux les modeles SQLAlchemy Vehicle, ScanLog et FilterResult persistes en SQLite,
Afin que les donnees d'analyse puissent etre stockees et interrogees.

**Criteres d'acceptation :**

**Etant donne** l'application Flask initialisee
**Quand** je lance le script `init_db.py`
**Alors** les tables vehicles, scan_logs, filter_results sont creees en SQLite
**Et** le modele Vehicle contient les champs : brand, model, year, fuel_type, transmission
**Et** le modele ScanLog contient : url, raw_data, score, created_at
**Et** le modele FilterResult contient : scan_id (FK), filter_id, status, score, message, details
**Et** le volume Docker persiste les donnees entre redemarrages (NFR17)

### Story 1.3 : Service d'extraction des donnees Leboncoin

En tant que systeme,
Je veux parser le JSON `__NEXT_DATA__` d'une annonce Leboncoin et extraire les donnees vehicule structurees,
Afin que les annonces puissent etre analysees par les filtres.

**Criteres d'acceptation :**

**Etant donne** un payload JSON `__NEXT_DATA__` valide
**Quand** le service d'extraction est appele
**Alors** il retourne un objet structure avec : prix, marque, modele, annee, km, carburant, boite, telephone, localisation, description
**Et** les donnees invalides ou manquantes levent une `ExtractionError`
**Et** le service ne crashe pas sur un JSON malforme (NFR10)
**Et** un test unitaire valide l'extraction sur des donnees reelles et edge cases

### Story 1.4 : Framework de filtres (BaseFilter + FilterEngine)

En tant que developpeur,
Je veux une classe abstraite BaseFilter et un FilterEngine avec parallelisation ThreadPoolExecutor,
Afin que les filtres puissent etre ajoutes incrementalement et s'executent en parallele.

**Criteres d'acceptation :**

**Etant donne** la classe abstraite BaseFilter avec methode `run(data) -> FilterResult`
**Quand** un filtre concret herite de BaseFilter
**Alors** il DOIT implementer `run()` et retourner un FilterResult (filter_id, status, score, message, details)
**Et** FilterEngine execute les filtres en parallele via ThreadPoolExecutor (NFR4)
**Et** un filtre qui leve FilterError retourne automatiquement un FilterResult avec status="skip" (FR14)
**Et** la hierarchie d'exceptions CoPilotError est definie (FilterError, ExtractionError, ExternalAPIError, ValidationError)
**Et** un stub filter de test passe avec succes

### Story 1.5 : Endpoint API /api/analyze avec scoring

En tant qu'utilisateur,
Je veux envoyer les donnees d'une annonce a POST /api/analyze et recevoir un score sur 100,
Afin de pouvoir evaluer la fiabilite de n'importe quelle annonce Leboncoin.

**Criteres d'acceptation :**

**Etant donne** un payload JSON valide avec les donnees d'une annonce
**Quand** je POST sur /api/analyze
**Alors** le systeme extrait les donnees, execute les filtres disponibles, calcule le score global
**Et** la reponse suit l'enveloppe `{"success": true, "data": {"score": 67, "filters": [...]}}`
**Et** un payload invalide retourne `{"success": false, "error": "VALIDATION_ERROR", "message": "..."}`
**Et** Pydantic valide et sanitize les donnees entrantes (NFR8)
**Et** CORS n'accepte que l'origine de l'extension Chrome
**Et** aucune stacktrace n'est exposee en cas d'erreur (NFR10)

### Story 1.6 : Infrastructure de tests et premiers tests

En tant que developpeur,
Je veux des fixtures pytest, des mocks et des tests pour chaque composant cree,
Afin que le projet ait une base de tests solide des le depart.

**Criteres d'acceptation :**

**Etant donne** le fichier conftest.py avec fixtures app, client, db
**Quand** je lance `pytest`
**Alors** les tests passent pour : health endpoint, analyze endpoint, extraction service, BaseFilter, FilterEngine
**Et** les mocks simulent les donnees __NEXT_DATA__ (mock_leboncoin.py)
**Et** au moins 1 test par composant avec donnees valides, invalides, edge case
**Et** la suite s'execute en moins de 60 secondes (NFR21)

## Epic 2 : Les 9 Filtres d'Intelligence

Les 9 filtres specialises tournent en parallele et convergent en un verdict detaille. Chaque filtre herite de BaseFilter et retourne un FilterResult uniforme. Degradation gracieuse integree.

### Story 2.1 : L1 Extraction Quality Filter

En tant que systeme,
Je veux valider la qualite des donnees extraites (champs critiques presents, formats corrects),
Afin que les filtres suivants travaillent sur des donnees fiables.

**Criteres d'acceptation :**

**Etant donne** des donnees extraites d'une annonce
**Quand** le filtre L1 s'execute
**Alors** il verifie la presence des champs critiques (prix, marque, modele, annee, km)
**Et** il retourne "pass" si tous les champs critiques sont presents et valides
**Et** il retourne "warning" si des champs secondaires manquent (telephone, couleur)
**Et** il retourne "fail" si des champs critiques manquent
**Et** le score reflecte le ratio champs presents/attendus

### Story 2.2 : L2 Referentiel Filter

En tant que systeme,
Je veux verifier si le modele vehicule de l'annonce existe dans le referentiel Co-Pilot,
Afin de savoir si on peut appliquer les filtres specifiques au modele.

**Criteres d'acceptation :**

**Etant donne** les donnees extraites avec marque et modele
**Quand** le filtre L2 s'execute
**Alors** il cherche une correspondance dans la table vehicles (FR9)
**Et** il retourne "pass" si le modele est reconnu
**Et** il retourne "warning" avec message convivial si non reconnu (FR36, FR38)
**Et** les filtres dependant du referentiel recoivent l'info via le champ details

### Story 2.3 : L3 Coherence Filter

En tant que systeme,
Je veux verifier la coherence des donnees de l'annonce entre elles,
Afin de detecter les incoherences suspectes (FR7).

**Criteres d'acceptation :**

**Etant donne** les donnees extraites (annee, km, prix)
**Quand** le filtre L3 s'execute
**Alors** il verifie la coherence km vs annee (ex: 15 000 km/an +/- marge)
**Et** il detecte les kilometrages anormalement bas ou hauts pour l'annee
**Et** il verifie que le prix est dans une fourchette credible pour le type de vehicule
**Et** il retourne "pass", "warning" ou "fail" avec message explicite
**Et** les details contiennent les calculs (km_par_an, ecart_attendu)

### Story 2.4 : L4 Price / Argus Filter

En tant que systeme,
Je veux comparer le prix annonce a l'argus geolocalise de la region,
Afin de detecter les prix anormalement bas ou hauts (FR6).

**Criteres d'acceptation :**

**Etant donne** un vehicule reconnu dans le referentiel et des donnees argus disponibles
**Quand** le filtre L4 s'execute
**Alors** il compare le prix annonce au prix argus de la region
**Et** il retourne "pass" si l'ecart est < 10%
**Et** il retourne "warning" si l'ecart est entre 10-25%
**Et** il retourne "fail" si l'ecart est > 25% (anomalie prix)
**Et** il retourne "skip" si pas de donnees argus disponibles
**Et** les details contiennent prix_annonce, prix_argus, ecart_pct, region

### Story 2.5 : L5 Visual / NumPy Filter

En tant que systeme,
Je veux effectuer une analyse statistique des donnees numeriques de l'annonce avec NumPy,
Afin de detecter des anomalies par rapport aux distributions connues (FR13).

**Criteres d'acceptation :**

**Etant donne** les donnees extraites et les stats du referentiel
**Quand** le filtre L5 s'execute
**Alors** il calcule le z-score du prix et du kilometrage par rapport au referentiel
**Et** il utilise NumPy pour les calculs statistiques (critere jury 07)
**Et** il retourne "pass" si les valeurs sont dans la norme (|z| < 2)
**Et** il retourne "warning" si les valeurs sont en marge (2 < |z| < 3)
**Et** il retourne "fail" si les valeurs sont des outliers (|z| > 3)
**Et** il retourne "skip" si pas assez de donnees de reference

### Story 2.6 : L6 Phone Filter

En tant que systeme,
Je veux analyser le numero de telephone de l'annonce,
Afin de detecter les indicatifs etrangers et formats suspects (FR10).

**Criteres d'acceptation :**

**Etant donne** les donnees extraites avec numero de telephone
**Quand** le filtre L6 s'execute
**Alors** il detecte les indicatifs etrangers (hors +33/06/07)
**Et** il detecte les formats suspects (numeros trop courts, trop longs)
**Et** il retourne "pass" pour un numero francais standard
**Et** il retourne "warning" pour un indicatif etranger
**Et** il retourne "skip" si pas de numero dans l'annonce
**Et** le message est lisible : "Numero avec indicatif etranger (+48)"

### Story 2.7 : L7 SIRET Filter

En tant que systeme,
Je veux verifier un numero SIRET via l'API publique gouv.fr,
Afin d'identifier les vendeurs professionnels et verifier leur legitimite (FR11).

**Criteres d'acceptation :**

**Etant donne** un SIRET ou SIREN dans les donnees de l'annonce
**Quand** le filtre L7 s'execute
**Alors** il appelle l'API SIRET gouv.fr avec timeout 5s (NFR13)
**Et** il retourne "pass" si l'entreprise est active et coherente
**Et** il retourne "warning" si l'entreprise existe mais est radiee ou incoherente
**Et** il retourne "fail" si le SIRET est invalide
**Et** il retourne "skip" si pas de SIRET ou API indisponible (NFR11)
**Et** les tests mockent l'API externe (NFR22)

### Story 2.8 : L8 Import Detection Filter

En tant que systeme,
Je veux detecter les signaux d'un vehicule importe,
Afin d'alerter l'utilisateur sur les risques associes (FR12).

**Criteres d'acceptation :**

**Etant donne** les donnees extraites de l'annonce
**Quand** le filtre L8 s'execute
**Alors** il detecte les signaux d'import : prix anormalement bas, indicatif etranger, description mentionnant import/etranger
**Et** il croise avec le filtre L6 (telephone) si disponible
**Et** il retourne "pass" si aucun signal d'import
**Et** il retourne "warning" si 1 signal detecte
**Et** il retourne "fail" si 2+ signaux convergent
**Et** le message explique les signaux detectes de facon lisible (FR5)

### Story 2.9 : L9 Global Assessment Filter

En tant que systeme,
Je veux produire une synthese globale des signaux de confiance,
Afin de donner un verdict final lisible sans expertise (FR4, FR5).

**Criteres d'acceptation :**

**Etant donne** les donnees extraites et le contexte general
**Quand** le filtre L9 s'execute
**Alors** il evalue les signaux transversaux (type vendeur, anciennete annonce, description)
**Et** il detecte les descriptions trop courtes ou copier-coller suspectes
**Et** il retourne un verdict synthetique avec message lisible
**Et** les details contiennent un resume des points forts et points faibles

### Story 2.10 : Registration des filtres + degradation gracieuse

En tant que developpeur,
Je veux que les 9 filtres soient enregistres dans le FilterEngine et que la degradation gracieuse fonctionne bout en bout,
Afin que le flux /api/analyze retourne un score complet ou partiel selon les cas.

**Criteres d'acceptation :**

**Etant donne** le FilterEngine avec les 9 filtres enregistres
**Quand** POST /api/analyze est appele avec une annonce complete
**Alors** les 9 filtres tournent en parallele et le score converge
**Et** si un modele n'est pas reconnu, les filtres universels tournent quand meme (FR36)
**Et** les filtres qui echouent retournent "skip" sans bloquer les autres (FR14)
**Et** les messages d'erreur sont conviviaux (FR38)
**Et** le champ is_partial est true si des filtres ont ete "skip"

## Epic 3 : Referentiel Vehicules & Argus

Le systeme connait 20 modeles vehicules avec fiches fiabilite et donnees argus geolocalisees.

### Story 3.1 : Seed des 20 modeles vehicules

En tant que developpeur,
Je veux un script qui peuple la base avec les 20 modeles les plus vendus en France (2010-2025),
Afin que le referentiel soit operationnel pour le MVP.

**Criteres d'acceptation :**

**Etant donne** le script seed_vehicles.py
**Quand** je l'execute
**Alors** 20 modeles sont inseres dans la table vehicles avec brand, model, generation, year_start, year_end
**Et** les modeles couvrent les marques : Peugeot, Renault, Citroen, Volkswagen, Toyota, Dacia, etc.
**Et** les specs de base (fuel_type, transmission, power_hp) sont renseignees dans vehicle_specs
**Et** le script est idempotent (pas de doublons si relance)

### Story 3.2 : Service de lookup vehicule

En tant que systeme,
Je veux un service qui associe les donnees d'une annonce au bon vehicule du referentiel,
Afin que les filtres puissent utiliser les specs et l'argus (FR24).

**Criteres d'acceptation :**

**Etant donne** une marque et un modele extraits de l'annonce
**Quand** le service vehicle_lookup est appele
**Alors** il retourne le Vehicle correspondant ou None
**Et** la recherche est insensible a la casse et tolere les variantes courantes
**Et** des tests couvrent les cas : match exact, variante, non trouve

### Story 3.3 : Fiches modele (fiabilite, problemes, couts)

En tant qu'utilisateur premium (futur),
Je veux que chaque modele ait une fiche avec fiabilite, problemes connus et couts a prevoir,
Afin de comprendre les risques specifiques au modele (FR23).

**Criteres d'acceptation :**

**Etant donne** un vehicule dans le referentiel
**Quand** la fiche modele est demandee
**Alors** elle contient : reliability_rating, known_issues (texte), expected_costs (texte)
**Et** au moins 5 des 20 modeles ont des fiches completement renseignees pour le MVP
**Et** les fiches sont stockees dans vehicle_specs

### Story 3.4 : Donnees argus geolocalisees

En tant que systeme,
Je veux des donnees de prix argus par region pour les modeles du referentiel,
Afin que le filtre L4 puisse comparer le prix annonce (FR25).

**Criteres d'acceptation :**

**Etant donne** la table argus_prices
**Quand** on cherche l'argus pour un modele, annee et region
**Alors** on obtient price_low, price_mid, price_high
**Et** un script de seed injecte des donnees argus pour au moins 5 modeles dans 3 regions
**Et** le service argus retourne None si pas de donnees (le filtre L4 "skip")

## Epic 4 : Experience Utilisateur Extension Chrome

L'utilisateur voit un bouton sur Leboncoin, clique, voit la jauge circulaire, scrolle les details et decouvre le paywall.

### Story 4.1 : Manifest V3 + content script

En tant qu'utilisateur,
Je veux que l'extension detecte automatiquement les pages annonces Leboncoin,
Afin que le bouton Co-Pilot apparaisse sans action de ma part.

**Criteres d'acceptation :**

**Etant donne** l'extension installee dans Chrome
**Quand** je visite une page annonce sur leboncoin.fr
**Alors** le content script se charge automatiquement
**Et** le manifest.json est Manifest V3 avec permissions minimales (activeTab, storage)
**Et** host_permissions couvre *.leboncoin.fr et l'URL du backend
**Et** l'extension ne ralentit pas la page de plus de 500ms (NFR3)

### Story 4.2 : Bouton d'injection + appel API

En tant qu'utilisateur,
Je veux cliquer sur un bouton "Analyser avec Co-Pilot" injecte dans la page,
Afin de declencher l'analyse de l'annonce (FR1, FR15).

**Criteres d'acceptation :**

**Etant donne** le content script charge sur une page annonce
**Quand** le DOM est pret
**Alors** un bouton stylise .copilot-btn est injecte pres du prix de l'annonce
**Et** au clic, le script extrait __NEXT_DATA__ du DOM
**Et** les donnees sont envoyees a POST /api/analyze
**Et** une animation d'attente demarre en < 200ms (NFR5, FR16)

### Story 4.3 : Popup resultats + jauge circulaire

En tant qu'utilisateur,
Je veux voir le score dans une jauge circulaire apres l'analyse,
Afin de comprendre le verdict en un coup d'oeil (FR17).

**Criteres d'acceptation :**

**Etant donne** la reponse de l'API recue
**Quand** le score est disponible
**Alors** une popup contextuelle s'affiche avec une jauge circulaire SVG
**Et** la jauge affiche le score 0-100 au centre avec code couleur (vert > 70, orange 40-70, rouge < 40)
**Et** la popup est scrollable pour les details (FR18)
**Et** tous les elements CSS sont prefixes .copilot-*

### Story 4.4 : Details filtres + verdicts couleur

En tant qu'utilisateur,
Je veux voir le detail de chaque filtre avec son verdict en couleur,
Afin d'identifier les points forts et les red flags (FR4, FR5).

**Criteres d'acceptation :**

**Etant donne** les resultats des filtres dans la reponse API
**Quand** l'utilisateur scrolle dans la popup
**Alors** chaque filtre est affiche avec icone + couleur (vert=pass, orange=warning, rouge=fail, gris=skip)
**Et** le message de chaque filtre est lisible sans expertise automobile
**Et** la fenetre est depliable pour plus de details (FR19)

### Story 4.5 : Liquid glass paywall + animation

En tant qu'utilisateur,
Je veux decouvrir le contenu premium floute derriere un effet liquid glass,
Afin d'etre incite a debloquer le rapport complet (FR20).

**Criteres d'acceptation :**

**Etant donne** les resultats gratuits affiches
**Quand** l'utilisateur scrolle au-dela des resultats gratuits
**Alors** le contenu premium apparait floute avec effet CSS backdrop-filter
**Et** un CTA "Debloquer l'analyse complete - 9,90 EUR" est visible
**Et** le clic sur le CTA est prepare (log pour le moment, Stripe en Phase 2)

### Story 4.6 : Messages de degradation UX

En tant qu'utilisateur,
Je veux voir des messages conviviaux en cas d'erreur,
Afin de ne jamais etre confronte a un mur technique (FR21, FR38).

**Criteres d'acceptation :**

**Etant donne** une erreur survient (backend down, extraction echouee, etc.)
**Quand** le content script recoit une erreur
**Alors** un message humoristique automobile s'affiche ("Oh mince, on a creve !")
**Et** aucune stacktrace n'est visible (NFR10)
**Et** l'extension reste fonctionnelle (peut retenter)

## Epic 5 : Dashboard de Pilotage Admin

Malik peut monitorer les stats, voir les modeles demandes, suivre les pipelines et consulter les logs.

### Story 5.1 : Blueprint admin + authentification Flask-Login

En tant qu'administrateur,
Je veux un dashboard protege par login,
Afin que seul Malik puisse acceder aux donnees de pilotage (NFR9).

**Criteres d'acceptation :**

**Etant donne** le blueprint admin enregistre dans l'app
**Quand** un visiteur accede a /admin/
**Alors** il est redirige vers /admin/login
**Et** apres authentification, il accede au dashboard
**Et** Flask-Login gere la session avec @login_required
**Et** les credentials sont dans la config (ADMIN_USERNAME, ADMIN_PASSWORD_HASH)
**Et** le template de base utilise Bootstrap 5 CDN

### Story 5.2 : Dashboard stats + graphiques Plotly

En tant qu'administrateur,
Je veux voir les statistiques d'utilisation sur la page principale du dashboard,
Afin de piloter le produit (FR26, FR29).

**Criteres d'acceptation :**

**Etant donne** des scans enregistres dans la base
**Quand** j'accede a /admin/dashboard
**Alors** je vois : nombre total de scans, scans aujourd'hui, score moyen, taux d'echec
**Et** un graphique Plotly montre l'evolution des scans dans le temps
**Et** un graphique montre la distribution des scores
**Et** le dashboard charge en < 3 secondes (NFR2)

### Story 5.3 : Modeles non reconnus + logs erreurs

En tant qu'administrateur,
Je veux voir les modeles vehicules les plus demandes mais non reconnus et les logs d'erreurs,
Afin d'alimenter la roadmap du referentiel (FR27, FR30, FR37).

**Criteres d'acceptation :**

**Etant donne** des scans avec modeles non reconnus
**Quand** j'accede a /admin/vehicles
**Alors** je vois un classement des marques/modeles non reconnus avec leur frequence
**Et** sur /admin/errors je vois les logs d'erreurs recents depuis app_logs
**Et** les logs sont filtres par niveau (ERROR, WARNING)

### Story 5.4 : Monitoring pipelines

En tant qu'administrateur,
Je veux monitorer l'etat des pipelines amont,
Afin de savoir si les donnees sont a jour (FR28).

**Criteres d'acceptation :**

**Etant donne** les pipelines configures (YouTube, argus, imports)
**Quand** j'accede a /admin/pipelines
**Alors** je vois la date du dernier run de chaque pipeline
**Et** le statut (OK, echec, jamais lance)
**Et** le nombre d'elements traites lors du dernier run

## Epic 6 : Pipeline d'Enrichissement Donnees

Le systeme ingere YouTube, Whisper, LLM, datasets et collecte l'argus geolocalise.

### Story 6.1 : Import et normalisation datasets vehicules

En tant que developpeur,
Je veux importer les fichiers car-list.json, CSVs Teoalida et les normaliser,
Afin d'enrichir le referentiel vehicules (FR31).

**Criteres d'acceptation :**

**Etant donne** les fichiers dans data/ (car-list.json, CSVs)
**Quand** le script datasets.py s'execute
**Alors** les donnees sont parsees, normalisees et inserees dans vehicles/vehicle_specs
**Et** les doublons sont detectes et geres
**Et** un rapport resume les donnees importees

### Story 6.2 : Extraction sous-titres YouTube

En tant que systeme,
Je veux extraire les sous-titres de videos de chaines automobiles YouTube,
Afin d'alimenter le pipeline de fiches vehicules (FR32).

**Criteres d'acceptation :**

**Etant donne** une liste de chaines YouTube dans youtube_channels.json
**Quand** le pipeline YouTube s'execute
**Alors** les sous-titres francais sont extraits pour chaque video pertinente
**Et** les fichiers sous-titres sont stockes localement
**Et** les erreurs (video sans sous-titres) sont loguees sans bloquer le pipeline

### Story 6.3 : Transcription Whisper locale

En tant que systeme,
Je veux transcrire des fichiers audio de videos YouTube via Whisper en local,
Afin de traiter les videos sans sous-titres (FR33).

**Criteres d'acceptation :**

**Etant donne** des fichiers audio de videos YouTube
**Quand** le pipeline Whisper s'execute
**Alors** les transcriptions sont generees localement sans appel reseau (NFR14)
**Et** les transcriptions sont stockees en fichiers texte
**Et** le modele Whisper utilise est configurable (tiny, base, small)

### Story 6.4 : Generation fiches vehicules via LLM

En tant que systeme,
Je veux generer des fiches vehicules structurees a partir des transcriptions,
Afin d'enrichir le referentiel avec des donnees de fiabilite (FR34).

**Criteres d'acceptation :**

**Etant donne** des transcriptions de videos automobiles
**Quand** le pipeline LLM s'execute
**Alors** il genere des fiches structurees : fiabilite, problemes connus, couts a prevoir
**Et** les fiches sont stockees dans vehicle_specs
**Et** un budget par modele limite les couts LLM

### Story 6.5 : Collecte argus geolocalise Leboncoin

En tant que systeme,
Je veux collecter des donnees de prix depuis Leboncoin par modele et region,
Afin d'alimenter l'argus geolocalise (FR35).

**Criteres d'acceptation :**

**Etant donne** les modeles du referentiel et les regions cibles
**Quand** le pipeline argus s'execute
**Alors** il collecte les prix annonces pour chaque modele dans chaque region
**Et** il calcule price_low, price_mid, price_high (percentiles)
**Et** les donnees sont inserees dans argus_prices

## Epic 7 : Monetisation Premium [Phase 2]

L'utilisateur s'authentifie, paie 9,90 EUR et accede au rapport detaille.

> **Note :** Cet epic est post-jury (16 mars 2026). Les stories sont definies pour la vision produit mais ne seront pas implementees dans le MVP.

### Story 7.1 : Authentification Firebase

En tant qu'utilisateur,
Je veux m'authentifier via email ou compte Google,
Afin d'acceder aux fonctionnalites premium (FR40).

**Criteres d'acceptation :**

**Etant donne** l'extension Chrome
**Quand** l'utilisateur clique sur "Debloquer"
**Alors** il s'authentifie via Firebase Auth (email ou Google)
**Et** un token securise est stocke dans chrome.storage.local (FR42)

### Story 7.2 : Paiement Stripe

En tant qu'utilisateur,
Je veux payer 9,90 EUR pour debloquer une analyse premium,
Afin d'acceder au rapport complet (FR41).

**Criteres d'acceptation :**

**Etant donne** un utilisateur authentifie
**Quand** il clique sur le CTA de paiement
**Alors** une session Stripe Checkout est creee
**Et** apres paiement reussi, le rapport premium est debloque
**Et** un webhook confirme le paiement cote backend

### Story 7.3 : Rapport PDF premium

En tant qu'utilisateur premium,
Je veux telecharger le rapport d'analyse au format PDF,
Afin de le conserver et le partager (FR43, FR45).

**Criteres d'acceptation :**

**Etant donne** une analyse premium payee
**Quand** l'utilisateur demande le PDF
**Alors** un rapport structure est genere avec toutes les donnees d'analyse
**Et** le PDF est telechargeable depuis l'extension

### Story 7.4 : Envoi rapport par email

En tant qu'utilisateur premium,
Je veux recevoir le rapport d'analyse par email,
Afin de le retrouver facilement (FR44).

**Criteres d'acceptation :**

**Etant donne** une analyse premium payee
**Quand** l'utilisateur fournit son email
**Alors** le rapport est envoye par email dans un format lisible
