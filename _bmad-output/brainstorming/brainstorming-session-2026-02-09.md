---
stepsCompleted: [1, 2, 3, 4]
inputDocuments: ['docs/vision.txt', 'docs/EXEMPLE leboncoin lbc_extract.py', 'docs/Critères_Evaluation_python_formation.pdf', 'docs/URL.txt', 'docs/car-list.json', 'docs/car_trim.csv', 'docs/car_specification_value.csv', 'docs/car_option.csv']
session_topic: 'MVP Co-Pilot automobile — borner le périmètre pour livrer un MVP fonctionnel avant le 16 mars 2026'
session_goals: 'Trancher quoi garder/couper, séquencer intelligemment, maximiser le score sur la grille d évaluation Python SE'
selected_approach: 'ai-recommended'
techniques_used: ['resource-constraints', 'assumption-reversal', 'first-principles-thinking']
ideas_generated: [12]
session_active: false
workflow_completed: true
---

# Brainstorming Session Results

**Facilitateur:** Malik
**Date:** 2026-02-09

## Session Overview

**Sujet :** MVP Co-Pilot automobile — définir le périmètre exact dans les contraintes de temps
**Objectifs :** Identifier quels piliers prioriser, quelles fonctionnalités couper, séquencer l'exécution semaine par semaine

### Documents de contexte

- `docs/vision.txt` — Vision complète avec 6 piliers techniques
- `docs/EXEMPLE leboncoin lbc_extract.py` — Extracteur Leboncoin fonctionnel
- `docs/Critères_Evaluation_python_formation.pdf` — Grille d'évaluation (10 critères, notation 1-6)
- `docs/URL.txt` — Sources de données (GitHub repos, Kaggle, APIs, bases auto)
- `docs/car-list.json` — 39 marques, ~1000 modèles (embryon référentiel)
- `docs/car_trim.csv` — 1 395 finitions (motorisation, puissance, années) — base allemande
- `docs/car_specification_value.csv` — 52 005 specs techniques (dimensions, moteur, carburant...)
- `docs/car_option.csv` — 1 266 options d'équipement
- `docs/European-Car-Database-by-Teoalida-full-specs-SAMPLE/Database-Tableau 1.csv` — 3 852 véhicules EU, 250+ colonnes (specs, conso WLTP, prix ADAC, assurance, sécurité, garantie)
- `docs/Year-Make-Model-Trim-Full-Specs-by-Teoalida-SAMPLE/DATABASE-Tableau 1.csv` — 18 702 véhicules US (Make/Model/Year/Trim, specs, prix MSRP, reviews, NHTSA ratings)
- `docs/Car-Models-Database-by-Teoalida-SAMPLE.csv` — 105 modèles résumés (marque, génération, carrosserie, dimensions, prix)
- `docs/European-Car-Database-by-Teoalida-full-specs-SAMPLE/Statistics makes-Tableau 1.csv` — 127 marques, 157 235 véhicules dans la base complète

### Configuration de session

- **Deadline :** 16 mars 2026 (~5 semaines)
- **Contrainte certification :** Python doit être le moteur central (Python Software Engineer)
- **Vision long terme :** SaaS
- **Existant :** Script extraction Leboncoin + référentiel véhicules quasi-complet

---

## Technique Selection

**Approche :** Recommandation IA (3 techniques ciblées)

- **Resource Constraints :** Cartographier les contraintes réelles et forcer la priorisation
- **Assumption Reversal :** Challenger les 6 piliers via la grille d'évaluation
- **First Principles Thinking :** Reconstruire le MVP depuis les fondations

---

## Technique Execution Results

### Technique 1 : Resource Constraints

**Focus :** Stresser chaque pilier sous contrainte de temps extrême pour révéler les priorités.

**Idées générées :**

**[#1] Heuristiques standalone sans BDD**
_Concept :_ Analyse d'annonce via signaux simples — vérification SIRET sur API gouv.fr, détection indicatif téléphone étranger, recherche Google pour valider l'existence du modèle, Google+"problème" pour jauger la réputation.
_Nouveauté :_ Pas besoin de BDD exhaustive, le web sert de "référentiel pauvre" — premier filtre crédible et faisable rapidement.

**[#2] Référentiel ciblé au lieu d'exhaustif**
_Concept :_ Se limiter aux voitures les plus vendues en France par catégorie/budget au lieu de couvrir tout le parc 2010-2025. Couvre 60-70% des annonces avec 10x moins d'effort.
_Nouveauté :_ Inversion du problème — on ne construit pas une base exhaustive, on cible le volume réel du marché.

**[#3] Analyse visuelle sans BDD d'images**
_Concept :_ Au lieu de comparer à des photos de référence par modèle, détecter les incohérences ENTRE les photos de la même annonce — couleur qui change, jantes différentes, intérieur qui ne matche pas, photos partielles suspectes.
_Nouveauté :_ Le Pilier 5 passe d'un "système de reconnaissance" (lourd) à un "détecteur d'anomalies intra-annonce" (léger et réaliste).

**[#4] Double filtre image : NumPy puis LLM**
_Concept :_ Première passe Python pure via np.ndarray — histogrammes couleur, patterns communs/divergents entre photos. LLM multimodal uniquement en deuxième passe sur les cas suspects.
_Nouveauté :_ 100% Python pour la première couche. NumPy est vu en cours → démonstration directe des acquis de formation.

**[#5] RAG qualité > quantité**
_Concept :_ Cibler ~100 vidéos YouTube de référence calées sur le référentiel restreint. Extraction audio → texte via Whisper. Corpus restreint mais fiable.
_Nouveauté :_ Pipeline artisanal pour valider la chaîne complète. L'industrialisation viendra en V2.

**[#6] car-list.json comme Pilier 2 MVP**
_Concept :_ Le référentiel existe déjà sous forme brute. En le croisant avec les top ventes FR et en enrichissant depuis les sources URL.txt, on a un référentiel ciblé fonctionnel.
_Nouveauté :_ Pas besoin de construire de zéro — enrichir l'existant.

**[#7] Alignement programme de formation**
_Concept :_ Chaque brique technique doit être reliée à un acquis du cursus — NumPy pour images, httpx pour scraping, JSON/SQL pour structuration, Pandas pour le référentiel. Le MVP = vitrine des compétences du certificat.
_Nouveauté :_ Le MVP n'est pas juste un produit, c'est une démonstration pédagogique.

### Technique 2 : Assumption Reversal

**Focus :** Retourner les hypothèses implicites de la vision.txt via la grille d'évaluation du jury.

**Révélation majeure :** La grille d'évaluation (Critères_Evaluation_python_formation.pdf) a complètement redistribué les priorités.

**Idées générées :**

**[R#3] Flask obligatoire, pas Streamlit**
_Concept :_ La grille évalue Flask DEUX FOIS (critère 05 Interface + critère 08 REST API). Streamlit ne coche aucune de ces cases. Flask rapporte potentiellement 12 points sur 60.
_Nouveauté :_ Le choix technique n'est pas un choix de goût — c'est un choix de scoring.

**[R#4] Audio/Vidéo et GPS sont des critères explicites**
_Concept :_ Le critère 06 mentionne Maps/GPS et Audio/Vidéo. Le pipeline YouTube (extraction audio → transcription) coche Audio/Vidéo. La géolocalisation de l'annonce coche Maps/GPS. Ces features "accessoires" sont des critères de notation.
_Nouveauté :_ Le Pilier 1 (ingestion YouTube) passe de nice-to-have à obligatoire.

**[R#5] SGBD obligatoire au lieu de JSON plat**
_Concept :_ Le critère 08 demande SGBD/Firebase/SQL et modélisation des données. Le car-list.json doit migrer vers SQLite/PostgreSQL. Le référentiel véhicule devient la démo parfaite de ce critère.
_Nouveauté :_ Le Pilier 2 est structurellement nécessaire pour la notation.

**[R#6] Scoring par convergence de red flags**
_Concept :_ Prix vs argus local + photos suspectes + numéro étranger + annonce vague + vendeur pro sans SIRET + modèle introuvable = chaque signal vaut des points. 10 filtres artisanaux qui convergent valent mieux qu'1 algo sophistiqué.
_Nouveauté :_ Le MVP n'a pas besoin d'IA pour être intelligent — il a besoin de bon sens systématisé en Python.

**[R#7] Argus géolocalisé = quick win massif**
_Concept :_ Prix annonce vs prix moyen du même modèle dans un rayon de X km. -30% → red flag. Données récupérables via scraping Leboncoin (extracteur existant). Coche le critère 06 (Maps/GPS) ET apporte une valeur utilisateur immédiate.
_Nouveauté :_ Un seul feature coche un critère de notation ET donne le "wahou" utilisateur.

### Technique 3 : First Principles Thinking

**Focus :** Reconstruire l'architecture MVP depuis les vérités fondamentales.

**Idées générées :**

**[FP#1] Deux pipelines, pas un**
_Concept :_ Pipeline AMONT (cold, exécuté une fois, enrichit la base) et pipeline LIVE (hot, déclenché au clic utilisateur). 60% de l'intelligence est précalculée. Le live ne fait que du lookup.
_Nouveauté :_ Fondation architecturale qui clarifie tout — le dev, les priorités, les performances.

**[FP#2] Digestion LLM en amont uniquement**
_Concept :_ Les transcriptions YouTube brutes sont inutiles en live. En amont : LLM extrait les signaux (points faibles, usure, avis) et stocke une fiche synthétique par modèle dans la BDD. En live : simple SELECT → fiche prête, zéro latence.
_Nouveauté :_ Le LLM travaille en amont pour produire des fiches structurées, pas en live pour improviser.

**[FP#3] Flask+Plotly = admin / Extension Chrome = utilisateur**
_Concept :_ Deux interfaces, deux publics. Flask + Plotly = tour de contrôle (données amont, état pipelines, stats SQL, monitoring). Extension Chrome en JS = côté utilisateur (clic → score). Le jury voit la profondeur technique ET l'usage réel.
_Nouveauté :_ Flask n'est pas une vitrine, c'est un vrai outil d'exploitation — coche le critère 10 "exploitation commerciale/professionnelle".

---

## Idea Organization and Prioritization

### Thème A : Architecture à deux pipelines

- **#2** Référentiel ciblé (top ventes FR = 60-70% des annonces)
- **#6** car-list.json + base allemande (54 000+ entrées) comme base du Pilier 2 → SQLite
- **FP#1** Séparation AMONT (cold) / LIVE (hot)
- **FP#2** Digestion LLM en amont → fiches synthétiques par modèle

### Thème B : Scoring par accumulation de red flags

- **#1** Heuristiques standalone (SIRET, tel étranger, Google check)
- **R#6** 10 filtres artisanaux convergents > 1 algo sophistiqué
- **R#7** Argus géolocalisé = quick win + critère Maps/GPS

### Thème C : Alignement grille d'évaluation

- **#7** Chaque brique = un acquis du cursus
- **R#3** Flask obligatoire (2 critères sur 10)
- **R#4** YouTube audio/vidéo + géoloc = critères explicites
- **R#5** SQLite au lieu de JSON plat

### Thème D : Double interface et analyse visuelle

- **#3** Analyse visuelle intra-annonce (cohérence entre photos)
- **#4** NumPy ndarray en première passe → programme de cours
- **FP#3** Flask+Plotly = admin / Extension Chrome = utilisateur

### Concepts de rupture

- **Le référentiel existe déjà :** car-list.json + base allemande (car_trim + car_specification_value + car_option) + échantillons Teoalida = le Pilier 2 est un travail d'import, pas de construction.
- **Le scoring par red flags :** pas besoin d'IA pour être pertinent. Bon sens systématisé en Python.
- **Artisanal d'abord, industriel ensuite :** chaque pilier a une version light crédible. La montée en puissance étaufe les piliers sans changer la base.

---

## Architecture MVP finale

### Pipeline AMONT (travail de fond)

| Étape | Input | Output en BDD | Tech Python |
|-------|-------|---------------|-------------|
| A1 - Référentiel véhicules | car-list.json + CSVs allemands + Teoalida | Table `vehicles` (marque, modèle, trim, année, specs) | Pandas, SQLite |
| A2 - Argus géolocalisé | Scraping prix Leboncoin par modèle/zone | Table `price_index` (modèle, zone, prix_moyen) | httpx, BeautifulSoup, géoloc |
| A3 - Extraction YouTube | ~100 vidéos ciblées → audio → texte | Table `raw_transcriptions` | Whisper / speech-to-text |
| A4 - Digestion LLM | Transcriptions → extraction signaux | Table `vehicle_insights` (points_faibles, usure, red_flags, avis) | API LLM, structuration JSON |

### Pipeline LIVE (au clic utilisateur)

| Filtre | Action | Temps | Critère grille |
|--------|--------|-------|----------------|
| L1 | Extraction annonce Leboncoin | ~2s | 06 (API distantes) |
| L2 | Véhicule existe dans le référentiel ? | instantané | 07, 08 (Pandas, SQL) |
| L3 | Cohérence modèle/année/motorisation | instantané | 04 (Classes, logique) |
| L4 | Prix vs argus géolocalisé | instantané | 06 (Maps/GPS) |
| L5 | Analyse photos intra-annonce | ~3-5s | 07 (NumPy) |
| L6 | Numéro de téléphone suspect | instantané | 04 (regex, built-in) |
| L7 | SIRET vendeur pro | ~1-2s | 06 (API gouv.fr) |
| L8 | Fiche réputation modèle | instantané | 08 (SQL lookup) |
| L9 | Score global + rapport red flags | instantané | 05, 10 (Flask, Plotly) |

### Interfaces

| Interface | Public | Tech | Critères grille |
|-----------|--------|------|-----------------|
| Flask + Plotly | Admin / Jury | Python, Bootstrap, Plotly | 05, 08, 10 |
| Extension Chrome | Utilisateur final | JavaScript | 10 (Proof of work) |

### Couverture complète de la grille d'évaluation

| Critère | Couverture MVP |
|---------|---------------|
| 01 Conception | Ambition (copilote IA auto) + workflow BMAD documenté |
| 02 Structure logique | Classes par filtre, modules, pipeline amont/live, SQLite |
| 03 Méthode de travail | BMAD Method, Git, fichiers organisés, fonctions pures |
| 04 Programmation Python | Classes, héritage, modules built-in, bibliothèques, scalabilité |
| 05 Flask Interface | Bootstrap, dashboard Plotly, formulaires, usabilité |
| 06 Modules externes | APIs (gouv.fr, Leboncoin, YouTube), géoloc, audio/vidéo |
| 07 NumPy/Pandas | NumPy analyse images, Pandas référentiel, visualisation |
| 08 Flask REST API | Routes, auth, SQLite, modélisation données |
| 09 DevOps | Git, Docker, déploiement serveur, testing |
| 10 Fonctionnalités | Proof of work (extension Chrome), vision SaaS, exploitation commerciale |

---

## Plan d'exécution proposé

### Semaines 1-2 : Fondations

- Référentiel SQLite (import car-list.json + CSVs allemands)
- Pipeline amont : argus géolocalisé + extraction YouTube
- Structure classes Python (Extractor, Analyzer, Scorer)
- Modèle de données SQL

### Semaine 3 : Pipeline live

- Les 9 filtres implémentés
- Scoring par accumulation de red flags
- Flask API + routes REST

### Semaine 4 : Interfaces

- Dashboard Flask + Plotly (tour de contrôle admin)
- Extension Chrome (clic → score)
- Docker

### Semaine 5 : Polish & démo

- Tests
- Déploiement serveur
- Préparation présentation jury
- Documentation

---

## Session Summary

### Achievements clés

- **12 idées** générées à travers 3 techniques ciblées
- **Game changer :** la grille d'évaluation a complètement redistribué les priorités (Flask, SQL, Audio/Vidéo, GPS deviennent obligatoires)
- **Référentiel quasi-prêt :** les CSV allemands (54 000+ entrées) + car-list.json + Teoalida réduisent le Pilier 2 à un travail d'import
- **Architecture clarifiée :** deux pipelines (AMONT/LIVE) + deux interfaces (Flask admin / Extension Chrome)
- **Philosophie MVP validée :** artisanal d'abord, industriel ensuite. 10 filtres de bon sens > 1 algo complexe

### Moments de rupture

1. L'analyse visuelle transformée en détecteur d'anomalies intra-annonce (pas besoin de BDD d'images)
2. La découverte que Flask vaut 2 critères sur 10 → abandon de Streamlit
3. Le scoring par convergence de red flags comme killer feature
4. La séparation amont/live qui résout le problème de latence

### Prochaine étape BMAD

**Phase 2 — Planification :** Créer le Product Brief puis le PRD à partir de cette session de brainstorming. Utiliser `/bmad-bmm-create-product-brief` dans un nouveau chat.
