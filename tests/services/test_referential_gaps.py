"""Tests unitaires du service referential_gaps — logique métier et cas limites."""

from datetime import datetime, timedelta

import pytest

from app.extensions import db as _db
from app.models.argus import ArgusPrice
from app.models.collection_job_as24 import CollectionJobAS24
from app.models.collection_job_lacentrale import CollectionJobLacentrale
from app.models.market_price import MarketPrice
from app.models.scan import ScanLog
from app.models.tire_size import TireSize
from app.models.vehicle import Vehicle, VehicleSpec
from app.models.vehicle_synthesis import VehicleSynthesis
from app.models.youtube import YouTubeTranscript, YouTubeVideo
from app.services.referential_gaps import (
    _compact_status,
    build_referential_compact_profiles,
    build_referential_summary,
    build_vehicle_business_snapshot,
    vehicle_pair_key,
)

NOW = datetime(2026, 3, 11, 12, 0, 0)


# ---------------------------------------------------------------------------
# vehicle_pair_key
# ---------------------------------------------------------------------------


class TestVehiclePairKey:
    def test_basic(self):
        assert vehicle_pair_key("Volkswagen", "Golf") == ("volkswagen", "golf")

    def test_case_insensitive(self):
        assert vehicle_pair_key("BMW", "Serie 3") == vehicle_pair_key("bmw", "serie 3")

    def test_none_brand(self):
        k = vehicle_pair_key(None, "Golf")
        assert k[0] == ""
        assert k[1] == "golf"

    def test_none_model(self):
        k = vehicle_pair_key("Volkswagen", None)
        assert k[0] == "volkswagen"
        assert k[1] == ""

    def test_both_none(self):
        assert vehicle_pair_key(None, None) == ("", "")

    def test_whitespace_and_accents(self):
        k1 = vehicle_pair_key("Citroën", "C3")
        k2 = vehicle_pair_key("citroën", "c3")
        assert k1 == k2


# ---------------------------------------------------------------------------
# _compact_status
# ---------------------------------------------------------------------------


class TestCompactStatus:
    def test_healthy_zero_gaps(self):
        assert _compact_status(0, has_market=True, has_scans=True) == "healthy"

    def test_healthy_one_gap(self):
        assert _compact_status(1, has_market=True, has_scans=True) == "healthy"

    def test_attention_two_gaps(self):
        assert _compact_status(2, has_market=True, has_scans=True) == "attention"

    def test_attention_four_gaps(self):
        assert _compact_status(4, has_market=True, has_scans=True) == "attention"

    def test_critical_five_gaps(self):
        assert _compact_status(5, has_market=True, has_scans=True) == "critical"

    def test_critical_many_gaps(self):
        assert _compact_status(10, has_market=True, has_scans=True) == "critical"

    def test_critical_no_market_no_scans(self):
        """Même avec 0 gaps, pas de market ET pas de scans = critical."""
        assert _compact_status(0, has_market=False, has_scans=False) == "critical"

    def test_critical_no_market_no_scans_with_gaps(self):
        assert _compact_status(3, has_market=False, has_scans=False) == "critical"

    def test_not_critical_if_market_present(self):
        """1 gap + market = healthy, pas critical."""
        assert _compact_status(1, has_market=True, has_scans=False) == "healthy"

    def test_not_critical_if_scans_present(self):
        """1 gap + scans = healthy, pas critical."""
        assert _compact_status(1, has_market=False, has_scans=True) == "healthy"


# ---------------------------------------------------------------------------
# Fixtures pour les tests avec DB
# ---------------------------------------------------------------------------


@pytest.fixture()
def empty_vehicle(app):
    """Véhicule nu — aucune donnée rattachée."""
    with app.app_context():
        v = Vehicle(brand="Tesla", model="Model 3", year_start=2020, year_end=2025)
        _db.session.add(v)
        _db.session.commit()
        vid = v.id
    yield vid
    with app.app_context():
        Vehicle.query.filter_by(id=vid).delete()
        _db.session.commit()


@pytest.fixture()
def rich_vehicle(app):
    """Véhicule complet avec toutes les sources renseignées."""
    with app.app_context():
        v = Vehicle(
            brand="Peugeot",
            model="308",
            year_start=2021,
            year_end=2025,
            enrichment_status="complete",
            site_brand_token="Peugeot",
            site_model_token="308",
            as24_slug_make="peugeot",
            as24_slug_model="308",
        )
        _db.session.add(v)
        _db.session.flush()

        # Specs
        _db.session.add(
            VehicleSpec(
                vehicle_id=v.id,
                fuel_type="Essence",
                transmission="Manuelle",
                engine="1.2 PureTech",
                power_hp=130,
                reliability_rating=3.8,
                known_issues="Courroie de distribution",
            )
        )

        # Pneus
        _db.session.add(
            TireSize(
                make="peugeot",
                model="308",
                generation="308-iii",
                year_start=2021,
                year_end=2025,
                dimensions='[{"size":"205/55R16"},{"size":"225/40R18"}]',
                source="allopneus",
                dimension_count=2,
                request_count=4,
            )
        )

        # Market FR avec LBC estimate
        _db.session.add(
            MarketPrice(
                make="Peugeot",
                model="308",
                year=2022,
                region="Île-de-France",
                country="FR",
                fuel="essence",
                price_min=15000,
                price_median=17500,
                price_mean=17400,
                price_max=20000,
                price_std=800.0,
                price_iqr_mean=17300,
                price_p25=16500,
                price_p75=18200,
                sample_count=30,
                precision=4,
                lbc_estimate_low=16000,
                lbc_estimate_high=18500,
                collected_at=NOW,
                refresh_after=NOW + timedelta(hours=12),
            )
        )

        # Market CH (hors FR)
        _db.session.add(
            MarketPrice(
                make="Peugeot",
                model="308",
                year=2022,
                region="Bern",
                country="CH",
                fuel="essence",
                price_min=16000,
                price_median=18500,
                price_mean=18400,
                price_max=21000,
                price_std=900.0,
                price_iqr_mean=18300,
                price_p25=17500,
                price_p75=19200,
                sample_count=12,
                precision=3,
                collected_at=NOW,
                refresh_after=NOW - timedelta(hours=2),
            )
        )

        # Argus seed
        _db.session.add(
            ArgusPrice(
                vehicle_id=v.id,
                region="Île-de-France",
                year=2022,
                price_low=15500,
                price_mid=17000,
                price_high=18500,
                source="seed",
            )
        )

        # Scans
        _db.session.add(
            ScanLog(
                vehicle_make="Peugeot",
                vehicle_model="308",
                source="leboncoin",
                score=75,
                created_at=NOW,
            )
        )
        _db.session.add(
            ScanLog(
                vehicle_make="Peugeot",
                vehicle_model="308",
                source="autoscout24",
                score=80,
                created_at=NOW - timedelta(days=2),
            )
        )

        # YouTube + transcript
        video = YouTubeVideo(
            video_id="peugeot308vid",
            title="Peugeot 308 III fiabilité",
            channel_name="Auto Review",
            vehicle_id=v.id,
        )
        _db.session.add(video)
        _db.session.flush()
        _db.session.add(
            YouTubeTranscript(
                video_db_id=video.id,
                language="fr",
                full_text="Transcript test 308",
                status="extracted",
                char_count=512,
            )
        )

        # Synthesis
        _db.session.add(
            VehicleSynthesis(
                vehicle_id=v.id,
                make="Peugeot",
                model="308",
                llm_model="llama3",
                prompt_used="test",
                synthesis_text="Synthèse 308.",
                raw_transcript_chars=512,
                status="draft",
            )
        )

        # Jobs
        _db.session.add(
            CollectionJobAS24(
                make="Peugeot",
                model="308",
                year=2022,
                region="Bern",
                country="CH",
                tld="ch",
                slug_make="peugeot",
                slug_model="308",
                status="done",
            )
        )
        _db.session.add(
            CollectionJobLacentrale(
                make="Peugeot",
                model="308",
                year=2022,
                region="France",
                country="FR",
                status="done",
            )
        )

        _db.session.commit()
        vid = v.id
    yield vid
    with app.app_context():
        # Nettoyage en cascade
        CollectionJobLacentrale.query.filter_by(make="Peugeot", model="308").delete()
        CollectionJobAS24.query.filter_by(make="Peugeot", model="308").delete()
        VehicleSynthesis.query.filter_by(vehicle_id=vid).delete()
        YouTubeTranscript.query.filter(
            YouTubeTranscript.video_db_id.in_(
                _db.session.query(YouTubeVideo.id).filter_by(vehicle_id=vid)
            )
        ).delete(synchronize_session=False)
        YouTubeVideo.query.filter_by(vehicle_id=vid).delete()
        ScanLog.query.filter_by(vehicle_make="Peugeot", vehicle_model="308").delete()
        ArgusPrice.query.filter_by(vehicle_id=vid).delete()
        MarketPrice.query.filter_by(make="Peugeot", model="308").delete()
        TireSize.query.filter_by(make="peugeot", model="308").delete()
        VehicleSpec.query.filter_by(vehicle_id=vid).delete()
        Vehicle.query.filter_by(id=vid).delete()
        _db.session.commit()


# ---------------------------------------------------------------------------
# build_referential_compact_profiles
# ---------------------------------------------------------------------------


class TestBuildCompactProfiles:
    def test_empty_vehicle_is_critical(self, app, empty_vehicle):
        """Un véhicule sans aucune donnée doit être critical avec 8 gaps."""
        with app.app_context():
            v = Vehicle.query.get(empty_vehicle)
            profiles = build_referential_compact_profiles([v])
            p = profiles[v.id]
            assert p["status"] == "critical"
            assert p["gap_count"] == 8
            assert p["readiness_pct"] == 0
            assert p["has_specs"] is False
            assert p["has_tires"] is False
            assert p["has_market"] is False
            assert p["has_youtube"] is False
            assert p["has_scans"] is False
            assert p["has_lbc_tokens"] is False
            assert p["has_as24_tokens"] is False

    def test_rich_vehicle_is_healthy(self, app, rich_vehicle):
        """Un véhicule complet doit être healthy avec 0 gaps."""
        with app.app_context():
            v = Vehicle.query.get(rich_vehicle)
            profiles = build_referential_compact_profiles([v])
            p = profiles[v.id]
            assert p["status"] == "healthy"
            assert p["gap_count"] == 0
            assert p["readiness_pct"] == 100
            assert p["has_specs"] is True
            assert p["has_tires"] is True
            assert p["has_market"] is True
            assert p["has_lbc_signal"] is True
            assert p["has_as24_signal"] is True
            assert p["has_youtube"] is True
            assert p["has_scans"] is True
            assert p["has_lbc_tokens"] is True
            assert p["has_as24_tokens"] is True

    def test_empty_list_returns_empty(self, app):
        """Pas de véhicules → dict vide."""
        with app.app_context():
            profiles = build_referential_compact_profiles([])
            assert profiles == {}

    def test_mixed_vehicles(self, app, empty_vehicle, rich_vehicle):
        """Deux véhicules : un nu et un complet, vérifier l'isolation."""
        with app.app_context():
            v_empty = Vehicle.query.get(empty_vehicle)
            v_rich = Vehicle.query.get(rich_vehicle)
            profiles = build_referential_compact_profiles([v_empty, v_rich])
            assert profiles[v_empty.id]["status"] == "critical"
            assert profiles[v_rich.id]["status"] == "healthy"
            assert len(profiles) == 2


# ---------------------------------------------------------------------------
# build_referential_summary
# ---------------------------------------------------------------------------


class TestBuildSummary:
    def test_summary_empty(self, app):
        """Base vide → tout à 0, pas de division par zéro."""
        with app.app_context():
            summary = build_referential_summary([], {})
            assert summary["total_vehicles"] == 0
            assert summary["avg_readiness_pct"] == 0
            assert summary["critical_count"] == 0

    def test_summary_single_critical(self, app, empty_vehicle):
        """Un véhicule nu → critical_count=1, avg_readiness=0."""
        with app.app_context():
            v = Vehicle.query.get(empty_vehicle)
            profiles = build_referential_compact_profiles([v])
            summary = build_referential_summary([v], profiles)
            assert summary["total_vehicles"] == 1
            assert summary["critical_count"] == 1
            assert summary["healthy_count"] == 0
            assert summary["avg_readiness_pct"] == 0
            assert summary["with_specs"] == 0

    def test_summary_single_healthy(self, app, rich_vehicle):
        """Un véhicule complet → healthy_count=1, avg_readiness=100."""
        with app.app_context():
            v = Vehicle.query.get(rich_vehicle)
            profiles = build_referential_compact_profiles([v])
            summary = build_referential_summary([v], profiles)
            assert summary["total_vehicles"] == 1
            assert summary["healthy_count"] == 1
            assert summary["critical_count"] == 0
            assert summary["avg_readiness_pct"] == 100
            assert summary["with_specs"] == 1
            assert summary["with_tires"] == 1

    def test_summary_mixed(self, app, empty_vehicle, rich_vehicle):
        """Deux véhicules → moyennes correctes."""
        with app.app_context():
            vehicles = [Vehicle.query.get(empty_vehicle), Vehicle.query.get(rich_vehicle)]
            profiles = build_referential_compact_profiles(vehicles)
            summary = build_referential_summary(vehicles, profiles)
            assert summary["total_vehicles"] == 2
            assert summary["critical_count"] == 1
            assert summary["healthy_count"] == 1
            assert summary["avg_readiness_pct"] == 50  # (0 + 100) / 2


# ---------------------------------------------------------------------------
# build_vehicle_business_snapshot
# ---------------------------------------------------------------------------


class TestBuildBusinessSnapshot:
    def test_empty_vehicle_snapshot(self, app, empty_vehicle):
        """Véhicule nu : toutes les sections vides, gaps maximum."""
        with app.app_context():
            v = Vehicle.query.get(empty_vehicle)
            snap = build_vehicle_business_snapshot(v, now=NOW)

            assert snap["vehicle"] is v
            assert snap["status"] == "critical"
            assert snap["gap_count"] >= 8
            assert snap["readiness_pct"] <= 20

            # Sections vides
            assert snap["specs"]["count"] == 0
            assert snap["tires"]["has_data"] is False
            assert snap["market"]["has_data"] is False
            assert snap["seed_argus"]["has_data"] is False
            assert snap["youtube"]["has_data"] is False
            assert snap["scans"]["has_data"] is False
            assert snap["tokens"]["lbc_ready"] is False
            assert snap["tokens"]["as24_ready"] is False

            # Gaps attendus
            assert "Specs techniques absentes" in snap["gap_items"]
            assert "Dimensions pneus absentes" in snap["gap_items"]
            assert "Argus maison absent" in snap["gap_items"]
            assert "Aucun scan historique" in snap["gap_items"]
            assert "Tokens LBC manquants" in snap["gap_items"]
            assert "Slugs AS24 manquants" in snap["gap_items"]

    def test_rich_vehicle_snapshot(self, app, rich_vehicle):
        """Véhicule complet : toutes les sections remplies, 0 gaps."""
        with app.app_context():
            v = Vehicle.query.get(rich_vehicle)
            snap = build_vehicle_business_snapshot(v, now=NOW)

            assert snap["status"] == "healthy"
            assert snap["gap_count"] == 0
            assert snap["readiness_pct"] == 100
            assert snap["gap_items"] == []

            # Specs
            assert snap["specs"]["count"] == 1
            assert "Essence" in snap["specs"]["fuel_values"]
            assert snap["specs"]["max_hp"] == 130
            assert snap["specs"]["avg_reliability"] == 3.8
            assert snap["specs"]["known_issues_count"] == 1

            # Pneus
            assert snap["tires"]["has_data"] is True
            assert snap["tires"]["dimension_count"] == 2
            assert "205/55R16" in snap["tires"]["dimensions_preview"]
            assert "allopneus" in snap["tires"]["source_values"]

            # Market
            assert snap["market"]["has_data"] is True
            assert snap["market"]["count"] == 2
            assert "FR" in snap["market"]["countries"]
            assert "CH" in snap["market"]["countries"]
            assert snap["market"]["lbc_estimate_count"] == 1
            assert snap["market"]["non_fr_count"] == 1
            assert snap["market"]["total_samples"] == 42  # 30 + 12

            # Market freshness: FR est fresh, CH est expiré
            assert snap["market"]["fresh_count"] == 1

            # Seed argus
            assert snap["seed_argus"]["has_data"] is True
            assert snap["seed_argus"]["count"] == 1

            # YouTube
            assert snap["youtube"]["transcript_count"] == 1
            assert snap["youtube"]["synthesis_count"] == 1
            assert snap["youtube"]["has_data"] is True

            # Scans
            assert snap["scans"]["has_data"] is True
            assert snap["scans"]["total"] == 2
            lbc_source = next(s for s in snap["scans"]["by_source"] if s["source"] == "leboncoin")
            assert lbc_source["count"] == 1

            # Tokens
            assert snap["tokens"]["lbc_ready"] is True
            assert snap["tokens"]["as24_ready"] is True
            assert snap["tokens"]["site_brand_token"] == "Peugeot"
            assert snap["tokens"]["as24_slug_make"] == "peugeot"

            # Jobs
            assert snap["jobs"]["as24"]["done"] == 1
            assert snap["jobs"]["lacentrale"]["done"] == 1

    def test_scan_time_windows(self, app, rich_vehicle):
        """Les fenêtres temporelles de scan (24h/7j/30j) sont correctes."""
        with app.app_context():
            v = Vehicle.query.get(rich_vehicle)
            snap = build_vehicle_business_snapshot(v, now=NOW)

            # scan LBC = NOW (dans les 24h), scan AS24 = NOW-2j (dans les 7j)
            assert snap["scans"]["day"] == 1
            assert snap["scans"]["week"] == 2
            assert snap["scans"]["month"] == 2

    def test_gap_argus_trop_fragile(self, app):
        """Argus présent mais tous en dessous du seuil d'échantillon → gap spécifique."""
        with app.app_context():
            v = Vehicle(brand="Dacia", model="Sandero", year_start=2020, year_end=2025)
            _db.session.add(v)
            _db.session.flush()

            # Market avec très peu d'annonces (sample_count=1)
            _db.session.add(
                MarketPrice(
                    make="Dacia",
                    model="Sandero",
                    year=2022,
                    region="Provence",
                    country="FR",
                    fuel="essence",
                    price_min=8000,
                    price_median=9500,
                    price_mean=9400,
                    price_max=11000,
                    price_std=500.0,
                    price_iqr_mean=9300,
                    price_p25=8800,
                    price_p75=10000,
                    sample_count=1,
                    precision=1,
                    collected_at=NOW,
                    refresh_after=NOW + timedelta(hours=6),
                )
            )
            _db.session.commit()

            snap = build_vehicle_business_snapshot(v, now=NOW)
            assert "Argus maison trop fragile" in snap["gap_items"]
            assert "Argus maison absent" not in snap["gap_items"]

            # Cleanup
            MarketPrice.query.filter_by(make="Dacia", model="Sandero").delete()
            Vehicle.query.filter_by(id=v.id).delete()
            _db.session.commit()

    def test_gap_no_youtube_but_synthesis(self, app):
        """Pas de transcript mais une synthèse → pas de gap YouTube."""
        with app.app_context():
            v = Vehicle(brand="Seat", model="Ibiza", year_start=2017, year_end=2024)
            _db.session.add(v)
            _db.session.flush()

            _db.session.add(
                VehicleSynthesis(
                    vehicle_id=v.id,
                    make="Seat",
                    model="Ibiza",
                    llm_model="llama3",
                    prompt_used="test",
                    synthesis_text="Synthèse Ibiza.",
                    raw_transcript_chars=256,
                    status="draft",
                )
            )
            _db.session.commit()

            snap = build_vehicle_business_snapshot(v, now=NOW)
            assert "Aucune matière YouTube / fiabilité" not in snap["gap_items"]

            # Cleanup
            VehicleSynthesis.query.filter_by(vehicle_id=v.id).delete()
            Vehicle.query.filter_by(id=v.id).delete()
            _db.session.commit()

    def test_gap_lbc_estimate_missing(self, app):
        """Market présent mais sans estimation LBC → gap spécifique."""
        with app.app_context():
            v = Vehicle(brand="Opel", model="Corsa", year_start=2019, year_end=2025)
            _db.session.add(v)
            _db.session.flush()

            _db.session.add(
                MarketPrice(
                    make="Opel",
                    model="Corsa",
                    year=2021,
                    region="Bretagne",
                    country="FR",
                    fuel="essence",
                    price_min=10000,
                    price_median=12000,
                    price_mean=11900,
                    price_max=14000,
                    price_std=600.0,
                    price_iqr_mean=11800,
                    price_p25=11000,
                    price_p75=12800,
                    sample_count=20,
                    precision=3,
                    lbc_estimate_low=None,
                    lbc_estimate_high=None,
                    collected_at=NOW,
                    refresh_after=NOW + timedelta(hours=6),
                )
            )
            _db.session.commit()

            snap = build_vehicle_business_snapshot(v, now=NOW)
            assert "Aucune estimation LBC en base" in snap["gap_items"]

            # Cleanup
            MarketPrice.query.filter_by(make="Opel", model="Corsa").delete()
            Vehicle.query.filter_by(id=v.id).delete()
            _db.session.commit()

    def test_gap_no_as24_coverage(self, app):
        """Que du marché FR, aucun hors FR → gap couverture AS24."""
        with app.app_context():
            v = Vehicle(brand="Fiat", model="500", year_start=2020, year_end=2025)
            _db.session.add(v)
            _db.session.flush()

            _db.session.add(
                MarketPrice(
                    make="Fiat",
                    model="500",
                    year=2021,
                    region="PACA",
                    country="FR",
                    fuel="essence",
                    price_min=9000,
                    price_median=11000,
                    price_mean=10900,
                    price_max=13000,
                    price_std=550.0,
                    price_iqr_mean=10800,
                    price_p25=10000,
                    price_p75=11700,
                    sample_count=25,
                    precision=3,
                    lbc_estimate_low=10000,
                    lbc_estimate_high=12000,
                    collected_at=NOW,
                    refresh_after=NOW + timedelta(hours=6),
                )
            )
            _db.session.commit()

            snap = build_vehicle_business_snapshot(v, now=NOW)
            assert "Aucune couverture AS24 hors FR" in snap["gap_items"]

            # Cleanup
            MarketPrice.query.filter_by(make="Fiat", model="500").delete()
            Vehicle.query.filter_by(id=v.id).delete()
            _db.session.commit()

    def test_readiness_calculation(self, app, rich_vehicle):
        """Readiness = (10 - gaps) / 10 * 100, snapshot utilise 10 critères."""
        with app.app_context():
            v = Vehicle.query.get(rich_vehicle)
            snap = build_vehicle_business_snapshot(v, now=NOW)
            expected = round(100 * (10 - snap["gap_count"]) / 10)
            assert snap["readiness_pct"] == expected

    def test_specs_aggregation(self, app):
        """Plusieurs specs → fuel_values triés, max_hp correct, avg_reliability."""
        with app.app_context():
            v = Vehicle(brand="Renault", model="Megane", year_start=2016, year_end=2023)
            _db.session.add(v)
            _db.session.flush()

            _db.session.add(
                VehicleSpec(
                    vehicle_id=v.id,
                    fuel_type="Diesel",
                    transmission="Manuelle",
                    power_hp=110,
                    reliability_rating=3.5,
                )
            )
            _db.session.add(
                VehicleSpec(
                    vehicle_id=v.id,
                    fuel_type="Essence",
                    transmission="Automatique",
                    power_hp=140,
                    reliability_rating=4.0,
                )
            )
            _db.session.commit()

            snap = build_vehicle_business_snapshot(v, now=NOW)
            assert snap["specs"]["count"] == 2
            assert snap["specs"]["fuel_values"] == ["Diesel", "Essence"]
            assert snap["specs"]["transmission_values"] == ["Automatique", "Manuelle"]
            assert snap["specs"]["max_hp"] == 140
            assert snap["specs"]["avg_reliability"] == 3.8  # (3.5 + 4.0) / 2

            # Cleanup
            VehicleSpec.query.filter_by(vehicle_id=v.id).delete()
            Vehicle.query.filter_by(id=v.id).delete()
            _db.session.commit()

    def test_last_seen_scan(self, app, rich_vehicle):
        """last_seen = created_at du scan le plus récent."""
        with app.app_context():
            v = Vehicle.query.get(rich_vehicle)
            snap = build_vehicle_business_snapshot(v, now=NOW)
            assert snap["scans"]["last_seen"] is not None
            # Le scan LBC est à NOW, le plus récent
            assert snap["scans"]["last_seen"] >= NOW - timedelta(seconds=5)
