"""Tests pour csv_enrichment service."""

from app.models.vehicle import Vehicle
from app.services.csv_enrichment import _load_csv_catalog, get_csv_missing_vehicles


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


def test_get_csv_missing_vehicles_structure(app):
    """La fonction doit retourner une liste de dicts avec structure attendue."""
    with app.app_context():
        missing = get_csv_missing_vehicles()

        # Doit retourner une liste
        assert isinstance(missing, list)

        # Si la liste n'est pas vide, vérifier la structure
        if missing:
            first = missing[0]
            assert "brand" in first
            assert "model" in first
            assert "year_start" in first
            assert "year_end" in first
            assert "specs_count" in first

            # Vérifier les types
            assert isinstance(first["brand"], str)
            assert isinstance(first["model"], str)
            assert isinstance(first["specs_count"], int)
            assert first["specs_count"] > 0


def test_get_csv_missing_vehicles_excludes_existing(app, db):
    """Les véhicules du référentiel ne doivent PAS apparaître dans missing."""
    with app.app_context():
        missing = get_csv_missing_vehicles()

        # Récupérer tous les véhicules du référentiel
        existing = {(v.brand.lower(), v.model.lower()) for v in Vehicle.query.all()}

        # Vérifier qu'aucun véhicule manquant n'est dans le référentiel
        for vehicle in missing:
            key = (vehicle["brand"].lower(), vehicle["model"].lower())
            assert key not in existing, (
                f"{vehicle['brand']} {vehicle['model']} ne devrait pas être "
                f"dans missing car il est dans le référentiel"
            )


def test_get_csv_missing_vehicles_sorted_by_specs(app):
    """La liste doit être triée par specs_count descendant."""
    with app.app_context():
        missing = get_csv_missing_vehicles()

        # Si au moins 2 éléments, vérifier le tri
        if len(missing) >= 2:
            specs_counts = [v["specs_count"] for v in missing]
            # Vérifier que la liste est triée par ordre décroissant
            assert specs_counts == sorted(specs_counts, reverse=True)
