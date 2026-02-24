# Testing Guidelines - Co-Pilot

## Règles générales

### 1. Isolation des tests
- ✅ Chaque test doit être **indépendant**
- ❌ Ne jamais assumer qu'un test s'exécute avant un autre
- ✅ Utiliser `with client:` pour isolation de requêtes
- ✅ Utiliser `with app.app_context():` pour accès DB

### 2. Resilience à l'environnement
- ✅ Accepter les cas CI (CSV absent, données limitées)
- ✅ Utiliser `pytest.skip()` si données manquantes
- ✅ Asserts conditionnels : `if data: assert ...`

**Exemple** :
```python
# ❌ Fragile
def test_csv_shows_vehicles(client):
    resp = client.get("/csv")
    assert b"Renault" in resp.data  # Échoue si CSV absent en CI

# ✅ Résilient
def test_csv_shows_vehicles_or_empty(client):
    resp = client.get("/csv")
    has_data = b"Renault" in resp.data
    has_empty = b"Aucun véhicule" in resp.data
    assert has_data or has_empty  # Accepte les deux
```

### 3. Cleanup automatique
- ✅ Fixture `_auto_logout_after_test` nettoie les sessions Flask-Login automatiquement
- ✅ Plus besoin de `client.get("/admin/logout")` manuel (mais ok si présent)
- ✅ Rollback DB automatique via fixture `db`

---

## Patterns à suivre

### Tests API
```python
def test_api_endpoint(client):
    """Format standard pour tests API."""
    # Arrange
    data = {"key": "value"}

    # Act
    response = client.post("/api/endpoint", json=data)

    # Assert
    assert response.status_code == 200
    result = response.get_json()
    assert result["success"] is True
    assert "data" in result
```

### Tests admin avec auth
```python
def test_admin_page(client, admin_user):
    """Les fixtures client + admin_user suffisent."""
    with client:
        # Login
        client.post("/admin/login", data={
            "username": "testuser",
            "password": "testpass"
        })

        # Test
        response = client.get("/admin/dashboard")
        assert response.status_code == 200

        # Pas besoin de logout manuel → fixture _auto_logout_after_test
```

### Tests avec DB
```python
def test_model_creation(app, db):
    """Utiliser app.app_context() pour DB access."""
    with app.app_context():
        vehicle = Vehicle(brand="Renault", model="Clio")
        db.session.add(vehicle)
        db.session.commit()

        # Query
        found = Vehicle.query.filter_by(brand="Renault").first()
        assert found is not None
        assert found.model == "Clio"

    # Rollback automatique après le test
```

---

## Anti-patterns à éviter

### ❌ Assumer l'ordre des tests
```python
# ❌ Mauvais : dépend d'un autre test
def test_step_2_uses_data_from_step_1(client):
    vehicle = Vehicle.query.first()  # Assume qu'un test précédent l'a créé
    assert vehicle is not None
```

### ❌ Hardcoder des données spécifiques
```python
# ❌ Mauvais : assume que le CSV contient "Renault Clio"
def test_csv_has_clio(client):
    catalog = _load_csv_catalog()
    assert ("renault", "clio") in catalog

# ✅ Bon : test la structure, pas les données
def test_csv_structure(client):
    catalog = _load_csv_catalog()
    if len(catalog) > 0:
        key = next(iter(catalog.keys()))
        assert isinstance(key, tuple)
        assert len(key) == 2
```

### ❌ Tests non atomiques
```python
# ❌ Mauvais : test multiple choses
def test_everything(client):
    assert 1 + 1 == 2
    resp = client.get("/")
    assert resp.status_code == 200
    vehicle = Vehicle(brand="X")
    assert vehicle.brand == "X"

# ✅ Bon : un test = une assertion logique
def test_addition():
    assert 1 + 1 == 2

def test_home_page_loads(client):
    resp = client.get("/")
    assert resp.status_code == 200

def test_vehicle_creation():
    vehicle = Vehicle(brand="X")
    assert vehicle.brand == "X"
```

---

## Checklist avant commit/PR

### Avant commit
- [ ] `make test-quick` passe (tests modifiés)
- [ ] `ruff check .` clean
- [ ] Pas de `print()` ou `breakpoint()` dans `app/`

### Avant push
- [ ] `make check` passe (tests complets + coverage)
- [ ] Tests résilients à l'environnement CI
- [ ] Docstrings à jour

### Avant PR
- [ ] Description claire du changement
- [ ] Tests E2E pour features utilisateur
- [ ] Coverage >= 70% maintenu
- [ ] CI GitHub Actions verte

---

## Commandes utiles

```bash
# Tests rapides (failed + changed)
make test-quick

# Tests complets
make test

# Tests avec coverage
make test-cov

# Validation complète (lint + tests + coverage)
make check

# Avant push
make pre-push

# Nettoyer les caches
make clean
```

---

## Debugging tests

### Test spécifique
```bash
pytest tests/test_admin/test_admin.py::TestLogin::test_login_success -v
```

### Avec output détaillé
```bash
pytest tests/test_admin/test_admin.py -v -s  # -s = pas de capture output
```

### Rejouer les failed
```bash
pytest --lf -v  # last failed
pytest --lf --tb=short  # avec traceback court
```

### Avec debugger
```bash
pytest tests/test_admin/test_admin.py --pdb  # drop dans pdb si échec
```

---

## Ressources

- [pytest docs](https://docs.pytest.org/)
- [Flask testing](https://flask.palletsprojects.com/en/3.1.x/testing/)
- [Coverage.py](https://coverage.readthedocs.io/)
