"""Tests pour les routes admin des gaps métier du référentiel."""

from datetime import datetime, timedelta, timezone

import pytest
from werkzeug.security import generate_password_hash

from app.models.user import User


@pytest.fixture()
def admin_user(app):
    """Crée un utilisateur admin pour les tests."""
    from app.extensions import db

    with app.app_context():
        user = User.query.filter_by(username="gapsadmin").first()
        if not user:
            user = User(
                username="gapsadmin",
                password_hash=generate_password_hash("gaps-password"),
                is_admin=True,
            )
            db.session.add(user)
            db.session.commit()
    return user


@pytest.fixture()
def sample_referential_vehicle(app):
    """Injecte un véhicule avec assez de données pour rendre la fiche parlante."""
    from app.extensions import db
    from app.models.argus import ArgusPrice
    from app.models.collection_job_as24 import CollectionJobAS24
    from app.models.collection_job_lacentrale import CollectionJobLacentrale
    from app.models.market_price import MarketPrice
    from app.models.scan import ScanLog
    from app.models.tire_size import TireSize
    from app.models.vehicle import Vehicle, VehicleSpec
    from app.models.vehicle_synthesis import VehicleSynthesis
    from app.models.youtube import YouTubeTranscript, YouTubeVideo

    with app.app_context():
        vehicle = Vehicle.query.filter_by(brand="Volkswagen", model="Golf").first()
        if not vehicle:
            vehicle = Vehicle(
                brand="Volkswagen",
                model="Golf",
                year_start=2019,
                year_end=2024,
                enrichment_status="complete",
                site_brand_token="Volkswagen",
                site_model_token="Golf",
                as24_slug_make="vw",
                as24_slug_model="golf",
            )
            db.session.add(vehicle)
            db.session.flush()
        else:
            vehicle.site_brand_token = "Volkswagen"
            vehicle.site_model_token = "Golf"
            vehicle.as24_slug_make = "vw"
            vehicle.as24_slug_model = "golf"
            db.session.flush()

        if VehicleSpec.query.filter_by(vehicle_id=vehicle.id).count() == 0:
            db.session.add(
                VehicleSpec(
                    vehicle_id=vehicle.id,
                    fuel_type="Essence",
                    transmission="Automatique",
                    engine="1.5 TSI",
                    power_hp=150,
                    reliability_rating=4.2,
                    known_issues="Pompe à eau à surveiller",
                )
            )

        tire = TireSize.query.filter_by(
            make="volkswagen", model="golf", generation="golf-viii"
        ).first()
        if not tire:
            tire = TireSize(
                make="volkswagen",
                model="golf",
                generation="golf-viii",
                year_start=2019,
                year_end=2024,
                dimensions='[{"size":"205/55R16"},{"size":"225/45R17"}]',
                source="allopneus",
                source_url="https://www.allopneus.com/vehicule/volkswagen/golf/golf-viii",
                dimension_count=2,
                request_count=6,
            )
            db.session.add(tire)

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        market = MarketPrice.query.filter_by(
            make="Volkswagen",
            model="Golf",
            year=2020,
            region="Hauts-de-France",
            country="FR",
        ).first()
        if not market:
            market = MarketPrice(
                make="Volkswagen",
                model="Golf",
                year=2020,
                region="Hauts-de-France",
                country="FR",
                fuel="essence",
                price_min=17000,
                price_median=19500,
                price_mean=19400,
                price_max=21500,
                price_std=900.0,
                price_iqr_mean=19300,
                price_p25=18600,
                price_p75=20100,
                sample_count=24,
                precision=4,
                lbc_estimate_low=18000,
                lbc_estimate_high=20500,
                collected_at=now,
                refresh_after=now + timedelta(hours=12),
            )
            db.session.add(market)

        as24_market = MarketPrice.query.filter_by(
            make="Volkswagen",
            model="Golf",
            year=2020,
            region="Zurich",
            country="CH",
        ).first()
        if not as24_market:
            as24_market = MarketPrice(
                make="Volkswagen",
                model="Golf",
                year=2020,
                region="Zurich",
                country="CH",
                fuel="essence",
                price_min=18500,
                price_median=20700,
                price_mean=20650,
                price_max=22900,
                price_std=1100.0,
                price_iqr_mean=20500,
                price_p25=19800,
                price_p75=21400,
                sample_count=8,
                precision=3,
                collected_at=now,
                refresh_after=now - timedelta(hours=2),
            )
            db.session.add(as24_market)

        if (
            ArgusPrice.query.filter_by(
                vehicle_id=vehicle.id, region="Île-de-France", year=2020
            ).first()
            is None
        ):
            db.session.add(
                ArgusPrice(
                    vehicle_id=vehicle.id,
                    region="Île-de-France",
                    year=2020,
                    price_low=17500,
                    price_mid=18900,
                    price_high=20300,
                    source="seed",
                )
            )

        if (
            ScanLog.query.filter_by(
                vehicle_make="Volkswagen", vehicle_model="Golf", source="leboncoin"
            ).count()
            == 0
        ):
            db.session.add(
                ScanLog(
                    vehicle_make="Volkswagen",
                    vehicle_model="Golf",
                    source="leboncoin",
                    score=78,
                    created_at=now,
                )
            )
            db.session.add(
                ScanLog(
                    vehicle_make="Volkswagen",
                    vehicle_model="Golf",
                    source="autoscout24",
                    score=82,
                    created_at=now - timedelta(days=3),
                )
            )

        video = YouTubeVideo.query.filter_by(video_id="golfvideo1").first()
        if not video:
            video = YouTubeVideo(
                video_id="golfvideo1",
                title="Volkswagen Golf VIII essai fiabilité",
                channel_name="Fiches auto",
                vehicle_id=vehicle.id,
            )
            db.session.add(video)
            db.session.flush()
            db.session.add(
                YouTubeTranscript(
                    video_db_id=video.id,
                    language="fr",
                    full_text="Transcript de test Golf VIII",
                    status="extracted",
                    char_count=1024,
                )
            )

        if (
            VehicleSynthesis.query.filter_by(vehicle_id=vehicle.id, llm_model="llama3").first()
            is None
        ):
            db.session.add(
                VehicleSynthesis(
                    vehicle_id=vehicle.id,
                    make="Volkswagen",
                    model="Golf",
                    llm_model="llama3",
                    prompt_used="prompt test",
                    synthesis_text="Synthèse fiabilité Golf.",
                    raw_transcript_chars=1024,
                    status="draft",
                )
            )

        if (
            CollectionJobAS24.query.filter_by(
                make="Volkswagen", model="Golf", year=2020, tld="ch"
            ).first()
            is None
        ):
            db.session.add(
                CollectionJobAS24(
                    make="Volkswagen",
                    model="Golf",
                    year=2020,
                    region="Zurich",
                    country="CH",
                    tld="ch",
                    slug_make="vw",
                    slug_model="golf",
                    status="pending",
                )
            )

        if (
            CollectionJobLacentrale.query.filter_by(
                make="Volkswagen", model="Golf", year=2020, region="France"
            ).first()
            is None
        ):
            db.session.add(
                CollectionJobLacentrale(
                    make="Volkswagen",
                    model="Golf",
                    year=2020,
                    region="France",
                    country="FR",
                    status="failed",
                )
            )

        db.session.commit()
        return vehicle.id


def _login(client):
    return client.post(
        "/admin/login",
        data={"username": "gapsadmin", "password": "gaps-password"},
        follow_redirects=True,
    )


def test_referential_gaps_requires_login(client):
    """La vue portefeuille nécessite une authentification."""
    response = client.get("/admin/referential-gaps")
    assert response.status_code == 302
    assert "/admin/login" in response.location


def test_referential_gaps_page_loads(client, admin_user, sample_referential_vehicle):
    """La page liste charge et expose les métriques clés par véhicule."""
    with client:
        _login(client)
        response = client.get("/admin/referential-gaps")
        assert response.status_code == 200
        assert b"Gaps m" in response.data
        assert b"Volkswagen" in response.data
        assert b"Golf" in response.data
        assert b"YouTube fine search" in response.data
        assert b"Argus maison" in response.data
        client.get("/admin/logout")


def test_referential_gap_detail_page_loads(client, admin_user, sample_referential_vehicle):
    """La fiche détaillée montre pneus, argus, YouTube et scans."""
    with client:
        _login(client)
        response = client.get(f"/admin/referential-gaps/{sample_referential_vehicle}")
        assert response.status_code == 200
        assert b"205/55R16" in response.data
        assert b"Hauts-de-France" in response.data
        assert b"Zurich" in response.data
        assert b"Lancer la recherche YouTube" in response.data
        assert b"LBC" in response.data
        assert b"AutoScout24" in response.data
        client.get("/admin/logout")
