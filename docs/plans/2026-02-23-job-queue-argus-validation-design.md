# Design : Job Queue + Validation LBC + HP Precision

**Date** : 2026-02-23
**Status** : Approuve

## Contexte

L'argus maison collecte des prix LBC via l'extension Chrome. Problemes identifies :

1. **Bonus jobs ignores** : quand le vehicule courant est frais (`collect=false`), l'extension ignore les `bonus_jobs` retournes par le serveur et affiche "Cooldown 24h"
2. **Pas de file d'attente** : aucun systeme d'issues pour organiser les collectes futures (variantes, regions manquantes)
3. **Granularite HP insuffisante** : MarketPrice ne differencie pas les variantes moteur (un 130ch et un 160ch du meme modele ecrasent le meme argus)
4. **Pas de validation croisee** : aucune comparaison entre notre argus et l'estimation LBC pour auto-evaluation

## Decisions

| Choix | Decision |
|-------|----------|
| Granularite issue | 1 issue = 1 vehicule x 1 region |
| Jobs bonus par scan | Max 3 |
| Ordre variantes | Regions → Fuel → Boite → Annee (+-1) |
| Validation LBC | Auto-evaluation : comparer notre argus vs fourchette LBC |
| Fourchette LBC | Pas encore collectee, a ajouter dans le payload |
| Anciens argus | Pas de suppression, recyclage naturel a 7 jours via les issues |
| Cylindree | Non disponible, on stocke chevaux DIN + chevaux fiscaux. LLM fera le lien plus tard |

## Section 1 : Modele CollectionJob

Nouveau modele DB -- file d'attente de jobs de collecte.

```
CollectionJob
  id (PK)
  make, model, year (vehicule cible)
  region (region a collecter)
  fuel (nullable -- variante carburant)
  gearbox (nullable -- variante boite)
  hp_range (nullable -- ex: "120-150")
  priority (1=meme vehicule/autre region, 2=variante fuel, 3=variante boite, 4=annee +-1)
  status: pending -> assigned -> done / failed
  source_vehicle (text -- "Renault Talisman 2016 diesel" -- le vehicule declencheur)
  created_at, assigned_at, completed_at
  attempts (int, default 0 -- pour retry apres fail, max 3)
  UniqueConstraint(make, model, year, region, fuel, gearbox, hp_range)
```

Regles :
- Deduplication a la creation : si le job existe deja en `done` avec un MarketPrice frais (< 7j) → skip
- Si `done` mais MarketPrice stale → repasse en `pending`
- Max 3 `attempts` -- apres = abandonne

## Section 2 : Generation des jobs (expansion en cascade)

Fonction `_expand_collection_jobs()` appelee lors de `next-job` quand un vehicule est scanne.

| Priority | Description | Exemple (Talisman 2016 diesel manuelle 130ch, Rhone-Alpes) |
|----------|-------------|-------------------------------------------------------------|
| 1 | Meme vehicule exact → autres regions | Talisman 2016 diesel manuelle 120-150ch x 12 regions restantes |
| 2 | Variante fuel (diesel ↔ essence) → toutes regions | Talisman 2016 essence manuelle (SANS filtre HP) x 13 regions |
| 3 | Variante boite (manuelle ↔ auto) → toutes regions | Talisman 2016 diesel auto 120-150ch x 13 regions |
| 4 | Annee +-1 (meme fuel/boite) → toutes regions | Talisman 2015 diesel manuelle 120-150ch x 13 regions |

Intelligence :
- Pas de job si MarketPrice frais existe deja pour cette combinaison
- Pas de variante fuel/gearbox si info absente du vehicule courant
- Fuel oppose : diesel ↔ essence uniquement (electrique/hybride → pas de variante)
- Boite opposee : manuelle ↔ automatique
- Jobs crees en batch (INSERT en lot)
- Declenchement : a chaque `next-job`, si aucun job existant pour ce `source_vehicle`

## Section 3 : Filtre HP resserre + hp_range dans MarketPrice

### Nouveau filtre HP (extension)

Au lieu de `130-max` (plancher ouvert), utiliser des fourchettes coherentes :

| Puissance | Range LBC | Segment |
|-----------|-----------|---------|
| < 80 ch | min-90 | Citadines |
| 80-110 | 70-120 | Compactes basses |
| 110-140 | 100-150 | Compactes hautes |
| 140-180 | 130-190 | Berlines |
| 180-250 | 170-260 | Sportives |
| 250-350 | 240-360 | GT |
| > 350 | 340-max | Supercars |

### MarketPrice : nouveau champ hp_range

- `hp_range` (String, nullable) ajoute a la UniqueConstraint
- `fiscal_hp` (Integer, nullable) -- chevaux fiscaux pour reference
- Nouvelle UniqueConstraint : `(make, model, year, region, fuel, hp_range)`
- Nullable pour retro-compat : les anciens argus sans HP restent valides, recycles naturellement a 7j

### Affichage dashboard argus

Colonne "Motorisation" : `fuel + hp_range + fiscal_hp`

Exemple : `Diesel · 120-150ch · 7cv`

## Section 4 : Collecte fourchette LBC + validation dashboard

### Extension -- collecte estimation LBC

- L'extension envoie `lbc_estimation_low` et `lbc_estimation_high` dans le payload POST `/api/market-prices`
- Valeurs de l'annonce qui a declenche la collecte (point de comparaison)

### MarketPrice -- nouveaux champs

- `lbc_estimate_low` (Integer, nullable)
- `lbc_estimate_high` (Integer, nullable)

### Dashboard -- auto-evaluation

Badge par ligne argus :

| Situation | Badge |
|-----------|-------|
| IQR mean dans fourchette LBC [low, high] | **Valide** (vert) |
| IQR mean a +-15% de la fourchette LBC | **Proche** (orange) |
| IQR mean hors fourchette > 15% | **Ecart** (rouge) |
| Pas de fourchette LBC disponible | **--** (gris) |

Stat card globale : "X% des argus valides par LBC"

## Section 5 : Extension -- bonus jobs meme quand collect=false

### Bug actuel

```
next-job → { collect: false, bonus_jobs: [...] }
Extension: if (!collect) → return → bonus_jobs ignores
```

### Fix

```
next-job → { collect: false, bonus_jobs: [...] }
Extension: skip collecte primaire
         MAIS bonus_jobs.length > 0 → executer les 3 jobs bonus
```

### Bonus job payload (serveur → extension)

```json
{
  "make": "Renault", "model": "Talisman", "year": 2016,
  "region": "Ile-de-France",
  "fuel": "diesel",
  "hp_range": "120-150",
  "gearbox": "manual",
  "job_id": 42
}
```

L'extension construit l'URL LBC, execute le fetch, POST les resultats. Le serveur marque le CollectionJob comme `done`.

Pas de cooldown sur les bonus jobs (pre-approuves par le serveur, max 3 par scan, delai anti-ban 1-2s entre chaque).

## Section 6 : Onglet admin /admin/issues

### Stat cards

- Jobs en attente (pending)
- Jobs assignes (assigned)
- Jobs completes (done)
- Jobs echoues (failed)
- Taux de completion

### Table

Colonnes : Priorite, Vehicule, Motorisation, Region, Status, Cree le, Source

Filtres : par status, vehicule, region, priorite

### Actions

- Purger les failed (reset → pending)
- Regenerer les issues (relancer `_expand_collection_jobs` pour un vehicule)
- Pas de creation manuelle -- les issues sont generees automatiquement par les scans
