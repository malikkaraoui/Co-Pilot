# Design : Corrections Fondamentales (Architecture & Scoring)

**Date** : 28/02/2026
**Priorite** : CRITIQUE -- regression et dette technique bloquante
**Deadline projet** : 16 mars 2026

---

## Contexte

4 problemes fondamentaux identifies lors des tests AS24 + LBC :
1. Les bonus jobs cross-site (LBC recoit des jobs CH destinee a AS24)
2. Les URLs AS24 font 404 (slugs make/model incorrects)
3. Le scoring penalise les particuliers pour l'absence de SIRET (-12 pts)
4. Les timestamps admin affichent UTC au lieu de Paris (12 bugs dans 6 templates)

## Chantier S1 : Tables separees CollectionJob par site

### Probleme
`CollectionJob` a un champ `country` mais pas de champ `site`. Le `pick_bonus_jobs()` pioche dans TOUS les jobs pending sans filtre site. Un job CH/AS24 peut etre assigne a une session LBC FR. De plus, les URLs AS24 font 404 car `buildSearchUrl()` recoit `make.toLowerCase()` (ex: "vw") alors qu'AS24 attend des slugs specifiques (ex: "volkswagen" ou "vw" selon la marque -- le RSC `make.key` est la source de verite).

### Design

**Nouveau modele `CollectionJobLBC`** (table `collection_jobs_lbc`) :
- Schema identique a l'actuel `CollectionJob`
- `country` toujours `"FR"`
- Migre depuis `collection_jobs` existante (renommage de table)

**Nouveau modele `CollectionJobAS24`** (table `collection_jobs_as24`) :
- `id`, `make`, `model`, `year`, `region` (canton ou region)
- `fuel`, `gearbox`, `hp_range`
- `country` (CH, DE, AT, FR, etc.)
- `tld` (ch, de, at, fr, it, es, be, nl, lu) -- NOT NULL
- `slug_make`, `slug_model` -- slugs AS24 extraits du RSC (ex: "vw", "tiguan")
- `search_strategy` -- enum: "zip_radius" | "national" | "canton"
- `currency` -- "CHF" | "EUR"
- `source_url` -- URL de l'annonce AS24 source (debug)
- `priority`, `status`, `source_vehicle`, `attempts`
- `created_at`, `assigned_at`, `completed_at`

**Services dedies** :
- `collection_job_lbc_service.py` : expand, pick_bonus, mark_done (refactoring de l'existant)
- `collection_job_as24_service.py` : expand, pick_bonus, mark_done (logique adaptee AS24)

**API** :
- `/market-prices/next-job?site=lbc` → `pick_bonus_jobs_lbc()`
- `/market-prices/next-job?site=as24&tld=ch` → `pick_bonus_jobs_as24(country, tld)`
- Default `site=lbc` pour retrocompat

**Token auto-learning AS24** :
- `normalizeToAdData()` extrait `rsc.make.key` et `rsc.model.key` (pas `.name`)
- Stockage dans `Vehicle.as24_slug_make` / `Vehicle.as24_slug_model` (nouvelles colonnes)
- Les bonus jobs AS24 sont servis avec `slug_make`/`slug_model` directement utilisables

**Admin `/admin/issues`** : onglets par site (LBC / AS24)

### Migration
- `collection_jobs` renommee en `collection_jobs_lbc` (ALTER TABLE RENAME)
- `collection_jobs_as24` creee vide
- `start.sh` gere le schema sync pour les nouvelles colonnes

---

## Chantier S2 : Status `neutral` dans le scoring

### Probleme
Le scoring traite `skip` uniformement : poids dans le denominateur, 0 au numerateur. Mais "non applicable" (SIRET sur particulier) != "donnees manquantes" (API down). Un particulier parfait perd 12 points a cause de L6+L7 skip.

### Design

**Nouveau status `neutral`** dans FilterResult :
- Statuts valides : `pass`, `warning`, `fail`, `skip`, `neutral`
- Semantique : `neutral` = "ce filtre ne s'applique pas, ne pas le compter"
- `skip` reste = "donnees manquantes, penaliser"

**Modification du scoring** (`scoring.py`) :
```python
if r.status == "neutral":
    skipped += 1
    # Neutral : NI numerateur NI denominateur
    continue

if r.status == "skip":
    skipped += 1
    # Skip : poids dans le denominateur, 0 dans le numerateur
    total_weight += w
    continue

total_weight += w
weighted_sum += w * r.score
```

**Filtres modifies** :

| Filtre | Cas | Ancien | Nouveau |
|--------|-----|--------|---------|
| L7 | Particulier | `skip` | `neutral` |
| L6 | Particulier sans tel | `skip` | `neutral` |

**Impact scoring** : Particulier parfait 84/100 → ~96/100

---

## Chantier S3 : Fix timezone systematique

### Probleme
12 endroits dans 6 templates affichent UTC au lieu de Paris.

### Design

**Nouveau filtre Jinja `|localdatetime`** (dans `app/__init__.py`) :
```python
@app.template_filter("localdatetime")
def localdatetime_filter(dt, fmt='%d/%m/%Y %H:%M'):
    if dt is None:
        return '-'
    return _to_paris(dt).strftime(fmt)
```

**12 bugs corriges** :
- issues.html:149
- car.html:179, 182
- argus.html:509
- email_detail.html:80
- email_list.html:117
- failed_search_detail.html:81, 85, 99
- failed_searches.html:284, 287
- youtube_search.html:295

**9 usages existants migres** : `(x|localtime).strftime(...)` → `x|localdatetime`

---

## Chantier S4 : Admin issues refonte

### Design
- Page `/admin/issues` avec onglets LBC / AS24
- Stats (pending/assigned/done/failed) par site
- Retention : jobs done gardes 30 jours, bouton "Purger done > 30j"
- `start.sh` ne drop/recreee PLUS les tables de jobs (ALTER TABLE ADD COLUMN uniquement)
- Tri : pending d'abord, puis priorite ASC, puis created_at DESC

---

## Priorites d'implementation

| # | Chantier | Priorite | Complexite |
|---|----------|----------|------------|
| 1 | S3 Timezone | MOYEN | Faible (templates only) |
| 2 | S2 Scoring neutral | HAUT | Faible (scoring.py + 2 filtres) |
| 3 | S1 Tables separees | CRITIQUE | Haute (modeles, services, API, extension, migration) |
| 4 | S4 Admin issues | MOYEN | Moyenne (template + route refonte) |

Ordre recommande : S3 → S2 → S1 → S4 (du plus simple au plus complexe, quick wins d'abord)
