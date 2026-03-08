# Matching véhicule — état initial, évolution et robustesse

_Date : 2026-03-08_

## Objectif

Documenter :

- l’état de base du matching marque/modèle,
- les faiblesses identifiées,
- les évolutions apportées en V1 puis en V2,
- le niveau de robustesse atteint,
- les limites résiduelles et les prochaines améliorations possibles.

---

## 1. État de base avant correction

Le matching historique reposait principalement sur :

- des comparaisons textuelles fragiles,
- quelques alias marque/modèle,
- des normalisations partielles (`lower()`, retrait d’accents dans certains cas),
- des recherches SQL encore basées sur `lower(Vehicle.brand)` / `lower(Vehicle.model)`.

### Symptômes observés

Cas concrets signalés :

- `Série 1` vs `Serie 1`
- `Citroën` vs `Citroen`
- `Mercedes‑Benz` vs `Mercedes-Benz`
- `C.HR` vs `C-HR` vs `CHR`
- variations d’espaces, tirets Unicode, ponctuation, casse

### Problèmes structurels

1. **Le matching était trop dépendant de la forme exacte du texte.**
2. **La normalisation de lookup et la forme canonique stockée étaient mélangées.**
3. **Les requêtes SQL n’étaient pas toutes alignées sur la même logique de matching.**
4. **La robustesse dépendait trop du fallback applicatif et pas assez de la base elle-même.**

### Risque métier

Ces fragilités pouvaient provoquer :

- des non-correspondances alors que le véhicule existe déjà,
- des doublons dans le référentiel,
- des incohérences entre quick-add, auto-create, lookup et routes API,
- des régressions sur des modèles légitimes comme `CX-5` si la normalisation est trop agressive.

---

## 2. Évolution V1 — matching durci côté application

Une première évolution a été réalisée puis poussée sur `main`.

### Commit V1

- `3be43f9` — `Harden vehicle lookup normalization`

### Principes introduits

La V1 a renforcé le matching applicatif en ajoutant :

- normalisation Unicode,
- retrait d’accents,
- harmonisation des tirets/apostrophes Unicode,
- gestion plus robuste de la ponctuation,
- clés de comparaison compactes,
- fallback accent-insensitive plus fiable,
- indexation d’alias plus robuste.

### Exemples de cas mieux gérés

- `Série 1` ↔ `Serie 1`
- `Citroën` ↔ `Citroen`
- `Mercedes‑Benz` ↔ `Mercedes-Benz`
- `C.HR` ↔ `C-HR` ↔ `CHR`

### Correction importante apportée pendant la V1

Une régression a été détectée pendant les hooks/tests :

- un modèle comme `CX-5` risquait d’être trop normalisé lors du stockage.

Le correctif a consisté à **séparer** :

- la **normalisation de lookup** (tolérante, robuste au bruit),
- la **normalisation canonique** (préserve les séparateurs utiles comme le tiret).

C’est un point fondamental :

> la bonne clé de matching n’est pas toujours la bonne forme à stocker et afficher.

---

## 3. Évolution V2 — lookup keys persistées + refactor global

La V2 vise à rendre le matching robuste **systématiquement**, pas seulement via des helpers Python.

## Principe central

Introduire des **lookup keys persistées** sur `Vehicle` :

- `brand_lookup_key`
- `model_lookup_key`

Ces clés sont :

- normalisées,
- compactes,
- stables,
- adaptées à la comparaison exacte,
- indexées en base.

### Bénéfices attendus

1. **Matching cohérent partout**
   - lookup
   - quick-add admin
   - auto-create
   - sélection API / marché

2. **Déduplication plus fiable**
   - même si la saisie varie (`C.HR`, `C-HR`, `CHR`)

3. **Requêtes SQL plus robustes**
   - moins de dépendance au simple `lower()`

4. **Performance meilleure à terme**
   - grâce aux index sur lookup keys

---

## 4. Changements techniques V2 réalisés

### 4.1 Nouveau module central de normalisation

Fichier ajouté :

- `app/services/vehicle_lookup_keys.py`

Contient les fonctions pures partagées :

- `strip_accents`
- `normalize_lookup_text`
- `normalize_canonical_text`
- `lookup_compact_key`
- `lookup_keys`

### 4.2 Modèle `Vehicle` enrichi

Fichier modifié :

- `app/models/vehicle.py`

Ajouts :

- colonnes persistées `brand_lookup_key`, `model_lookup_key`
- index composite `ix_vehicle_lookup_keys`
- méthode `sync_lookup_keys()`
- hooks SQLAlchemy `before_insert` / `before_update`

Effet :

- les clés sont alimentées automatiquement à l’insertion et à la mise à jour.

### 4.3 Refactor du service principal de matching

Fichier modifié :

- `app/services/vehicle_lookup.py`

Évolution :

- la logique réutilise désormais le module partagé de lookup keys,
- `find_vehicle()` s’appuie en priorité sur les clés persistées,
- les alias restent gérés, mais avec une base de matching plus stable.

### 4.4 SQLite aligné avec la même logique de matching

Fichier modifié :

- `app/extensions.py`

Ajout d’une fonction SQLite :

- `vehicle_lookup_key(...)`

Effet :

- les requêtes SQL peuvent calculer la même logique de clé de lookup côté base.

### 4.5 Déduplication quick-add admin migrée

Fichier modifié :

- `app/admin/routes.py`

Évolution :

- déduplication basée sur `brand_lookup_key` + `model_lookup_key`
- meilleure couverture de variantes typographiques
- création de `Vehicle` cohérente avec les nouvelles clés

### 4.6 Auto-create migré

Fichier modifié :

- `app/services/vehicle_factory.py`

Évolution :

- déduplication par lookup keys persistées
- stockage explicite des clés à la création

### 4.7 Requêtes marché migrées

Fichier modifié :

- `app/api/market_routes.py`

Évolution :

- suppression des dernières jointures `lower(Vehicle.brand/model)`
- utilisation des lookup keys persistées / SQL function

### 4.8 Backfill et indexation au démarrage

Fichier modifié :

- `start.sh`

Évolution :

- backfill des lookup keys sur les véhicules déjà présents
- création des index nécessaires

---

## 5. Robustesse gagnée

## Variantes désormais bien mieux couvertes

### Accents / diacritiques

- `Citroën` ↔ `Citroen`
- `Série 1` ↔ `Serie 1`
- `Škoda` ↔ `Skoda`

### Ponctuation

- `C.HR` ↔ `C-HR`
- `ID3` ↔ `ID.3`

### Tirets et Unicode

- `Mercedes‑Benz` ↔ `Mercedes-Benz`
- variantes de tirets typographiques mieux absorbées

### Casse et espaces

- `BMW` / `bmw`
- espaces multiples ou parasites

### Alias métier

- `VW` → `Volkswagen`
- `DS 3` → `3`
- `Clio 5` → `Clio V`
- `Golf VII` / `Golf Variant` → `Golf`

### Préservation de la forme canonique

La V2 conserve le principe essentiel :

- **lookup robuste pour matcher**
- **forme canonique raisonnable pour stocker et afficher**

Exemple :

- `CX-5` reste stockable proprement sans être “cassé” par une normalisation excessive.

---

## 6. Tests et validation

## Déjà validé pendant la V1

- tests ciblés du lookup : `61 passed`
- suite complète projet : `827 passed, 1 skipped`

### Couverture ajoutée ensuite

Des tests supplémentaires ont été ajoutés pour couvrir la V2 :

- population automatique des lookup keys sur `Vehicle`
- mise à jour automatique des lookup keys lors d’un changement marque/modèle
- présence des lookup keys sur véhicule auto-créé
- idempotence / absence de doublons via clés persistées
- rejet d’un doublon admin même avec variante typographique (`C-HR` vs `C.HR`)

> Important : la robustesse n’est plus seulement validée par la lookup function, mais aussi par les flux métiers qui créent et dédupliquent les véhicules.

---

## 7. Résultat actuel

À l’issue de cette évolution, le matching est passé :

- d’un système **tolérant mais encore fragile**,
- à un système **plus unifié, plus explicite, plus durable**.

### En pratique

Le système est maintenant bien plus robuste face à :

- accents,
- alias,
- ponctuation,
- variantes Unicode,
- différences de casse,
- doublons créés par saisies non homogènes.

### Point clé

La vraie avancée n’est pas seulement “un meilleur `normalize_model()`”.

La vraie avancée est d’avoir introduit une architecture de matching en 3 niveaux :

1. **texte brut entrant**
2. **forme canonique stockée/affichée**
3. **lookup key persistée pour la comparaison robuste**

C’est cette séparation qui rend le matching nettement plus fiable.

---

## 8. Limites restantes / vigilance

Même avec cette V2, il reste quelques zones d’attention :

1. **Alias métier incomplets**
   - le matching sera toujours borné par la qualité des alias connus

2. **Cas ambigus volontairement exclus**
   - certains faux modèles ou noms génériques doivent rester rejetés

3. **Qualité des données externes**
   - si une source fournit des valeurs trop bruitées ou incohérentes, il faudra enrichir les règles

4. **Migration de l’historique**
   - le backfill au démarrage doit continuer à rester fiable pour les anciennes bases

---

## 9. Recommandations pour la suite

### Court terme

- continuer à enrichir les alias à partir des vrais cas terrain,
- surveiller les doublons empêchés par les lookup keys,
- vérifier les performances sur base volumineuse.

### Moyen terme

- ajouter éventuellement une contrainte/unicité métier basée sur lookup keys si souhaité,
- ajouter des métriques de matching (hit direct / hit alias / hit fallback),
- tracer les cas non reconnus pour enrichir automatiquement les règles.

### Long terme

- faire des lookup keys un standard transverse à tous les pipelines véhicule,
- consolider les tableaux de bord admin autour de ces clés.

---

## 10. Résumé exécutif

### Avant

Le matching fonctionnait, mais restait fragile sur les variantes réelles : accents, ponctuation, Unicode, aliases et cohérence SQL.

### Après V1

Le lookup applicatif a été nettement durci et validé par les tests.

### Après V2

Le matching devient structurellement plus solide grâce à :

- des lookup keys persistées,
- des index dédiés,
- des flux admin / auto-create / API alignés,
- une séparation saine entre stockage canonique et comparaison robuste.

### Conclusion

Le matching n’est plus seulement “amélioré” :

il est désormais **beaucoup moins fragile par conception**.
