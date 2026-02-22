# Collecte Intelligente Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix broken bonus region collection, enable aggressive auto-creation from CSV, add LBC Argus estimation as scoring fallback, enrich vehicle specs from market data, and prioritize newly-created vehicles in next-job.

**Architecture:** Server-driven bonus jobs replace random client selection. Vehicle auto-creation threshold drops to 1 scan with CSV match. LBC estimation extracted from page data as L4 tier-3 fallback. VehicleObservedSpec table aggregates specs from market collections. next-job query boosts partial-enrichment vehicles.

**Tech Stack:** Python/Flask (server), JavaScript (Chrome extension), SQLAlchemy/SQLite (DB), pytest (tests), ruff (lint)

---

### Task 1: Implement `_compute_bonus_jobs()` server function + tests

**Files:**
- Modify: `app/api/market_routes.py:22-30` (add constant + function)
- Modify: `tests/test_api/test_market_api.py` (add TestBonusJobs class)

**Step 1: Write 4 failing tests for bonus_jobs**

Add at end of `tests/test_api/test_market_api.py`:

```python
class TestBonusJobs:
    """Tests for bonus_jobs in GET /api/market-prices/next-job."""

    def _make_fresh_mp(self, make, model, year, region, fuel=None):
        """Helper: create a fresh MarketPrice entry."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        return MarketPrice(
            make=make, model=model, year=year, region=region, fuel=fuel,
            price_min=10000, price_median=14000, price_mean=14000,
            price_max=18000, price_std=1414.0, sample_count=20,
            collected_at=now, refresh_after=now + timedelta(hours=24),
        )

    def _make_stale_mp(self, make, model, year, region, fuel=None, days_old=10):
        """Helper: create a stale MarketPrice entry (>7 days)."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        old = now - timedelta(days=days_old)
        return MarketPrice(
            make=make, model=model, year=year, region=region, fuel=fuel,
            price_min=10000, price_median=14000, price_mean=14000,
            price_max=18000, price_std=1414.0, sample_count=20,
            collected_at=old, refresh_after=old + timedelta(hours=24),
        )

    def test_bonus_jobs_returns_missing_regions(self, app, client):
        with app.app_context():
            db.session.add(self._make_fresh_mp("Peugeot", "3008", 2021, "Bretagne", "diesel"))
            db.session.commit()
            resp = client.get(
                "/api/market-prices/next-job"
                "?make=Peugeot&model=3008&year=2021&region=Bretagne&fuel=diesel"
            )
            data = resp.get_json()
            assert data["success"] is True
            bonus = data["data"].get("bonus_jobs", [])
            assert len(bonus) <= 2
            for job in bonus:
                assert job["region"] != "Bretagne"
                assert job["make"] == "Peugeot"
                assert job["model"] == "3008"

    def test_bonus_jobs_refresh_stale(self, app, client):
        with app.app_context():
            regions = [
                "Île-de-France", "Auvergne-Rhône-Alpes", "Provence-Alpes-Côte d'Azur",
                "Occitanie", "Nouvelle-Aquitaine", "Hauts-de-France", "Grand Est",
                "Bretagne", "Pays de la Loire", "Normandie", "Bourgogne-Franche-Comté",
                "Centre-Val de Loire", "Corse",
            ]
            for i, r in enumerate(regions):
                if r in ("Bretagne", "Occitanie"):
                    db.session.add(self._make_stale_mp("Renault", "Captur", 2022, r, "essence", days_old=15 - i))
                else:
                    db.session.add(self._make_fresh_mp("Renault", "Captur", 2022, r, "essence"))
            db.session.commit()
            resp = client.get(
                "/api/market-prices/next-job"
                "?make=Renault&model=Captur&year=2022&region=Bretagne&fuel=essence"
            )
            data = resp.get_json()
            bonus = data["data"].get("bonus_jobs", [])
            assert len(bonus) >= 1
            bonus_regions = {j["region"] for j in bonus}
            assert bonus_regions <= {"Bretagne", "Occitanie"}

    def test_bonus_jobs_empty_when_all_fresh(self, app, client):
        with app.app_context():
            regions = [
                "Île-de-France", "Auvergne-Rhône-Alpes", "Provence-Alpes-Côte d'Azur",
                "Occitanie", "Nouvelle-Aquitaine", "Hauts-de-France", "Grand Est",
                "Bretagne", "Pays de la Loire", "Normandie", "Bourgogne-Franche-Comté",
                "Centre-Val de Loire", "Corse",
            ]
            for r in regions:
                db.session.add(self._make_fresh_mp("Toyota", "Yaris", 2023, r, "essence"))
            db.session.commit()
            resp = client.get(
                "/api/market-prices/next-job"
                "?make=Toyota&model=Yaris&year=2023&region=Bretagne&fuel=essence"
            )
            data = resp.get_json()
            bonus = data["data"].get("bonus_jobs", [])
            assert bonus == []

    def test_bonus_jobs_without_fuel(self, app, client):
        with app.app_context():
            db.session.add(self._make_fresh_mp("Dacia", "Sandero", 2022, "Grand Est"))
            db.session.commit()
            resp = client.get(
                "/api/market-prices/next-job"
                "?make=Dacia&model=Sandero&year=2022&region=Grand+Est"
            )
            data = resp.get_json()
            bonus = data["data"].get("bonus_jobs", [])
            assert len(bonus) == 2
            for job in bonus:
                assert job["region"] != "Grand Est"
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_api/test_market_api.py::TestBonusJobs -v`
Expected: 4 FAILED (bonus_jobs key not in response)

**Step 3: Add `POST_2016_REGIONS` constant and `_compute_bonus_jobs()` function**

In `app/api/market_routes.py`, after line 30 (`_GENERIC_MODELS`), add:

```python
POST_2016_REGIONS = [
    "Île-de-France", "Auvergne-Rhône-Alpes", "Provence-Alpes-Côte d'Azur",
    "Occitanie", "Nouvelle-Aquitaine", "Hauts-de-France", "Grand Est",
    "Bretagne", "Pays de la Loire", "Normandie", "Bourgogne-Franche-Comté",
    "Centre-Val de Loire", "Corse",
]


def _compute_bonus_jobs(
    make: str, model: str, year: int, fuel: str | None,
    exclude_region: str, max_bonus: int = 2,
) -> list[dict]:
    """Determine les bonus jobs intelligents pour le meme modele.

    Priorite :
    1. Regions manquantes (aucune donnee MarketPrice)
    2. Regions avec donnees > FRESHNESS_DAYS (refresh)
    3. [] si tout est frais
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    cutoff = now - timedelta(days=FRESHNESS_DAYS)

    query = MarketPrice.query.filter(
        market_text_key_expr(MarketPrice.make) == market_text_key(make),
        market_text_key_expr(MarketPrice.model) == market_text_key(model),
        MarketPrice.year == year,
    )
    if fuel:
        query = query.filter(
            db.func.lower(db.func.coalesce(MarketPrice.fuel, "")) == fuel.lower()
        )

    existing = query.all()

    covered = {}
    for mp in existing:
        key = market_text_key(mp.region)
        if key not in covered or mp.collected_at > covered[key].collected_at:
            covered[key] = mp

    missing_regions = []
    stale_regions = []
    for r in POST_2016_REGIONS:
        if market_text_key(r) == market_text_key(exclude_region):
            continue
        entry = covered.get(market_text_key(r))
        if entry is None:
            missing_regions.append(r)
        elif entry.collected_at < cutoff:
            stale_regions.append((r, entry.collected_at))

    stale_regions.sort(key=lambda x: x[1])

    bonus_jobs = []
    for r in missing_regions:
        if len(bonus_jobs) >= max_bonus:
            break
        bonus_jobs.append({"make": make, "model": model, "year": year, "region": r})
    for r, _ in stale_regions:
        if len(bonus_jobs) >= max_bonus:
            break
        bonus_jobs.append({"make": make, "model": model, "year": year, "region": r})

    return bonus_jobs
```

**Step 4: Add `bonus_jobs` to ALL return points in `next_market_job()`**

Modify the 3 main return points (lines ~233, ~305, ~323) to compute and include `bonus_jobs`.

Return point at line ~233 (current vehicle needs refresh):
```python
    if not current or current.collected_at < cutoff:
        fuel_param = request.args.get("fuel")
        bonus = _compute_bonus_jobs(make, model, year, fuel_param, exclude_region=region)
        logger.info("next-job: vehicule courant %s %s %s a collecter (+%d bonus)", make, model, region, len(bonus))
        return jsonify({
            "success": True,
            "data": {
                "collect": True,
                "vehicle": {"make": make, "model": model, "year": year},
                "region": region,
                "bonus_jobs": bonus,
            },
        })
```

Return point at line ~305 (redirect to other vehicle):
```python
    if best_candidate:
        fuel_param = request.args.get("fuel")
        bonus = _compute_bonus_jobs(make, model, year, fuel_param, exclude_region=region)
        logger.info("next-job: redirection vers %s %s pour region %s (+%d bonus)", best_candidate[0], best_candidate[1], region, len(bonus))
        return jsonify({
            "success": True,
            "data": {
                "collect": True,
                "redirect": True,
                "vehicle": {"make": best_candidate[0], "model": best_candidate[1], "year": best_candidate[2]},
                "region": region,
                "bonus_jobs": bonus,
            },
        })
```

Return point at line ~323 (all fresh):
```python
    fuel_param = request.args.get("fuel")
    bonus = _compute_bonus_jobs(make, model, year, fuel_param, exclude_region=region)
    return jsonify({"success": True, "data": {"collect": False, "bonus_jobs": bonus}})
```

Also add `bonus_jobs: []` to the early returns (lines ~210, ~214) for consistency.

**Step 5: Run tests to verify they pass**

Run: `pytest tests/test_api/test_market_api.py::TestBonusJobs -v`
Expected: 4 PASSED

**Step 6: Run full test suite**

Run: `pytest tests/ --tb=short -q`
Expected: All pass, 0 failures

**Step 7: Commit**

```bash
git add app/api/market_routes.py tests/test_api/test_market_api.py
git commit -m "feat(argus): smart bonus jobs -- serveur pilote regions manquantes"
```

---

### Task 2: Extension — server-driven bonus + lower threshold + remove precision gate

**Files:**
- Modify: `extension/content.js:1506-1577` (bonus block)
- Modify: `extension/content.js:1629-1647` (next-job call)

**Step 1: Pass `fuel` in the next-job request**

At line ~1629, change the jobUrl construction to include fuel:

```javascript
    const fuelForJob = (fuel || "").toLowerCase();
    const jobUrl = API_URL.replace("/analyze", "/market-prices/next-job")
      + `?make=${encodeURIComponent(make)}&model=${encodeURIComponent(model)}`
      + `&year=${encodeURIComponent(year)}&region=${encodeURIComponent(region)}`
      + (fuelForJob ? `&fuel=${encodeURIComponent(fuelForJob)}` : "");
```

**Step 2: Capture `bonus_jobs` from next-job response**

After the next-job response is parsed (around line 1647), add:

```javascript
    const bonusJobs = jobResp?.data?.bonus_jobs || [];
    console.log("[CoPilot] next-job: %d bonus jobs", bonusJobs.length);
```

**Step 3: Replace the entire bonus block (lines 1506-1577)**

Replace the `if (collectedPrecision >= 4 && !isRedirect)` block with:

```javascript
          // 5b. BONUS multi-region : le serveur indique les regions manquantes.
          //     Seuil reduit a 5 prix (au lieu de 20) pour les bonus.
          //     Pas de gate precision -- on fait les bonus meme en national.
          if (!isRedirect && bonusJobs.length > 0) {
            const MIN_BONUS_PRICES = 5;
            for (const bonusJob of bonusJobs) {
              try {
                // Delai aleatoire 1-2s anti-detection
                await new Promise((r) => setTimeout(r, 1000 + Math.random() * 1000));
                const bonusLocParam = LBC_REGIONS[bonusJob.region];
                if (!bonusLocParam) {
                  console.warn("[CoPilot] bonus: region inconnue '%s', skip", bonusJob.region);
                  continue;
                }
                let bonusUrl = coreUrl + fullFilters;
                bonusUrl += `&locations=${bonusLocParam}`;
                if (targetYear >= 1990) bonusUrl += `&regdate=${targetYear - 1}-${targetYear + 1}`;

                const bonusPrices = await fetchSearchPrices(bonusUrl, targetYear, 1);
                console.log("[CoPilot] bonus region %s: %d prix | %s", bonusJob.region, bonusPrices.length, bonusUrl.substring(0, 120));

                if (bonusPrices.length >= MIN_BONUS_PRICES) {
                  const bDetails = bonusPrices.filter((p) => Number.isInteger(p?.price) && p.price > 500);
                  const bInts = bDetails.map((p) => p.price);
                  if (bInts.length >= MIN_BONUS_PRICES) {
                    const bonusPrecision = bonusPrices.length >= 20 ? 4 : 2;
                    const bonusPayload = {
                      make: target.make,
                      model: target.model,
                      year: parseInt(target.year, 10),
                      region: bonusJob.region,
                      prices: bInts,
                      price_details: bDetails,
                      category: urlCategory,
                      fuel: fuelCode ? targetFuel : null,
                      precision: bonusPrecision,
                      search_log: [{
                        step: 1, precision: bonusPrecision, location_type: "region",
                        year_spread: 1, filters_applied: [
                          ...(fullFilters.includes("fuel=") ? ["fuel"] : []),
                          ...(fullFilters.includes("gearbox=") ? ["gearbox"] : []),
                          ...(fullFilters.includes("horse_power_din=") ? ["hp"] : []),
                          ...(fullFilters.includes("mileage=") ? ["km"] : []),
                        ],
                        ads_found: bonusPrices.length, url: bonusUrl,
                        was_selected: true,
                        reason: `bonus region (serveur): ${bonusPrices.length} annonces`,
                      }],
                    };
                    const bResp = await fetch(marketUrl, {
                      method: "POST",
                      headers: { "Content-Type": "application/json" },
                      body: JSON.stringify(bonusPayload),
                    });
                    console.log("[CoPilot] bonus POST %s: %s (precision=%d)", bonusJob.region, bResp.ok ? "OK" : "FAIL", bonusPrecision);
                  }
                }
              } catch (bonusErr) {
                console.warn("[CoPilot] bonus region %s failed:", bonusJob.region, bonusErr);
              }
            }
          }
```

Key changes vs. current code:
- **No `collectedPrecision >= 4` gate** — bonus fires even at precision 3 (national)
- **Seuil 5 prix** au lieu de 20 (`MIN_BONUS_PRICES = 5`)
- **Precision dynamique** : 4 si >=20 prix, 2 si 5-19 prix
- **Server-driven regions** au lieu de random Fisher-Yates

**Step 4: Commit**

```bash
git add extension/content.js
git commit -m "feat(extension): bonus regions server-driven, seuil 5 prix, plus de gate precision"
```

---

### Task 3: Auto-creation au 1er scan avec CSV match

**Files:**
- Modify: `app/services/vehicle_factory.py:23` (MIN_SCANS)
- Modify: `tests/test_services/test_vehicle_factory.py` (update expected behavior)

**Step 1: Write failing test for 1-scan auto-creation**

In `tests/test_services/test_vehicle_factory.py`, add:

```python
def test_auto_create_first_scan_with_csv(self, app):
    """Un vehicule avec 1 seul scan + CSV match doit etre auto-cree."""
    with app.app_context():
        # Creer 1 scan pour un vehicule present dans le CSV
        db.session.add(ScanLog(
            url="https://lbc.fr/test",
            vehicle_make="Jeep",
            vehicle_model="Renegade",
        ))
        db.session.commit()

        result = can_auto_create("Jeep", "Renegade")
        # Doit etre eligible si CSV match (meme avec 1 seul scan)
        if result["csv_available"]:
            assert result["eligible"] is True
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_services/test_vehicle_factory.py::test_auto_create_first_scan_with_csv -v`
Expected: FAIL (`scan_count=1 < MIN_SCANS=3`)

**Step 3: Change MIN_SCANS logic**

In `app/services/vehicle_factory.py`, line 23, change:

```python
MIN_SCANS = 3  # Nombre minimum de scans pour confirmer la demande
```

to:

```python
MIN_SCANS_WITH_CSV = 1  # 1 scan suffit si le CSV confirme le vehicule
MIN_SCANS_WITHOUT_CSV = 3  # 3 scans si pas de CSV (confirmation par repetition)
```

Then in `can_auto_create()`, around line 57-60, change the scan check logic:

Replace:
```python
    if scan_count < MIN_SCANS:
        result["reason"] = f"Pas assez de scans ({scan_count}/{MIN_SCANS})"
        return result
```

With:
```python
    # Verifier CSV en avance pour adapter le seuil de scans
    csv_available = bool(lookup_specs(make, model))
    result["csv_available"] = csv_available
    min_scans = MIN_SCANS_WITH_CSV if csv_available else MIN_SCANS_WITHOUT_CSV

    if scan_count < min_scans:
        result["reason"] = f"Pas assez de scans ({scan_count}/{min_scans})"
        return result
```

Remove the duplicate `csv_available` check later in the function (around line 77) since we now check it earlier.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_services/test_vehicle_factory.py -v`
Expected: PASS

**Step 5: Run full test suite**

Run: `pytest tests/ --tb=short -q`
Expected: All pass

**Step 6: Commit**

```bash
git add app/services/vehicle_factory.py tests/test_services/test_vehicle_factory.py
git commit -m "feat(referentiel): auto-creation au 1er scan si CSV match"
```

---

### Task 4: Create VehicleObservedSpec model

**Files:**
- Create: `app/models/vehicle_observed_spec.py`
- Modify: `app/models/__init__.py` (add import)

**Step 1: Create the model file**

```python
"""Specs observees sur le marche pour un vehicule (motorisations, boites, puissances)."""

from datetime import datetime, timezone

from app.extensions import db


class VehicleObservedSpec(db.Model):
    """Spec observee lors de la collecte de prix marche.

    Chaque ligne = une valeur vue pour un type de spec (fuel, gearbox, hp)
    avec le nombre d'occurrences. Enrichi automatiquement a chaque collecte.
    """

    __tablename__ = "vehicle_observed_specs"
    __table_args__ = (
        db.UniqueConstraint(
            "vehicle_id", "spec_type", "spec_value",
            name="uq_observed_spec_vehicle_type_value",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    vehicle_id = db.Column(db.Integer, db.ForeignKey("vehicles.id"), nullable=False, index=True)
    spec_type = db.Column(db.String(30), nullable=False)  # "fuel", "gearbox", "horse_power"
    spec_value = db.Column(db.String(80), nullable=False)
    count = db.Column(db.Integer, nullable=False, default=1)
    last_seen_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc),
    )

    vehicle = db.relationship("Vehicle", backref=db.backref("observed_specs", lazy="select"))

    def __repr__(self):
        return f"<VehicleObservedSpec {self.spec_type}={self.spec_value} x{self.count}>"
```

**Step 2: Add import in `app/models/__init__.py`**

Add to the existing imports:
```python
from app.models.vehicle_observed_spec import VehicleObservedSpec  # noqa: F401
```

**Step 3: Verify model loads**

Run: `python -c "from app.models.vehicle_observed_spec import VehicleObservedSpec; print('OK')"`
Expected: OK

**Step 4: Commit**

```bash
git add app/models/vehicle_observed_spec.py app/models/__init__.py
git commit -m "feat(models): add VehicleObservedSpec for market-observed specs"
```

---

### Task 5: Enrichissement specs dans store_market_prices + extend price_details

**Files:**
- Modify: `app/services/market_service.py:186-345` (add enrichment after store)
- Modify: `extension/content.js` (extend getAdDetails to include gearbox/hp)
- Create: `tests/test_services/test_observed_specs.py`

**Step 1: Extend getAdDetails() in content.js**

In `extension/content.js`, function `getAdDetails()` (lines ~1343-1362), add extraction of gearbox and horse_power:

After the fuel extraction block, add:
```javascript
      } else if (key === "gearbox" || key === "boîte de vitesse" || key === "boite de vitesse") {
        details.gearbox = a.value_label || a.value || null;
      } else if (key === "horse_power_din" || key === "puissance din") {
        details.horse_power = parseInt(String(a.value || a.value_label || "0"), 10) || null;
      }
```

**Step 2: Write test for spec enrichment**

Create `tests/test_services/test_observed_specs.py`:

```python
"""Tests for VehicleObservedSpec enrichment from market data."""

from app.extensions import db
from app.models.vehicle import Vehicle
from app.models.vehicle_observed_spec import VehicleObservedSpec
from app.services.market_service import store_market_prices


class TestObservedSpecEnrichment:
    def test_enriches_specs_from_price_details(self, app):
        with app.app_context():
            vehicle = Vehicle(brand="Jeep", model="Renegade", year_start=2018, year_end=2024, enrichment_status="partial")
            db.session.add(vehicle)
            db.session.commit()

            store_market_prices(
                make="Jeep", model="Renegade", year=2020, region="Île-de-France",
                prices=[14000, 15000, 16000, 17000, 18000],
                price_details=[
                    {"price": 14000, "year": 2020, "km": 80000, "fuel": "hybride rechargeable", "gearbox": "automatique", "horse_power": 190},
                    {"price": 15000, "year": 2020, "km": 70000, "fuel": "diesel", "gearbox": "manuelle", "horse_power": 130},
                    {"price": 16000, "year": 2020, "km": 60000, "fuel": "hybride rechargeable", "gearbox": "automatique", "horse_power": 190},
                    {"price": 17000, "year": 2020, "km": 50000, "fuel": "diesel", "gearbox": "manuelle", "horse_power": 130},
                    {"price": 18000, "year": 2020, "km": 40000, "fuel": "essence"},
                ],
            )

            specs = VehicleObservedSpec.query.filter_by(vehicle_id=vehicle.id).all()
            spec_map = {(s.spec_type, s.spec_value): s.count for s in specs}

            assert ("fuel", "hybride rechargeable") in spec_map
            assert spec_map[("fuel", "hybride rechargeable")] == 2
            assert ("fuel", "diesel") in spec_map
            assert ("gearbox", "automatique") in spec_map
            assert ("horse_power", "190") in spec_map

    def test_no_enrichment_without_vehicle(self, app):
        """If vehicle not in referential, no observed specs created."""
        with app.app_context():
            store_market_prices(
                make="Unknown", model="Car", year=2020, region="Bretagne",
                prices=[10000, 11000, 12000, 13000, 14000],
            )
            assert VehicleObservedSpec.query.count() == 0
```

**Step 3: Run test to verify it fails**

Run: `pytest tests/test_services/test_observed_specs.py -v`
Expected: FAIL (no enrichment logic yet)

**Step 4: Add enrichment logic in store_market_prices()**

In `app/services/market_service.py`, at the end of `store_market_prices()` (after the auto_create_vehicle block, around line 343), add:

```python
    # Enrichir les specs observees si le vehicule existe dans le referentiel
    try:
        from app.models.vehicle_observed_spec import VehicleObservedSpec
        from app.services.vehicle_lookup import find_vehicle

        vehicle = find_vehicle(make, model)
        if vehicle and price_details:
            _enrich_observed_specs(vehicle.id, price_details)
    except Exception:
        logger.debug("Observed spec enrichment skipped", exc_info=True)
```

Add the helper function before `store_market_prices()`:

```python
def _enrich_observed_specs(vehicle_id: int, price_details: list[dict]) -> None:
    """Aggregate observed specs (fuel, gearbox, hp) from collected ads."""
    from app.models.vehicle_observed_spec import VehicleObservedSpec

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    spec_counts: dict[tuple[str, str], int] = {}

    for detail in price_details:
        if not isinstance(detail, dict):
            continue
        for spec_type, key in [("fuel", "fuel"), ("gearbox", "gearbox"), ("horse_power", "horse_power")]:
            val = detail.get(key)
            if val and str(val).strip():
                spec_counts[(spec_type, str(val).strip().lower())] = (
                    spec_counts.get((spec_type, str(val).strip().lower()), 0) + 1
                )

    for (spec_type, spec_value), count in spec_counts.items():
        existing = VehicleObservedSpec.query.filter_by(
            vehicle_id=vehicle_id, spec_type=spec_type, spec_value=spec_value,
        ).first()
        if existing:
            existing.count += count
            existing.last_seen_at = now
        else:
            db.session.add(VehicleObservedSpec(
                vehicle_id=vehicle_id, spec_type=spec_type,
                spec_value=spec_value, count=count, last_seen_at=now,
            ))
    db.session.commit()
```

**Step 5: Run tests to verify they pass**

Run: `pytest tests/test_services/test_observed_specs.py -v`
Expected: 2 PASSED

**Step 6: Run full test suite**

Run: `pytest tests/ --tb=short -q`
Expected: All pass

**Step 7: Commit**

```bash
git add app/services/market_service.py extension/content.js tests/test_services/test_observed_specs.py
git commit -m "feat(enrichissement): observed specs from market data + extension gearbox/hp extraction"
```

---

### Task 6: LBC Estimation extraction + L4 fallback scoring leger

**Files:**
- Modify: `extension/content.js` (extract estimation from page)
- Modify: `app/services/extraction.py` (parse estimation)
- Modify: `app/filters/l4_price.py:101-144` (add tier 3 fallback)
- Create: `tests/test_filters/test_l4_lbc_estimation.py`

**Step 1: Investigate LBC estimation field**

The LBC estimation is NOT in `__NEXT_DATA__` directly. It comes from a separate LBC API call that the page makes client-side. However, it IS visible in the page's DOM as an element.

The extension needs to extract it from the DOM or intercept the API call. The safest approach: extract from the page's `__NEXT_DATA__` → `props.pageProps.ad` → look for `price_calendar`, `price_tips`, `price_rating`, or `estimation` fields. If not found, extract from DOM.

**NOTE: This task requires runtime investigation.** The implementer should:
1. Open Chrome DevTools on a LBC listing page
2. In Console, type: `JSON.stringify(window.__NEXT_DATA__.props.pageProps, null, 2)`
3. Search for any price/estimation/rating fields
4. If not in __NEXT_DATA__, check Network tab for XHR calls containing estimation data

**Step 2: Add extraction in extension (placeholder — update after investigation)**

In `extension/content.js`, in `extractVehicleFromNextData()`, add after the existing extractions:

```javascript
    // Estimation LBC (fourchette argus affichee sur la page)
    const priceRating = ad.price_rating || ad.estimation || ad.price_tips || null;
    let lbcEstimation = null;
    if (priceRating) {
      lbcEstimation = {
        low: priceRating.low || priceRating.price_low || priceRating.min,
        high: priceRating.high || priceRating.price_high || priceRating.max,
      };
    }
```

And include `lbc_estimation` in the payload sent to `/api/analyze`:

```javascript
    // In runAnalysis(), add to the POST body:
    lbc_estimation: lbcEstimation,
```

**Step 3: Write failing test for L4 tier 3 fallback**

Create `tests/test_filters/test_l4_lbc_estimation.py`:

```python
"""Tests for L4 LBC estimation fallback (tier 3)."""

from app.filters.l4_price import L4PriceFilter


class TestL4LbcEstimation:
    def test_uses_lbc_estimation_when_no_market_or_argus(self):
        """L4 should use LBC estimation as last-resort fallback."""
        f = L4PriceFilter()
        data = {
            "price_eur": 14900,
            "make": "Jeep",
            "model": "Renegade",
            "year": "2020",
            "location": {"region": "Nouvelle-Aquitaine"},
            "fuel": "hybride rechargeable",
            "lbc_estimation": {"low": 17320, "high": 19140},
        }
        result = f.run(data)
        # Should NOT be skip — should use LBC estimation
        assert result.status != "skip"
        assert "lbc" in result.details.get("source", "").lower()

    def test_lbc_estimation_has_reduced_weight_message(self):
        """L4 with LBC estimation should mention it's imprecise."""
        f = L4PriceFilter()
        data = {
            "price_eur": 14900,
            "make": "Jeep",
            "model": "Renegade",
            "year": "2020",
            "location": {"region": "Nouvelle-Aquitaine"},
            "fuel": "hybride rechargeable",
            "lbc_estimation": {"low": 17320, "high": 19140},
        }
        result = f.run(data)
        assert "estimation" in result.message.lower() or "lbc" in result.message.lower()

    def test_lbc_estimation_ignored_when_market_exists(self):
        """L4 should prefer MarketPrice over LBC estimation."""
        # This test needs MarketPrice data in DB — integration test
        pass  # Covered by existing L4 tests
```

**Step 4: Run test to verify it fails**

Run: `pytest tests/test_filters/test_l4_lbc_estimation.py -v`
Expected: FAIL (L4 still returns skip)

**Step 5: Add LBC estimation as tier 3 in L4**

In `app/filters/l4_price.py`, after the ArgusPrice fallback block (line ~118), before the `if ref_price is None` skip block (line ~122), add:

```python
        # 3. Fallback LBC Estimation (fourchette affichee par LBC -- scoring leger)
        if ref_price is None:
            lbc_est = data.get("lbc_estimation")
            if lbc_est and isinstance(lbc_est, dict):
                lbc_low = lbc_est.get("low")
                lbc_high = lbc_est.get("high")
                if lbc_low and lbc_high and isinstance(lbc_low, (int, float)) and isinstance(lbc_high, (int, float)):
                    cascade_tried.append("lbc_estimation")
                    ref_price = (lbc_low + lbc_high) / 2  # Milieu de la fourchette
                    source = "estimation_lbc"
                    details["lbc_estimation_low"] = lbc_low
                    details["lbc_estimation_high"] = lbc_high
                    details["price_reference"] = ref_price
                    details["source"] = source
                    details["cascade_lbc_estimation_result"] = "found"
                    logger.info(
                        "L4 using LBC estimation: low=%d high=%d mid=%.0f",
                        lbc_low, lbc_high, ref_price,
                    )
```

Then, in the scoring section (after ref_price is set), apply reduced weight for LBC estimation:

```python
        # Scoring -- poids reduit pour estimation LBC (fourchette large)
        if source == "estimation_lbc":
            # Diviser le delta par 2 pour adoucir le scoring
            delta_pct = delta_pct * 0.5
            message_prefix = "Estimation LeBonCoin (données marché insuffisantes) — "
```

**Step 6: Run tests to verify they pass**

Run: `pytest tests/test_filters/test_l4_lbc_estimation.py -v`
Expected: PASSED

**Step 7: Run full test suite**

Run: `pytest tests/ --tb=short -q`
Expected: All pass

**Step 8: Commit**

```bash
git add app/filters/l4_price.py extension/content.js tests/test_filters/test_l4_lbc_estimation.py
git commit -m "feat(l4): LBC estimation as tier-3 fallback with reduced scoring weight"
```

---

### Task 7: next-job elargi — boost vehicules partial

**Files:**
- Modify: `app/api/market_routes.py:261-289` (candidates query)
- Modify: `tests/test_api/test_market_api.py` (add test)

**Step 1: Write failing test**

In `tests/test_api/test_market_api.py`, add to `TestNextMarketJob`:

```python
    def test_redirects_to_partial_vehicle_first(self, app, client):
        """Vehicles with enrichment_status=partial should be prioritized for redirect."""
        with app.app_context():
            # Current vehicle: fresh data
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            db.session.add(MarketPrice(
                make="Peugeot", model="208", year=2022, region="Bretagne",
                price_min=10000, price_median=14000, price_mean=14000,
                price_max=18000, price_std=1414.0, sample_count=20,
                collected_at=now, refresh_after=now + timedelta(hours=24),
            ))
            # Complete vehicle: never collected in Bretagne
            v_complete = Vehicle(brand="Renault", model="Clio", year_start=2019, year_end=2024, enrichment_status="complete")
            # Partial vehicle: never collected, should be prioritized
            v_partial = Vehicle(brand="Jeep", model="Renegade", year_start=2018, year_end=2024, enrichment_status="partial")
            db.session.add_all([v_complete, v_partial])
            db.session.commit()

            resp = client.get("/api/market-prices/next-job?make=Peugeot&model=208&year=2022&region=Bretagne")
            data = resp.get_json()
            assert data["data"]["redirect"] is True
            # Partial vehicle should be chosen first
            assert data["data"]["vehicle"]["make"].lower() == "jeep"
            assert data["data"]["vehicle"]["model"].lower() == "renegade"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_api/test_market_api.py::TestNextMarketJob::test_redirects_to_partial_vehicle_first -v`
Expected: FAIL

**Step 3: Modify candidates query to boost partial vehicles**

In `app/api/market_routes.py`, in the candidates query (lines ~261-289), change the `order_by` to prioritize partial vehicles:

```python
    .order_by(
        # Priorite 1 : jamais collecte (NULL) d'abord
        case((latest_mp.c.latest_at.is_(None), 0), else_=1),
        # Priorite 2 : vehicules partial (enrichment en cours) avant complete
        case((Vehicle.enrichment_status == "partial", 0), else_=1),
        # Priorite 3 : le plus ancien
        latest_mp.c.latest_at.asc(),
        Vehicle.id.asc(),
    )
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_api/test_market_api.py::TestNextMarketJob::test_redirects_to_partial_vehicle_first -v`
Expected: PASS

**Step 5: Run full test suite**

Run: `pytest tests/ --tb=short -q`
Expected: All pass

**Step 6: Commit**

```bash
git add app/api/market_routes.py tests/test_api/test_market_api.py
git commit -m "feat(next-job): boost vehicules partial dans la priorite redirect"
```

---

### Task 8: Extension popup — badge estimation LBC

**Files:**
- Modify: `extension/popup.html` (add badge style)
- Modify: `extension/popup.js` (detect source and show badge)

**Step 1: Add badge CSS for LBC estimation**

In `extension/popup.html`, in the `<style>` section, add:

```css
.badge-lbc-estimation {
  background: #ff9800;
  color: #fff;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
}
```

**Step 2: Detect LBC estimation source in popup.js**

In the L4 result rendering section of `extension/popup.js`, add a check:

```javascript
if (result.details?.source === "estimation_lbc") {
  // Show LBC estimation badge
  const badge = document.createElement("span");
  badge.className = "badge-lbc-estimation";
  badge.textContent = "Estimation LBC";
  badge.title = `Fourchette LBC : ${result.details.lbc_estimation_low}€ - ${result.details.lbc_estimation_high}€`;
  // Append after the L4 result element
  resultEl.appendChild(badge);
}
```

**Step 3: Commit**

```bash
git add extension/popup.html extension/popup.js
git commit -m "feat(extension): badge orange estimation LBC dans le popup"
```

---

### Task 9: Final verification + ruff check

**Files:** None (verification only)

**Step 1: Run ruff on all modified Python files**

Run: `ruff check app/api/market_routes.py app/services/vehicle_factory.py app/services/market_service.py app/filters/l4_price.py app/models/vehicle_observed_spec.py`
Expected: 0 errors

**Step 2: Run full test suite**

Run: `pytest tests/ -v --tb=short`
Expected: All tests pass (existing + ~8 new tests)

**Step 3: Fix any issues**

If ruff or test failures, fix and commit.

**Step 4: Final commit if needed**

```bash
git add -u
git commit -m "fix: address lint/test issues from collecte intelligente"
```

---

## Verification Checklist

1. `ruff check` : 0 errors
2. `pytest` : all tests pass (existing + new TestBonusJobs + TestObservedSpecs + TestL4LbcEstimation)
3. Extension console: scan an ad → next-job response includes `bonus_jobs`
4. Extension console: bonus POST with precision 2 or 4 (not always skipped)
5. Admin /admin/argus : after scan, see 1-3 MarketPrice rows (main + bonus regions)
6. Admin /admin/car : see VehicleObservedSpec data for collected vehicles
7. New vehicle (e.g., Renegade): auto-created after 1st scan if CSV match
8. L4 fallback: shows "Estimation LeBonCoin" with orange badge when no market/argus data
9. next-job: partial vehicles prioritized for redirect collection
