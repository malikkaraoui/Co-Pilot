"""Tests du service `tire_service` (sans appels réseau)."""


def test_wheel_size_model_map():
    """Verifie le mapping des modeles composites pour Wheel-Size API."""
    from app.services.tire_service import WHEEL_SIZE_MODEL_MAP

    assert WHEEL_SIZE_MODEL_MAP["a4 allroad"] == "a4"
    assert WHEEL_SIZE_MODEL_MAP["a6 allroad"] == "a6"
    assert WHEEL_SIZE_MODEL_MAP["allroad"] == "a6"
    # Un modele normal ne doit PAS etre dans le mapping
    assert "golf" not in WHEEL_SIZE_MODEL_MAP


def test_store_tire_sizes_dedup_and_sort(db, app):
    from app.services.tire_service import store_tire_sizes

    dims = [
        {"size": "205/55R16", "load_index": 91, "speed_index": "V", "is_stock": True},
        {"size": "205/55R16", "load_index": 91, "speed_index": "V", "is_stock": True},
        {"size": "195/65R15", "load_index": 91, "speed_index": "H", "is_stock": True},
    ]

    with app.app_context():
        t = store_tire_sizes(
            make="volkswagen",
            model="golf",
            generation="golf-vii",
            year_start=2012,
            year_end=2021,
            dimensions=dims,
            source="allopneus",
            source_url="https://example.com",
        )

        out = t.get_dimensions_list()
        assert t.dimension_count == 2
        assert len(out) == 2
        # Tri par diamètre de jante : R15 avant R16
        assert out[0]["size"].endswith("R15")
        assert out[1]["size"].endswith("R16")


def test_store_tire_sizes_upsert_updates_existing(db, app):
    from app.services.tire_service import store_tire_sizes

    with app.app_context():
        first = store_tire_sizes(
            make="volkswagen",
            model="golf",
            generation="golf-vii",
            year_start=2012,
            year_end=2021,
            dimensions=[{"size": "205/55R16"}],
            source="allopneus",
        )

        second = store_tire_sizes(
            make="volkswagen",
            model="golf",
            generation="golf-vii",
            year_start=2013,
            year_end=2022,
            dimensions=[{"size": "195/65R15"}, {"size": "205/55R16"}],
            source="wheel-size",
            source_url="https://wheel-size.example",
        )

        assert second.id == first.id
        assert second.source == "wheel-size"
        assert second.year_start == 2013
        assert second.year_end == 2022
        assert second.dimension_count == 2
