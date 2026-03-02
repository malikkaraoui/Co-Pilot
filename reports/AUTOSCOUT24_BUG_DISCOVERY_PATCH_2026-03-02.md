# AutoScout24 — découverte de bug et correctif (2026-03-02)

## Contexte

Des anomalies récurrentes ont été observées sur l’extracteur AutoScout24 dans l’extension :

1. **Données « stale » en SPA** : après navigation interne, la page Ford Ranger pouvait afficher des
   données d’un Ford Transit Custom.
2. **Description manquante** (« Pas de description ») malgré une description visible sur l’annonce.

## Symptômes constatés

### Bug 1 — mismatch modèle (SPA stale)

- URL active : annonce `ford-ranger-...`
- Données extraites : `FORD TRANSIT CUSTOM`
- Impact : incohérence des filtres, score et signaux basés sur un véhicule incorrect.

### Bug 2 — description absente

- Description visible côté annonce, mais extraction vide ou teaser court.
- Impact : perte d’information qualitative dans l’analyse.

## Root cause (analyse)

### Cause A — Sélection de payload RSC fragile

- Le parser pouvait retenir un payload non pertinent quand plusieurs scripts coexistent (cas SPA).
- Le guard précédent make/model ne couvrait pas assez bien certains cas de slug modèle
  (variantes/troncatures).

### Cause B — Décodage Flight RSC fragile

- Le texte `self.__next_f` contient des échappements multiples.
- Un décodage trop agressif cassait certains contenus avec guillemets échappés dans les champs
  texte.

### Cause C — Priorité teaser vs description

- La normalisation favorisait un champ court (`teaser`) au lieu de la description complète quand
  disponible.

## Correctif appliqué

### 1) RSC candidate scoring aligné URL

Fichier : `extension/extractors/autoscout24.js`

- Ajout de `_scoreVehicleAgainstUrl(vehicle, urlSlug, expectedMake)`.
- `parseRSCPayload(doc, currentUrl)` :
  - accumule plusieurs candidats,
  - score chaque candidat contre le slug URL,
  - retient le meilleur match (pas seulement le dernier/ premier trouvé).

### 2) Décodage Flight renforcé

Fichier : `extension/extractors/autoscout24.js`

- Décodage en 2 variantes pour compatibilité payloads.
- Protection/restauration des guillemets échappés dans les valeurs (`description`) via sentinel.
- Résultat : les descriptions avec guillemets internes sont correctement parsées.

### 3) Guard SPA make+model durci

Fichier : `extension/extractors/autoscout24.js`

- Validation make + modèle obligatoire pour considérer les données cohérentes avec l’URL.
- Tolérance sur tokens de modèle (slug partiel), mais rejet du same-make/wrong-model.
- Fallback JSON-LD ciblé via `_findJsonLdByMake(document, make, model, urlSlug)`.

### 4) Priorité description complète

Fichier : `extension/extractors/autoscout24.js`

- Ajout de `resolveDescription()` :
  - priorité à `rsc.description` si disponible,
  - fallback sur `rsc.teaser` sinon.

## Couverture de tests ajoutée/ajustée

Fichier : `extension/tests/autoscout24.test.js`

Tests de non-régression ajoutés :

- parsing Flight avec description contenant des guillemets échappés,
- préférence `description` > `teaser`,
- sélection RSC cohérente avec URL en cas de scripts stale,
- scénario extract() SPA : rejet Transit Custom et conservation Ranger via JSON-LD.

## Fichiers concernés

- `extension/extractors/autoscout24.js`
- `extension/tests/autoscout24.test.js`
- `reports/AUTOSCOUT24_BUG_DISCOVERY_PATCH_2026-03-02.md`

## Résultat attendu

- Extraction stable en navigation SPA, même make mais modèle différent.
- Récupération correcte de la description vendeur complète.
- Réduction forte des faux « Pas de description » et des incohérences véhicule/URL.

## Mise à jour (2026-03-02) — cas L9 « Pas de description »

### Incident terrain observé

- URL concernée :
  `https://www.autoscout24.ch/fr/d/ford-mondeo-station-wagon-20-ecoblue-190-st-line-4x4-20233448`
- Symptôme UI :
  `L9 -> Résultat de scan 80% -> Pas de description`
- Constat : l’annonce contient une section **Équipement** riche, mais `description` restait vide dans `ad_data`.

### Cause racine additionnelle

- Le filtre backend `L9` (`app/filters/l9_score.py`) pénalise dès que `description == ""`.
- Sur certaines pages AS24 CH, ni RSC ni JSON-LD ne fournissent un champ description exploitable.
- Résultat : faux négatif L9 malgré une annonce détaillée côté DOM.

### Correctif additionnel appliqué

Fichier : `extension/extractors/autoscout24.js`

1. Ajout d’un fallback DOM `_extractDescriptionFromDom(doc)` avec priorités :
   - blocs description dédiés,
   - section Équipement/Options (listes `li`),
   - `og:description` / `meta description`.
2. Intégration du fallback dans :
   - `fallbackAdDataFromDom(...)`,
   - `extract()` (post-traitement final si description absente),
   - `normalizeToAdData(...)` (fallback JSON-LD `description` si RSC vide).

### Tests ajoutés

Fichier : `extension/tests/autoscout24.test.js`

- `falls back to JSON-LD description when RSC has no description`
- `fills description from DOM equipment list when RSC/JSON-LD have none`

Exécution : `156/156` tests AS24 passés.

### Référence de livraison

- Commit : `66d3796`
- Message : `fix(autoscout24): fallback description from DOM equipment for L9`

