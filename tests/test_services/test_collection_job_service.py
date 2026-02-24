"""Tests for collection_job_service."""

from datetime import datetime, timedelta, timezone

import pytest

from app.extensions import db
from app.models.collection_job import CollectionJob
from app.services.collection_job_service import (
    LOW_DATA_FAIL_THRESHOLD,
    MAX_ATTEMPTS,
    _cancel_low_data_pending,
    _expand_cache,
    _get_low_data_vehicles,
    _reclaim_stale_jobs,
    expand_collection_jobs,
    mark_job_done,
    pick_bonus_jobs,
)


@pytest.fixture(autouse=True)
def _clean_collection_jobs(app):
    """Supprime tous les CollectionJob et vide le cache avant/apres chaque test."""
    with app.app_context():
        CollectionJob.query.delete()
        db.session.commit()
        _expand_cache.clear()
        yield
        CollectionJob.query.delete()
        db.session.commit()
        _expand_cache.clear()


class TestExpandCollectionJobs:
    def test_creates_region_jobs_priority_1(self, app):
        """Expanding creates priority-1 jobs for all other regions."""
        with app.app_context():
            jobs = expand_collection_jobs(
                make="Renault",
                model="Talisman",
                year=2016,
                region="Auvergne-Rhône-Alpes",
                fuel="diesel",
                gearbox="manual",
                hp_range="120-150",
            )
            p1_jobs = [j for j in jobs if j.priority == 1]
            assert len(p1_jobs) == 12
            regions = {j.region for j in p1_jobs}
            assert "Auvergne-Rhône-Alpes" not in regions
            assert "Île-de-France" in regions

    def test_creates_fuel_variant_priority_2(self, app):
        """Expanding diesel creates essence variant jobs at priority 2."""
        with app.app_context():
            jobs = expand_collection_jobs(
                make="Renault",
                model="Megane",
                year=2018,
                region="Bretagne",
                fuel="diesel",
                gearbox="manual",
                hp_range="120-150",
            )
            p2_jobs = [j for j in jobs if j.priority == 2]
            assert len(p2_jobs) == 13
            assert all(j.fuel == "essence" for j in p2_jobs)
            assert all(j.hp_range is None for j in p2_jobs)

    def test_creates_gearbox_variant_priority_3(self, app):
        """Expanding manual creates auto variant jobs at priority 3."""
        with app.app_context():
            jobs = expand_collection_jobs(
                make="Peugeot",
                model="308",
                year=2019,
                region="Normandie",
                fuel="diesel",
                gearbox="manual",
                hp_range="100-130",
            )
            p3_jobs = [j for j in jobs if j.priority == 3]
            assert len(p3_jobs) == 13
            assert all(j.gearbox == "automatique" for j in p3_jobs)

    def test_creates_year_variant_priority_4_current_region_only(self, app):
        """P4 creates year+/-1 jobs for current region only (2 jobs, not 26)."""
        with app.app_context():
            jobs = expand_collection_jobs(
                make="Ford",
                model="Focus",
                year=2016,
                region="Corse",
                fuel="essence",
                gearbox="manual",
                hp_range="70-120",
            )
            p4_jobs = [j for j in jobs if j.priority == 4]
            years = {j.year for j in p4_jobs}
            assert 2015 in years
            assert 2017 in years
            assert len(p4_jobs) == 2  # region courante seulement
            assert all(j.region == "Corse" for j in p4_jobs)

    def test_no_fuel_variant_for_electrique(self, app):
        """No fuel variant created for electric vehicles."""
        with app.app_context():
            jobs = expand_collection_jobs(
                make="Tesla",
                model="Model 3",
                year=2022,
                region="Île-de-France",
                fuel="electrique",
                gearbox=None,
                hp_range="240-360",
            )
            p2_jobs = [j for j in jobs if j.priority == 2]
            assert len(p2_jobs) == 0

    def test_deduplication_skips_existing_jobs(self, app):
        """Calling expand with same vehicle after clearing cache does not duplicate."""
        with app.app_context():
            jobs1 = expand_collection_jobs(
                make="Audi",
                model="A3",
                year=2020,
                region="Grand Est",
                fuel="diesel",
                gearbox="manual",
                hp_range="130-190",
            )
            count1 = len(jobs1)
            assert count1 > 0

            # Vider le cache pour que le 2e appel ne soit pas court-circuite
            _expand_cache.clear()

            jobs2 = expand_collection_jobs(
                make="Audi",
                model="A3",
                year=2020,
                region="Grand Est",
                fuel="diesel",
                gearbox="manual",
                hp_range="130-190",
            )
            assert len(jobs2) == 0
            total = CollectionJob.query.count()
            assert total >= count1

    def test_no_gearbox_variant_without_gearbox(self, app):
        """No gearbox variant if gearbox is None."""
        with app.app_context():
            jobs = expand_collection_jobs(
                make="Dacia",
                model="Sandero",
                year=2021,
                region="Occitanie",
                fuel="essence",
                gearbox=None,
                hp_range="70-120",
            )
            p3_jobs = [j for j in jobs if j.priority == 3]
            assert len(p3_jobs) == 0

    def test_cache_prevents_re_expansion(self, app):
        """Second call within cooldown returns empty (cache hit)."""
        with app.app_context():
            jobs1 = expand_collection_jobs(
                make="Fiat",
                model="500",
                year=2020,
                region="Corse",
                fuel="essence",
                gearbox="manual",
                hp_range="50-70",
            )
            assert len(jobs1) > 0

            # Cache is still warm — second call returns []
            jobs2 = expand_collection_jobs(
                make="Fiat",
                model="500",
                year=2020,
                region="Corse",
                fuel="essence",
                gearbox="manual",
                hp_range="50-70",
            )
            assert len(jobs2) == 0

    def test_normalizes_inputs_case_insensitive(self, app):
        """Expand normalizes make/model/fuel/gearbox (case-insensitive dedup)."""
        with app.app_context():
            jobs1 = expand_collection_jobs(
                make="RENAULT",
                model="CLIO",
                year=2022,
                region="Bretagne",
                fuel="Diesel",
                gearbox="Manual",
                hp_range="70-120",
            )
            assert len(jobs1) > 0

            _expand_cache.clear()

            # Meme vehicule, casse differente — 0 nouveaux jobs
            jobs2 = expand_collection_jobs(
                make="renault",
                model="clio",
                year=2022,
                region="Bretagne",
                fuel="diesel",
                gearbox="manual",
                hp_range="70-120",
            )
            assert len(jobs2) == 0


class TestReclaimStaleJobs:
    def test_reclaims_stale_assigned(self, app):
        """Jobs assigned > 30 min ago are reclaimed to pending."""
        with app.app_context():
            job = CollectionJob(
                make="Toyota",
                model="Yaris",
                year=2021,
                region="Bretagne",
                priority=1,
                status="assigned",
                assigned_at=datetime.now(timezone.utc) - timedelta(minutes=45),
                source_vehicle="test",
            )
            db.session.add(job)
            db.session.commit()

            count = _reclaim_stale_jobs()
            assert count == 1
            db.session.refresh(job)
            assert job.status == "pending"
            assert job.assigned_at is None

    def test_does_not_reclaim_recent_assigned(self, app):
        """Jobs assigned < 30 min ago are NOT reclaimed."""
        with app.app_context():
            job = CollectionJob(
                make="Toyota",
                model="Corolla",
                year=2022,
                region="Normandie",
                priority=1,
                status="assigned",
                assigned_at=datetime.now(timezone.utc) - timedelta(minutes=10),
                source_vehicle="test",
            )
            db.session.add(job)
            db.session.commit()

            count = _reclaim_stale_jobs()
            assert count == 0
            db.session.refresh(job)
            assert job.status == "assigned"


class TestPickBonusJobs:
    def test_picks_highest_priority_first(self, app):
        """pick_bonus_jobs returns priority-1 jobs before priority-2."""
        with app.app_context():
            expand_collection_jobs(
                make="BMW",
                model="Serie 3",
                year=2019,
                region="Pays de la Loire",
                fuel="diesel",
                gearbox="manual",
                hp_range="130-190",
            )
            picked = pick_bonus_jobs(max_jobs=3)
            assert len(picked) == 3
            assert all(j.priority == 1 for j in picked)
            assert all(j.status == "assigned" for j in picked)

    def test_picks_respects_max(self, app):
        """pick_bonus_jobs respects max_jobs limit."""
        with app.app_context():
            expand_collection_jobs(
                make="VW",
                model="Golf",
                year=2020,
                region="Hauts-de-France",
                fuel="essence",
                gearbox="manual",
                hp_range="70-120",
            )
            picked = pick_bonus_jobs(max_jobs=2)
            assert len(picked) == 2

    def test_skips_assigned_jobs(self, app):
        """pick_bonus_jobs does not pick already-assigned jobs."""
        with app.app_context():
            expand_collection_jobs(
                make="Citroen",
                model="C3",
                year=2021,
                region="Centre-Val de Loire",
                fuel="essence",
                gearbox="manual",
                hp_range="70-120",
            )
            pick1 = pick_bonus_jobs(max_jobs=3)
            pick2 = pick_bonus_jobs(max_jobs=3)
            ids1 = {j.id for j in pick1}
            ids2 = {j.id for j in pick2}
            assert ids1.isdisjoint(ids2)

    def test_reclaims_stale_before_picking(self, app):
        """pick_bonus_jobs reclaims stale assigned jobs and can re-pick them."""
        with app.app_context():
            job = CollectionJob(
                make="Kia",
                model="Picanto",
                year=2023,
                region="Corse",
                priority=1,
                status="assigned",
                assigned_at=datetime.now(timezone.utc) - timedelta(minutes=45),
                source_vehicle="test",
            )
            db.session.add(job)
            db.session.commit()

            picked = pick_bonus_jobs(max_jobs=3)
            assert any(j.id == job.id for j in picked)
            db.session.refresh(job)
            assert job.status == "assigned"  # re-assigned


class TestMarkJobDone:
    def test_mark_done_from_assigned(self, app):
        """Mark an assigned job as done."""
        with app.app_context():
            job = CollectionJob(
                make="Seat",
                model="Ibiza",
                year=2020,
                region="Bretagne",
                priority=1,
                status="assigned",
                source_vehicle="test",
            )
            db.session.add(job)
            db.session.commit()
            mark_job_done(job.id, success=True)
            db.session.refresh(job)
            assert job.status == "done"
            assert job.completed_at is not None

    def test_mark_done_from_pending(self, app):
        """Mark a pending job as done (accepted status)."""
        with app.app_context():
            job = CollectionJob(
                make="Seat",
                model="Leon",
                year=2021,
                region="Bretagne",
                priority=1,
                source_vehicle="test",
            )
            db.session.add(job)
            db.session.commit()
            mark_job_done(job.id, success=True)
            db.session.refresh(job)
            assert job.status == "done"

    def test_mark_failed_increments_attempts(self, app):
        """Failing a job increments attempts; under MAX_ATTEMPTS goes back to pending."""
        with app.app_context():
            job = CollectionJob(
                make="Seat",
                model="Arona",
                year=2021,
                region="Corse",
                priority=1,
                status="assigned",
                source_vehicle="test",
            )
            db.session.add(job)
            db.session.commit()
            mark_job_done(job.id, success=False)
            db.session.refresh(job)
            assert job.attempts == 1
            assert job.status == "pending"

    def test_mark_failed_stays_failed_after_max_attempts(self, app):
        """Job stays failed after reaching MAX_ATTEMPTS."""
        with app.app_context():
            job = CollectionJob(
                make="Opel",
                model="Corsa",
                year=2019,
                region="Normandie",
                priority=1,
                status="assigned",
                source_vehicle="test",
                attempts=2,
            )
            db.session.add(job)
            db.session.commit()
            mark_job_done(job.id, success=False)
            db.session.refresh(job)
            assert job.attempts == 3
            assert job.status == "failed"

    def test_rejects_already_done_job(self, app):
        """Cannot mark a done job as done again."""
        with app.app_context():
            job = CollectionJob(
                make="Opel",
                model="Mokka",
                year=2022,
                region="Occitanie",
                priority=1,
                status="done",
                source_vehicle="test",
            )
            db.session.add(job)
            db.session.commit()
            with pytest.raises(ValueError, match="expected 'assigned' or 'pending'"):
                mark_job_done(job.id, success=True)

    def test_rejects_already_failed_job(self, app):
        """Cannot mark a failed job."""
        with app.app_context():
            job = CollectionJob(
                make="Opel",
                model="Astra",
                year=2020,
                region="Grand Est",
                priority=1,
                status="failed",
                source_vehicle="test",
            )
            db.session.add(job)
            db.session.commit()
            with pytest.raises(ValueError, match="expected 'assigned' or 'pending'"):
                mark_job_done(job.id, success=False)

    def test_raises_for_missing_job(self, app):
        """Raises ValueError for non-existent job ID."""
        with app.app_context():
            with pytest.raises(ValueError, match="not found"):
                mark_job_done(99999, success=True)


class TestJobExistsBlocksFailedRecent:
    """_job_exists blocks re-creation of recently failed jobs."""

    def test_failed_recent_blocks_expansion(self, app):
        """A failed job < 7 days old prevents creating the same job again."""
        with app.app_context():
            # Create and fail a job manually
            job = CollectionJob(
                make="Kia",
                model="Optima",
                year=2019,
                region="Nouvelle-Aquitaine",
                fuel="diesel",
                gearbox="automatique",
                hp_range="100-150",
                priority=1,
                status="failed",
                attempts=3,
                source_vehicle="test",
            )
            db.session.add(job)
            db.session.commit()

            # Expand same vehicle — should NOT re-create Nouvelle-Aquitaine
            jobs = expand_collection_jobs(
                make="Kia",
                model="Optima",
                year=2019,
                region="Île-de-France",  # scanning from IDF
                fuel="diesel",
                gearbox="automatique",
                hp_range="100-150",
            )
            regions = {j.region for j in jobs if j.priority == 1}
            assert "Nouvelle-Aquitaine" not in regions

    def test_failed_old_allows_re_creation(self, app):
        """A failed job > 7 days old allows re-creating the same job."""
        with app.app_context():
            old_date = datetime.now(timezone.utc) - timedelta(days=10)
            job = CollectionJob(
                make="Kia",
                model="Stonic",
                year=2020,
                region="Bretagne",
                fuel="essence",
                gearbox="manuelle",
                hp_range="70-120",
                priority=1,
                status="failed",
                attempts=3,
                source_vehicle="test",
                created_at=old_date,
            )
            db.session.add(job)
            db.session.commit()

            # Expand same vehicle — Bretagne should be re-created (old fail)
            jobs = expand_collection_jobs(
                make="Kia",
                model="Stonic",
                year=2020,
                region="Île-de-France",
                fuel="essence",
                gearbox="manuelle",
                hp_range="70-120",
            )
            regions = {j.region for j in jobs if j.priority == 1}
            assert "Bretagne" in regions


class TestLowDataVehicleSkip:
    """pick_bonus_jobs skips vehicles with too many recent fails."""

    def _create_failed_jobs(self, make, model, count):
        """Helper: create N failed jobs for a vehicle across different regions."""
        from app.services.collection_job_service import POST_2016_REGIONS

        for i in range(count):
            job = CollectionJob(
                make=make,
                model=model,
                year=2019,
                region=POST_2016_REGIONS[i % len(POST_2016_REGIONS)],
                fuel="diesel",
                gearbox="automatique",
                hp_range="100-150",
                priority=1,
                status="failed",
                attempts=3,
                source_vehicle="test",
            )
            db.session.add(job)
        db.session.commit()

    def test_low_data_vehicles_detected(self, app):
        """Vehicles with >= threshold fails are detected as low-data."""
        with app.app_context():
            self._create_failed_jobs("Kia", "Optima", LOW_DATA_FAIL_THRESHOLD)
            low_data = _get_low_data_vehicles()
            assert ("kia", "optima") in low_data

    def test_below_threshold_not_detected(self, app):
        """Vehicles with < threshold fails are NOT detected as low-data."""
        with app.app_context():
            self._create_failed_jobs("Kia", "Niro", LOW_DATA_FAIL_THRESHOLD - 1)
            low_data = _get_low_data_vehicles()
            assert ("kia", "niro") not in low_data

    def test_pick_bonus_skips_low_data_vehicle(self, app):
        """pick_bonus_jobs does not pick pending jobs from low-data vehicles."""
        with app.app_context():
            # Create 3 failed jobs for Kia Optima (= threshold)
            self._create_failed_jobs("Kia", "Optima", LOW_DATA_FAIL_THRESHOLD)

            # Create a pending job for the same low-data vehicle
            pending_bad = CollectionJob(
                make="Kia",
                model="Optima",
                year=2019,
                region="Corse",
                fuel="diesel",
                gearbox="automatique",
                hp_range="100-150",
                priority=1,
                source_vehicle="test",
            )
            # Create a pending job for a healthy vehicle
            pending_good = CollectionJob(
                make="Renault",
                model="Clio",
                year=2022,
                region="Île-de-France",
                fuel="essence",
                gearbox="manuelle",
                hp_range="70-120",
                priority=1,
                source_vehicle="test",
            )
            db.session.add_all([pending_bad, pending_good])
            db.session.commit()

            picked = pick_bonus_jobs(max_jobs=3)
            picked_ids = {j.id for j in picked}
            assert pending_bad.id not in picked_ids
            assert pending_good.id in picked_ids

    def test_pick_bonus_still_works_without_low_data(self, app):
        """pick_bonus_jobs works normally when no low-data vehicles exist."""
        with app.app_context():
            job = CollectionJob(
                make="Peugeot",
                model="208",
                year=2021,
                region="Bretagne",
                fuel="essence",
                gearbox="manuelle",
                hp_range="70-120",
                priority=1,
                source_vehicle="test",
            )
            db.session.add(job)
            db.session.commit()

            picked = pick_bonus_jobs(max_jobs=3)
            assert len(picked) == 1
            assert picked[0].id == job.id

    def test_cancel_low_data_pending_marks_zombies_failed(self, app):
        """Pending/assigned jobs for low-data vehicles are cancelled as failed."""
        with app.app_context():
            # Seuil atteint -> Kia Optima devient low-data
            self._create_failed_jobs("Kia", "Optima", LOW_DATA_FAIL_THRESHOLD)

            pending_bad = CollectionJob(
                make="Kia",
                model="Optima",
                year=2019,
                region="Corse",
                fuel="diesel",
                gearbox="automatique",
                hp_range="100-150",
                priority=1,
                status="pending",
                attempts=0,
                source_vehicle="test",
            )
            assigned_bad = CollectionJob(
                make="Kia",
                model="Optima",
                year=2019,
                region="Bretagne",
                fuel="diesel",
                gearbox="automatique",
                hp_range="100-150",
                priority=1,
                status="assigned",
                attempts=1,
                assigned_at=datetime.now(timezone.utc),
                source_vehicle="test",
            )
            db.session.add_all([pending_bad, assigned_bad])
            db.session.commit()

            low_data = _get_low_data_vehicles()
            cancelled = _cancel_low_data_pending(low_data)
            assert cancelled >= 2

            db.session.refresh(pending_bad)
            db.session.refresh(assigned_bad)
            assert pending_bad.status == "failed"
            assert assigned_bad.status == "failed"
            assert pending_bad.attempts == MAX_ATTEMPTS
            assert assigned_bad.attempts == MAX_ATTEMPTS

    def test_expand_skips_low_data_vehicle(self, app):
        """expand_collection_jobs returns [] for low-data vehicles."""
        with app.app_context():
            self._create_failed_jobs("Kia", "Optima", LOW_DATA_FAIL_THRESHOLD)

            created = expand_collection_jobs(
                make="Kia",
                model="Optima",
                year=2019,
                region="Île-de-France",
                fuel="diesel",
                gearbox="automatique",
                hp_range="100-150",
            )

            assert created == []
