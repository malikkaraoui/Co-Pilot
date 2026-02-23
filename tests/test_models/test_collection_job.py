"""Tests for CollectionJob model."""

import sqlalchemy

from app.models.collection_job import CollectionJob


class TestCollectionJob:
    def test_create_job(self, db):
        job = CollectionJob(
            make="Renault",
            model="Talisman",
            year=2016,
            region="Bretagne",
            fuel="diesel",
            gearbox="manual",
            hp_range="120-150",
            priority=1,
            source_vehicle="Renault Talisman 2016 diesel",
        )
        db.session.add(job)
        db.session.commit()
        assert job.id is not None
        assert job.status == "pending"
        assert job.attempts == 0

    def test_unique_constraint(self, db):
        """Duplicate job key raises IntegrityError."""
        shared = dict(
            make="Toyota",
            model="Corolla",
            year=2019,
            region="Normandie",
            fuel="essence",
            gearbox="automatique",
            hp_range="100-130",
            priority=1,
            source_vehicle="test",
        )
        job1 = CollectionJob(**shared)
        db.session.add(job1)
        db.session.commit()

        job2 = CollectionJob(**shared)
        db.session.add(job2)
        try:
            db.session.commit()
            assert False, "Should have raised IntegrityError"
        except sqlalchemy.exc.IntegrityError:
            db.session.rollback()

    def test_different_hp_range_is_separate_job(self, db):
        job1 = CollectionJob(
            make="Peugeot",
            model="308",
            year=2018,
            region="PACA",
            fuel="diesel",
            hp_range="100-130",
            priority=1,
            source_vehicle="test",
        )
        job2 = CollectionJob(
            make="Peugeot",
            model="308",
            year=2018,
            region="PACA",
            fuel="diesel",
            hp_range="130-160",
            priority=1,
            source_vehicle="test",
        )
        db.session.add_all([job1, job2])
        db.session.commit()
        assert job1.id != job2.id

    def test_different_gearbox_is_separate_job(self, db):
        job1 = CollectionJob(
            make="Citroen",
            model="C3",
            year=2020,
            region="Occitanie",
            fuel="diesel",
            gearbox="manual",
            priority=1,
            source_vehicle="test",
        )
        job2 = CollectionJob(
            make="Citroen",
            model="C3",
            year=2020,
            region="Occitanie",
            fuel="diesel",
            gearbox="automatique",
            priority=1,
            source_vehicle="test",
        )
        db.session.add_all([job1, job2])
        db.session.commit()
        assert job1.id != job2.id

    def test_default_status_is_pending(self, db):
        job = CollectionJob(
            make="Peugeot",
            model="208",
            year=2020,
            region="Ile-de-France",
            priority=1,
            source_vehicle="test",
        )
        db.session.add(job)
        db.session.commit()
        assert job.status == "pending"
        assert job.attempts == 0
        assert job.assigned_at is None
        assert job.completed_at is None
