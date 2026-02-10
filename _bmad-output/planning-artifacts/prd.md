---
stepsCompleted: ['step-01-init', 'step-02-discovery', 'step-03-success', 'step-04-journeys', 'step-05-domain', 'step-06-innovation', 'step-07-project-type', 'step-08-scoping', 'step-09-functional', 'step-10-nonfunctional', 'step-11-polish', 'step-12-complete']
workflow_completed: true
inputDocuments: ['_bmad-output/planning-artifacts/product-brief-Co-Pilot-2026-02-09.md', '_bmad-output/brainstorming/brainstorming-session-2026-02-09.md']
workflowType: 'prd'
documentCounts:
  briefs: 1
  research: 0
  brainstorming: 1
  projectDocs: 0
  projectContext: 0
classification:
  projectType: 'Web App + Extension navigateur (evolution SaaS)'
  domain: 'Automotive consumer / marketplace VO'
  complexity: 'medium'
  projectContext: 'greenfield'
  dbScope: '2010-2025'
  existingCode: 'lbc_extract.py (extraction Leboncoin via __NEXT_DATA__ JSON)'
---

# Product Requirements Document - Co-Pilot

**Author:** Malik
**Date:** 2026-02-09

## Executive Summary

**Co-Pilot** est une extension Chrome qui analyse les annonces de vehicules d'occasion sur Leboncoin et delivre un verdict de confiance instantane (score sur 100) -- sans que l'utilisateur ait besoin de connaissances automobiles.

**Probleme :** L'achat VO en C2C est un parcours anxiogene. Arnaques, imports trafiques, prix opaques, donnees eparpillees. Les outils existants (HistoVec, argus, forums) fournissent des donnees brutes que le non-expert ne peut pas interpreter.

**Solution :** Un clic sur l'annonce Leboncoin. 10 secondes. Un score clair. Des red flags lisibles. L'utilisateur sait immediatement si l'annonce est fiable ou suspecte. Toute la complexite (9 filtres, referentiel vehicules, argus geolocalise, analyse des signaux) est cachee derriere une jauge circulaire.

**Differenciateur :** "Verdict, pas donnees" -- Co-Pilot est le seul outil qui combine detection + education + verdict dans une interface zero-friction. Aucun concurrent direct sur ce positionnement.

**Cible principale :** L'acheteur VO lambda qui achete une voiture tous les 5 ans, ne connait rien a la mecanique, et ne peut pas se permettre de se tromper.

**Modele economique :** Freemium. Analyse gratuite (score + red flags) → Premium a 9,90€ (rapport detaille, fiche modele, pronostic). Liquid glass blur comme mecanisme de conversion UX.

**Deadline :** MVP pour le 16 mars 2026 (jury certification Python Software Engineer). Demo live sur de vraies annonces.

---

## Success Criteria

### User Success

- L'utilisateur comprend la jauge sur 100 et les red flags **sans explication** -- l'UI est auto-porteuse
- L'utilisateur gagne la **confiance d'acheter en C2C** sans intermediaire couteux
- Le temps de decision passe de **jours/semaines a quelques secondes** (scan) + minutes (lecture rapport)
- L'utilisateur ne sollicite plus son entourage pour valider un achat -- **autonomie acquise**
- Le moment "aha" : la jauge circulaire s'affiche, le score est clair, les red flags sont lisibles

### Business Success

- **Milestone 0 (16 mars 2026)** : le jury valide -- demo live sur une vraie annonce, grille Python SE couverte, vision commerciale comprise
- **3 mois** : 1 000+ installations Chrome, 5% conversion gratuit → premium, premiers revenus
- **12 mois** : bouche-a-oreille organique, revenu recurrent stable, partenariats actifs (YouTubeurs, assurances)
- **Metric cle** : 9,90€ / analyse premium (4,95€ via code promo YouTubeur)

### Technical Success

- **Performance** : scan gratuit repond en < 10 secondes (animation d'attente UX pendant le traitement)
- **Fiabilite des filtres** : chaque filtre est teste individuellement avec des jeux de donnees valides/invalides/edge cases
- **Suite de tests automatises** : stress tests, inputs de bonne/mauvaise qualite, fausses annonces, annonces reelles connues
- **Referentiel complet** : 20 top modeles FR (2010-2025) ficeles de bout en bout (specs, argus, fiches vehicules)
- **Pipeline amont fonctionnel** : extraction YouTube → Whisper → LLM → fiches synthetiques operationnelles pour les 20 modeles
- **Docker** : `docker-compose up` lance tout le stack (Flask, SQLite, pipelines) -- container base sur l'existant configure en cours
- **Deploiement** : local pour le jury, beta prod (VPS/cloud) dans la foulee

### Measurable Outcomes

| Critere | Cible MVP (16 mars) | Cible 3 mois | Methode de mesure |
|---------|---------------------|--------------|-------------------|
| Temps de reponse scan gratuit | < 10s | < 5s (optimisation) | Chrono UX + logs |
| Filtres operationnels | 9/9 | 9/9 + ameliorations | Tests auto |
| Modeles dans referentiel | 20 | 50+ | COUNT SQL |
| Couverture tests | 1 suite par filtre | 80%+ coverage | pytest |
| Docker fonctionnel | docker-compose up | Deploye beta prod | CI/CD |

---

## User Journeys

### Journey 1 : Jean-Pierre decouvre Co-Pilot (Succes Path)

**Scene d'ouverture :** Jean-Pierre, 58 ans, sa Megane de 2014 vient de rendre l'ame. Controle technique refuse. Il est a pied. Sa femme lui dit "faut qu'on rachete une voiture, mais pas n'importe quoi cette fois". C'est aussi l'argent de sa femme -- il ne peut pas se planter.

**Rising Action :** Il va sur Leboncoin -- reflexe de francais. Il voit une Peugeot 3008 2019 a 18 500€. Ca a l'air bien, mais il ne sait pas si c'est le bon prix, si le vendeur est fiable, si l'hybride c'est fiable. Son gendre lui a parle d'une extension Chrome, "Co-Pilot". Il installe l'extension.

**Climax :** Il retourne sur l'annonce. Un bouton apparait. Il clique. Ca mouline (animation). La jauge circulaire s'affiche : **67/100** entourant le chiffre. Il scrolle dans la fenetre contextuelle -- resultats detailles point par point. Deux warnings orange : "Prix 12% au-dessus de l'argus local", "Numero de telephone avec indicatif etranger". Un check vert : "Modele reconnu, coherence OK". En bas, le contenu se floute en effet liquid glass : "Analyse premium -- debloquer pour 9,90€". Jean-Pierre comprend immediatement le verdict sans etre expert.

**Resolution :** Il passe a une autre annonce. Score 89/100. Tous checks verts. Il peut deplier la fenetre a droite pour plus de details. Prix en ligne avec l'argus. Il appelle le vendeur avec confiance. Il negocie 500€. Il achete sans mandataire, sans concession. Il economise ~2 000€. Message a son gendre : "Ton truc la, Co-Pilot, c'est top."

---

### Journey 2 : Sophie sort du circuit traditionnel (Decouverte/Confiance)

**Scene d'ouverture :** Sophie, 34 ans, en LOA depuis 3 ans sur un Captur. Le loyer la saigne : 350€/mois. Elle veut en sortir mais le marche de l'occasion lui fait peur.

**Rising Action :** Elle voit une video YouTube de Terry Gollow qui teste Co-Pilot en live sur 5 annonces. Elle voit les avis Chrome Web Store : 4.6 etoiles. Elle installe l'extension.

**Climax :** Elle scanne une Clio V de 2021 a 14 000€. Score 82/100. Warning : "Kilometrage eleve pour l'annee (45 000 km)". La fiche modele lui explique que la Clio V est fiable, que 45 000 km c'est beaucoup mais pas alarmant, et que le prix est correct vu le km. Elle scrolle -- les details premium sont floutes derriere le liquid glass. Elle paie 9,90€ pour le rapport complet. Elle comprend enfin ce qu'elle regarde.

**Resolution :** Elle achete sa premiere voiture en C2C. Economise 4 000€ par rapport a la LOA. Elle recommande Co-Pilot a sa collegue.

---

### Journey 3 : Kevin se protege apres la C3 Pluriel (Post-Echec)

**Scene d'ouverture :** Kevin, 24 ans. Sa C3 Pluriel est un gouffre -- problemes electriques, faisceau cabriolet defaillant. Il a paye 5 500€ pour une voiture qui en vaut 2 000. Il a appris.

**Rising Action :** Il cherche un remplacement. Il installe Co-Pilot "pour voir". Il scanne une Golf 7 TDI 2017 a 13 000€.

**Climax :** Score 45/100. Red flag : "Vehicule potentiellement importe (historique incomplet)". Warning : "Prix 22% sous l'argus -- anomalie". La fiche modele mentionne "Attention compteur : modele frequemment concerne par le trafic kilometrique sur les imports". Kevin reconnait le piege dans lequel il serait tombe avant.

**Resolution :** Il passe. Trouve une autre Golf 7, score 91/100, prix en ligne. Il achete en confiance. La brulure de la C3 ne se repetera pas.

---

### Journey 4 : Karim optimise son stock (Pro/Productivite)

**Scene d'ouverture :** Karim, 41 ans, petit revendeur VO. Il scanne 30-40 annonces par jour pour trouver les bonnes affaires a racheter et revendre avec marge.

**Rising Action :** Sans Co-Pilot, chaque annonce lui prend 10-15 minutes d'analyse. Avec Co-Pilot : un clic, score instantane.

**Climax :** En 2 heures, il a scanne 40 annonces. 8 sont au-dessus de 85/100 avec un prix sous l'argus. Il contacte ces 8 vendeurs directement. Sa productivite a triple.

**Resolution :** Il gagne 2h par jour. Sa marge augmente car il identifie les bonnes affaires plus vite que la concurrence. Il prend l'abonnement pro mensuel.

---

### Journey 5 : Malik pilote Co-Pilot (Admin/Operateur)

**Scene d'ouverture :** Malik, createur de Co-Pilot. C'est le matin, il ouvre le dashboard Flask.

**Rising Action :** Il voit les stats : 147 scans gratuits, 6 conversions premium, 23 echecs "modele non reconnu". Il clique sur les echecs : 15 tentatives sur Dacia Sandero, 5 sur Renault Scenic, 3 sur Tesla Model 3. Il sait que Dacia Sandero doit etre le prochain modele a ajouter.

**Climax :** Il verifie l'etat des pipelines amont. Le pipeline YouTube a ingere 3 nouvelles videos. L'argus a mis a jour 12 modeles. Tout est vert. Il lance un enrichissement Dacia Sandero.

**Resolution :** Le lendemain, les utilisateurs Sandero obtiennent un score complet. Le taux d'echec baisse. Le produit s'ameliore grace aux donnees d'usage.

---

### Journey 6 : Modele non reconnu (Degradation gracieuse)

**Scene d'ouverture :** Un utilisateur scanne une annonce pour une MG ZS EV (marque chinoise, modele recent).

**Rising Action :** Co-Pilot extrait les donnees normalement. Le filtre L2 cherche dans le referentiel : aucune correspondance.

**Climax :** Message convivial : "On ne connait pas encore ce modele -- on prepare le garage pour l'expertiser tres prochainement !" Les filtres universels tournent quand meme (telephone, SIRET, prix global). Score partiel affiche avec mention "analyse limitee".

**Resolution :** L'echec est remonte au dashboard Flask (compteur +1 sur MG ZS EV). L'utilisateur a quand meme eu une valeur partielle. Les donnees d'echec alimentent la roadmap du referentiel.

---

### Journey Requirements Summary

| Journey | Capacites revelees |
|---------|-------------------|
| Jean-Pierre (succes) | Extraction annonce, scoring, jauge circulaire UX, argus geolocalise, fiche modele, filtres L1-L9, fenetre depliable, blur liquid glass paywall |
| Sophie (decouverte) | Onboarding zero friction, preuve sociale (avis Chrome Store), fiche modele educative, paiement premium 9,90€, rapport complet |
| Kevin (post-echec) | Red flags pertinents, detection imports, alerte compteur trafique, anomalie prix |
| Karim (pro) | Scan en masse, rapidite, identification bonnes affaires, abonnement pro |
| Malik (admin) | Dashboard Flask, stats scans/echecs/conversions, monitoring pipelines, enrichissement referentiel, logs |
| Echec (modele inconnu) | Degradation gracieuse, filtres universels, message UX convivial, remontee stats echec au dashboard |

---

## Domain-Specific Requirements

### Contraintes Domaine (Automotive Consumer / Marketplace VO)

**Complexite : Moyenne** -- pas de contraintes reglementaires lourdes (pas d'ISO 26262, pas de safety-critical).

### Acces aux donnees

- **Leboncoin** : lecture du JSON `__NEXT_DATA__` publiquement accessible dans le DOM -- meme acces que le navigateur, pas de scraping intrusif
- **SIRET gouv.fr** : API publique ouverte, compte gouv connect si besoin de quotas eleves
- **YouTube** : extraction des fichiers sous-titres (pas d'API officielle necessaire) -- source du RAG pour les fiches vehicules
- **Whisper** : execution locale, zero dependance externe, zero cout, zero limite

### Donnees personnelles (RGPD)

- Pas de stockage de donnees personnelles -- utilisation en transit uniquement
- Numeros de telephone et SIRET sont des donnees publiques affichees dans l'annonce
- Pas de profilage utilisateur, pas de tracking, pas de cookies tiers

### Risques et mitigations

| Risque | Probabilite | Mitigation |
|--------|------------|------------|
| Leboncoin change la structure `__NEXT_DATA__` | Moyenne | Monitoring structure JSON + alerte dashboard + adaptation rapide |
| Blocage IP par Leboncoin a fort volume | Faible (MVP) | Volume faible au MVP, rotation proxies en V2 si necessaire |
| Changement Chrome Web Store policies | Faible | Privacy policy conforme, permissions minimales |
| Cout LLM pour digestion transcriptions | A surveiller | Budget par modele, LLM local en fallback |

---

## Innovation & Novel Patterns

### Detected Innovation Areas

1. **"Verdict, pas donnees"** -- Inversion du paradigme existant. Tous les outils du marche (HistoVec, LaCentrale, forums) fournissent des donnees brutes. Co-Pilot interprete et delivre un verdict actionnable. L'utilisateur ne doit rien savoir pour comprendre.

2. **"Pronostic, pas historique"** -- HistoVec regarde dans le retroviseur. Co-Pilot regarde la route : couts a prevoir, problemes connus, risques a anticiper. Personne ne fait ca aujourd'hui.

3. **Scoring par convergence de red flags** -- 10 filtres simples qui convergent valent mieux qu'1 algorithme sophistique. Du "bon sens systematise en Python". L'innovation est dans l'approche, pas dans la techno.

4. **Architecture two-tier invisible** -- Pipeline amont (intelligence pre-calculee, zero latence) + pipeline live (reactivite au clic). Toute la complexite est cachee derriere un bouton.

5. **RAG artisanal YouTube** -- Sous-titres YouTube → Whisper local → LLM → fiches vehicules structurees. Zero API couteuse, zero base proprietaire. Pipeline 100% maitrise et reproductible.

6. **Liquid glass paywall** -- Mecanisme de conversion UX : l'utilisateur voit la valeur gratuite, scrolle, et decouvre le contenu premium floute derriere un effet liquid glass. Elegant, non-agressif, demonstratif.

### Market Context & Competitive Landscape

- **Aucun concurrent direct** sur le positionnement "verdict instantane + education vehicule + protection acheteur" en un clic
- Outils existants sont fragmentes (HistoVec, argus, forums) et passifs (l'utilisateur doit chercher)
- Co-Pilot est le premier outil qui combine detection + education + verdict dans une interface zero-friction
- Marche adressable : des millions de transactions VO/an en France

### Validation Approach

- **Demo jury 16 mars** : validation technique et produit en live sur de vraies annonces
- **Pertinence des filtres** : suite de tests automatises (annonces bonnes/mauvaises/fausses)
- **Pertinence du score** : comparaison du verdict Co-Pilot vs analyse manuelle experte sur un panel d'annonces
- **Adoption** : 1 000+ installations post-lancement = signal de validation marche

### Risk Mitigation

| Innovation | Risque | Fallback |
|-----------|--------|----------|
| Scoring par convergence | Filtres insuffisants pour certains cas | Ajout progressif de filtres, degradation gracieuse ("analyse limitee") |
| RAG YouTube | Sous-titres absents ou de mauvaise qualite | Fiches vehicules pre-redigees manuellement en fallback |
| Liquid glass paywall | Taux de conversion trop bas | Ajuster le point de coupure gratuit/premium, A/B testing |
| Architecture two-tier | Pipeline amont incomplet au lancement | Les 20 modeles ficeles = couverture suffisante pour le MVP |

---

## Web App + Extension Chrome - Exigences Specifiques

### Vue d'ensemble du type projet

Co-Pilot est un produit hybride a deux faces :

1. **Extension Chrome** -- interface utilisateur finale, injectee dans les pages Leboncoin. C'est le produit visible par l'acheteur VO. Architecture la plus simple possible : content script qui detecte les pages Leboncoin + popup contextuelle pour afficher le score et les resultats.

2. **Dashboard Flask (MPA)** -- interface d'administration pour l'operateur (Malik). Multi-page traditionnel avec templates Jinja2 + Bootstrap, graphiques Plotly. Sert au monitoring des pipelines, stats d'usage, gestion du referentiel.

Les deux faces communiquent via une **API REST** hebergee sur le meme backend Flask.

### Considerations d'architecture technique

#### Extension Chrome (face utilisateur)

| Composant | Choix | Justification |
|-----------|-------|---------------|
| Architecture | Content Script + Popup | Le plus simple, le moins risque, fonctionne a coup sur |
| Injection | Content script sur `*.leboncoin.fr` | Detection automatique des pages annonces |
| Communication | REST API vers backend Flask | Appels HTTP standards, zero complexite |
| Stockage local | `chrome.storage.local` | Token session, preferences utilisateur |
| Permissions | `activeTab`, `storage`, `host_permissions` (leboncoin.fr, API backend) | Permissions minimales pour conformite Chrome Web Store |

**Flux principal :**
1. Content script detecte une page annonce Leboncoin
2. Injecte un bouton "Analyser avec Co-Pilot"
3. Au clic : extrait le JSON `__NEXT_DATA__` du DOM
4. Envoie les donnees au backend via REST API
5. Recoit le score + resultats des filtres
6. Affiche la popup contextuelle : jauge circulaire, details, liquid glass paywall

#### Backend Flask (API + Dashboard)

| Composant | Choix | Justification |
|-----------|-------|---------------|
| Framework | Flask | Simple, maitrise, suffisant pour le MVP |
| Templating | Jinja2 + Bootstrap | MPA traditionnel, efficace, pas de JS framework |
| Dashboard | Plotly (integre aux templates) | Graphiques interactifs sans SPA |
| Base de donnees | SQLite | Zero config, suffisant pour le volume MVP |
| API | REST (JSON) | Standard, simple, compatible extension Chrome |
| Conteneurisation | Docker + docker-compose | Environnement reproductible, deploiement simplifie |

**Endpoints API principaux :**
- `POST /api/analyze` -- recoit les donnees annonce, retourne score + filtres (gratuit)
- `POST /api/analyze/premium` -- rapport detaille premium (authentifie)
- `GET /api/health` -- sante du service

#### Communication Extension - Backend

```
Extension Chrome                    Backend Flask
+---------------+    REST API     +--------------------+
| Content       |---------------->| /api/analyze       |
| Script        |<----------------| (score + filtres)  |
|               |    JSON         |                    |
| Popup UI      |                 | Dashboard MPA      |
| (jauge,       |                 | (Jinja2+Plotly)    |
|  details)     |                 |                    |
+---------------+                 +--------------------+
                                         |
                                    SQLite + Referentiel
```

### Matrice navigateurs

| Navigateur | MVP | Post-MVP |
|------------|-----|----------|
| Chrome (desktop) | Supporte | Supporte |
| Chromium-based (Edge, Brave, Opera) | Non teste, potentiellement compatible | A valider |
| Firefox | Non supporte | Extension Firefox (WebExtension API) |
| Safari | Non supporte | Non prevu |
| Mobile | Non supporte | Non prevu (Leboncoin mobile = app native) |

### Objectifs de performance

> Voir NFR1-NFR5 pour les exigences mesurables detaillees.

**Strategie UX pour la latence :**
- Animation d'attente engageante (pas un sablier vide)
- Affichage progressif si possible (score d'abord, details ensuite)
- L'utilisateur ne doit jamais se sentir face a un mur -- toujours du feedback visuel

### Considerations d'implementation

**Approche MVP (16 mars 2026) :**
- Privilegier la simplicite a chaque decision technique
- Pas de framework JS cote extension (vanilla JS + DOM manipulation)
- Pas de framework CSS cote extension (styles inline ou CSS simple)
- Flask sert a la fois l'API REST et le dashboard MPA
- Un seul `docker-compose.yml` pour tout le stack
- Tests pytest pour chaque filtre individuellement
- GitHub public des le debut

---

## Project Scoping & Phased Development

### MVP Strategy & Philosophy

**Approche MVP :** Problem-Solving MVP -- prouver que le verdict instantane fonctionne et delivre de la valeur a l'acheteur VO.

**Contrainte cadre :** Jury Python SE le 16 mars 2026. Le MVP doit maximiser la couverture des 10 criteres d'evaluation (notation 1 a 6).

**Ressources :** Developpeur solo + assistance IA. Pas d'equipe, pas de freelance.

**Philosophie de coupe :** En cas de retard, sacrifier le pipeline amont (YouTube/Whisper) en dernier recours -- mais conscient que ca impacte les criteres 06 (Audio/Video) et 07 (collection de donnees).

### Alignement MVP - Grille d'evaluation jury

| Critere jury | Composant Co-Pilot MVP | Priorite |
|-------------|----------------------|----------|
| 01 Conception | Documentation BMAD (brief, PRD, architecture) | Deja fait |
| 02 Structure logique | Classes Python OOP (filtres, modeles, services), SQLite | Critique |
| 03 Methode de travail | Organisation fichiers propre, nomenclature, fonctions pures, docstrings | Critique |
| 04 Programmation Python | Classe de base abstraite Filtre + 9 sous-classes, heritage, built-ins, scalabilite | Critique |
| 05 Flask-1 UI | Dashboard admin Bootstrap + Plotly, pages monitoring | Important |
| 06 Modules externes | httpx, BeautifulSoup, Whisper (audio), Plotly, API SIRET gouv, geolocalisation argus | Important |
| 07 Traitement donnees | NumPy (filtre L5 analyse visuelle), Pandas (datasets), Plotly (visualisation dashboard) | Important |
| 08 Flask-2 REST API | Routes /api/analyze, auth basique premium, SQLite, modeles de donnees | Critique |
| 09 DevOps | Git + GitHub, Docker + docker-compose, deploiement serveur, pytest | Critique |
| 10 Fonctionnalites | Demo live sur vraie annonce, usages incrementables, vision commerciale 9,90€ | Critique |

### MVP Feature Set (Phase 1 -- 16 mars 2026)

**Journeys supportees :**
- Jean-Pierre (succes path) -- parcours complet gratuit
- Kevin (post-echec) -- red flags et warnings
- Malik (admin) -- dashboard monitoring
- Modele non reconnu (degradation gracieuse)

**Capacites Must-Have :**
- Extension Chrome : content script + popup + jauge circulaire
- 9 filtres live (L1-L9) avec classes OOP + heritage
- REST API Flask (/api/analyze, /api/health)
- SQLite + referentiel 20 modeles (2010-2025)
- Dashboard Flask admin (Bootstrap + Plotly) : stats, monitoring, logs echecs
- Argus geolocalise (critere Maps/GPS du jury)
- Pipeline amont : import datasets (car-list.json, CSVs, Teoalida)
- Pipeline YouTube : 10 chaines → Whisper → LLM → fiches vehicules (critere Audio du jury)
- Filtre L5 analyse NumPy (critere traitement donnees du jury)
- Docker + docker-compose fonctionnel
- Suite de tests pytest (1 par filtre minimum)
- Git + GitHub public
- Degradation gracieuse ("Oh mince, j'ai creve !" pour les erreurs)

**Explicitement OUT du MVP :**
- Stripe / paiement reel
- PDF rapport premium (concept montre, pas fonctionnel)
- Email calibre au vendeur
- Deploiement production (local pour jury, beta prod dans la foulee)
- Firefox / autres navigateurs
- Abonnement pro mensuel

### Noyau dur irreductible (si retard critique)

Si le 10 mars on est en retard, voici la hierarchie de sacrifice :

| Ordre de coupe | Composant | Impact jury |
|---------------|-----------|-------------|
| Dernier a couper | Extension Chrome + filtres + API + SQLite | Criteres 02, 04, 08 -- coeur du projet |
| Dernier a couper | Docker + Git + tests | Critere 09 -- obligatoire |
| Dernier a couper | Dashboard Flask + Plotly | Criteres 05, 07 -- differenciateur |
| A couper si necessaire | Pipeline YouTube/Whisper | Criteres 06 (Audio) -- perte de points |
| Premier a couper | Argus geolocalise (si scraping trop complexe) | Critere 06 (Maps) -- perte de points |

### Post-MVP Features (Phase 2 -- Post-jury)

- Stripe integration (paiement 9,90€ one-shot)
- PDF rapport detaille premium fonctionnel
- Email calibre au vendeur (bouclier juridique)
- Deploiement beta prod (VPS/cloud)
- Referentiel elargi (50+ modeles)
- Pipeline YouTube etendu (50+ chaines)
- Liquid glass paywall fonctionnel (pas juste maquette)

### Expansion (Phase 3 -- Vision)

- Multi-plateformes : AutoScout24, La Centrale, Facebook Marketplace
- Stripe + abonnements + partenariats B2B
- App mobile native
- API ouverte
- LLM multimodal pour photos
- Communaute utilisateurs

### Strategie de mitigation des risques

**Risques techniques :**
- Plus gros risque : integration Extension <-> API (CORS, timing). Mitigation : prototyper ce flux en premier.
- Chrome Web Store review lent. Mitigation : soumettre tot, respecter les policies.
- `__NEXT_DATA__` structure change. Mitigation : monitoring + adaptation rapide.
- SQLite limitations a fort volume. Mitigation : suffisant MVP, migration PostgreSQL/Firestore en V2.
- Risque pipeline : Whisper + LLM = chaine longue. Mitigation : fiches manuelles en fallback pour les 20 modeles.

**Risques calendrier :**
- Solo dev avec deadline fixe. Mitigation : hierarchie de coupe definie, pas de scope creep.
- Pipeline amont = premier sacrifice si retard.

**Risques demo jury :**
- Backend down pendant la demo. Mitigation : demo sur environnement local Docker stable.
- Annonce Leboncoin cassee. Mitigation : avoir 5 annonces de test pre-validees.

**Degradation gracieuse (beta) :**
- Backend injoignable : message UX fun "Oh mince, j'ai creve ! On repare le moteur, reessayez dans un instant."
- Modele non reconnu : "On ne connait pas encore ce modele -- on prepare le garage !"
- Erreur inattendue : message generique avec humour automobile, jamais de stacktrace utilisateur

---

## Functional Requirements

> **Note :** Ce contrat de capacites couvre le MVP et les phases futures. Les FRs marquees Phase 2 seront implementees post-jury. Le contrat est evolutif -- de nouvelles capacites pourront etre ajoutees apres le MVP.

### Analyse d'annonce (core)

- FR1: L'utilisateur peut declencher une analyse sur n'importe quelle page annonce Leboncoin
- FR2: Le systeme peut extraire les donnees structurees d'une annonce Leboncoin (prix, marque, modele, annee, kilometrage, carburant, boite, etc.)
- FR3: Le systeme peut calculer un score global sur 100 a partir de la convergence des filtres individuels
- FR4: L'utilisateur peut consulter le detail de chaque filtre avec son verdict individuel (vert/orange/rouge)
- FR5: L'utilisateur peut identifier les red flags et warnings sans connaissance automobile prealable
- FR6: Le systeme peut comparer le prix annonce a l'argus geolocalise de la region de l'annonce
- FR7: Le systeme peut verifier la coherence des donnees de l'annonce (km vs annee, prix vs modele, etc.)

### Scoring & Filtres (intelligence)

- FR8: Le systeme peut executer 9 filtres independants (L1-L9) sur une annonce
- FR9: Le systeme peut verifier si le modele vehicule est present dans le referentiel
- FR10: Le systeme peut analyser le numero de telephone de l'annonce (indicatif etranger, format suspect)
- FR11: Le systeme peut verifier un numero SIRET via l'API publique gouv.fr
- FR12: Le systeme peut detecter les signaux d'import (historique incomplet, anomalie prix)
- FR13: Le systeme peut effectuer une analyse visuelle des donnees avec NumPy
- FR14: Le systeme peut produire un score partiel quand certains filtres ne sont pas applicables (modele non reconnu)

### Interface utilisateur Extension Chrome

- FR15: L'utilisateur peut voir un bouton d'action injecte sur les pages annonces Leboncoin
- FR16: L'utilisateur peut voir une animation d'attente pendant le traitement de l'analyse
- FR17: L'utilisateur peut voir le score global dans une jauge circulaire
- FR18: L'utilisateur peut scroller dans la fenetre contextuelle pour voir les resultats detailles
- FR19: L'utilisateur peut deplier la fenetre contextuelle pour plus de details
- FR20: L'utilisateur peut voir le contenu premium floute derriere un effet liquid glass avec invitation a debloquer
- FR21: Le systeme peut afficher un message de degradation gracieuse humoristique en cas d'erreur

### Referentiel vehicules (knowledge base)

- FR22: Le systeme peut stocker et interroger un referentiel de specifications vehicules (20 modeles MVP)
- FR23: Le systeme peut fournir une fiche modele avec informations de fiabilite, problemes connus, et couts a prevoir
- FR24: Le systeme peut associer les donnees d'une annonce au bon modele dans le referentiel
- FR25: Le systeme peut stocker des donnees argus geolocalisees par region

### Dashboard & Monitoring (admin)

- FR26: L'administrateur peut consulter les statistiques d'utilisation (scans gratuits, conversions premium, echecs)
- FR27: L'administrateur peut voir les modeles vehicules les plus demandes mais non reconnus
- FR28: L'administrateur peut monitorer l'etat des pipelines amont (YouTube, argus, imports)
- FR29: L'administrateur peut visualiser les donnees sous forme de graphiques interactifs
- FR30: L'administrateur peut consulter les logs d'erreurs et d'echecs

### Pipeline amont (ingestion de donnees)

- FR31: Le systeme peut importer et normaliser des datasets vehicules (car-list.json, CSVs, Teoalida)
- FR32: Le systeme peut extraire les sous-titres de videos YouTube de chaines automobiles
- FR33: Le systeme peut transcrire des fichiers audio via Whisper en local
- FR34: Le systeme peut generer des fiches vehicules structurees a partir de transcriptions via LLM
- FR35: Le systeme peut collecter des donnees argus geolocalisees depuis Leboncoin

### Degradation & Resilience

- FR36: Le systeme peut fonctionner en mode degrade quand un modele n'est pas reconnu (filtres universels uniquement)
- FR37: Le systeme peut remonter les echecs et erreurs au dashboard pour alimenter la roadmap
- FR38: Le systeme peut afficher des messages d'erreur conviviaux avec humour automobile sans exposer de details techniques
- FR39: Le systeme peut fonctionner dans un environnement Docker conteneurise

### Monetisation & Acces Premium (Phase 2)

- FR40: L'utilisateur peut s'authentifier via email ou compte Google (Firebase Auth)
- FR41: L'utilisateur peut acheter une analyse premium via paiement one-shot (Stripe checkout session)
- FR42: Le systeme peut gerer l'acces premium via token stocke dans le navigateur
- FR43: L'utilisateur peut telecharger le rapport d'analyse premium au format PDF
- FR44: L'utilisateur peut recevoir le rapport d'analyse premium par email
- FR45: Le rapport premium presente les memes donnees d'analyse dans un format structure et lisible

---

## Non-Functional Requirements

### Performance

- NFR1: L'analyse gratuite (scan) repond en moins de 10 secondes dans des conditions normales
- NFR2: Le dashboard admin charge en moins de 3 secondes
- NFR3: L'extension Chrome n'impacte pas le temps de chargement des pages Leboncoin de plus de 500ms
- NFR4: Les filtres s'executent en parallele quand ils sont independants pour minimiser le temps total
- NFR5: L'animation d'attente demarre en moins de 200ms apres le clic utilisateur (feedback immediat)

### Securite

- NFR6: L'API REST n'expose aucune donnee personnelle utilisateur dans les reponses
- NFR7: L'authentification premium repose sur Firebase Auth (tokens securises, pas de credentials en clair)
- NFR8: L'API valide et sanitize toutes les donnees recues de l'extension avant traitement
- NFR9: Le dashboard admin est protege par authentification (acces Malik uniquement)
- NFR10: Aucune stacktrace ou erreur technique n'est exposee a l'utilisateur final

### Integration

- NFR11: Le systeme gere gracieusement l'indisponibilite de l'API SIRET gouv.fr (timeout + fallback)
- NFR12: Le systeme detecte les changements de structure du JSON `__NEXT_DATA__` de Leboncoin et alerte l'admin
- NFR13: Les appels API externes (SIRET) ont un timeout de 5 secondes maximum
- NFR14: Le pipeline Whisper fonctionne entierement en local sans dependance reseau
- NFR15: Firebase Auth + Stripe checkout s'integrent via webhooks et Firebase Functions (Phase 2)

### Fiabilite

- NFR16: Le systeme affiche un score partiel plutot qu'une erreur quand des filtres echouent individuellement
- NFR17: Le backend supporte un redemarrage Docker sans perte de donnees (SQLite persistant)
- NFR18: L'extension fonctionne meme si le backend est temporairement injoignable (message de degradation)
- NFR19: Le systeme dispose de 5 annonces de test pre-validees pour les demos

### Testabilite

- NFR20: Chaque filtre (L1-L9) dispose d'au moins un test unitaire avec donnees valides, invalides, et edge cases
- NFR21: La suite de tests peut s'executer avec `pytest` en moins de 60 secondes
- NFR22: Les tests sont reproductibles sans dependance a des services externes (mocks pour APIs)
- NFR23: Le code maintient une couverture de test suffisante pour demontrer la rigueur au jury

### Evolutivite

- NFR24: La base de donnees peut migrer de SQLite vers Firestore ou PostgreSQL sans refonte de l'architecture
- NFR25: L'ajout d'un nouveau filtre ne necessite que la creation d'une nouvelle sous-classe (pattern extensible)
