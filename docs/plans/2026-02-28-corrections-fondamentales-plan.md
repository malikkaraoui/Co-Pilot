# Corrections Fondamentales Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Corriger 4 problemes fondamentaux : timezone admin, scoring neutral, tables separees LBC/AS24, refonte admin issues.

**Architecture:** Ordre du plus simple au plus complexe (quick wins d'abord). S3 timezone (templates), S2 scoring neutral (dataclass + service + 2 filtres), S1 tables separees (modeles, services, API, extension, migration), S4 admin issues (onglets par site).

**Tech Stack:** Python 3.12, Flask, SQLAlchemy 2.0, Jinja2, pytest, extension Chrome JS

---

## Task 1: Filtre Jinja `localdatetime` (S3)

**Files:**
- Modify: `app/__init__.py:94-96`
- Test: `tests/test_app_factory.py` (si existant, sinon inline)

**Step 1: Ajouter le filtre `localdatetime` apres le filtre `localtime` existant**

Dans `app/__init__.py`, apres la ligne 96, ajouter :

```python
@app.template_filter("localdatetime")
def localdatetime_filter(dt, fmt='%d/%m/%Y %H:%M'):
    """Convertit UTC → Paris et formate. Retourne '-' si None."""
    if dt is None:
        return '-'
    return _to_paris(dt).strftime(fmt)
```

**Step 2: Run tests**

Run: `pytest tests/ -x -q`
Expected: PASS (aucun test casse)

**Step 3: Commit**

```bash
git add app/__init__.py
git commit -m "feat: add localdatetime Jinja filter (UTC→Paris + format)"
```

---

## Task 2: Fix les 12 bugs timezone dans les templates (S3)

**Files:**
- Modify: `app/admin/templates/admin/issues.html:149`
- Modify: `app/admin/templates/admin/car.html:179,182`
- Modify: `app/admin/templates/admin/argus.html:509`
- Modify: `app/admin/templates/admin/email_detail.html:80`
- Modify: `app/admin/templates/admin/email_list.html:117`
- Modify: `app/admin/templates/admin/failed_search_detail.html:81,85,99`
- Modify: `app/admin/templates/admin/failed_searches.html:284,287`
- Modify: `app/admin/templates/admin/youtube_search.html:295`

**Step 1: Remplacer chaque `{{ x.strftime(...) }}` par `{{ x|localdatetime }}`**

Pattern a chercher et remplacer dans chaque fichier :

| Fichier | Ancien | Nouveau |
|---------|--------|---------|
| issues.html:149 | `{{ j.created_at.strftime('%d/%m/%Y %H:%M') if j.created_at else '-' }}` | `{{ j.created_at\|localdatetime }}` |
| car.html:179 | `{{ item.first_seen.strftime('%d/%m/%Y') if item.first_seen else '-' }}` | `{{ item.first_seen\|localdatetime('%d/%m/%Y') }}` |
| car.html:182 | `{{ item.last_seen.strftime('%d/%m/%Y') if item.last_seen else '-' }}` | `{{ item.last_seen\|localdatetime('%d/%m/%Y') }}` |
| argus.html:509 | `{{ a.collected_at.strftime('%d/%m/%Y') if a.collected_at else '-' }}` | `{{ a.collected_at\|localdatetime('%d/%m/%Y') }}` |
| email_detail.html:80 | `{{ draft.created_at.strftime('%d/%m/%Y %H:%M') }}` | `{{ draft.created_at\|localdatetime }}` |
| email_list.html:117 | `{{ d.created_at.strftime('%d/%m/%Y %H:%M') }}` | `{{ d.created_at\|localdatetime }}` |
| failed_search_detail.html:81 | `{{ first_seen.strftime('%d/%m/%Y %H:%M') if first_seen else '-' }}` | `{{ first_seen\|localdatetime }}` |
| failed_search_detail.html:85 | `{{ last_seen.strftime('%d/%m/%Y %H:%M') if last_seen else '-' }}` | `{{ last_seen\|localdatetime }}` |
| failed_search_detail.html:99 | `{{ rec.created_at.strftime('%d/%m/%Y %H:%M') if rec.created_at else '-' }}` | `{{ rec.created_at\|localdatetime }}` |
| failed_searches.html:284 | `{{ g.first_seen.strftime('%d/%m/%y') if g.first_seen else '-' }}` | `{{ g.first_seen\|localdatetime('%d/%m/%Y') }}` |
| failed_searches.html:287 | `{{ g.last_seen.strftime('%d/%m/%y %H:%M') if g.last_seen else '-' }}` | `{{ g.last_seen\|localdatetime }}` |
| youtube_search.html:295 | `{{ s.created_at.strftime('%d/%m/%Y %H:%M') }}` | `{{ s.created_at\|localdatetime }}` |

**Step 2: Migrer aussi les 9 usages corrects vers le nouveau filtre**

Chercher `(x|localtime).strftime(` dans les templates et remplacer par `x|localdatetime` (ou `x|localdatetime('format')` si format different du default).

Fichiers concernes : argus.html:119, dashboard.html:166,204, errors.html:41, pipelines.html:40,56,67, youtube.html:146, youtube_detail.html:112.

**Step 3: Run tests**

Run: `pytest tests/ -x -q`
Expected: PASS

**Step 4: Commit**

```bash
git add app/admin/templates/
git commit -m "fix: use localdatetime filter on all admin templates (12 UTC bugs + 9 migrations)"
```

---

## Task 3: Status `neutral` dans FilterResult (S2)

**Files:**
- Modify: `app/filters/base.py:17-33`
- Modify: `app/filters/base.py:56-68`
- Test: `tests/test_services/test_scoring.py`

**Step 1: Ecrire le test qui echoue pour le status neutral**

Dans `tests/test_services/test_scoring.py`, ajouter :

```python
def test_neutral_excluded_from_weight(self):
    """Neutral filters are excluded from both numerator AND denominator."""
    results = [
        FilterResult("L1", "pass", 1.0, "OK"),
        FilterResult("L2", "pass", 0.8, "OK"),
        FilterResult("L7", "neutral", 0.0, "Non applicable"),
    ]
    score, is_partial = calculate_score(results)
    # L7 neutral: exclu du calcul
    # Weighted: L1(1.0*1.0) + L2(2.0*0.8) = 2.6 / 3.0 = 87
    assert score == 87
    assert is_partial is True  # has neutral → partial

def test_neutral_vs_skip_difference(self):
    """Skip penalizes (0 in numerator, weight in denom), neutral does not."""
    results_skip = [
        FilterResult("L1", "pass", 1.0, "OK"),
        FilterResult("L7", "skip", 0.0, "Skipped"),
    ]
    results_neutral = [
        FilterResult("L1", "pass", 1.0, "OK"),
        FilterResult("L7", "neutral", 0.0, "Non applicable"),
    ]
    score_skip, _ = calculate_score(results_skip)
    score_neutral, _ = calculate_score(results_neutral)
    # Skip: 1.0 / 2.0 = 50
    # Neutral: 1.0 / 1.0 = 100
    assert score_skip == 50
    assert score_neutral == 100

def test_private_seller_neutral_high_score(self):
    """Vendeur prive avec L6+L7 neutral doit scorer >= 90."""
    results = [
        FilterResult("L1", "warning", 0.8, "Infos manquantes"),
        FilterResult("L2", "pass", 1.0, "Reconnu"),
        FilterResult("L3", "pass", 1.0, "Coherent"),
        FilterResult("L4", "pass", 1.0, "Prix ok"),
        FilterResult("L5", "pass", 1.0, "Stats ok"),
        FilterResult("L6", "neutral", 0.0, "Particulier sans tel"),
        FilterResult("L7", "neutral", 0.0, "Vendeur particulier"),
        FilterResult("L8", "pass", 1.0, "Pas d'import"),
        FilterResult("L9", "warning", 0.75, "Pas de telephone"),
    ]
    score, is_partial = calculate_score(results)
    # Exclu: L6(0.5) + L7(1.0) du denom
    # Weighted: (0.8 + 2.0 + 1.5 + 2.0 + 1.5 + 1.0 + 1.125) / 10.5 = 95
    assert score >= 90
    assert score <= 100
```

**Step 2: Run tests pour verifier qu'ils echouent**

Run: `pytest tests/test_services/test_scoring.py -v -k "neutral"`
Expected: FAIL (neutral pas gere)

**Step 3: Modifier la docstring de FilterResult pour inclure neutral**

Dans `app/filters/base.py:29` :

```python
status: str  # "pass" | "warning" | "fail" | "skip" | "neutral"
```

Et la docstring ligne 22 :

```python
status: Un parmi "pass", "warning", "fail", "skip", "neutral".
```

**Step 4: Ajouter la methode `neutral()` a BaseFilter**

Dans `app/filters/base.py`, apres la methode `skip()` (ligne 68), ajouter :

```python
def neutral(
    self,
    message: str = "Filtre non applicable",
    details: dict[str, Any] | None = None,
) -> FilterResult:
    """Retourne un resultat neutral pour ce filtre (exclu du scoring)."""
    return FilterResult(
        filter_id=self.filter_id,
        status="neutral",
        score=0.0,
        message=message,
        details=details,
    )
```

**Step 5: Modifier le scoring pour gerer neutral**

Dans `app/services/scoring.py`, remplacer le bloc lignes 46-55 :

```python
for r in filter_results:
    w = FILTER_WEIGHTS.get(r.filter_id, 1.0)

    if r.status == "neutral":
        skipped += 1
        # Neutral : exclu du calcul (ni numerateur ni denominateur)
        continue

    total_weight += w

    if r.status == "skip":
        skipped += 1
        # Skip : poids dans le denominateur, 0 dans le numerateur
        continue

    weighted_sum += w * r.score
```

**Step 6: Run tests**

Run: `pytest tests/test_services/test_scoring.py -v`
Expected: PASS pour les nouveaux tests, les anciens inchanges

**Step 7: Mettre a jour le test `test_private_seller_no_phone_still_green`**

Ce test utilise `skip` pour L6 et L7. Il doit rester tel quel car il teste le cas `skip` (pas neutral). Les nouveaux tests couvrent le cas neutral.

**Step 8: Run tous les tests**

Run: `pytest tests/ -x -q`
Expected: PASS

**Step 9: Commit**

```bash
git add app/filters/base.py app/services/scoring.py tests/test_services/test_scoring.py
git commit -m "feat: add neutral status to FilterResult (excluded from scoring weight)"
```

---

## Task 4: L7 et L6 retournent `neutral` pour les particuliers (S2)

**Files:**
- Modify: `app/filters/l7_siret.py:77-79`
- Modify: `app/filters/l6_phone.py:99-101`
- Test: `tests/test_filters/test_l7_siret.py`
- Test: `tests/test_filters/test_l6_phone.py`

**Step 1: Ecrire les tests qui echouent**

Dans `tests/test_filters/test_l7_siret.py`, ajouter :

```python
def test_private_seller_returns_neutral(self):
    """Particulier doit retourner neutral, pas skip."""
    result = L7SiretFilter().run({"owner_type": "private"})
    assert result.status == "neutral"
    assert result.score == 0.0
    assert "particulier" in result.message.lower()

def test_particulier_returns_neutral(self):
    """owner_type francais 'particulier' aussi."""
    result = L7SiretFilter().run({"owner_type": "particulier"})
    assert result.status == "neutral"
```

Dans `tests/test_filters/test_l6_phone.py`, ajouter :

```python
def test_private_no_phone_returns_neutral(self):
    """Particulier sans tel doit retourner neutral, pas skip."""
    result = L6PhoneFilter().run({"owner_type": "private"})
    assert result.status == "neutral"
    assert result.score == 0.0

def test_particulier_no_phone_returns_neutral(self):
    result = L6PhoneFilter().run({"owner_type": "particulier"})
    assert result.status == "neutral"
```

**Step 2: Run tests pour verifier qu'ils echouent**

Run: `pytest tests/test_filters/test_l7_siret.py::test_private_seller_returns_neutral tests/test_filters/test_l6_phone.py::test_private_no_phone_returns_neutral -v`
Expected: FAIL (retourne skip au lieu de neutral)

**Step 3: Modifier L7 pour retourner neutral**

Dans `app/filters/l7_siret.py:77-79`, remplacer :

```python
# Particulier : pas de verification entreprise
if owner_type in ("private", "particulier"):
    return self.neutral("Vendeur particulier — vérification entreprise non applicable")
```

**Step 4: Modifier L6 pour retourner neutral**

Dans `app/filters/l6_phone.py:99-101`, remplacer :

```python
# Particulier sans telephone : normal, pas de penalite
if owner_type in ("private", "particulier", ""):
    return self.neutral("Pas de numéro — vendeur particulier, pas de pénalité")
```

**Step 5: Run tests**

Run: `pytest tests/test_filters/test_l7_siret.py tests/test_filters/test_l6_phone.py -v`
Expected: PASS

**Step 6: Run tous les tests**

Run: `pytest tests/ -x -q`
Expected: PASS (verifier que les tests existants qui checkent `skip` pour d'autres cas marchent encore)

**Step 7: Commit**

```bash
git add app/filters/l7_siret.py app/filters/l6_phone.py tests/test_filters/test_l7_siret.py tests/test_filters/test_l6_phone.py
git commit -m "fix: L6/L7 return neutral (not skip) for private sellers"
```

---

## Task 5: Modele CollectionJobAS24 (S1)

**Files:**
- Create: `app/models/collection_job_as24.py`
- Test: `tests/test_models/test_collection_job_as24.py`

**Step 1: Ecrire le test du modele**

```python
"""Tests for CollectionJobAS24 model."""
from app.models.collection_job_as24 import CollectionJobAS24


class TestCollectionJobAS24Model:
    def test_create_basic(self, app):
        """Basic creation with required fields."""
        from app.extensions import db

        job = CollectionJobAS24(
            make="Volkswagen",
            model="Tiguan",
            year=2016,
            region="Berne",
            tld="ch",
            slug_make="vw",
            slug_model="tiguan",
            country="CH",
            currency="CHF",
            search_strategy="zip_radius",
        )
        db.session.add(job)
        db.session.commit()
        assert job.id is not None
        assert job.status == "pending"
        assert job.tld == "ch"
        assert job.slug_make == "vw"

    def test_unique_constraint(self, app):
        """Duplicate job raises IntegrityError."""
        from sqlalchemy.exc import IntegrityError
        from app.extensions import db

        kwargs = dict(
            make="VW", model="TIGUAN", year=2016, region="Berne",
            tld="ch", slug_make="vw", slug_model="tiguan",
            country="CH", currency="CHF", search_strategy="zip_radius",
        )
        db.session.add(CollectionJobAS24(**kwargs))
        db.session.commit()
        db.session.add(CollectionJobAS24(**kwargs))
        try:
            db.session.commit()
            assert False, "Should have raised IntegrityError"
        except IntegrityError:
            db.session.rollback()

    def test_default_values(self, app):
        """Defaults: status=pending, attempts=0, priority=1."""
        from app.extensions import db

        job = CollectionJobAS24(
            make="BMW", model="X4", year=2020, region="Zurich",
            tld="ch", slug_make="bmw", slug_model="x4",
            country="CH", currency="CHF", search_strategy="national",
        )
        db.session.add(job)
        db.session.commit()
        assert job.status == "pending"
        assert job.attempts == 0
        assert job.priority == 1
```

**Step 2: Run test pour verifier qu'il echoue**

Run: `pytest tests/test_models/test_collection_job_as24.py -v`
Expected: FAIL (module not found)

**Step 3: Creer le modele**

Creer `app/models/collection_job_as24.py` :

```python
"""Modele CollectionJobAS24 -- file d'attente de collecte prix pour AutoScout24."""

from datetime import datetime, timezone

from app.extensions import db


class CollectionJobAS24(db.Model):
    """Job de collecte de prix a executer par l'extension Chrome sur AutoScout24."""

    __tablename__ = "collection_jobs_as24"

    id = db.Column(db.Integer, primary_key=True)
    make = db.Column(db.String(80), nullable=False, index=True)
    model = db.Column(db.String(80), nullable=False, index=True)
    year = db.Column(db.Integer, nullable=False)
    region = db.Column(db.String(80), nullable=False)
    fuel = db.Column(db.String(30), nullable=True)
    gearbox = db.Column(db.String(20), nullable=True)
    hp_range = db.Column(db.String(20), nullable=True)
    country = db.Column(db.String(5), nullable=False, default="CH")
    tld = db.Column(db.String(5), nullable=False)  # ch, de, at, fr, it, es, be, nl, lu
    slug_make = db.Column(db.String(80), nullable=False)  # AS24 URL slug (ex: "vw")
    slug_model = db.Column(db.String(80), nullable=False)  # AS24 URL slug (ex: "tiguan")
    search_strategy = db.Column(db.String(20), nullable=False, default="zip_radius")  # zip_radius, national, canton
    currency = db.Column(db.String(5), nullable=False, default="CHF")  # CHF, EUR
    source_url = db.Column(db.String(500), nullable=True)  # URL annonce AS24 source

    priority = db.Column(db.Integer, nullable=False, default=1, index=True)
    status = db.Column(
        db.String(20), nullable=False, default="pending", index=True
    )  # pending, assigned, done, failed
    source_vehicle = db.Column(db.String(200), nullable=True)
    attempts = db.Column(db.Integer, nullable=False, default=0)

    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    assigned_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)

    __table_args__ = (
        db.UniqueConstraint(
            "make", "model", "year", "region", "fuel", "gearbox", "hp_range",
            "country", "tld",
            name="uq_collection_job_as24_key",
        ),
    )

    def __repr__(self):
        return f"<CollectionJobAS24 {self.make} {self.model} {self.year} {self.region} [{self.status}] tld={self.tld}>"
```

**Step 4: Enregistrer le modele dans les imports**

Verifier que `app/models/__init__.py` importe le nouveau modele (ou que `db.create_all()` le detecte via l'import dans les routes).

**Step 5: Run tests**

Run: `pytest tests/test_models/test_collection_job_as24.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add app/models/collection_job_as24.py tests/test_models/test_collection_job_as24.py
git commit -m "feat: add CollectionJobAS24 model (separate table for AS24 jobs)"
```

---

## Task 6: Renommer collection_jobs → collection_jobs_lbc (S1)

**Files:**
- Modify: `app/models/collection_job.py` (rename tablename)
- Modify: `tests/test_models/test_collection_job.py`
- Modify: `tests/test_services/test_collection_job_service.py`
- Modify: `start.sh` (schema sync)

**Step 1: Renommer le `__tablename__` dans le modele**

Dans `app/models/collection_job.py:11`, changer :

```python
__tablename__ = "collection_jobs_lbc"
```

Et renommer la classe :

```python
class CollectionJobLBC(db.Model):
```

Et la contrainte unique :

```python
name="uq_collection_job_lbc_key",
```

**Step 2: Mettre a jour TOUS les imports**

Chercher `from app.models.collection_job import CollectionJob` dans tout le projet et remplacer par `from app.models.collection_job import CollectionJobLBC` (ou ajouter un alias `CollectionJob = CollectionJobLBC` pour la retrocompat temporaire).

**Strategie recommandee** : garder un alias dans le fichier modele :

```python
# Alias pour retrocompat pendant la migration
CollectionJob = CollectionJobLBC
```

**Step 3: Ajouter la migration SQLite dans start.sh**

Le `start.sh` doit :
1. Renommer `collection_jobs` → `collection_jobs_lbc` si elle existe encore
2. Creer `collection_jobs_as24` si absente

```bash
# Migration table collection_jobs → collection_jobs_lbc
python -c "
from app import create_app
from app.extensions import db
app = create_app()
with app.app_context():
    tables = db.inspect(db.engine).get_table_names()
    if 'collection_jobs' in tables and 'collection_jobs_lbc' not in tables:
        db.engine.execute('ALTER TABLE collection_jobs RENAME TO collection_jobs_lbc')
        print('Renamed collection_jobs → collection_jobs_lbc')
    db.create_all()
"
```

**Step 4: Run tous les tests**

Run: `pytest tests/ -x -q`
Expected: PASS (l'alias CollectionJob = CollectionJobLBC assure la retrocompat)

**Step 5: Commit**

```bash
git add app/models/collection_job.py start.sh
git commit -m "refactor: rename CollectionJob → CollectionJobLBC (table collection_jobs_lbc)"
```

---

## Task 7: Service AS24 collection jobs (S1)

**Files:**
- Create: `app/services/collection_job_as24_service.py`
- Test: `tests/test_services/test_collection_job_as24_service.py`

**Step 1: Ecrire le test de `pick_bonus_jobs_as24`**

```python
"""Tests for AS24 collection job service."""
from app.models.collection_job_as24 import CollectionJobAS24
from app.services.collection_job_as24_service import pick_bonus_jobs_as24


class TestPickBonusJobsAS24:
    def test_pick_returns_only_matching_country(self, app):
        """pick_bonus_jobs_as24 ne retourne que les jobs du bon pays."""
        from app.extensions import db

        # Job CH
        ch = CollectionJobAS24(
            make="VW", model="Tiguan", year=2016, region="Berne",
            tld="ch", slug_make="vw", slug_model="tiguan",
            country="CH", currency="CHF", search_strategy="zip_radius",
        )
        # Job DE
        de = CollectionJobAS24(
            make="VW", model="Tiguan", year=2016, region="Bayern",
            tld="de", slug_make="vw", slug_model="tiguan",
            country="DE", currency="EUR", search_strategy="national",
        )
        db.session.add_all([ch, de])
        db.session.commit()

        jobs = pick_bonus_jobs_as24(country="CH", tld="ch", max_jobs=3)
        assert len(jobs) == 1
        assert jobs[0].country == "CH"

    def test_pick_excludes_lbc_jobs(self, app):
        """AS24 service ne pioche jamais dans la table LBC."""
        from app.extensions import db
        from app.models.collection_job import CollectionJobLBC

        lbc = CollectionJobLBC(
            make="VW", model="Tiguan", year=2016, region="Bretagne",
        )
        db.session.add(lbc)
        db.session.commit()

        jobs = pick_bonus_jobs_as24(country="FR", tld="fr", max_jobs=3)
        assert len(jobs) == 0

    def test_mark_job_done_as24(self, app):
        """mark_job_done fonctionne sur un job AS24."""
        from app.extensions import db
        from app.services.collection_job_as24_service import mark_job_done_as24

        job = CollectionJobAS24(
            make="BMW", model="X4", year=2020, region="Zurich",
            tld="ch", slug_make="bmw", slug_model="x4",
            country="CH", currency="CHF", search_strategy="national",
            status="assigned",
        )
        db.session.add(job)
        db.session.commit()

        mark_job_done_as24(job.id, success=True)
        assert job.status == "done"
```

**Step 2: Run test pour verifier qu'il echoue**

Run: `pytest tests/test_services/test_collection_job_as24_service.py -v`
Expected: FAIL

**Step 3: Creer le service**

Creer `app/services/collection_job_as24_service.py` :

```python
"""Service CollectionJobAS24 -- gestion de la file d'attente pour AutoScout24."""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.collection_job_as24 import CollectionJobAS24

logger = logging.getLogger(__name__)

FRESHNESS_DAYS = 7
MAX_ATTEMPTS = 3
ASSIGNMENT_TIMEOUT_MINUTES = 30


def _reclaim_stale_jobs_as24() -> int:
    """Remet en pending les jobs assigned depuis trop longtemps."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=ASSIGNMENT_TIMEOUT_MINUTES)
    stale = CollectionJobAS24.query.filter(
        CollectionJobAS24.status == "assigned",
        CollectionJobAS24.assigned_at < cutoff,
    ).all()
    for job in stale:
        job.status = "pending"
        job.assigned_at = None
    if stale:
        db.session.commit()
        logger.info("AS24: reclaimed %d stale jobs", len(stale))
    return len(stale)


def pick_bonus_jobs_as24(country: str, tld: str, max_jobs: int = 3) -> list[CollectionJobAS24]:
    """Selectionne les N jobs AS24 pending pour le bon pays/tld."""
    _reclaim_stale_jobs_as24()

    jobs = (
        CollectionJobAS24.query
        .filter(
            CollectionJobAS24.status == "pending",
            CollectionJobAS24.country == country.upper(),
            CollectionJobAS24.tld == tld.lower(),
        )
        .order_by(CollectionJobAS24.priority.asc(), CollectionJobAS24.created_at.asc())
        .limit(max_jobs)
        .all()
    )

    now = datetime.now(timezone.utc)
    for job in jobs:
        job.status = "assigned"
        job.assigned_at = now
    db.session.commit()
    return jobs


def mark_job_done_as24(job_id: int, success: bool = True) -> None:
    """Marque un job AS24 comme done ou failed."""
    job = db.session.get(CollectionJobAS24, job_id)
    if job is None:
        raise ValueError(f"AS24 Job {job_id} not found")
    if job.status not in ("assigned", "pending"):
        raise ValueError(f"AS24 Job {job_id} has status '{job.status}'")
    if success:
        job.status = "done"
        job.completed_at = datetime.now(timezone.utc)
    else:
        job.attempts += 1
        if job.attempts >= MAX_ATTEMPTS:
            job.status = "failed"
        else:
            job.status = "pending"
    db.session.commit()
```

**Step 4: Run tests**

Run: `pytest tests/test_services/test_collection_job_as24_service.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add app/services/collection_job_as24_service.py tests/test_services/test_collection_job_as24_service.py
git commit -m "feat: add collection_job_as24_service (isolated bonus job queue)"
```

---

## Task 8: API next-job filtre par site (S1)

**Files:**
- Modify: `app/api/market_routes.py:50-69,342-531`
- Test: `tests/test_api/test_market_routes.py` (ajouter tests)

**Step 1: Ecrire le test**

```python
def test_next_job_site_as24_returns_only_as24_jobs(self, client, app):
    """next-job?site=as24&tld=ch ne retourne que des jobs AS24 CH."""
    from app.models.collection_job_as24 import CollectionJobAS24
    from app.extensions import db

    job = CollectionJobAS24(
        make="VW", model="Tiguan", year=2016, region="Berne",
        tld="ch", slug_make="vw", slug_model="tiguan",
        country="CH", currency="CHF", search_strategy="zip_radius",
    )
    db.session.add(job)
    db.session.commit()

    resp = client.get("/api/market-prices/next-job?make=VW&model=Tiguan&year=2016&region=Berne&country=CH&site=as24&tld=ch")
    data = resp.get_json()["data"]
    for bj in data.get("bonus_jobs", []):
        assert bj["country"] == "CH"
        assert "slug_make" in bj
        assert "slug_model" in bj

def test_next_job_default_site_lbc(self, client, app):
    """Sans param site, default=lbc, ne retourne pas de jobs AS24."""
    resp = client.get("/api/market-prices/next-job?make=BMW&model=X4&year=2016&region=Bretagne")
    data = resp.get_json()["data"]
    for bj in data.get("bonus_jobs", []):
        assert bj.get("country", "FR") == "FR"
```

**Step 2: Modifier l'API next-job**

Dans `app/api/market_routes.py`, modifier `next_market_job()` :

1. Lire `site = request.args.get("site", "lbc")`
2. Lire `tld = request.args.get("tld", "")`
3. Si `site == "as24"` : appeler `pick_bonus_jobs_as24(country, tld)` et serialiser avec `slug_make`/`slug_model`
4. Si `site == "lbc"` : appeler `pick_bonus_jobs()` comme avant

Modifier `_pick_and_serialize_bonus` pour prendre un parametre `site` :

```python
def _pick_and_serialize_bonus(site: str = "lbc", country: str = "FR", tld: str = "") -> list[dict]:
    if site == "as24":
        from app.services.collection_job_as24_service import pick_bonus_jobs_as24
        picked = pick_bonus_jobs_as24(country=country, tld=tld)
        result = []
        for j in picked:
            result.append({
                "make": j.make, "model": j.model, "year": j.year,
                "region": j.region, "fuel": j.fuel, "gearbox": j.gearbox,
                "hp_range": j.hp_range, "country": j.country,
                "tld": j.tld, "slug_make": j.slug_make, "slug_model": j.slug_model,
                "search_strategy": j.search_strategy, "currency": j.currency,
                "job_id": j.id,
            })
        return result
    # LBC (default)
    picked = pick_bonus_jobs(max_jobs=3)
    result = []
    for j in picked:
        entry = {
            "make": j.make, "model": j.model, "year": j.year,
            "region": j.region, "fuel": j.fuel, "gearbox": j.gearbox,
            "hp_range": j.hp_range, "country": j.country or "FR",
            "job_id": j.id,
        }
        tokens = _lookup_site_tokens(j.make, j.model)
        entry.update(tokens)
        result.append(entry)
    return result
```

Mettre a jour tous les appels a `_pick_and_serialize_bonus()` dans la route pour passer `site`, `country`, `tld`.

**Step 3: Run tests**

Run: `pytest tests/test_api/test_market_routes.py -v`
Expected: PASS

**Step 4: Run tous les tests**

Run: `pytest tests/ -x -q`
Expected: PASS

**Step 5: Commit**

```bash
git add app/api/market_routes.py tests/test_api/test_market_routes.py
git commit -m "feat: next-job API filters by site (lbc/as24) with isolated bonus queues"
```

---

## Task 9: Extension AS24 envoie `site=as24` + utilise les slugs (S1)

**Files:**
- Modify: `extension/extractors/autoscout24.js`

**Step 1: Modifier le next-job call pour envoyer `site=as24&tld=X`**

Dans `autoscout24.js`, la methode qui appelle `/market-prices/next-job`, ajouter les params `site=as24` et `tld=<current_tld>`.

**Step 2: Modifier `_executeBonusJobs` pour utiliser `slug_make`/`slug_model`**

Remplacer lignes 1285-1286 :

```javascript
// Avant
const jobMakeKey = job.make.toLowerCase();
const jobModelKey = job.model.toLowerCase();

// Apres
const jobMakeKey = job.slug_make || job.make.toLowerCase();
const jobModelKey = job.slug_model || job.model.toLowerCase();
```

**Step 3: Extraire et envoyer les RSC keys au serveur**

Dans `normalizeToAdData()`, extraire `rsc.make.key` et `rsc.model.key` et les inclure dans les donnees envoyees au serveur (via POST /market-prices).

**Step 4: Builder et tester manuellement**

Run: `npm run build` (dans extension/)
Recharger l'extension Chrome et tester sur une annonce AS24.

**Step 5: Commit**

```bash
git add extension/extractors/autoscout24.js
git commit -m "feat: AS24 extension sends site=as24, uses slug_make/slug_model for search URLs"
```

---

## Task 10: Extension LBC envoie `site=lbc` (S1)

**Files:**
- Modify: `extension/extractors/leboncoin.js`

**Step 1: Modifier le next-job call pour envoyer `site=lbc`**

Dans `leboncoin.js`, la methode `maybeCollectMarketPrices` qui appelle `/market-prices/next-job`, ajouter `&site=lbc` au query string.

**Step 2: Run tests JS**

Run: `npm test` (dans extension/)
Expected: PASS

**Step 3: Commit**

```bash
git add extension/extractors/leboncoin.js
git commit -m "feat: LBC extension sends site=lbc in next-job requests"
```

---

## Task 11: Colonnes AS24 slug sur Vehicle (S1)

**Files:**
- Modify: `app/models/vehicle.py`
- Modify: `start.sh` (schema sync)

**Step 1: Ajouter les colonnes `as24_slug_make` et `as24_slug_model`**

Dans `app/models/vehicle.py`, apres les colonnes `site_model_token` :

```python
# Slugs AutoScout24 pour les URLs de recherche (auto-appris depuis le RSC).
# Ex: "vw" pour Volkswagen, "tiguan" pour Tiguan.
as24_slug_make = db.Column(db.String(80), nullable=True)
as24_slug_model = db.Column(db.String(80), nullable=True)
```

**Step 2: Schema sync dans start.sh**

Ajouter les colonnes `as24_slug_make` et `as24_slug_model` a la liste de colonnes a synchro dans `start.sh`.

**Step 3: Run tests**

Run: `pytest tests/ -x -q`
Expected: PASS

**Step 4: Commit**

```bash
git add app/models/vehicle.py start.sh
git commit -m "feat: add as24_slug_make/as24_slug_model columns on Vehicle"
```

---

## Task 12: Admin issues avec onglets par site (S4)

**Files:**
- Modify: `app/admin/routes.py:1861-1932`
- Modify: `app/admin/templates/admin/issues.html`

**Step 1: Modifier la route pour charger les deux tables**

Ajouter un param `site` (default "lbc") et charger les stats/records depuis la bonne table.

```python
from app.models.collection_job_as24 import CollectionJobAS24

site = request.args.get("site", "lbc")
if site == "as24":
    Model = CollectionJobAS24
else:
    Model = CollectionJobLBC

pending = Model.query.filter_by(status="pending").count()
# ... idem pour assigned, done, failed
```

**Step 2: Ajouter les onglets dans le template**

En haut de issues.html, ajouter :

```html
<ul class="nav nav-tabs mb-4">
  <li class="nav-item">
    <a class="nav-link {% if site == 'lbc' %}active{% endif %}"
       href="{{ url_for('admin.issues', site='lbc') }}">LeBonCoin</a>
  </li>
  <li class="nav-item">
    <a class="nav-link {% if site == 'as24' %}active{% endif %}"
       href="{{ url_for('admin.issues', site='as24') }}">AutoScout24</a>
  </li>
</ul>
```

**Step 3: Appliquer le filtre `localdatetime` sur les dates**

S'assurer que toutes les dates dans le template utilisent `|localdatetime`.

**Step 4: Run tests**

Run: `pytest tests/ -x -q`
Expected: PASS

**Step 5: Tester manuellement**

Visiter http://localhost:5001/admin/issues et http://localhost:5001/admin/issues?site=as24

**Step 6: Commit**

```bash
git add app/admin/routes.py app/admin/templates/admin/issues.html
git commit -m "feat: admin issues page with LBC/AS24 tabs"
```

---

## Task 13: Run complet + ruff + verification finale

**Step 1: Ruff check**

Run: `ruff check app/ tests/`
Expected: clean

**Step 2: Ruff format**

Run: `ruff format --check app/ tests/`
Expected: clean

**Step 3: Tests complets**

Run: `pytest tests/ -v --tb=short`
Expected: ALL PASS

**Step 4: Commit final si corrections**

```bash
git add -A
git commit -m "chore: ruff cleanup after corrections fondamentales"
```
