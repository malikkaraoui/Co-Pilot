"""Tests for collection_job_lc_service."""

from datetime import datetime, timedelta, timezone

import pytest

from app.extensions import db
from app.models.collection_job_lacentrale import CollectionJobLacentrale
from app.services.collection_job_lc_service import (
    LOW_DATA_FAIL_THRESHOLD,
    MAX_ATTEMPTS,
    _cancel_low_data_pending_lc,
    _expand_cache,
    _get_low_data_vehicles_lc,
    _reclaim_stale_jobs_lc,
    expand_collection_jobs_lc,
    mark_job_done_lc,
    pick_bonus_jobs_lc,
)


@pytest.fixture(autouse=True)
def _clean_lc_jobs(app):
    """Supprime tous les CollectionJobLacentrale et vide le cache."""
    with app.app_context():
        CollectionJobLacentrale.query.delete()
        db.session.commit()
        _expand_cache.clear()
        yield
        CollectionJobLacentrale.query.delete()
        db.session.commit()
        _expand_cache.clear()


class TestExpandCollectionJobsLc:
    def test_creates_fuel_variant(self, app):
        """Expanding diesel creates essence variant at priority 1."""
        with app.app_context():
            jobs = expand_collection_jobs_lc(
                make="Peugeot",
                model="308",
                year=2019,
                fuel="diesel",
                gearbox="manual",
            )
            p1 = [j for j in jobs if j.priority == 1]
            assert len(p1) == 1
            assert p1[0].fuel == "essence"
            assert p1[0].region == "France"
            assert p1[0].country == "FR"

    def test_creates_gearbox_variant(self, app):
        """Expanding manual creates automatique variant at priority 2."""
        with app.app_context():
            jobs = expand_collection_jobs_lc(
                make="Renault",
                model="Megane",
                year=2018,
                fuel="diesel",
                gearbox="manual",
            )
            p2 = [j for j in jobs if j.priority == 2]
            assert len(p2) == 1
            assert p2[0].gearbox == "automatique"

    def test_creates_year_variants(self, app):
        """Expanding creates year +/-1 variants at priority 3."""
        with app.app_context():
            jobs = expand_collection_jobs_lc(
                make="BMW",
                model="Serie 3",
                year=2020,
                fuel="diesel",
            )
            p3 = [j for j in jobs if j.priority == 3]
            assert len(p3) == 2
            years = {j.year for j in p3}
            assert years == {2019, 2021}

    def test_no_fuel_variant_for_electric(self, app):
        """Electric has no fuel opposite, so no P1 jobs."""
        with app.app_context():
            jobs = expand_collection_jobs_lc(
                make="Tesla",
                model="Model 3",
                year=2022,
                fuel="electric",
            )
            p1 = [j for j in jobs if j.priority == 1]
            assert len(p1) == 0

    def test_dedup_skips_existing_job(self, app):
        """Second expand is skipped by cache cooldown."""
        with app.app_context():
            jobs1 = expand_collection_jobs_lc(
                make="Peugeot",
                model="208",
                year=2021,
                fuel="diesel",
            )
            assert len(jobs1) > 0

            jobs2 = expand_collection_jobs_lc(
                make="Peugeot",
                model="208",
                year=2021,
                fuel="diesel",
            )
            assert len(jobs2) == 0  # cache cooldown

    def test_all_jobs_have_region_france(self, app):
        """All LC jobs should have region=France."""
        with app.app_context():
            jobs = expand_collection_jobs_lc(
                make="Renault",
                model="Clio",
                year=2020,
                fuel="essence",
                gearbox="manual",
            )
            assert all(j.region == "France" for j in jobs)

    def test_no_gearbox_variant_when_none(self, app):
        """No gearbox variant when gearbox is not provided."""
        with app.app_context():
            jobs = expand_collection_jobs_lc(
                make="Dacia",
                model="Sandero",
                year=2021,
                fuel="essence",
            )
            p2 = [j for j in jobs if j.priority == 2]
            assert len(p2) == 0


class TestPickBonusJobsLc:
    def test_picks_pending_jobs(self, app):
        """pick_bonus_jobs_lc returns pending jobs ordered by priority."""
        with app.app_context():
            j1 = CollectionJobLacentrale(
                make="Peugeot",
                model="308",
                year=2019,
                region="France",
                fuel="diesel",
                priority=2,
                source_vehicle="test",
                country="FR",
            )
            j2 = CollectionJobLacentrale(
                make="Renault",
                model="Megane",
                year=2020,
                region="France",
                fuel="essence",
                priority=1,
                source_vehicle="test",
                country="FR",
            )
            db.session.add_all([j1, j2])
            db.session.commit()

            picked = pick_bonus_jobs_lc(max_jobs=3)
            assert len(picked) == 2
            # P1 first
            assert picked[0].model == "Megane"
            assert picked[1].model == "308"
            assert all(j.status == "assigned" for j in picked)

    def test_respects_max_jobs(self, app):
        """pick_bonus_jobs_lc respects max_jobs limit."""
        with app.app_context():
            for i in range(5):
                db.session.add(
                    CollectionJobLacentrale(
                        make="BMW",
                        model=f"Serie {i}",
                        year=2020,
                        region="France",
                        priority=1,
                        source_vehicle="test",
                        country="FR",
                    )
                )
            db.session.commit()

            picked = pick_bonus_jobs_lc(max_jobs=2)
            assert len(picked) == 2


class TestMarkJobDoneLc:
    def test_mark_done(self, app):
        """mark_job_done_lc sets status to done."""
        with app.app_context():
            job = CollectionJobLacentrale(
                make="Toyota",
                model="Yaris",
                year=2021,
                region="France",
                priority=1,
                status="assigned",
                source_vehicle="test",
                country="FR",
            )
            db.session.add(job)
            db.session.commit()
            job_id = job.id

            mark_job_done_lc(job_id, success=True)
            updated = db.session.get(CollectionJobLacentrale, job_id)
            assert updated.status == "done"
            assert updated.completed_at is not None

    def test_mark_failed_retries(self, app):
        """Failed job goes back to pending if attempts < MAX_ATTEMPTS."""
        with app.app_context():
            job = CollectionJobLacentrale(
                make="Honda",
                model="Civic",
                year=2019,
                region="France",
                priority=1,
                status="assigned",
                source_vehicle="test",
                country="FR",
            )
            db.session.add(job)
            db.session.commit()
            job_id = job.id

            mark_job_done_lc(job_id, success=False)
            updated = db.session.get(CollectionJobLacentrale, job_id)
            assert updated.status == "pending"
            assert updated.attempts == 1

    def test_mark_failed_exhausted(self, app):
        """Failed job stays failed after MAX_ATTEMPTS."""
        with app.app_context():
            job = CollectionJobLacentrale(
                make="Kia",
                model="Niro",
                year=2022,
                region="France",
                priority=1,
                status="assigned",
                source_vehicle="test",
                country="FR",
                attempts=MAX_ATTEMPTS - 1,
            )
            db.session.add(job)
            db.session.commit()
            job_id = job.id

            mark_job_done_lc(job_id, success=False)
            updated = db.session.get(CollectionJobLacentrale, job_id)
            assert updated.status == "failed"

    def test_not_found_raises(self, app):
        """mark_job_done_lc raises ValueError for unknown job."""
        with app.app_context():
            with pytest.raises(ValueError, match="LC Job"):
                mark_job_done_lc(999999, success=True)


class TestReclaimStaleJobsLc:
    def test_reclaims_old_assigned(self, app):
        """Stale assigned jobs are reclaimed to pending."""
        with app.app_context():
            job = CollectionJobLacentrale(
                make="Fiat",
                model="500",
                year=2020,
                region="France",
                priority=1,
                status="assigned",
                assigned_at=datetime.now(timezone.utc) - timedelta(minutes=60),
                source_vehicle="test",
                country="FR",
            )
            db.session.add(job)
            db.session.commit()

            reclaimed = _reclaim_stale_jobs_lc()
            assert reclaimed == 1
            assert job.status == "pending"


class TestLowDataLc:
    def test_detects_low_data(self, app):
        """Vehicles with many recent failures are detected."""
        with app.app_context():
            for _ in range(LOW_DATA_FAIL_THRESHOLD):
                db.session.add(
                    CollectionJobLacentrale(
                        make="Lancia",
                        model="Ypsilon",
                        year=2015,
                        region="France",
                        priority=1,
                        status="failed",
                        source_vehicle="test",
                        country="FR",
                    )
                )
            db.session.commit()

            low = _get_low_data_vehicles_lc()
            assert ("lancia", "ypsilon") in low

    def test_cancels_pending_for_low_data(self, app):
        """Pending jobs for low-data vehicles are cancelled."""
        with app.app_context():
            for _ in range(LOW_DATA_FAIL_THRESHOLD):
                db.session.add(
                    CollectionJobLacentrale(
                        make="Lancia",
                        model="Delta",
                        year=2010,
                        region="France",
                        priority=1,
                        status="failed",
                        source_vehicle="test",
                        country="FR",
                    )
                )
            pending = CollectionJobLacentrale(
                make="Lancia",
                model="Delta",
                year=2011,
                region="France",
                priority=3,
                status="pending",
                source_vehicle="test",
                country="FR",
            )
            db.session.add(pending)
            db.session.commit()

            low = _get_low_data_vehicles_lc()
            cancelled = _cancel_low_data_pending_lc(low)
            assert cancelled == 1
            assert pending.status == "failed"

    def test_skips_expansion_for_low_data(self, app):
        """expand_collection_jobs_lc skips low-data vehicles."""
        with app.app_context():
            for i in range(LOW_DATA_FAIL_THRESHOLD):
                db.session.add(
                    CollectionJobLacentrale(
                        make="Lancia",
                        model="Musa",
                        year=2008 + i,
                        region="France",
                        priority=1,
                        status="failed",
                        source_vehicle="test",
                        country="FR",
                    )
                )
            db.session.commit()

            jobs = expand_collection_jobs_lc(
                make="Lancia",
                model="Musa",
                year=2009,
                fuel="diesel",
            )
            assert len(jobs) == 0
