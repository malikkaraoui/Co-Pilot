"""Tests for CollectionJobAS24 model."""

from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.collection_job_as24 import CollectionJobAS24


class TestCollectionJobAS24Model:
    def test_create_basic(self, app):
        """Basic creation with required fields."""
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
        kwargs = dict(
            make="VW",
            model="TIGUAN",
            year=2016,
            region="Berne",
            fuel="essence",
            gearbox="auto",
            hp_range="150-200",
            tld="ch",
            slug_make="vw",
            slug_model="tiguan",
            country="CH",
            currency="CHF",
            search_strategy="zip_radius",
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
        assert job.status == "pending"
        assert job.attempts == 0
        assert job.priority == 1

    def test_repr(self, app):
        """__repr__ includes key info."""
        job = CollectionJobAS24(
            make="Audi",
            model="A3",
            year=2021,
            region="Zurich",
            tld="ch",
            slug_make="audi",
            slug_model="a3",
            country="CH",
            currency="CHF",
            search_strategy="zip_radius",
        )
        assert "Audi" in repr(job)
        assert "tld=ch" in repr(job)
