"""Tests for AS24 collection job service."""

import pytest

from app.extensions import db
from app.models.collection_job import CollectionJobLBC
from app.models.collection_job_as24 import CollectionJobAS24
from app.services.collection_job_as24_service import mark_job_done_as24, pick_bonus_jobs_as24


@pytest.fixture(autouse=True)
def _clean_as24_jobs(app):
    """Nettoie la table AS24 avant chaque test."""
    CollectionJobAS24.query.delete()
    CollectionJobLBC.query.delete()
    db.session.commit()
    yield
    CollectionJobAS24.query.delete()
    CollectionJobLBC.query.delete()
    db.session.commit()


class TestPickBonusJobsAS24:
    def test_pick_returns_only_matching_country(self, app):
        """pick_bonus_jobs_as24 ne retourne que les jobs du bon pays."""
        ch = CollectionJobAS24(
            make="VW",
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
        de = CollectionJobAS24(
            make="VW",
            model="Tiguan",
            year=2016,
            region="Bayern",
            tld="de",
            slug_make="vw",
            slug_model="tiguan",
            country="DE",
            currency="EUR",
            search_strategy="national",
        )
        db.session.add_all([ch, de])
        db.session.commit()

        jobs = pick_bonus_jobs_as24(country="CH", tld="ch", max_jobs=3)
        assert len(jobs) == 1
        assert jobs[0].country == "CH"

    def test_pick_excludes_lbc_jobs(self, app):
        """AS24 service ne pioche jamais dans la table LBC."""
        lbc = CollectionJobLBC(
            make="VW",
            model="Tiguan",
            year=2016,
            region="Bretagne",
        )
        db.session.add(lbc)
        db.session.commit()

        jobs = pick_bonus_jobs_as24(country="FR", tld="fr", max_jobs=3)
        assert len(jobs) == 0

    def test_pick_marks_assigned(self, app):
        """Les jobs pickes passent en status assigned."""
        job = CollectionJobAS24(
            make="BMW",
            model="X4",
            year=2020,
            region="Zurich",
            tld="ch",
            slug_make="bmw",
            slug_model="x4",
            country="CH",
            currency="CHF",
            search_strategy="national",
        )
        db.session.add(job)
        db.session.commit()

        picked = pick_bonus_jobs_as24(country="CH", tld="ch", max_jobs=3)
        assert len(picked) == 1
        assert picked[0].status == "assigned"
        assert picked[0].assigned_at is not None


class TestMarkJobDoneAS24:
    def test_mark_job_done_success(self, app):
        """mark_job_done fonctionne sur un job AS24."""
        job = CollectionJobAS24(
            make="BMW",
            model="X4",
            year=2020,
            region="Zurich",
            tld="ch",
            slug_make="bmw",
            slug_model="x4",
            country="CH",
            currency="CHF",
            search_strategy="national",
            status="assigned",
        )
        db.session.add(job)
        db.session.commit()

        mark_job_done_as24(job.id, success=True)
        assert job.status == "done"
        assert job.completed_at is not None

    def test_mark_job_done_failure_retries(self, app):
        """Failed job avec attempts < max reste en pending."""
        job = CollectionJobAS24(
            make="Audi",
            model="A3",
            year=2021,
            region="Berne",
            tld="ch",
            slug_make="audi",
            slug_model="a3",
            country="CH",
            currency="CHF",
            search_strategy="zip_radius",
            status="assigned",
            attempts=1,
        )
        db.session.add(job)
        db.session.commit()

        mark_job_done_as24(job.id, success=False)
        assert job.status == "pending"
        assert job.attempts == 2

    def test_mark_job_done_max_attempts_fails(self, app):
        """Failed job avec attempts >= max passe en failed."""
        job = CollectionJobAS24(
            make="Audi",
            model="Q5",
            year=2019,
            region="Geneve",
            tld="ch",
            slug_make="audi",
            slug_model="q5",
            country="CH",
            currency="CHF",
            search_strategy="canton",
            status="assigned",
            attempts=2,
        )
        db.session.add(job)
        db.session.commit()

        mark_job_done_as24(job.id, success=False)
        assert job.status == "failed"
        assert job.attempts == 3

    def test_mark_job_not_found_raises(self, app):
        """Job inexistant leve ValueError."""
        import pytest

        with pytest.raises(ValueError, match="not found"):
            mark_job_done_as24(99999, success=True)
