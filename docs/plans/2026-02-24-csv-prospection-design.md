# Design : Prospection CSV - Onglet Admin

**Date** : 2026-02-24
**Auteur** : Claude Sonnet 4.5 + Malik
**Statut** : Validé

---

## Contexte

Le projet Co-Pilot dispose de **144+ modèles** dans le référentiel `Vehicle`, enrichis avec **1707 fiches specs** provenant de CSV Kaggle (~172k lignes).

Actuellement, l'ajout de nouveaux véhicules au référentiel se fait de manière réactive :
1. L'utilisateur scanne une annonce LBC avec l'extension
2. Si le véhicule n'est pas reconnu → filtre L2 warning
3. Le véhicule apparaît dans "Modèles demandés mais non reconnus" (`/admin/car`)
4. L'utilisateur clique sur "Ajouter" → ajout manuel au référentiel
5. Auto-enrichissement depuis CSV Kaggle via `lookup_specs()`

**Problème** : L'utilisateur ne sait pas **quels véhicules sont disponibles** dans les CSV avant de les rencontrer par hasard sur LBC.

**Objectif** : Créer un nouvel onglet admin pour identifier **proactivement** les véhicules présents dans les CSV mais absents du référentiel, afin de les scanner et les ajouter de manière ciblée.

---

## Besoin utilisateur

### Ce que l'utilisateur veut

- **Voir la liste** des véhicules disponibles dans les CSV Kaggle mais pas encore dans le référentiel `Vehicle`
- **Savoir combien de fiches** seront importées en ajoutant chaque véhicule
- **Accéder rapidement** à LBC pour scanner ces véhicules avec l'extension

### Ce que l'utilisateur ne veut PAS

- ❌ Importer en masse tous les CSV (perte de qualité)
- ❌ Priorisation automatique complexe (risque de perdre le contrôle)
- ❌ Ajout automatique (il veut valider manuellement)

### Workflow cible

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Ouvrir /admin/csv-prospection                            │
│ 2. Consulter la liste des véhicules CSV manquants           │
│ 3. Cliquer "🔍 Chercher sur LBC" pour un modèle intéressant │
│ 4. Scanner des annonces avec l'extension                    │
│ 5. Ajouter le véhicule via /admin/car (bouton quick-add)    │
│ 6. Bénéficier de l'auto-enrichissement CSV (X fiches)       │
└─────────────────────────────────────────────────────────────┘
```

---

## Architecture globale

### Vue d'ensemble

```
┌─────────────────────────────────────────────────────────────┐
│  Nouvel onglet : /admin/csv-prospection                     │
│                                                              │
│  ┌────────────────────────────────────────────────────┐    │
│  │ Stat card : X véhicules CSV non importés          │    │
│  │             Y fiches specs disponibles au total    │    │
│  └────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌────────────────────────────────────────────────────┐    │
│  │ Tableau                                             │    │
│  │ ┌────────┬────────┬───────────┬─────┬──────────┐  │    │
│  │ │ Marque │ Modèle │ Années    │ CSV │ Action   │  │    │
│  │ ├────────┼────────┼───────────┼─────┼──────────┤  │    │
│  │ │ Renault│ Clio   │ 2012-2024 │ 35  │ [🔍 LBC] │  │    │
│  │ │ Peugeot│ 208    │ 2015-2023 │ 28  │ [🔍 LBC] │  │    │
│  │ └────────┴────────┴───────────┴─────┴──────────┘  │    │
│  └────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

### Flux de données

1. **Au démarrage de l'app** : `csv_enrichment.py` charge le cache CSV enrichi en mémoire
2. **Page admin** : appelle `get_csv_missing_vehicles()` qui fait la diff entre cache CSV et table `Vehicle`
3. **Affichage** : tableau trié par nombre de fiches (descendant) pour prioriser les modèles riches en données
4. **Clic sur lien LBC** : ouvre `https://www.leboncoin.fr/recherche?category=2&text=Marque+Modele`

---

## Approche technique retenue : Extension du cache CSV existant

### Pourquoi cette approche ?

Le service `csv_enrichment.py` dispose déjà d'un cache mémoire `_load_model_index()` qui charge ~2k paires (make, model) du CSV Kaggle.

On **étend ce cache** pour stocker aussi :
- Plage d'années (`year_start`, `year_end`)
- Nombre de fiches specs (`specs_count`)

**Avantages :**
- ✅ Réutilise l'infrastructure existante
- ✅ Rapide : O(1) lookup après le 1er appel
- ✅ Simple à maintenir (pas de nouvelle table SQL)
- ✅ Cohérent avec l'architecture actuelle

**Inconvénients :**
- ⚠️ Un peu plus de mémoire (~5-10 MB au lieu de ~1 MB)
- ⚠️ Rebuild au restart de l'app (mais c'est déjà le cas)

### Alternatives écartées

**Approche 2 : Scan CSV à la volée**
- ❌ Trop lent : 3-5 secondes par chargement de page
- ❌ Bloque l'UI

**Approche 3 : Table SQL dédiée `CsvVehicleCatalog`**
- ❌ Overhead : migration, seed, maintenance
- ❌ Risque de devenir stale si CSV change

---

## Design détaillé

### 1. Modifications du cache CSV (`app/services/csv_enrichment.py`)

#### Nouveau cache enrichi

Remplacement de `_load_model_index()` par `_load_csv_catalog()` :

```python
@lru_cache(maxsize=1)
def _load_csv_catalog() -> dict[tuple[str, str], dict]:
    """Charge le catalogue complet CSV avec métadonnées.

    Returns:
        {
            ("renault", "clio"): {
                "year_start": 2012,
                "year_end": 2024,
                "specs_count": 35
            },
            ...
        }
    """
    if not CSV_PATH.exists():
        return {}

    catalog: dict[tuple[str, str], dict] = {}

    with open(CSV_PATH, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            make = (row.get("Make") or "").strip().lower()
            model = (row.get("Modle") or "").strip().lower()

            if not make or not model:
                continue

            key = (make, model)
            year_from = _int_or_none(row.get("Year_from", ""))
            year_to = _int_or_none(row.get("Year_to", ""))

            if key not in catalog:
                catalog[key] = {
                    "year_start": year_from,
                    "year_end": year_to,
                    "specs_count": 0
                }
            else:
                # Étendre la plage d'années si nécessaire
                if year_from and (catalog[key]["year_start"] is None or year_from < catalog[key]["year_start"]):
                    catalog[key]["year_start"] = year_from
                if year_to and (catalog[key]["year_end"] is None or year_to > catalog[key]["year_end"]):
                    catalog[key]["year_end"] = year_to

            catalog[key]["specs_count"] += 1

    logger.info("CSV catalog loaded: %d unique vehicles", len(catalog))
    return catalog
```

**Explication détaillée :**

1. **Cache LRU** : `@lru_cache(maxsize=1)` garantit qu'on ne charge le CSV qu'**une seule fois**
2. **Structure de données** : `dict[tuple[str, str], dict]`
   - Clé : `(make_lower, model_lower)` pour lookup rapide O(1)
   - Valeur : dict avec `year_start`, `year_end`, `specs_count`
3. **Agrégation** : Pour chaque ligne CSV du même modèle :
   - Étend la plage d'années (min/max)
   - Incrémente le compteur de fiches
4. **Résultat** : Un catalogue complet de tous les véhicules CSV avec métadonnées

#### Nouvelle fonction publique

```python
def get_csv_missing_vehicles() -> list[dict]:
    """Retourne les véhicules présents dans le CSV mais absents du référentiel.

    Returns:
        [
            {
                "brand": "Renault",
                "model": "Clio",
                "year_start": 2012,
                "year_end": 2024,
                "specs_count": 35
            },
            ...
        ]
        Trié par specs_count descendant (modèles les plus riches d'abord).
    """
    from app.models.vehicle import Vehicle

    catalog = _load_csv_catalog()

    # Récupérer tous les véhicules du référentiel (lower case pour comparaison)
    existing = {
        (v.brand.lower(), v.model.lower())
        for v in Vehicle.query.all()
    }

    # Diff : véhicules CSV non présents dans Vehicle
    missing = []
    for (make, model), meta in catalog.items():
        if (make, model) not in existing:
            missing.append({
                "brand": make.title(),  # Capitalisation pour affichage
                "model": model.title(),
                "year_start": meta["year_start"],
                "year_end": meta["year_end"],
                "specs_count": meta["specs_count"]
            })

    # Tri par nombre de fiches (descendant)
    missing.sort(key=lambda x: x["specs_count"], reverse=True)

    return missing
```

**Explication :**

1. **Récupération du catalogue** : Appel `_load_csv_catalog()` (instant grâce au cache)
2. **Récupération du référentiel** : Query SQL pour tous les `Vehicle` (144+)
3. **Diff** : Set difference `catalog.keys() - existing`
4. **Capitalisation** : `.title()` pour un affichage propre ("Renault" au lieu de "renault")
5. **Tri** : Par `specs_count` descendant → les modèles les plus riches en données d'abord

#### Compatibilité backwards

On garde `has_specs()` fonctionnel :

```python
def has_specs(brand: str, model: str) -> bool:
    """Vérifie rapidement si un véhicule a des specs dans le CSV."""
    b, m = _normalize_for_csv(brand, model)
    return (b, m) in _load_csv_catalog()
```

---

### 2. Route admin (`app/admin/routes.py`)

#### Nouvelle route `/admin/csv-prospection`

```python
@admin_bp.route("/csv-prospection")
@login_required
def csv_prospection():
    """Prospection CSV : véhicules disponibles dans les CSV mais pas encore importés."""
    from app.services.csv_enrichment import get_csv_missing_vehicles
    from urllib.parse import quote_plus

    # Récupérer les véhicules manquants
    missing_vehicles = get_csv_missing_vehicles()

    # Stats pour les cards
    total_missing = len(missing_vehicles)
    total_specs = sum(v["specs_count"] for v in missing_vehicles)

    # Pagination
    page = request.args.get("page", 1, type=int)
    per_page = 50
    total_pages = max(1, (total_missing + per_page - 1) // per_page)
    page = min(page, total_pages)

    start = (page - 1) * per_page
    end = start + per_page
    paginated_vehicles = missing_vehicles[start:end]

    # Préconstruire les URLs LBC (Option B : plus simple dans le template)
    for vehicle in paginated_vehicles:
        query = f"{vehicle['brand']} {vehicle['model']}"
        vehicle["lbc_url"] = f"https://www.leboncoin.fr/recherche?category=2&text={quote_plus(query)}"

    return render_template(
        "admin/csv_prospection.html",
        missing_vehicles=paginated_vehicles,
        total_missing=total_missing,
        total_specs=total_specs,
        page=page,
        total_pages=total_pages,
    )
```

**Design choices :**

- **Pagination** : 50 résultats par page (cohérent avec `/admin/database`)
- **URLs préconstruites** : Boucle côté Python pour simplicité template (voir ci-dessous)
- **Stats cards** : Total manquants + total fiches (donne une vision de la "richesse" disponible)

#### Choix design : URLs préconstruites (Option B)

**Option A (écartée) : Fonction dans le template**
```python
return render_template(
    ...,
    generate_lbc_url=_generate_lbc_url,  # fonction passée
)
```
```html
<a href="{{ generate_lbc_url(vehicle.brand, vehicle.model) }}">
```
- ⚠️ Logique dans le template (moins propre MVC)
- ⚠️ Appels Jinja2 (légèrement plus lents)

**Option B (retenue) : URLs préconstruites**
```python
for vehicle in paginated_vehicles:
    vehicle["lbc_url"] = _generate_lbc_url(vehicle["brand"], vehicle["model"])
```
```html
<a href="{{ vehicle.lbc_url }}">
```
- ✅ Template ultra-simple (juste affichage)
- ✅ Python pur (plus rapide)
- ✅ Séparation responsabilités (logique vs présentation)
- ✅ Pattern cohérent avec le reste du code (`/admin/car` précalcule `trend`, etc.)

**Scalabilité :** Aucun problème car on boucle uniquement sur `paginated_vehicles` (50 max), pas sur tous les véhicules manquants.

---

### 3. Template HTML (`app/admin/templates/admin/csv_prospection.html`)

```html
{% extends "admin/base.html" %}
{% block title %}Prospection CSV - Co-Pilot Admin{% endblock %}

{% block content %}
<h2 class="mb-4">Prospection CSV</h2>

<!-- Stat cards -->
<div class="row g-3 mb-4">
  <div class="col-md-6">
    <div class="stat-card">
      <div class="stat-value">{{ total_missing }}</div>
      <div class="stat-label">Véhicules CSV non importés</div>
    </div>
  </div>
  <div class="col-md-6">
    <div class="stat-card">
      <div class="stat-value">{{ total_specs }}</div>
      <div class="stat-label">Fiches specs disponibles au total</div>
    </div>
  </div>
</div>

<!-- Description -->
<div class="alert alert-info mb-4">
  <strong>💡 Comment ça marche :</strong> Ces véhicules sont présents dans le CSV Kaggle mais pas encore dans ton référentiel.
  Clique sur "Chercher sur LBC" pour scanner des annonces avec ton extension, puis ajoute-les manuellement via <a href="{{ url_for('admin.car') }}">/admin/car</a>.
</div>

<!-- Tableau -->
<div class="table-responsive">
  <table class="table table-hover">
    <thead>
      <tr>
        <th>Marque</th>
        <th>Modèle</th>
        <th>Plage années</th>
        <th class="text-center">Fiches CSV</th>
        <th class="text-center">Action</th>
      </tr>
    </thead>
    <tbody>
      {% if missing_vehicles %}
        {% for vehicle in missing_vehicles %}
        <tr>
          <td><strong>{{ vehicle.brand }}</strong></td>
          <td>{{ vehicle.model }}</td>
          <td>
            {% if vehicle.year_start and vehicle.year_end %}
              {{ vehicle.year_start }}-{{ vehicle.year_end }}
            {% elif vehicle.year_start %}
              Depuis {{ vehicle.year_start }}
            {% else %}
              <span class="text-muted">Non renseigné</span>
            {% endif %}
          </td>
          <td class="text-center">
            <span class="badge bg-primary">{{ vehicle.specs_count }}</span>
          </td>
          <td class="text-center">
            <a href="{{ vehicle.lbc_url }}"
               target="_blank"
               class="btn btn-sm btn-outline-primary"
               title="Ouvrir la recherche LBC pour {{ vehicle.brand }} {{ vehicle.model }}">
              🔍 Chercher sur LBC
            </a>
          </td>
        </tr>
        {% endfor %}
      {% else %}
        <tr>
          <td colspan="5" class="text-center text-muted py-4">
            🎉 Tous les véhicules CSV sont déjà importés !
          </td>
        </tr>
      {% endif %}
    </tbody>
  </table>
</div>

<!-- Pagination -->
{% if total_pages > 1 %}
<nav>
  <ul class="pagination justify-content-center">
    {% if page > 1 %}
    <li class="page-item">
      <a class="page-link" href="{{ url_for('admin.csv_prospection', page=page-1) }}">Précédent</a>
    </li>
    {% endif %}

    <li class="page-item disabled">
      <span class="page-link">Page {{ page }} / {{ total_pages }}</span>
    </li>

    {% if page < total_pages %}
    <li class="page-item">
      <a class="page-link" href="{{ url_for('admin.csv_prospection', page=page+1) }}">Suivant</a>
    </li>
    {% endif %}
  </ul>
</nav>
{% endif %}

{% endblock %}
```

**Design choices :**

- **Stat cards** : Style cohérent avec `/admin/dashboard`
- **Alert info** : Explique le workflow à l'utilisateur
- **Badge fiches** : Badge Bootstrap pour le compteur de fiches
- **Target blank** : Lien LBC ouvre dans un nouvel onglet (évite de perdre la page admin)
- **Empty state** : Message "🎉 Tous importés" si liste vide

#### Ajout du lien dans la navbar

Dans `app/admin/templates/admin/base.html`, ajouter l'onglet :

```html
<li class="nav-item">
  <a class="nav-link {% if request.endpoint == 'admin.csv_prospection' %}active{% endif %}"
     href="{{ url_for('admin.csv_prospection') }}">
    📊 Prospection CSV
  </a>
</li>
```

Position recommandée : après "Base Véhicules" et avant "YouTube".

---

### 4. Corrections des chiffres obsolètes

#### `app/models/vehicle.py` (ligne 9)

**Avant :**
```python
class Vehicle(db.Model):
    """Vehicule connu dans la base de reference (70 modeles, objectif 200+)."""
```

**Après :**
```python
class Vehicle(db.Model):
    """Vehicule connu dans la base de reference (144+ modeles, objectif 200+)."""
```

#### `data/seeds/seed_vehicles.py` (ligne 2)

**Avant :**
```python
"""Seed du referentiel vehicules -- Top 77 modeles les plus vendus en France.
```

**Après :**
```python
"""Seed du referentiel vehicules -- Top 144+ modeles les plus vendus en France.
```

#### `data/seeds/seed_vehicles.py` (ligne 18)

**Avant :**
```python
# Top 70 modeles les plus vendus en France (ventes 2024-2025 + parc occasion)
```

**Après :**
```python
# Top 144+ modeles les plus vendus en France (ventes 2024-2025 + parc occasion)
```

**Note :** "144+" indique que c'est évolutif (l'utilisateur ajoute régulièrement de nouveaux modèles).

---

## Impact et avantages

### Avantages immédiats

✅ **Visibilité proactive** : L'utilisateur voit instantanément ce qui est disponible dans les CSV
✅ **Gain de temps** : Accès direct à LBC via liens préconstruits
✅ **Qualité maintenue** : Ajout manuel conservé, pas d'import automatique
✅ **ROI élevé** : Priorisation par nombre de fiches (ajouter une Clio = 35 fiches d'un coup)

### Métriques de succès

- Nombre de véhicules ajoutés au référentiel après consultation de `/admin/csv-prospection`
- Taux de conversion : clics LBC → scans effectués → ajouts au référentiel
- Évolution de la couverture référentiel (144+ → objectif 200+)

---

## Risques et mitigations

### Risque 1 : Performance au démarrage

**Problème** : Chargement du catalogue CSV au 1er appel peut prendre ~500ms

**Mitigation** :
- Cache LRU garantit un seul chargement par session
- Chargement lazy (uniquement si page `/admin/csv-prospection` visitée)
- Acceptable car admin uniquement (pas user-facing)

### Risque 2 : Mémoire

**Problème** : Cache complet prend ~5-10 MB au lieu de ~1 MB

**Mitigation** :
- Négligeable pour une app Flask moderne
- Peut ajouter un TTL si besoin (ex: rebuild cache toutes les 24h)

### Risque 3 : Données CSV obsolètes

**Problème** : Si CSV Kaggle change, le cache devient stale

**Mitigation** :
- Rebuild automatique au restart de l'app
- Ajout futur possible : bouton admin "Recharger le cache CSV"

---

## Points d'attention pour l'implémentation

1. **Import circulaire** : `get_csv_missing_vehicles()` importe `Vehicle` → vérifier que pas de circular import
2. **Normalisation** : Utiliser `_normalize_for_csv()` pour gérer les aliases (Mercedes-Benz, DS, etc.)
3. **Tests** : Tester avec un CSV vide, un CSV incomplet, un référentiel plein
4. **URL encoding** : Utiliser `urllib.parse.quote_plus()` pour gérer les espaces/accents dans les URLs LBC

---

## Tests de validation

### Test 1 : Cache chargé correctement
```python
from app.services.csv_enrichment import _load_csv_catalog

catalog = _load_csv_catalog()
assert len(catalog) > 0
assert ("renault", "clio") in catalog
assert catalog[("renault", "clio")]["specs_count"] > 0
```

### Test 2 : Diff correcte
```python
from app.services.csv_enrichment import get_csv_missing_vehicles

missing = get_csv_missing_vehicles()
# Vérifier qu'aucun véhicule du référentiel n'apparaît dans missing
from app.models.vehicle import Vehicle
existing = {(v.brand.lower(), v.model.lower()) for v in Vehicle.query.all()}
for v in missing:
    assert (v["brand"].lower(), v["model"].lower()) not in existing
```

### Test 3 : URLs LBC valides
```python
from urllib.parse import urlparse, parse_qs

url = "https://www.leboncoin.fr/recherche?category=2&text=Renault+Clio"
parsed = urlparse(url)
assert parsed.scheme == "https"
assert parsed.netloc == "www.leboncoin.fr"
assert parse_qs(parsed.query)["category"] == ["2"]
assert parse_qs(parsed.query)["text"] == ["Renault Clio"]
```

---

## Évolutions futures possibles

1. **Filtrage par marque** : Dropdown pour filtrer les véhicules CSV par marque
2. **Recherche** : Champ de recherche pour filtrer par modèle
3. **Bouton "Tout afficher"** : Désactiver la pagination (si <200 véhicules)
4. **Export CSV** : Bouton pour exporter la liste au format CSV
5. **Statistiques** : Graphique de la couverture référentiel par marque
6. **Recommandation intelligente** : Prioriser les véhicules les plus scannés (croiser avec `ScanLog`)

---

## Conclusion

Cette feature apporte une **visibilité proactive** sur les véhicules CSV disponibles, tout en conservant le contrôle manuel de l'utilisateur.

L'approche par **extension du cache existant** est simple, performante et cohérente avec l'architecture actuelle.

Le workflow **consulter → scanner → ajouter** s'intègre naturellement dans les habitudes de l'utilisateur.

**Prochaine étape** : Rédaction du plan d'implémentation détaillé.
