"""Tests du normaliseur `docs/data FULL`."""

from scripts.normalize_data_full import (
    RawVehicle,
    normalize_vehicle,
    normalize_vehicles,
    transform_payload,
)


def test_normalize_vehicle_splits_family_generation_and_body() -> None:
    normalized = normalize_vehicle(
        RawVehicle(
            marque="AUDI",
            generation="A1",
            modele="A1 (2E GENERATION) SPORTBACK",
            annee=2024,
        )
    )

    assert normalized["brand"] == "Audi"
    assert normalized["model"] == "A1"
    assert normalized["generation"] == "2E GENERATION"
    assert normalized["body_variant"] == "Sportback"
    assert normalized["brand_lookup_key"] == "audi"
    assert normalized["model_lookup_key"] == "a1"
    assert normalized["generation_lookup_key"] == "2egeneration"
    assert normalized["body_variant_lookup_key"] == "sportback"


def test_normalize_vehicles_aggregates_contiguous_years() -> None:
    vehicles = normalize_vehicles(
        [
            {
                "marque": "AUDI",
                "generation": "A1",
                "modele": "A1 (2E GENERATION) SPORTBACK",
                "annee": "2023",
                "url": "https://example.test/2023",
            },
            {
                "marque": "AUDI",
                "generation": "A1",
                "modele": "A1 (2E GENERATION) SPORTBACK",
                "annee": "2024",
                "url": "https://example.test/2024",
            },
            {
                "marque": "AUDI",
                "generation": "A1",
                "modele": "A1 (2E GENERATION) SPORTBACK",
                "annee": "2026",
                "url": "https://example.test/2026",
            },
        ]
    )

    assert len(vehicles) == 2
    assert vehicles[0].year_start == 2023
    assert vehicles[0].year_end == 2024
    assert vehicles[0].years == [2023, 2024]
    assert vehicles[1].year_start == 2026
    assert vehicles[1].year_end == 2026
    assert vehicles[1].years == [2026]


def test_transform_payload_can_rebuild_from_schema_v2_sources() -> None:
    payload = {
        "meta": {
            "schema_version": 2,
            "normalized_at": "2026-03-14",
        },
        "vehicles": [
            {
                "brand": "Ac",
                "model": "Mkvi",
                "generation": None,
                "body_variant": None,
                "year_start": 2011,
                "year_end": 2012,
                "years": [2011, 2012],
                "brand_lookup_key": "ac",
                "model_lookup_key": "mkvi",
                "generation_lookup_key": None,
                "body_variant_lookup_key": None,
                "referential_key": "ac:mkvi",
                "source_brand": "AC",
                "source_generation": "MKVI",
                "source_model": "MKVI",
            }
        ],
    }

    transformed = transform_payload(payload)

    assert transformed["meta"]["schema_version"] == 2
    assert transformed["vehicles"][0]["brand"] == "AC"
    assert transformed["vehicles"][0]["model"] == "MKVI"
