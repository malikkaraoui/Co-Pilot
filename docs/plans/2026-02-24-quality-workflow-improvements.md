# Quality Workflow Improvements

## Objectif
Garantir la qualité du code **avant le push**, réduire les échecs CI, et documenter les bonnes pratiques.

---

## 1. Pre-commit hooks renforcés

### Actuellement
```yaml
- ruff (lint + fix)
- ruff-format
- pytest tests/ -x -q --tb=short  # Stop à la 1ère erreur
```

### Proposé
```yaml
repos:
  # Ruff (lint + format)
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.11.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  # Pytest avec cache et coverage minimum
  - repo: local
    hooks:
      - id: pytest-quick
        name: pytest (changed + failed)
        entry: python -m pytest --lf --co -q
        language: system
        pass_filenames: false
        always_run: true
        stages: [pre-commit]

      - id: pytest-full
        name: pytest (all tests)
        entry: python -m pytest tests/ -x -q --tb=short --cov=app --cov-report=term-missing:skip-covered --cov-fail-under=70
        language: system
        pass_filenames: false
        always_run: true
        stages: [pre-commit]

  # Security check
  - repo: https://github.com/PyCQA/bandit
    rev: 1.7.10
    hooks:
      - id: bandit
        args: [-r, app/, -ll]  # Low severity + low confidence minimum

  # Type checking (optionnel, peut être activé progressivement)
  # - repo: https://github.com/pre-commit/mirrors-mypy
  #   rev: v1.11.1
  #   hooks:
  #     - id: mypy
  #       args: [--ignore-missing-imports, --strict-optional]
```

**Bénéfices** :
- Coverage minimum 70% obligatoire
- Bandit détecte SQL injection, hardcoded secrets, etc.
- `--lf` (last failed) = fast feedback sur les tests qui échouaient

---

## 2. Pre-push hook (validation complète)

### Créer `.git/hooks/pre-push`
```bash
#!/bin/bash
# Pre-push hook : validation complète avant push

echo "🔍 Running pre-push validation..."

# 1. Tous les tests doivent passer
echo "📋 Running full test suite..."
python -m pytest tests/ --tb=short -v --cov=app --cov-report=term-missing:skip-covered --cov-fail-under=70
if [ $? -ne 0 ]; then
    echo "❌ Tests failed. Push aborted."
    exit 1
fi

# 2. Ruff doit être clean
echo "🔧 Checking code style..."
ruff check .
if [ $? -ne 0 ]; then
    echo "❌ Ruff checks failed. Push aborted."
    exit 1
fi

# 3. Pas de print() ou breakpoint() dans app/
echo "🔍 Checking for debug statements..."
if grep -rn "print(" app/ --include="*.py" | grep -v "# noqa: T201"; then
    echo "⚠️  Warning: print() statements found in app/"
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

if grep -rn "breakpoint()" app/ --include="*.py"; then
    echo "❌ breakpoint() found in app/. Push aborted."
    exit 1
fi

echo "✅ Pre-push validation passed!"
```

**Installation** :
```bash
chmod +x .git/hooks/pre-push
```

**Alternative Git worktree-safe** : Ajouter dans `.pre-commit-config.yaml` avec `stages: [pre-push]`

---

## 3. Fixtures de cleanup automatiques

### Problème actuel
Tests qui login doivent manuellement logout → oublis fréquents → pollution

### Solution : Fixture autouse

**tests/conftest.py**
```python
@pytest.fixture(autouse=True)
def _auto_logout_after_test(client):
    """Logout automatique après chaque test qui utilise client.

    Prévient la pollution de session Flask-Login entre tests.
    """
    yield
    # Cleanup : logout si une session existe
    try:
        client.get("/admin/logout", follow_redirects=False)
    except Exception:
        pass  # Si pas de session, pas grave
```

**Bénéfice** : Plus besoin de `client.get("/admin/logout")` manuel

---

## 4. Guidelines de test (documentation)

### Créer `docs/testing-guidelines.md`

```markdown
# Testing Guidelines

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

### 3. Cleanup
- ✅ Fixture `_auto_logout_after_test` nettoie automatiquement
- ✅ Si test crée des fichiers temporaires : nettoyer dans finally
- ✅ Rollback DB automatique via fixture `db`

## Patterns à éviter

❌ **Test assumant données présentes**
```python
def test_csv_shows_vehicles(client):
    resp = client.get("/csv")
    assert b"Renault" in resp.data  # ❌ Échoue si CSV absent
```

✅ **Test résilient**
```python
def test_csv_shows_vehicles_or_empty(client):
    resp = client.get("/csv")
    has_data = b"Renault" in resp.data
    has_empty = b"Aucun véhicule" in resp.data
    assert has_data or has_empty  # ✅ Accepte les deux
```

## Checklist avant PR

- [ ] Tous les tests passent localement : `pytest tests/`
- [ ] Coverage >= 70% : `pytest --cov=app`
- [ ] Ruff clean : `ruff check .`
- [ ] Pas de `print()` ou `breakpoint()` dans `app/`
- [ ] Tests résilients à l'environnement CI
- [ ] Cleanup automatique (logout, temp files)
```

---

## 5. GitHub Actions améliorées

### `.github/workflows/test.yml`
```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ['3.12', '3.13']  # Matrix testing
      fail-fast: true  # Stop dès la 1ère erreur

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}

      - name: Cache dependencies
        uses: actions/cache@v4
        with:
          path: ~/.cache/pip
          key: ${{ runner.os }}-pip-${{ hashFiles('requirements.txt') }}

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run ruff
        run: ruff check .

      - name: Run tests with coverage
        run: |
          pytest tests/ --cov=app --cov-report=xml --cov-report=term-missing --cov-fail-under=70

      - name: Upload coverage to Codecov
        uses: codecov/codecov-action@v4
        with:
          file: ./coverage.xml
          fail_ci_if_error: true
```

**Bénéfices** :
- Matrix testing : détecte les incompatibilités Python 3.12/3.13
- Fail-fast : économise les minutes CI
- Coverage report : visibilité sur la qualité

---

## 6. Makefile pour standardiser les commandes

### `Makefile`
```makefile
.PHONY: test lint format check pre-push install

install:
	pip install -r requirements.txt
	pre-commit install --hook-type pre-commit --hook-type pre-push

test:
	pytest tests/ -v

test-quick:
	pytest tests/ -x --lf -v  # Stop à la 1ère erreur, rejoue les failed

test-cov:
	pytest tests/ --cov=app --cov-report=html --cov-report=term-missing --cov-fail-under=70
	@echo "Coverage report: htmlcov/index.html"

lint:
	ruff check .

format:
	ruff format .

check: lint test-cov
	@echo "✅ All checks passed!"

pre-push: check
	@echo "✅ Ready to push!"

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache htmlcov .coverage
```

**Usage** :
```bash
make install      # Setup projet
make test-quick   # Rapide (failed tests)
make check        # Validation complète
make pre-push     # Avant git push
```

---

## 7. Implémentation progressive

### Phase 1 (Immédiat) ✅
- [x] Ajouter fixture `_auto_logout_after_test` dans conftest.py
- [x] Créer `docs/testing-guidelines.md`
- [ ] Créer `Makefile`

### Phase 2 (Cette semaine)
- [ ] Ajouter pre-push hook
- [ ] Activer bandit dans pre-commit
- [ ] Augmenter coverage à 70%

### Phase 3 (Optionnel)
- [ ] Ajouter mypy (type checking)
- [ ] Matrix testing dans GitHub Actions
- [ ] Badge coverage dans README

---

## Résumé des bénéfices

| Avant | Après |
|-------|-------|
| Échecs découverts en CI (5-10 min) | Échecs bloqués en local (<1 min) |
| Tests fragiles (CI vs local) | Tests résilients à l'environnement |
| Cleanup manuel → oublis | Cleanup automatique |
| Pas de métriques qualité | Coverage 70% minimum |
| Workflow ad-hoc | `make check` standardisé |

**ROI** : ~15 min d'implémentation → économie de 2-3h par semaine d'échecs CI évitables
