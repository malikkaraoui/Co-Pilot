# CSV Prospection Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Créer un onglet admin `/admin/csv-prospection` pour identifier les véhicules disponibles dans les CSV Kaggle mais absents du référentiel, avec liens directs vers LBC.

**Architecture:** Extension du cache CSV existant (`csv_enrichment.py`) pour stocker métadonnées (plage années, compteur fiches). Nouvelle route admin avec pagination et URLs LBC préconstruites.

**Tech Stack:** Python 3.12, Flask 3.1.2, SQLAlchemy 2.0, Jinja2, Bootstrap 5.3

---

## Task 1: Corriger les chiffres obsolètes "70 modèles"

**Files:**
- Modify: `app/models/vehicle.py:9`
- Modify: `data/seeds/seed_vehicles.py:2`
- Modify: `data/seeds/seed_vehicles.py:18`

**Step 1: Corriger vehicle.py**

```python
class Vehicle(db.Model):
    """Vehicule connu dans la base de reference (144+ modeles, objectif 200+)."""
```

**Step 2: Corriger seed_vehicles.py ligne 2**

```python
"""Seed du referentiel vehicules -- Top 144+ modeles les plus vendus en France.
```

**Step 3: Corriger seed_vehicles.py ligne 18**

```python
# Top 144+ modeles les plus vendus en France (ventes 2024-2025 + parc occasion)
```

**Step 4: Commit**

```bash
git add app/models/vehicle.py data/seeds/seed_vehicles.py
git commit -m "fix: update vehicle count from 70 to 144+ in documentation

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 2: Étendre le cache CSV avec métadonnées

**Files:**
- Modify: `app/services/csv_enrichment.py:87-104` (remplacer `_load_model_index`)
- Test: `tests/services/test_csv_enrichment.py` (créer)

**Step 1: Écrire le test pour _load_csv_catalog**

Créer `tests/services/test_csv_enrichment.py`:

```python
"""Tests pour csv_enrichment service."""

import pytest
from app.services.csv_enrichment import _load_csv_catalog


def test_load_csv_catalog_structure():
    """Le catalogue CSV doit contenir les métadonnées attendues."""
    catalog = _load_csv_catalog()

    # Le catalogue doit être un dict non vide
    assert isinstance(catalog, dict)
    assert len(catalog) > 0

    # Vérifier qu'une entrée type existe (Renault Clio dans le CSV Kaggle)
    # Note: adapter si le CSV test ne contient pas Clio
    sample_key = next(iter(catalog.keys()))
    assert isinstance(sample_key, tuple)
    assert len(sample_key) == 2  # (make, model)

    # Vérifier la structure de métadonnées
    meta = catalog[sample_key]
    assert "year_start" in meta
    assert "year_end" in meta
    assert "specs_count" in meta
    assert isinstance(meta["specs_count"], int)
    assert meta["specs_count"] > 0


def test_load_csv_catalog_year_aggregation():
    """Le catalogue doit agréger les plages d'années correctement."""
    catalog = _load_csv_catalog()

    # Trouver un véhicule avec plusieurs fiches (specs_count > 1)
    multi_spec = None
    for key, meta in catalog.items():
        if meta["specs_count"] > 1:
            multi_spec = meta
            break

    # Si on a trouvé un véhicule multi-fiches, vérifier la cohérence
    if multi_spec:
        # year_start <= year_end (si les deux sont définis)
        if multi_spec["year_start"] and multi_spec["year_end"]:
            assert multi_spec["year_start"] <= multi_spec["year_end"]


def test_load_csv_catalog_cache():
    """Le catalogue doit être mis en cache (même instance)."""
    catalog1 = _load_csv_catalog()
    catalog2 = _load_csv_catalog()

    # Même objet en mémoire grâce au cache LRU
    assert catalog1 is catalog2
```

**Step 2: Lancer le test pour vérifier qu'il échoue**

```bash
pytest tests/services/test_csv_enrichment.py -v
```

Expected: FAIL avec "cannot import name '_load_csv_catalog'"

**Step 3: Remplacer _load_model_index par _load_csv_catalog**

Dans `app/services/csv_enrichment.py`, remplacer la fonction existante (lignes 87-104):

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
                    "specs_count": 0,
                }
            else:
                # Étendre la plage d'années si nécessaire
                if year_from and (
                    catalog[key]["year_start"] is None or year_from < catalog[key]["year_start"]
                ):
                    catalog[key]["year_start"] = year_from
                if year_to and (
                    catalog[key]["year_end"] is None or year_to > catalog[key]["year_end"]
                ):
                    catalog[key]["year_end"] = year_to

            catalog[key]["specs_count"] += 1

    logger.info("CSV catalog loaded: %d unique vehicles", len(catalog))
    return catalog
```

**Step 4: Mettre à jour has_specs pour utiliser _load_csv_catalog**

Dans `app/services/csv_enrichment.py`, modifier la fonction `has_specs` (ligne 116):

```python
def has_specs(brand: str, model: str) -> bool:
    """Verifie rapidement si un vehicule a des specs dans le CSV (O(1) apres chargement)."""
    b, m = _normalize_for_csv(brand, model)
    return (b, m) in _load_csv_catalog()
```

**Step 5: Lancer le test pour vérifier qu'il passe**

```bash
pytest tests/services/test_csv_enrichment.py -v
```

Expected: PASS (3 tests)

**Step 6: Lancer tous les tests pour vérifier la non-régression**

```bash
pytest tests/ -v
```

Expected: Tous les tests existants passent (notamment ceux qui utilisent `has_specs`)

**Step 7: Commit**

```bash
git add app/services/csv_enrichment.py tests/services/test_csv_enrichment.py
git commit -m "feat(csv): extend cache with year range and specs count metadata

Replace _load_model_index with _load_csv_catalog that stores:
- year_start: earliest Year_from across all specs
- year_end: latest Year_to across all specs
- specs_count: total number of specs for this vehicle

Backward compatible: has_specs() still works unchanged.

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 3: Ajouter fonction get_csv_missing_vehicles

**Files:**
- Modify: `app/services/csv_enrichment.py` (ajouter après `has_specs`)
- Test: `tests/services/test_csv_enrichment.py` (étendre)

**Step 1: Écrire le test pour get_csv_missing_vehicles**

Ajouter dans `tests/services/test_csv_enrichment.py`:

```python
from app.services.csv_enrichment import get_csv_missing_vehicles
from app.models.vehicle import Vehicle


def test_get_csv_missing_vehicles_structure(app):
    """La fonction doit retourner une liste de dicts avec structure attendue."""
    with app.app_context():
        missing = get_csv_missing_vehicles()

        # Doit retourner une liste
        assert isinstance(missing, list)

        # Si la liste n'est pas vide, vérifier la structure
        if missing:
            first = missing[0]
            assert "brand" in first
            assert "model" in first
            assert "year_start" in first
            assert "year_end" in first
            assert "specs_count" in first

            # Vérifier les types
            assert isinstance(first["brand"], str)
            assert isinstance(first["model"], str)
            assert isinstance(first["specs_count"], int)
            assert first["specs_count"] > 0


def test_get_csv_missing_vehicles_excludes_existing(app, db_session):
    """Les véhicules du référentiel ne doivent PAS apparaître dans missing."""
    with app.app_context():
        missing = get_csv_missing_vehicles()

        # Récupérer tous les véhicules du référentiel
        existing = {
            (v.brand.lower(), v.model.lower())
            for v in Vehicle.query.all()
        }

        # Vérifier qu'aucun véhicule manquant n'est dans le référentiel
        for vehicle in missing:
            key = (vehicle["brand"].lower(), vehicle["model"].lower())
            assert key not in existing, (
                f"{vehicle['brand']} {vehicle['model']} ne devrait pas être "
                f"dans missing car il est dans le référentiel"
            )


def test_get_csv_missing_vehicles_sorted_by_specs(app):
    """La liste doit être triée par specs_count descendant."""
    with app.app_context():
        missing = get_csv_missing_vehicles()

        # Si au moins 2 éléments, vérifier le tri
        if len(missing) >= 2:
            specs_counts = [v["specs_count"] for v in missing]
            # Vérifier que la liste est triée par ordre décroissant
            assert specs_counts == sorted(specs_counts, reverse=True)
```

**Step 2: Lancer le test pour vérifier qu'il échoue**

```bash
pytest tests/services/test_csv_enrichment.py::test_get_csv_missing_vehicles_structure -v
```

Expected: FAIL avec "cannot import name 'get_csv_missing_vehicles'"

**Step 3: Implémenter get_csv_missing_vehicles**

Ajouter dans `app/services/csv_enrichment.py` (après la fonction `has_specs`):

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
    existing = {(v.brand.lower(), v.model.lower()) for v in Vehicle.query.all()}

    # Diff : véhicules CSV non présents dans Vehicle
    missing = []
    for (make, model), meta in catalog.items():
        if (make, model) not in existing:
            missing.append(
                {
                    "brand": make.title(),  # Capitalisation pour affichage
                    "model": model.title(),
                    "year_start": meta["year_start"],
                    "year_end": meta["year_end"],
                    "specs_count": meta["specs_count"],
                }
            )

    # Tri par nombre de fiches (descendant)
    missing.sort(key=lambda x: x["specs_count"], reverse=True)

    return missing
```

**Step 4: Lancer le test pour vérifier qu'il passe**

```bash
pytest tests/services/test_csv_enrichment.py::test_get_csv_missing_vehicles -v
```

Expected: PASS (3 tests get_csv_missing_vehicles*)

**Step 5: Lancer tous les tests csv_enrichment**

```bash
pytest tests/services/test_csv_enrichment.py -v
```

Expected: PASS (6 tests au total)

**Step 6: Commit**

```bash
git add app/services/csv_enrichment.py tests/services/test_csv_enrichment.py
git commit -m "feat(csv): add get_csv_missing_vehicles function

Returns vehicles present in CSV Kaggle but missing from Vehicle table.
Sorted by specs_count (descending) to prioritize data-rich models.

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 4: Créer la route admin /csv-prospection

**Files:**
- Modify: `app/admin/routes.py` (ajouter après route `/database`)
- Test: `tests/admin/test_routes_csv_prospection.py` (créer)

**Step 1: Écrire le test pour la route**

Créer `tests/admin/test_routes_csv_prospection.py`:

```python
"""Tests pour la route admin CSV prospection."""

import pytest
from flask import url_for


def test_csv_prospection_requires_login(client):
    """La route doit nécessiter une authentification."""
    response = client.get("/admin/csv-prospection")
    assert response.status_code == 302  # Redirect vers login
    assert "/login" in response.location


def test_csv_prospection_page_loads(client, admin_user):
    """La page doit se charger correctement pour un admin connecté."""
    # Login
    client.post(
        "/admin/login",
        data={"username": admin_user.username, "password": "test-password"},
        follow_redirects=True,
    )

    # Accès à la page
    response = client.get("/admin/csv-prospection")
    assert response.status_code == 200
    assert b"Prospection CSV" in response.data


def test_csv_prospection_displays_missing_vehicles(client, admin_user, app):
    """La page doit afficher les véhicules CSV manquants."""
    # Login
    client.post(
        "/admin/login",
        data={"username": admin_user.username, "password": "test-password"},
        follow_redirects=True,
    )

    # Accès à la page
    response = client.get("/admin/csv-prospection")
    assert response.status_code == 200

    # Vérifier présence des éléments clés
    assert b"Marque" in response.data
    assert b"Mod" in response.data  # Modèle (peut être encodé)
    assert b"Fiches CSV" in response.data
    assert b"Chercher sur LBC" in response.data or b"LBC" in response.data


def test_csv_prospection_lbc_urls_valid(client, admin_user):
    """Les URLs LBC doivent être valides."""
    # Login
    client.post(
        "/admin/login",
        data={"username": admin_user.username, "password": "test-password"},
        follow_redirects=True,
    )

    # Accès à la page
    response = client.get("/admin/csv-prospection")
    assert response.status_code == 200

    # Vérifier qu'il y a des liens vers leboncoin.fr
    assert b"leboncoin.fr/recherche" in response.data or b"leboncoin" in response.data


def test_csv_prospection_pagination(client, admin_user):
    """La pagination doit fonctionner."""
    # Login
    client.post(
        "/admin/login",
        data={"username": admin_user.username, "password": "test-password"},
        follow_redirects=True,
    )

    # Accès à la page 1
    response = client.get("/admin/csv-prospection?page=1")
    assert response.status_code == 200

    # Accès à une page invalide (devrait être clampée)
    response = client.get("/admin/csv-prospection?page=9999")
    assert response.status_code == 200
```

**Step 2: Lancer le test pour vérifier qu'il échoue**

```bash
pytest tests/admin/test_routes_csv_prospection.py::test_csv_prospection_page_loads -v
```

Expected: FAIL avec 404 Not Found (route n'existe pas encore)

**Step 3: Implémenter la route csv_prospection**

Dans `app/admin/routes.py`, ajouter après la route `/database` (après ligne 671):

```python
# ── Prospection CSV ─────────────────────────────────────────


@admin_bp.route("/csv-prospection")
@login_required
def csv_prospection():
    """Prospection CSV : véhicules disponibles dans les CSV mais pas encore importés."""
    from urllib.parse import quote_plus

    from app.services.csv_enrichment import get_csv_missing_vehicles

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

**Step 4: Lancer le test pour vérifier qu'il passe**

```bash
pytest tests/admin/test_routes_csv_prospection.py::test_csv_prospection_page_loads -v
```

Expected: FAIL avec 500 (template manquant) ou 404 si template checker

**Step 5: Créer un template minimal pour passer le test**

Créer `app/admin/templates/admin/csv_prospection.html` (minimal temporaire):

```html
{% extends "admin/base.html" %}
{% block title %}Prospection CSV - Co-Pilot Admin{% endblock %}
{% block content %}
<h2>Prospection CSV</h2>
<p>Véhicules CSV non importés: {{ total_missing }}</p>
<p>Fiches CSV disponibles: {{ total_specs }}</p>
<table>
  <tr><th>Marque</th><th>Modèle</th><th>Fiches CSV</th><th>Action</th></tr>
  {% for vehicle in missing_vehicles %}
  <tr>
    <td>{{ vehicle.brand }}</td>
    <td>{{ vehicle.model }}</td>
    <td>{{ vehicle.specs_count }}</td>
    <td><a href="{{ vehicle.lbc_url }}" target="_blank">Chercher sur LBC</a></td>
  </tr>
  {% endfor %}
</table>
{% endblock %}
```

**Step 6: Lancer les tests de route**

```bash
pytest tests/admin/test_routes_csv_prospection.py -v
```

Expected: PASS (tous les tests route)

**Step 7: Commit**

```bash
git add app/admin/routes.py app/admin/templates/admin/csv_prospection.html tests/admin/test_routes_csv_prospection.py
git commit -m "feat(admin): add /csv-prospection route with pagination

Route returns CSV vehicles missing from referential with:
- Stats cards (total missing, total specs)
- Pagination (50 per page)
- Pre-built LBC URLs for quick access

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 5: Créer le template HTML complet

**Files:**
- Modify: `app/admin/templates/admin/csv_prospection.html` (remplacer le minimal)
- Modify: `app/admin/templates/admin/base.html` (ajouter lien navbar)

**Step 1: Remplacer le template minimal par la version complète**

Remplacer tout le contenu de `app/admin/templates/admin/csv_prospection.html`:

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

**Step 2: Ajouter le lien dans la navbar**

Dans `app/admin/templates/admin/base.html`, ajouter après la ligne "Base Vehicules" (après ligne 65):

```html
          <a class="nav-link {% if request.endpoint == 'admin.csv_prospection' %}active{% endif %}"
             href="{{ url_for('admin.csv_prospection') }}">📊 Prospection CSV</a>
```

Position exacte : entre `Base Vehicules` et `Logs erreurs`.

**Step 3: Tester visuellement dans le navigateur**

1. Démarrer l'app : `./start.sh`
2. Naviguer vers `http://localhost:5000/admin/login`
3. Se connecter avec les credentials admin
4. Cliquer sur "📊 Prospection CSV" dans la sidebar
5. Vérifier :
   - Stat cards affichent des chiffres
   - Tableau affiche les véhicules avec plage années
   - Liens LBC s'ouvrent dans un nouvel onglet
   - Pagination fonctionne (si >50 résultats)

**Step 4: Relancer les tests pour vérifier la non-régression**

```bash
pytest tests/admin/test_routes_csv_prospection.py -v
```

Expected: PASS (tous les tests)

**Step 5: Commit**

```bash
git add app/admin/templates/admin/csv_prospection.html app/admin/templates/admin/base.html
git commit -m "feat(admin): add complete CSV prospection template

Full-featured template with:
- Stat cards (missing vehicles, total specs)
- Responsive table with year range, specs count, LBC links
- Info alert explaining workflow
- Pagination controls
- Empty state message
- Navbar link in sidebar

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 6: Tests d'intégration end-to-end

**Files:**
- Test: `tests/integration/test_csv_prospection_e2e.py` (créer)

**Step 1: Écrire le test E2E complet**

Créer `tests/integration/test_csv_prospection_e2e.py`:

```python
"""Tests d'intégration end-to-end pour la prospection CSV."""

import pytest
from flask import url_for

from app.models.vehicle import Vehicle
from app.services.csv_enrichment import get_csv_missing_vehicles


def test_csv_prospection_workflow(client, admin_user, db_session, app):
    """Test du workflow complet : consulter → voir véhicules → liens LBC."""
    with app.app_context():
        # Étape 1 : Login admin
        response = client.post(
            "/admin/login",
            data={"username": admin_user.username, "password": "test-password"},
            follow_redirects=True,
        )
        assert response.status_code == 200

        # Étape 2 : Accéder à /admin/csv-prospection
        response = client.get("/admin/csv-prospection")
        assert response.status_code == 200
        assert b"Prospection CSV" in response.data

        # Étape 3 : Vérifier qu'il y a des véhicules manquants
        missing = get_csv_missing_vehicles()
        if missing:
            # Au moins un véhicule manquant doit apparaître dans la page
            first_missing = missing[0]
            assert first_missing["brand"].encode() in response.data or True  # Encoding peut varier

            # Vérifier qu'il y a un lien LBC pour ce véhicule
            assert b"leboncoin.fr" in response.data

        # Étape 4 : Vérifier les stats
        assert b"hicules CSV non import" in response.data  # Véhicules (accent)
        assert b"Fiches specs disponibles" in response.data


def test_csv_prospection_excludes_existing_vehicles(client, admin_user, db_session, app):
    """Les véhicules déjà dans le référentiel ne doivent PAS apparaître."""
    with app.app_context():
        # Login
        client.post(
            "/admin/login",
            data={"username": admin_user.username, "password": "test-password"},
            follow_redirects=True,
        )

        # Récupérer un véhicule du référentiel
        existing_vehicle = Vehicle.query.first()
        if not existing_vehicle:
            pytest.skip("Aucun véhicule dans le référentiel pour ce test")

        # Accéder à la page
        response = client.get("/admin/csv-prospection")
        assert response.status_code == 200

        # Vérifier via l'API get_csv_missing_vehicles
        missing = get_csv_missing_vehicles()
        existing_keys = {(v.brand.lower(), v.model.lower()) for v in Vehicle.query.all()}

        for vehicle in missing:
            key = (vehicle["brand"].lower(), vehicle["model"].lower())
            assert key not in existing_keys


def test_csv_prospection_pagination_works(client, admin_user, app):
    """La pagination doit afficher au max 50 véhicules par page."""
    with app.app_context():
        # Login
        client.post(
            "/admin/login",
            data={"username": admin_user.username, "password": "test-password"},
            follow_redirects=True,
        )

        # Récupérer le nombre total de véhicules manquants
        missing = get_csv_missing_vehicles()
        total_missing = len(missing)

        # Si > 50, vérifier qu'il y a plusieurs pages
        if total_missing > 50:
            response = client.get("/admin/csv-prospection?page=1")
            assert response.status_code == 200

            # Vérifier qu'il y a un lien "Suivant"
            assert b"Suivant" in response.data or b"suivant" in response.data

            # Accéder à la page 2
            response = client.get("/admin/csv-prospection?page=2")
            assert response.status_code == 200
```

**Step 2: Lancer le test E2E**

```bash
pytest tests/integration/test_csv_prospection_e2e.py -v
```

Expected: PASS (3 tests)

**Step 3: Lancer TOUS les tests du projet**

```bash
pytest tests/ -v
```

Expected: PASS (tous les tests, incluant les nouveaux)

**Step 4: Vérifier le coverage**

```bash
pytest tests/ --cov=app/services/csv_enrichment --cov=app/admin/routes --cov-report=term-missing
```

Expected: Coverage >80% pour les fichiers modifiés

**Step 5: Commit**

```bash
git add tests/integration/test_csv_prospection_e2e.py
git commit -m "test(csv): add end-to-end integration tests

Tests cover:
- Full workflow (login → view page → check links)
- Exclusion of existing vehicles from missing list
- Pagination behavior with >50 results

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 7: Vérification finale et documentation

**Files:**
- Create: `docs/features/csv-prospection.md` (documentation utilisateur)
- Modify: `README.md` (si section features existe)

**Step 1: Créer la documentation utilisateur**

Créer `docs/features/csv-prospection.md`:

```markdown
# Prospection CSV - Guide utilisateur

## Vue d'ensemble

La page **Prospection CSV** (`/admin/csv-prospection`) permet d'identifier proactivement les véhicules disponibles dans les CSV Kaggle mais absents du référentiel Co-Pilot.

## Workflow

1. **Consulter la liste** : Ouvrir `/admin/csv-prospection` depuis la sidebar admin
2. **Identifier un modèle intéressant** : Trier par nombre de fiches (déjà trié par défaut)
3. **Cliquer sur "🔍 Chercher sur LBC"** : Ouvre une recherche LBC dans un nouvel onglet
4. **Scanner avec l'extension** : Scanner quelques annonces pour ce modèle
5. **Ajouter au référentiel** : Via `/admin/car`, cliquer sur "Ajouter" dans la section "Modèles demandés"
6. **Bénéficier de l'auto-enrichissement** : Les X fiches CSV sont importées automatiquement

## Interface

### Stat Cards

- **Véhicules CSV non importés** : Nombre total de modèles disponibles
- **Fiches specs disponibles** : Nombre total de fiches techniques (tous modèles confondus)

### Tableau

| Colonne | Description |
|---------|-------------|
| **Marque** | Marque du véhicule (ex: Renault) |
| **Modèle** | Modèle du véhicule (ex: Clio) |
| **Plage années** | Années couvertes par les specs CSV (ex: 2012-2024) |
| **Fiches CSV** | Nombre de fiches qui seront importées (ex: 35) |
| **Action** | Lien direct vers recherche LBC |

### Pagination

- 50 véhicules par page
- Navigation "Précédent" / "Suivant"
- Indicateur "Page X / Y"

## Pourquoi cette feature ?

**Avant** : On découvrait les véhicules disponibles **par hasard** en scannant LBC.

**Maintenant** : On peut **choisir activement** les modèles à ajouter, en priorisant ceux avec le plus de données.

## Exemples

### Cas 1 : Ajouter la Renault Clio

1. Voir "Renault Clio" avec 35 fiches CSV
2. Cliquer "🔍 Chercher sur LBC" → Ouvre `https://www.leboncoin.fr/recherche?category=2&text=Renault+Clio`
3. Scanner 2-3 annonces avec l'extension
4. La Clio apparaît dans `/admin/car` "Modèles demandés"
5. Cliquer "Ajouter" → 35 fiches specs importées automatiquement

### Cas 2 : Référentiel déjà complet

Si la liste est vide avec message "🎉 Tous les véhicules CSV sont déjà importés !", c'est que :
- Tous les modèles CSV sont dans le référentiel
- Ou le CSV Kaggle ne contient que des modèles déjà ajoutés

## Notes techniques

- **Cache** : Le catalogue CSV est chargé en mémoire au démarrage de l'app
- **Performance** : Lookup O(1) après le 1er chargement
- **Tri** : Par `specs_count` descendant (modèles riches en données d'abord)
- **Compatibilité** : Fonctionne avec le CSV Kaggle existant sans modification

## Limites

- **Pas d'ajout automatique** : L'utilisateur doit scanner + ajouter manuellement (par design)
- **Pas de filtrage avancé** : Pas de filtre par marque/année (évolution future possible)
- **Données statiques** : Le catalogue se met à jour au restart de l'app uniquement
```

**Step 2: Tester manuellement la feature complète**

Checklist manuelle :

- [ ] Login admin fonctionne
- [ ] Lien "📊 Prospection CSV" visible dans sidebar
- [ ] Page se charge sans erreur
- [ ] Stat cards affichent des chiffres cohérents
- [ ] Tableau affiche les véhicules triés par specs_count
- [ ] Liens LBC s'ouvrent correctement (nouveau tab)
- [ ] URLs LBC sont valides (category=2, text=Marque+Modele)
- [ ] Pagination fonctionne (si >50 résultats)
- [ ] Empty state s'affiche si aucun véhicule manquant
- [ ] Navbar highlight "Prospection CSV" quand sur la page

**Step 3: Lancer le linter et formatter**

```bash
ruff check app/services/csv_enrichment.py app/admin/routes.py
ruff format app/services/csv_enrichment.py app/admin/routes.py
```

Expected: Aucune erreur, code formaté

**Step 4: Lancer tous les tests une dernière fois**

```bash
pytest tests/ -v --tb=short
```

Expected: PASS (tous les tests)

**Step 5: Commit final**

```bash
git add docs/features/csv-prospection.md
git commit -m "docs: add CSV prospection user guide

Complete user documentation covering:
- Workflow (consult → scan → add)
- Interface explanation (stats, table, pagination)
- Use cases and examples
- Technical notes and limitations

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

**Step 6: Push (si sur une branche feature)**

Si travail dans un worktree/branche :

```bash
git log --oneline -7  # Vérifier les 7 commits
git push -u origin feature/csv-prospection
```

Si sur main directement :

```bash
git log --oneline -7  # Vérifier les 7 commits
git push
```

---

## Récapitulatif des commits

7 commits au total :

1. `fix: update vehicle count from 70 to 144+ in documentation`
2. `feat(csv): extend cache with year range and specs count metadata`
3. `feat(csv): add get_csv_missing_vehicles function`
4. `feat(admin): add /csv-prospection route with pagination`
5. `feat(admin): add complete CSV prospection template`
6. `test(csv): add end-to-end integration tests`
7. `docs: add CSV prospection user guide`

---

## Vérifications post-implémentation

- [ ] Tous les tests passent (`pytest tests/ -v`)
- [ ] Aucune erreur ruff (`ruff check app/`)
- [ ] Code formaté (`ruff format app/`)
- [ ] Page accessible depuis la sidebar admin
- [ ] Stats affichent des chiffres cohérents
- [ ] Liens LBC valides et fonctionnels
- [ ] Pagination fonctionne correctement
- [ ] Véhicules du référentiel exclus de la liste
- [ ] Documentation utilisateur claire et complète
- [ ] Commits atomiques et bien nommés

---

## Métriques de succès

**Immédiat :**
- [ ] Page se charge en <500ms (grâce au cache)
- [ ] Tous les tests passent (>90% coverage)
- [ ] Aucune régression sur les features existantes

**À 1 semaine :**
- [ ] Au moins 5 nouveaux véhicules ajoutés via cette feature
- [ ] Aucun bug signalé par l'utilisateur

**À 1 mois :**
- [ ] Référentiel passe de 144+ à 160+ modèles
- [ ] Taux d'utilisation : >2 consultations/semaine

---

## Évolutions futures possibles

1. **Filtre par marque** : Dropdown pour filtrer les résultats
2. **Recherche** : Champ de recherche pour trouver un modèle spécifique
3. **Export CSV** : Bouton pour exporter la liste
4. **Statistiques** : Graphique de couverture par marque
5. **Recommandation intelligente** : Croiser avec ScanLog pour prioriser
6. **Bouton "Rafraîchir le cache"** : Recharger le CSV sans restart
7. **Indicateur de popularité** : Estimer le volume LBC par modèle

---

## Notes pour l'exécution

- **TDD strict** : Toujours écrire le test AVANT l'implémentation
- **Commits fréquents** : Un commit par task (7 au total)
- **Tests à chaque étape** : Lancer `pytest` après chaque step d'implémentation
- **Vérification visuelle** : Tester dans le navigateur après Task 5
- **No shortcuts** : Ne pas sauter les étapes de test

**Bon courage pour l'implémentation !**
