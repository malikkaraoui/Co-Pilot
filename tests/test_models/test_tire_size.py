"""Tests du modèle TireSize."""

import json


def test_tire_size_get_set_dimensions(db):
    from app.models.tire_size import TireSize

    t = TireSize(
        make="volkswagen",
        model="golf",
        generation="golf-vii",
        year_start=2012,
        year_end=2021,
        dimensions=json.dumps([{"size": "205/55R16", "load_index": 91, "speed_index": "V"}]),
        source="allopneus",
        source_url="https://example.com",
        dimension_count=1,
        request_count=0,
    )
    db.session.add(t)
    db.session.commit()

    dims = t.get_dimensions_list()
    assert isinstance(dims, list)
    assert dims[0]["size"] == "205/55R16"

    t.set_dimensions_list(
        [
            {"size": "195/65R15", "load_index": 91, "speed_index": "H"},
            {"size": "205/55R16", "load_index": 91, "speed_index": "V"},
        ]
    )
    db.session.commit()

    assert t.dimension_count == 2
    dims2 = t.get_dimensions_list()
    assert len(dims2) == 2
    assert {d["size"] for d in dims2} == {"195/65R15", "205/55R16"}
