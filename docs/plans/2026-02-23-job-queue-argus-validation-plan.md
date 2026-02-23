# Job Queue + Validation LBC + HP Precision — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a CollectionJob queue system so the extension never wastes a scan, improve argus precision with HP ranges, and validate our estimates against LBC's own price range.

**Architecture:** New `CollectionJob` model as a persistent task queue. Server generates jobs on scan via `_expand_collection_jobs()`. Extension executes bonus jobs even when primary vehicle is fresh. MarketPrice gains `hp_range`, `fiscal_hp`, `lbc_estimate_low/high` columns. New `/admin/issues` page.

**Tech Stack:** Python/Flask/SQLAlchemy (backend), Jinja2/Bootstrap (admin), vanilla JS (extension)

---

## Task 1: MarketPrice — add hp_range, fiscal_hp, lbc_estimate columns

**Files:**
- Modify: `app/models/market_price.py`
- Modify: `app/services/market_service.py`
- Test: `tests/test_services/test_market_service.py`

**Step 1: Write failing test for hp_range in store_market_prices**

Add to `tests/test_services/test_market_service.py`:

```python
def test_store_with_hp_range(self, app):
    """store_market_prices stores hp_range when provided."""
    with app.app_context():
        mp = store_market_prices(
            make="Renault",
            model="Talisman",
            year=2016,
            region="Ile-de-France",
            prices=[12000, 13000, 14000, 15000, 16000],
            fuel="diesel",
            hp_range="120-150",
        )
        assert mp.hp_range == "120-150"

def test_store_with_fiscal_hp(self, app):
    """store_market_prices stores fiscal_hp when provided."""
    with app.app_context():
        mp = store_market_prices(
            make="Renault",
            model="Talisman",
            year=2016,
            region="Bretagne",
            prices=[12000, 13000, 14000, 15000, 16000],
            fuel="diesel",
            fiscal_hp=7,
        )
        assert mp.fiscal_hp == 7

def test_same_vehicle_different_hp_range_creates_two_records(self, app):
    """Two different hp_ranges for same vehicle create separate MarketPrice entries."""
    with app.app_context():
        mp1 = store_market_prices(
            make="Renault", model="Talisman", year=2016,
            region="Ile-de-France", prices=[12000, 13000, 14000, 15000, 16000],
            fuel="diesel", hp_range="100-130",
        )
        mp2 = store_market_prices(
            make="Renault", model="Talisman", year=2016,
            region="Ile-de-France", prices=[15000, 16000, 17000, 18000, 19000],
            fuel="diesel", hp_range="130-160",
        )
        assert mp1.id != mp2.id
        assert mp1.hp_range == "100-130"
        assert mp2.hp_range == "130-160"

def test_store_with_lbc_estimates(self, app):
    """store_market_prices stores LBC estimate low/high."""
    with app.app_context():
        mp = store_market_prices(
            make="Peugeot", model="208", year=2021,
            region="Ile-de-France", prices=[12000, 13000, 14000, 15000, 16000],
            lbc_estimate_low=12500, lbc_estimate_high=15500,
        )
        assert mp.lbc_estimate_low == 12500
        assert mp.lbc_estimate_high == 15500
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_services/test_market_service.py -v -k "hp_range or fiscal_hp or lbc_estimate"`
Expected: FAIL (unknown kwargs)

**Step 3: Add columns to MarketPrice model**

In `app/models/market_price.py`, add after `precision` column:

```python
hp_range = db.Column(db.String(20), nullable=True)  # ex: "120-150"
fiscal_hp = db.Column(db.Integer, nullable=True)  # chevaux fiscaux

lbc_estimate_low = db.Column(db.Integer, nullable=True)
lbc_estimate_high = db.Column(db.Integer, nullable=True)
```

Update UniqueConstraint:

```python
__table_args__ = (
    db.UniqueConstraint(
        "make", "model", "year", "region", "fuel", "hp_range",
        name="uq_market_price_vehicle_region_fuel_hp",
    ),
)
```

**Step 4: Update store_market_prices signature and logic**

In `app/services/market_service.py`, add `hp_range`, `fiscal_hp`, `lbc_estimate_low`, `lbc_estimate_high` params to `store_market_prices()`. Add them to the `stats` dict and the filter query (add `hp_range` to the unique lookup, handle nullable same as `fuel`).

**Step 5: Update get_market_stats to handle hp_range**

Add `hp_range` param to `get_market_stats()`. Search strategy:
1. Exact match with hp_range
2. Fallback to hp_range=NULL (generic)
3. Then existing year fallback logic

**Step 6: Run tests to verify they pass**

Run: `pytest tests/test_services/test_market_service.py -v`
Expected: ALL PASS

**Step 7: Commit**

```bash
git add app/models/market_price.py app/services/market_service.py tests/test_services/test_market_service.py
git commit -m "feat(argus): add hp_range, fiscal_hp, lbc_estimate columns to MarketPrice"
```

---

## Task 2: Update API route to accept new fields

**Files:**
- Modify: `app/api/market_routes.py`
- Test: `tests/test_api/test_market_api.py`

**Step 1: Write failing test**

Add to `tests/test_api/test_market_api.py`:

```python
def test_submit_with_hp_range_and_lbc_estimate(self, app, client):
    """POST with hp_range, fiscal_hp, lbc estimates stores them."""
    prices_20 = list(range(12000, 22000, 500))
    resp = client.post(
        "/api/market-prices",
        data=json.dumps({
            "make": "Renault", "model": "Talisman", "year": 2016,
            "region": "Ile-de-France", "prices": prices_20,
            "fuel": "diesel", "hp_range": "120-150", "fiscal_hp": 7,
            "lbc_estimate_low": 12000, "lbc_estimate_high": 15000,
        }),
        content_type="application/json",
    )
    assert resp.status_code == 200
    with app.app_context():
        mp = MarketPrice.query.first()
        assert mp.hp_range == "120-150"
        assert mp.fiscal_hp == 7
        assert mp.lbc_estimate_low == 12000
        assert mp.lbc_estimate_high == 15000
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_api/test_market_api.py::TestMarketPricesAPI::test_submit_with_hp_range_and_lbc_estimate -v`
Expected: FAIL

**Step 3: Update MarketPricesRequest schema and route**

In `app/api/market_routes.py`, add to `MarketPricesRequest`:

```python
hp_range: str | None = Field(default=None, max_length=20)
fiscal_hp: int | None = Field(default=None, ge=1, le=100)
lbc_estimate_low: int | None = Field(default=None, ge=0)
lbc_estimate_high: int | None = Field(default=None, ge=0)
```

Pass these to `store_market_prices()` in `submit_market_prices()`.

**Step 4: Run tests**

Run: `pytest tests/test_api/test_market_api.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add app/api/market_routes.py tests/test_api/test_market_api.py
git commit -m "feat(api): accept hp_range, fiscal_hp, lbc_estimate in market-prices POST"
```

---

## Task 3: CollectionJob model

**Files:**
- Create: `app/models/collection_job.py`
- Modify: `app/models/__init__.py`
- Create: `tests/test_models/test_collection_job.py`

**Step 1: Write failing test**

Create `tests/test_models/test_collection_job.py`:

```python
"""Tests for CollectionJob model."""

from app.extensions import db
from app.models.collection_job import CollectionJob


class TestCollectionJob:
    def test_create_job(self, app):
        with app.app_context():
            job = CollectionJob(
                make="Renault", model="Talisman", year=2016,
                region="Bretagne", fuel="diesel", gearbox="manual",
                hp_range="120-150", priority=1,
                source_vehicle="Renault Talisman 2016 diesel",
            )
            db.session.add(job)
            db.session.commit()
            assert job.id is not None
            assert job.status == "pending"
            assert job.attempts == 0

    def test_unique_constraint(self, app):
        """Duplicate job key raises IntegrityError."""
        import sqlalchemy
        with app.app_context():
            job1 = CollectionJob(
                make="Renault", model="Talisman", year=2016,
                region="Bretagne", fuel="diesel", hp_range="120-150",
                priority=1, source_vehicle="test",
            )
            job2 = CollectionJob(
                make="Renault", model="Talisman", year=2016,
                region="Bretagne", fuel="diesel", hp_range="120-150",
                priority=1, source_vehicle="test",
            )
            db.session.add(job1)
            db.session.commit()
            db.session.add(job2)
            try:
                db.session.commit()
                assert False, "Should have raised IntegrityError"
            except sqlalchemy.exc.IntegrityError:
                db.session.rollback()

    def test_different_hp_range_is_separate_job(self, app):
        with app.app_context():
            job1 = CollectionJob(
                make="Renault", model="Talisman", year=2016,
                region="Bretagne", fuel="diesel", hp_range="100-130",
                priority=1, source_vehicle="test",
            )
            job2 = CollectionJob(
                make="Renault", model="Talisman", year=2016,
                region="Bretagne", fuel="diesel", hp_range="130-160",
                priority=1, source_vehicle="test",
            )
            db.session.add_all([job1, job2])
            db.session.commit()
            assert job1.id != job2.id
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_models/test_collection_job.py -v`
Expected: FAIL (ImportError)

**Step 3: Create CollectionJob model**

Create `app/models/collection_job.py`:

```python
"""Modele CollectionJob -- file d'attente de collecte argus crowdsource."""

from datetime import datetime, timezone

from app.extensions import db


class CollectionJob(db.Model):
    """Job de collecte de prix a executer par l'extension Chrome."""

    __tablename__ = "collection_jobs"

    id = db.Column(db.Integer, primary_key=True)
    make = db.Column(db.String(80), nullable=False, index=True)
    model = db.Column(db.String(80), nullable=False, index=True)
    year = db.Column(db.Integer, nullable=False)
    region = db.Column(db.String(80), nullable=False)
    fuel = db.Column(db.String(30), nullable=True)
    gearbox = db.Column(db.String(20), nullable=True)
    hp_range = db.Column(db.String(20), nullable=True)

    priority = db.Column(db.Integer, nullable=False, default=1, index=True)
    status = db.Column(
        db.String(20), nullable=False, default="pending", index=True
    )  # pending, assigned, done, failed
    source_vehicle = db.Column(db.String(200), nullable=True)
    attempts = db.Column(db.Integer, nullable=False, default=0)

    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    assigned_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)

    __table_args__ = (
        db.UniqueConstraint(
            "make", "model", "year", "region", "fuel", "gearbox", "hp_range",
            name="uq_collection_job_key",
        ),
    )

    def __repr__(self):
        return f"<CollectionJob {self.make} {self.model} {self.year} {self.region} [{self.status}]>"
```

**Step 4: Register in __init__.py**

Add to `app/models/__init__.py`:

```python
from app.models.collection_job import CollectionJob  # noqa: F401
```

**Step 5: Run tests**

Run: `pytest tests/test_models/test_collection_job.py -v`
Expected: ALL PASS

**Step 6: Commit**

```bash
git add app/models/collection_job.py app/models/__init__.py tests/test_models/test_collection_job.py
git commit -m "feat(models): add CollectionJob model for argus task queue"
```

---

## Task 4: Job expansion service — _expand_collection_jobs()

**Files:**
- Create: `app/services/collection_job_service.py`
- Create: `tests/test_services/test_collection_job_service.py`

**Step 1: Write failing tests**

Create `tests/test_services/test_collection_job_service.py`:

```python
"""Tests for collection_job_service -- expansion et gestion de la file d'attente."""

from app.extensions import db
from app.models.collection_job import CollectionJob
from app.services.collection_job_service import (
    expand_collection_jobs,
    pick_bonus_jobs,
    mark_job_done,
)


class TestExpandCollectionJobs:
    def test_creates_region_jobs_priority_1(self, app):
        """Expanding creates priority-1 jobs for all other regions."""
        with app.app_context():
            jobs = expand_collection_jobs(
                make="Renault", model="Talisman", year=2016,
                region="Auvergne-Rhone-Alpes", fuel="diesel",
                gearbox="manual", hp_range="120-150",
            )
            p1_jobs = [j for j in jobs if j.priority == 1]
            # 13 regions - 1 (current) = 12 region jobs
            assert len(p1_jobs) == 12
            regions = {j.region for j in p1_jobs}
            assert "Auvergne-Rhone-Alpes" not in regions
            assert "Ile-de-France" in regions

    def test_creates_fuel_variant_priority_2(self, app):
        """Expanding diesel creates essence variant jobs at priority 2."""
        with app.app_context():
            jobs = expand_collection_jobs(
                make="Renault", model="Talisman", year=2016,
                region="Auvergne-Rhone-Alpes", fuel="diesel",
                gearbox="manual", hp_range="120-150",
            )
            p2_jobs = [j for j in jobs if j.priority == 2]
            assert len(p2_jobs) == 13  # all 13 regions for essence variant
            assert all(j.fuel == "essence" for j in p2_jobs)
            # HP range is NULL for fuel variants (different engine)
            assert all(j.hp_range is None for j in p2_jobs)

    def test_creates_gearbox_variant_priority_3(self, app):
        """Expanding manual creates auto variant jobs at priority 3."""
        with app.app_context():
            jobs = expand_collection_jobs(
                make="Renault", model="Talisman", year=2016,
                region="Auvergne-Rhone-Alpes", fuel="diesel",
                gearbox="manual", hp_range="120-150",
            )
            p3_jobs = [j for j in jobs if j.priority == 3]
            assert len(p3_jobs) == 13
            assert all(j.gearbox == "automatique" for j in p3_jobs)

    def test_creates_year_variant_priority_4(self, app):
        """Expanding year 2016 creates 2015 and 2017 jobs at priority 4."""
        with app.app_context():
            jobs = expand_collection_jobs(
                make="Renault", model="Talisman", year=2016,
                region="Auvergne-Rhone-Alpes", fuel="diesel",
                gearbox="manual", hp_range="120-150",
            )
            p4_jobs = [j for j in jobs if j.priority == 4]
            years = {j.year for j in p4_jobs}
            assert 2015 in years
            assert 2017 in years

    def test_no_fuel_variant_for_electrique(self, app):
        """No fuel variant created for electric vehicles."""
        with app.app_context():
            jobs = expand_collection_jobs(
                make="Tesla", model="Model 3", year=2022,
                region="Ile-de-France", fuel="electrique",
                gearbox=None, hp_range="240-360",
            )
            p2_jobs = [j for j in jobs if j.priority == 2]
            assert len(p2_jobs) == 0

    def test_deduplication_skips_existing_jobs(self, app):
        """Calling expand twice does not create duplicates."""
        with app.app_context():
            jobs1 = expand_collection_jobs(
                make="Renault", model="Talisman", year=2016,
                region="Bretagne", fuel="diesel",
                gearbox="manual", hp_range="120-150",
            )
            count1 = len(jobs1)
            jobs2 = expand_collection_jobs(
                make="Renault", model="Talisman", year=2016,
                region="Bretagne", fuel="diesel",
                gearbox="manual", hp_range="120-150",
            )
            # Second call creates 0 new jobs (all deduplicated)
            assert len(jobs2) == 0
            total = CollectionJob.query.count()
            assert total == count1

    def test_no_variant_without_info(self, app):
        """No fuel/gearbox variants if those fields are None."""
        with app.app_context():
            jobs = expand_collection_jobs(
                make="Peugeot", model="208", year=2020,
                region="Bretagne", fuel=None,
                gearbox=None, hp_range=None,
            )
            # Only priority 1 (regions) and 4 (years), no fuel/gearbox variants
            assert all(j.priority != 2 for j in jobs)
            assert all(j.priority != 3 for j in jobs)


class TestPickBonusJobs:
    def test_picks_highest_priority_first(self, app):
        """pick_bonus_jobs returns priority-1 jobs before priority-2."""
        with app.app_context():
            expand_collection_jobs(
                make="Renault", model="Talisman", year=2016,
                region="Bretagne", fuel="diesel",
                gearbox="manual", hp_range="120-150",
            )
            picked = pick_bonus_jobs(max_jobs=3)
            assert len(picked) == 3
            assert all(j.priority == 1 for j in picked)
            assert all(j.status == "assigned" for j in picked)

    def test_picks_max_jobs(self, app):
        """pick_bonus_jobs respects max_jobs limit."""
        with app.app_context():
            expand_collection_jobs(
                make="Peugeot", model="208", year=2020,
                region="Bretagne", fuel="essence",
                gearbox="manual", hp_range="70-120",
            )
            picked = pick_bonus_jobs(max_jobs=2)
            assert len(picked) == 2


class TestMarkJobDone:
    def test_mark_done(self, app):
        """mark_job_done sets status and completed_at."""
        with app.app_context():
            job = CollectionJob(
                make="Renault", model="Talisman", year=2016,
                region="Bretagne", priority=1, source_vehicle="test",
            )
            db.session.add(job)
            db.session.commit()
            mark_job_done(job.id, success=True)
            db.session.refresh(job)
            assert job.status == "done"
            assert job.completed_at is not None

    def test_mark_failed_increments_attempts(self, app):
        """mark_job_done with success=False increments attempts."""
        with app.app_context():
            job = CollectionJob(
                make="Renault", model="Talisman", year=2016,
                region="Bretagne", priority=1, source_vehicle="test",
            )
            db.session.add(job)
            db.session.commit()
            mark_job_done(job.id, success=False)
            db.session.refresh(job)
            assert job.status == "failed"
            assert job.attempts == 1
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_services/test_collection_job_service.py -v`
Expected: FAIL (ImportError)

**Step 3: Implement collection_job_service.py**

Create `app/services/collection_job_service.py` with three functions:

- `expand_collection_jobs(make, model, year, region, fuel, gearbox, hp_range)` — generates all jobs using the priority cascade (regions P1, fuel P2, gearbox P3, year P4). Uses `INSERT OR IGNORE` pattern for deduplication. Returns list of newly created jobs.
- `pick_bonus_jobs(max_jobs=3)` — picks N highest-priority pending jobs, marks them `assigned`, returns them.
- `mark_job_done(job_id, success=True)` — marks job as `done` or `failed`, increments attempts on failure.

Key constants:
```python
POST_2016_REGIONS = [...]  # Import from market_routes
FUEL_OPPOSITES = {"diesel": "essence", "essence": "diesel"}
GEARBOX_OPPOSITES = {"manual": "automatique", "manuelle": "automatique", "automatique": "manuelle"}
MAX_ATTEMPTS = 3
```

**Step 4: Run tests**

Run: `pytest tests/test_services/test_collection_job_service.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add app/services/collection_job_service.py tests/test_services/test_collection_job_service.py
git commit -m "feat(services): add collection_job_service for argus task queue expansion"
```

---

## Task 5: Update next-job endpoint to use CollectionJob queue

**Files:**
- Modify: `app/api/market_routes.py`
- Test: `tests/test_api/test_market_api.py`

**Step 1: Write failing test**

Add to `tests/test_api/test_market_api.py`:

```python
class TestNextJobWithQueue:
    def test_fresh_vehicle_returns_bonus_from_queue(self, app, client):
        """When current vehicle is fresh, next-job returns queued bonus jobs."""
        with app.app_context():
            # Create fresh MarketPrice for current vehicle
            from app.services.market_service import store_market_prices
            store_market_prices(
                make="Renault", model="Talisman", year=2016,
                region="Ile-de-France",
                prices=list(range(12000, 22000, 500)),
                fuel="diesel", hp_range="120-150",
            )
            # Create pending CollectionJob
            from app.models.collection_job import CollectionJob
            job = CollectionJob(
                make="Renault", model="Talisman", year=2016,
                region="Bretagne", fuel="diesel", hp_range="120-150",
                priority=1, source_vehicle="test",
            )
            db.session.add(job)
            db.session.commit()
            saved_id = job.id

        resp = client.get(
            "/api/market-prices/next-job?make=Renault&model=Talisman&year=2016"
            "&region=Ile-de-France&fuel=diesel&hp_range=120-150"
        )
        data = resp.get_json()
        assert data["success"] is True
        # collect=false (vehicle is fresh) but bonus_jobs not empty
        bonus = data["data"]["bonus_jobs"]
        assert len(bonus) >= 1
        assert any(j["region"] == "Bretagne" for j in bonus)
        assert any("job_id" in j for j in bonus)

    def test_next_job_triggers_expansion(self, app, client):
        """First scan triggers _expand_collection_jobs and returns bonus jobs."""
        resp = client.get(
            "/api/market-prices/next-job?make=Renault&model=Talisman&year=2016"
            "&region=Ile-de-France&fuel=diesel&gearbox=manual&hp_range=120-150"
        )
        data = resp.get_json()
        assert data["data"]["collect"] is True
        bonus = data["data"]["bonus_jobs"]
        # Should have bonus jobs from expansion
        assert len(bonus) >= 1
        # Verify jobs were created in DB
        with app.app_context():
            from app.models.collection_job import CollectionJob
            total = CollectionJob.query.count()
            assert total > 0
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_api/test_market_api.py::TestNextJobWithQueue -v`
Expected: FAIL

**Step 3: Update next-job endpoint**

In `app/api/market_routes.py`, modify `next_market_job()`:

1. Accept new query params: `gearbox`, `hp_range`, `fiscal_hp`
2. Call `expand_collection_jobs()` on every request (deduplication handles repeats)
3. Replace `_compute_bonus_jobs()` with `pick_bonus_jobs(max_jobs=3)` — returns queued jobs with `job_id`
4. When `collect=false` AND queue has pending jobs → still return `bonus_jobs` (the fix)
5. Each bonus job in response includes `job_id` for completion callback

**Step 4: Run tests**

Run: `pytest tests/test_api/test_market_api.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add app/api/market_routes.py tests/test_api/test_market_api.py
git commit -m "feat(api): next-job uses CollectionJob queue, returns bonus even when fresh"
```

---

## Task 6: Add job completion callback endpoint

**Files:**
- Modify: `app/api/market_routes.py`
- Test: `tests/test_api/test_market_api.py`

**Step 1: Write failing test**

```python
class TestJobCompletion:
    def test_mark_job_done_via_api(self, app, client):
        """POST /api/market-prices/job-done marks job as done."""
        with app.app_context():
            from app.models.collection_job import CollectionJob
            job = CollectionJob(
                make="Renault", model="Talisman", year=2016,
                region="Bretagne", priority=1, source_vehicle="test",
                status="assigned",
            )
            db.session.add(job)
            db.session.commit()
            job_id = job.id

        resp = client.post(
            "/api/market-prices/job-done",
            data=json.dumps({"job_id": job_id, "success": True}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        with app.app_context():
            from app.models.collection_job import CollectionJob
            job = CollectionJob.query.get(job_id)
            assert job.status == "done"
```

**Step 2: Run test, verify fail**

**Step 3: Add POST `/api/market-prices/job-done` endpoint**

```python
@api_bp.route("/market-prices/job-done", methods=["POST"])
@limiter.limit("60/minute")
def mark_job_complete():
    data = request.get_json(silent=True)
    if not data or "job_id" not in data:
        return jsonify({"success": False, "error": "MISSING_JOB_ID"}), 400
    success = data.get("success", True)
    mark_job_done(data["job_id"], success=success)
    return jsonify({"success": True})
```

**Step 4: Run tests, verify pass**

**Step 5: Commit**

```bash
git add app/api/market_routes.py tests/test_api/test_market_api.py
git commit -m "feat(api): add /market-prices/job-done completion callback"
```

---

## Task 7: Extension — fix bonus execution when collect=false + HP range filter

**Files:**
- Modify: `extension/content.js`
- Test: `extension/tests/content.test.js`

**Step 1: Fix getHorsePowerRange to return tight ranges**

Replace the function at line ~1296:

```javascript
function getHorsePowerRange(hp) {
    if (!hp || hp <= 0) return null;
    if (hp < 80)  return "min-90";
    if (hp < 110) return "70-120";
    if (hp < 140) return "100-150";
    if (hp < 180) return "130-190";
    if (hp < 250) return "170-260";
    if (hp < 350) return "240-360";
    return "340-max";
}
```

**Step 2: Fix collect=false bonus execution**

At line ~1657, replace the early return block:

```javascript
if (!jobResp?.data?.collect) {
    const queuedJobs = jobResp?.data?.bonus_jobs || [];
    if (queuedJobs.length === 0) {
        // Truly nothing to do
        if (progress) {
            progress.update("job", "done", "Données déjà à jour, pas de collecte nécessaire");
            progress.update("collect", "skip", "Non nécessaire");
            progress.update("submit", "skip");
            progress.update("bonus", "skip");
        }
        return { submitted: false };
    }
    // Vehicle is fresh but we have queued bonus jobs to execute
    if (progress) {
        progress.update("job", "done", "Véhicule à jour — exécution de " + queuedJobs.length + " jobs en attente");
        progress.update("collect", "skip", "Véhicule déjà à jour");
        progress.update("submit", "skip");
    }
    // Execute bonus jobs from queue (reuse bonus execution logic)
    await executeBonusJobs(queuedJobs, progress);
    return { submitted: false };
}
```

**Step 3: Extract bonus execution into reusable function**

Extract lines ~1897-1961 into a new `async function executeBonusJobs(bonusJobs, progress)` that:
1. Iterates over bonus jobs (max 3)
2. For each job, builds LBC URL from job fields (make, model, year, region, fuel, hp_range, gearbox)
3. Fetches prices, POST to `/api/market-prices`
4. POST to `/api/market-prices/job-done` with `job_id` and `success`
5. Updates progress

**Step 4: Send hp_range, fiscal_hp, lbc_estimate in primary POST**

At line ~1867, add to the payload object:

```javascript
hp_range: hpRange,
fiscal_hp: parseInt(attrs?.horse_power_tax || attrs?.fiscal_hp || "0", 10) || null,
lbc_estimate_low: nextData?.props?.pageProps?.ad?.price_rating?.low || null,
lbc_estimate_high: nextData?.props?.pageProps?.ad?.price_rating?.high || null,
```

**Step 5: Send hp_range and gearbox in next-job request**

At line ~1637, add to the URL params:

```javascript
+ (gearbox ? `&gearbox=${encodeURIComponent(gearbox)}` : "")
+ (hpRange ? `&hp_range=${encodeURIComponent(hpRange)}` : "")
```

Note: `hpRange` needs to be computed before the next-job call. Move `getHorsePowerRange(hp)` computation earlier in the function.

**Step 6: Run extension tests**

Run: `npm test --prefix extension`
Expected: PASS (update existing tests as needed for new getHorsePowerRange return values)

**Step 7: Commit**

```bash
git add extension/content.js extension/tests/content.test.js
git commit -m "feat(extension): execute bonus jobs when collect=false, tighter HP ranges"
```

---

## Task 8: Admin /admin/issues page

**Files:**
- Modify: `app/admin/routes.py`
- Create: `app/admin/templates/admin/issues.html`
- Modify: `app/admin/templates/admin/base.html`

**Step 1: Add route in admin/routes.py**

```python
@admin_bp.route("/issues")
@login_required
def issues():
    """File d'attente des collectes argus (CollectionJob queue)."""
    from app.models.collection_job import CollectionJob

    status_filter = request.args.get("status", "").strip()
    make_filter = request.args.get("make", "").strip()
    page = request.args.get("page", 1, type=int)

    # Stats
    pending = CollectionJob.query.filter_by(status="pending").count()
    assigned = CollectionJob.query.filter_by(status="assigned").count()
    done = CollectionJob.query.filter_by(status="done").count()
    failed = CollectionJob.query.filter_by(status="failed").count()
    total = pending + assigned + done + failed
    completion_rate = round(done / total * 100) if total > 0 else 0

    # Query
    query = CollectionJob.query.order_by(
        CollectionJob.priority.asc(), CollectionJob.created_at.desc()
    )
    if status_filter:
        query = query.filter(CollectionJob.status == status_filter)
    if make_filter:
        query = query.filter(CollectionJob.make == make_filter)

    per_page = 50
    total_results = query.count()
    total_pages = max(1, (total_results + per_page - 1) // per_page)
    page = min(page, total_pages)
    records = query.offset((page - 1) * per_page).limit(per_page).all()

    make_list = [r[0] for r in db.session.query(CollectionJob.make).distinct().order_by(CollectionJob.make).all()]

    return render_template(
        "admin/issues.html",
        pending=pending, assigned=assigned, done=done, failed=failed,
        completion_rate=completion_rate,
        records=records, page=page, total_pages=total_pages,
        total_results=total_results,
        status_filter=status_filter, make_filter=make_filter,
        make_list=make_list,
    )


@admin_bp.route("/issues/purge-failed", methods=["POST"])
@login_required
def purge_failed_jobs():
    """Reset all failed jobs back to pending."""
    from app.models.collection_job import CollectionJob
    count = CollectionJob.query.filter_by(status="failed").update(
        {"status": "pending", "attempts": 0}
    )
    db.session.commit()
    flash(f"{count} jobs failed remis en attente.", "success")
    return redirect(url_for("admin.issues"))
```

**Step 2: Create issues.html template**

Create `app/admin/templates/admin/issues.html` with:
- 5 stat cards (pending, assigned, done, failed, completion rate)
- Filter by status, by make
- Table: Priority, Vehicule, Motorisation (fuel + hp_range + gearbox), Region, Status (colored badge), Cree le, Source
- Pagination
- Button "Purger les failed"

**Step 3: Add sidebar link in base.html**

After the Argus maison link (line ~73), add:

```html
<a class="nav-link {% if request.endpoint == 'admin.issues' %}active{% endif %}"
   href="{{ url_for('admin.issues') }}">Issues collecte</a>
```

**Step 4: Commit**

```bash
git add app/admin/routes.py app/admin/templates/admin/issues.html app/admin/templates/admin/base.html
git commit -m "feat(admin): add /admin/issues page for collection job queue"
```

---

## Task 9: Admin argus — add motorisation column + LBC validation badge

**Files:**
- Modify: `app/admin/routes.py` (argus route — pass validation data)
- Modify: `app/admin/templates/admin/argus.html`

**Step 1: Update argus route to compute validation**

In the `argus()` route, after building `records`, compute validation for each record:

```python
for r in records:
    r._validation = None  # default
    if r.lbc_estimate_low and r.lbc_estimate_high and r.price_iqr_mean:
        iqr = r.price_iqr_mean
        low, high = r.lbc_estimate_low, r.lbc_estimate_high
        if low <= iqr <= high:
            r._validation = "valid"
        elif iqr < low * 0.85 or iqr > high * 1.15:
            r._validation = "ecart"
        else:
            r._validation = "proche"
```

Add stat card for global validation rate:

```python
validated = sum(1 for r in all_market if r.lbc_estimate_low and r.lbc_estimate_high
                and r.price_iqr_mean and r.lbc_estimate_low <= r.price_iqr_mean <= r.lbc_estimate_high)
total_with_lbc = sum(1 for r in all_market if r.lbc_estimate_low and r.lbc_estimate_high)
validation_rate = round(validated / total_with_lbc * 100) if total_with_lbc > 0 else 0
```

**Step 2: Update argus.html — add Motorisation column and Validation column**

After the "Vehicule" column, add "Motorisation":

```html
<th>Motorisation</th>
```

In the row:

```html
<td style="font-size:12px">
  {% if m.fuel %}<span class="badge bg-secondary">{{ m.fuel }}</span>{% endif %}
  {% if m.hp_range %}<span class="badge bg-info text-dark">{{ m.hp_range }}ch</span>{% endif %}
  {% if m.fiscal_hp %}<span class="text-muted">{{ m.fiscal_hp }}cv</span>{% endif %}
</td>
```

After "Fraicheur" column, add "Validation LBC":

```html
<th class="text-center">Validation LBC</th>
```

In the row:

```html
<td class="text-center">
  {% if m._validation == "valid" %}
    <span class="badge bg-success" title="IQR mean dans la fourchette LBC">Valide</span>
  {% elif m._validation == "proche" %}
    <span class="badge bg-warning text-dark" title="IQR mean proche fourchette LBC (+-15%)">Proche</span>
  {% elif m._validation == "ecart" %}
    <span class="badge bg-danger" title="IQR mean hors fourchette LBC (>15%)">Ecart</span>
  {% else %}
    <span class="text-muted" style="font-size:11px">-</span>
  {% endif %}
</td>
```

Add validation stat card in the stats row.

**Step 3: Commit**

```bash
git add app/admin/routes.py app/admin/templates/admin/argus.html
git commit -m "feat(admin): argus shows motorisation column + LBC validation badges"
```

---

## Task 10: Run full test suite + ruff

**Step 1: Run ruff**

```bash
ruff check app/ tests/ --fix
ruff format app/ tests/
```

**Step 2: Run full test suite**

```bash
pytest -v
```

Expected: ALL PASS, 0 ruff errors

**Step 3: Final commit if any fixes**

```bash
git add -A
git commit -m "chore: ruff fixes and test cleanup"
```
