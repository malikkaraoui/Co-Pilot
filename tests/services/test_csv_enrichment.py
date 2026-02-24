"""Tests pour csv_enrichment service."""

from app.services.csv_enrichment import _load_csv_catalog


def test_load_csv_catalog_structure():
    """Le catalogue CSV doit contenir les métadonnées attendues."""
    catalog = _load_csv_catalog()

    # Le catalogue doit être un dict non vide
    assert isinstance(catalog, dict)
    assert len(catalog) > 0

    # Vérifier qu'une entrée type existe (Renault Clio dans le CSV Kaggle)
    # Note: adapter si le CSV test ne contient pas Clio
    sample_key = next(iter(catalog.keys()))
    assert isinstance(sample_key, tuple)
    assert len(sample_key) == 2  # (make, model)

    # Vérifier la structure de métadonnées
    meta = catalog[sample_key]
    assert "year_start" in meta
    assert "year_end" in meta
    assert "specs_count" in meta
    assert isinstance(meta["specs_count"], int)
    assert meta["specs_count"] > 0


def test_load_csv_catalog_year_aggregation():
    """Le catalogue doit agréger les plages d'années correctement."""
    catalog = _load_csv_catalog()

    # Trouver un véhicule avec plusieurs fiches (specs_count > 1)
    multi_spec = None
    for key, meta in catalog.items():
        if meta["specs_count"] > 1:
            multi_spec = meta
            break

    # Si on a trouvé un véhicule multi-fiches, vérifier la cohérence
    if multi_spec:
        # year_start <= year_end (si les deux sont définis)
        if multi_spec["year_start"] and multi_spec["year_end"]:
            assert multi_spec["year_start"] <= multi_spec["year_end"]


def test_load_csv_catalog_cache():
    """Le catalogue doit être mis en cache (même instance)."""
    catalog1 = _load_csv_catalog()
    catalog2 = _load_csv_catalog()

    # Même objet en mémoire grâce au cache LRU
    assert catalog1 is catalog2
