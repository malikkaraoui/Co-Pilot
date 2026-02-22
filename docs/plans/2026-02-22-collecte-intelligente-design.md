# Design : Collecte Intelligente & Argus Universel

**Date** : 2026-02-22
**Statut** : Valide
**Budget requetes par scan** : 3-5 (1 principale + 2 bonus max)
**Contrainte anti-detection** : delais aleatoires 1-2s entre chaque requete

---

## Contexte & Problemes

### P1 — Bonus regions ne marchent pas
Les bonus regions sont random (Fisher-Yates), avec un seuil de 20 prix minimum et une seule tentative de requete. Pour les vehicules niche (Renegade hybride, Cupra Formentor...), ca ne ramene quasi jamais 20 resultats en une requete regionale. Resultat : les bonus sont silencieusement ignores.

### P2 — Referentiel ferme (auto-creation trop conservatrice)
Un vehicule doit avoir 3 scans + (CSV match OU 20 market samples) pour etre auto-cree. Un Jeep Renegade scanne 1 fois ne rentre jamais dans la base, donc pas de collecte, pas d'Argus, L4 skip.

### P3 — Argus LBC ignore
LBC affiche une fourchette Argus (basse/haute) sur chaque annonce. Cette donnee est disponible mais jamais extraite. Pour un vehicule inconnu, l'utilisateur n'a aucune reference prix.

### P4 — Pas d'enrichissement specs depuis la collecte
Quand on collecte 20+ annonces, on recupere prix/year/km/fuel mais on jette les infos motorisation/boite/puissance. Ces donnees enrichiraient le referentiel.

### P5 — next-job ne propose que les vehicules du referentiel historique
Les vehicules auto-crees recemment (enrichment_status=partial) ne sont pas priorises pour la collecte redirect. Les vases ne communiquent pas.

---

## Feature 1 : Fix Bonus Regions (server-driven)

### Changements
- Implementer `_compute_bonus_jobs()` dans `market_routes.py` (reprendre le plan du 21 fev)
- Le serveur retourne `bonus_jobs` dans la reponse `next-job`
- Priorite : regions manquantes > regions stales (>7j) > rien
- **Baisser le seuil bonus de 20 a 5 prix** — precision marquee a 2 pour ces collectes
- Extension remplace le random Fisher-Yates par les jobs serveur
- Delai aleatoire 1-2s entre chaque requete bonus (conserve)

### Flux
```
Extension -> GET /next-job?make=Jeep&model=Renegade&year=2020&region=Nouvelle-Aquitaine&fuel=hybride
Server    <- {collect: true, vehicle: {...}, bonus_jobs: [{region: "IDF"}, {region: "Occitanie"}]}
Extension -> fetch principal (Nouvelle-Aquitaine) [1-2s pause]
Extension -> fetch bonus (IDF) [1-2s pause]
Extension -> fetch bonus (Occitanie)
Extension -> POST /market-prices x 3
```

### Fichiers impactes
- `app/api/market_routes.py` : ajouter `_compute_bonus_jobs()`, modifier 3 return points de `next_market_job()`
- `extension/content.js` : passer fuel dans next-job, remplacer bloc bonus random par server-driven, baisser seuil a 5

---

## Feature 2 : Auto-creation au 1er scan

### Changements
- `MIN_SCANS = 1` (etait 3) quand CSV match existe
- `MIN_MARKET_SAMPLES = 20` conserve comme alternative sans CSV
- La creation se fait dans `auto_create_vehicle()` avec `enrichment_status="partial"`
- Le vehicule auto-cree est immediatement eligible pour next-job et bonus
- Les modeles generiques ("Autres", "Divers") restent rejetes

### Garde-fous
- CSV match obligatoire pour le 1er scan (on ne cree pas un vehicule qui n'existe pas dans les specs)
- Dedup via `find_vehicle()` avec normalisation brand/model existante
- enrichment_status="partial" distingue des vehicules manuels ("complete")

### Fichiers impactes
- `app/services/vehicle_factory.py` : modifier `can_auto_create()`, `MIN_SCANS=1`

---

## Feature 3 : Argus LBC comme fallback (scoring leger)

### Changements
- Extension extrait l'estimation prix LBC depuis la page annonce (API LBC ou __NEXT_DATA__)
- Envoyee dans le payload `/api/analyze` : `lbc_estimation: {low: int, high: int}`
- Nouveau champ JSON sur le resultat d'analyse (pas de nouveau modele DB — on le stocke dans les details du filtre)
- Cascade L4 mise a jour :
  1. MarketPrice (crowdsource) — notre recette precise
  2. ArgusPrice (seed) — donnees pre-chargees
  3. **LBC Estimation** — fallback scoring leger, poids reduit
- Quand on utilise le fallback LBC :
  - Score avec poids reduit (facteur 0.5 sur le delta)
  - Message clair : "Estimation LeBonCoin (donnees marche insuffisantes)"
  - Badge distinct dans le popup extension

### Recherche necessaire
- Identifier le champ exact dans l'API LBC / __NEXT_DATA__ qui contient l'estimation Argus
- Peut etre un appel API separe (price_rating endpoint LBC)

### Fichiers impactes
- `extension/content.js` : extraction estimation LBC
- `app/filters/l4_price.py` : 3eme tier de fallback
- `extension/popup.html` / `extension/popup.js` : badge estimation LBC

---

## Feature 4 : Enrichissement specs opportuniste

### Changements
- Etendre `price_details` dans le payload POST /market-prices pour inclure `gearbox`, `horse_power_din` quand dispo
- Nouvelle table `VehicleObservedSpec` :
  ```
  id, vehicle_id (FK), spec_type (fuel/gearbox/horse_power), spec_value, count, last_seen_at
  ```
- Dans `store_market_prices()`, apres stockage prix, agreger les specs vues et upsert dans `VehicleObservedSpec`
- Visible dans l'admin `/admin/car/<id>` pour enrichissement manuel

### Exemple
```
VehicleObservedSpec:
| vehicle_id | spec_type   | spec_value              | count | last_seen |
|------------|-------------|-------------------------|-------|-----------|
| 125 (Renegade) | fuel    | hybride_rechargeable    | 8     | 2026-02-22|
| 125 (Renegade) | fuel    | diesel                  | 15    | 2026-02-22|
| 125 (Renegade) | gearbox | automatique             | 20    | 2026-02-22|
| 125 (Renegade) | hp      | 190                     | 8     | 2026-02-22|
| 125 (Renegade) | hp      | 130                     | 12    | 2026-02-22|
```

### Fichiers impactes
- `app/models/vehicle_observed_spec.py` : nouveau modele
- `app/models/__init__.py` : import
- `app/services/market_service.py` : agregation dans `store_market_prices()`
- `extension/content.js` : etendre price_details avec gearbox/hp
- `app/admin/routes.py` : afficher observed_specs dans detail vehicule

---

## Feature 5 : next-job elargi (vehicules partial priorises)

### Changements
- Dans `next_market_job()`, la query candidates inclut TOUS les vehicules (pas seulement ceux avec year_start)
- Les vehicules `enrichment_status="partial"` ont un boost de priorite (tries avant les "complete" a anciennete egale)
- Priorite finale :
  1. Vehicule courant (si besoin refresh)
  2. Vehicule partial le plus scanne (demande forte) dans la meme region
  3. Vehicule complete le plus ancien dans la meme region

### Fichiers impactes
- `app/api/market_routes.py` : modifier query candidates dans `next_market_job()`

---

## Resume des contraintes

- Budget : 3-5 requetes par scan
- Delais aleatoires 1-2s entre requetes (anti-detection LBC)
- Pas de regression sur les 400+ tests existants
- ruff clean
- Compatible SQLite (schema drift auto via start.sh)
