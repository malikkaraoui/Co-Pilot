"""Tests for collection_job_service."""

import pytest

from app.extensions import db
from app.models.collection_job import CollectionJob
from app.services.collection_job_service import (
    expand_collection_jobs,
    mark_job_done,
    pick_bonus_jobs,
)


@pytest.fixture(autouse=True)
def _clean_collection_jobs(app):
    """Supprime tous les CollectionJob avant et apres chaque test.

    Necessaire car le fixture 'app' est session-scoped et d'autres tests
    (test_collection_job.py) peuvent laisser des donnees residuelles.
    """
    with app.app_context():
        CollectionJob.query.delete()
        db.session.commit()
        yield
        CollectionJob.query.delete()
        db.session.commit()


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

    def test_creates_year_variant_priority_4(self, app):
        """Expanding year 2016 creates 2015 and 2017 jobs at priority 4."""
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
            assert len(p4_jobs) == 26  # 2 years x 13 regions

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
        """Calling expand twice does not create duplicates."""
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


class TestMarkJobDone:
    def test_mark_done(self, app):
        with app.app_context():
            job = CollectionJob(
                make="Seat",
                model="Ibiza",
                year=2020,
                region="Bretagne",
                priority=1,
                source_vehicle="test",
            )
            db.session.add(job)
            db.session.commit()
            mark_job_done(job.id, success=True)
            db.session.refresh(job)
            assert job.status == "done"
            assert job.completed_at is not None

    def test_mark_failed_increments_attempts(self, app):
        with app.app_context():
            job = CollectionJob(
                make="Seat",
                model="Arona",
                year=2021,
                region="Corse",
                priority=1,
                source_vehicle="test",
            )
            db.session.add(job)
            db.session.commit()
            mark_job_done(job.id, success=False)
            db.session.refresh(job)
            assert job.attempts == 1
            # Under MAX_ATTEMPTS (3), back to pending for retry
            assert job.status == "pending"

    def test_mark_failed_stays_failed_after_max_attempts(self, app):
        with app.app_context():
            job = CollectionJob(
                make="Opel",
                model="Corsa",
                year=2019,
                region="Normandie",
                priority=1,
                source_vehicle="test",
                attempts=2,  # already at 2
            )
            db.session.add(job)
            db.session.commit()
            mark_job_done(job.id, success=False)
            db.session.refresh(job)
            assert job.attempts == 3
            assert job.status == "failed"  # stays failed at max
