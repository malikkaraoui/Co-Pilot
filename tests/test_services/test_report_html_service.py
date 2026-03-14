"""Tests du service de generation de rapport HTML/PDF via WeasyPrint."""

import pytest

from app.models.filter_result import FilterResultDB
from app.models.scan import ScanLog

# Reuse the fixtures from conftest.py (app fixture is available)


@pytest.fixture()
def scan_with_filters(app):
    """Cree un scan avec des resultats de filtres pour les tests."""
    from datetime import datetime, timezone

    from app.extensions import db

    with app.app_context():
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        scan = ScanLog(
            url="https://www.leboncoin.fr/voitures/12345.htm",
            score=72,
            is_partial=False,
            vehicle_make="Peugeot",
            vehicle_model="308",
            price_eur=14500,
            source="leboncoin",
            country="FR",
            created_at=now,
            raw_data={
                "year": 2019,
                "km": 85000,
                "phone": "06 12 34 56 78",
                "fuel": "Diesel",
                "gearbox": "Manuelle",
                "color": "Gris",
                "power": "130 ch",
                "doors": "5",
                "body_type": "Berline",
                "seller_name": "Jean Dupont",
                "seller_type": "Particulier",
                "location": "Paris 75001",
            },
        )
        db.session.add(scan)
        db.session.flush()

        filters_data = [
            ("L1", "pass", 1.0, "Donnees completes", None),
            ("L2", "pass", 1.0, "Vehicule reconnu", None),
            (
                "L3",
                "warning",
                0.5,
                "Kilometrage eleve",
                {
                    "mileage_km": 85000,
                    "expected_km": 72000,
                    "age": 6,
                    "km_per_year": 14167,
                    "category": "compacte",
                },
            ),
            (
                "L4",
                "pass",
                0.8,
                "Prix coherent",
                {
                    "price_annonce": 14500,
                    "price_reference": 14900,
                    "delta_eur": -400,
                    "delta_pct": -2.7,
                    "source": "marche_leboncoin",
                    "sample_count": 24,
                    "price_argus_mid": 14300,
                    "price_argus_low": 13600,
                    "price_argus_high": 15100,
                },
            ),
        ]
        for fid, status, score, msg, details in filters_data:
            fr = FilterResultDB(
                scan_id=scan.id,
                filter_id=fid,
                status=status,
                score=score,
                message=msg,
                details=details,
            )
            db.session.add(fr)
        db.session.commit()
        return scan.id


@pytest.fixture()
def scan_minimal(app):
    """Cree un scan minimal sans filtres ni raw_data."""
    from datetime import datetime, timezone

    from app.extensions import db

    with app.app_context():
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        scan = ScanLog(
            url="https://www.autoscout24.de/angebote/99999",
            score=45,
            is_partial=True,
            vehicle_make="BMW",
            vehicle_model="Serie 3",
            price_eur=22000,
            source="autoscout24",
            country="DE",
            created_at=now,
        )
        db.session.add(scan)
        db.session.commit()
        return scan.id


class TestHelpers:
    """Tests des fonctions utilitaires HTML."""

    def test_badge_pass(self):
        from app.services.report_html_service import _badge_html

        result = _badge_html("pass")
        assert "badge-pass" in result
        assert "OK" in result

    def test_badge_fail(self):
        from app.services.report_html_service import _badge_html

        result = _badge_html("fail")
        assert "badge-fail" in result

    def test_badge_custom_label(self):
        from app.services.report_html_service import _badge_html

        result = _badge_html("pass", label="Verifie")
        assert "Verifie" in result

    def test_stars_html(self):
        from app.services.report_html_service import _stars_html

        result = _stars_html(3.0)
        assert "\u2605" * 3 in result
        assert "\u2606" * 2 in result

    def test_phone_link(self):
        from app.services.report_html_service import _phone_link

        result = _phone_link("06 12 34 56 78")
        assert "tel:" in result
        assert "+33" in result

    def test_score_color_class(self):
        from app.services.report_html_service import _score_color_class

        assert _score_color_class(90) == "text-green"
        assert _score_color_class(70) == "text-blue"
        assert _score_color_class(50) == "text-amber"
        assert _score_color_class(20) == "text-red"
        assert _score_color_class(None) == "text-gray"


def _weasyprint_available() -> bool:
    """Verifie que WeasyPrint peut charger ses libs natives (gobject/pango)."""
    try:
        from weasyprint import HTML  # noqa: F401

        return True
    except OSError:
        return False


_skip_no_weasyprint = pytest.mark.skipif(
    not _weasyprint_available(),
    reason="WeasyPrint native libs (gobject/pango) non disponibles",
)


class TestGeneratePdf:
    """Tests de generation PDF end-to-end."""

    @_skip_no_weasyprint
    def test_generate_pdf_returns_valid_bytes(self, app, scan_with_filters):
        from app.services.report_html_service import generate_scan_report_pdf

        with app.app_context():
            pdf_bytes = generate_scan_report_pdf(scan_with_filters)
        assert isinstance(pdf_bytes, bytes)
        assert pdf_bytes[:5] == b"%PDF-"
        assert len(pdf_bytes) > 500

    def test_generate_pdf_unknown_scan_raises(self, app):
        from app.services.report_html_service import generate_scan_report_pdf

        with app.app_context():
            with pytest.raises(ValueError, match="Scan .* introuvable"):
                generate_scan_report_pdf(99999)

    @_skip_no_weasyprint
    def test_generate_pdf_minimal_scan(self, app, scan_minimal):
        from app.services.report_html_service import generate_scan_report_pdf

        with app.app_context():
            pdf_bytes = generate_scan_report_pdf(scan_minimal)
        assert isinstance(pdf_bytes, bytes)
        assert pdf_bytes[:5] == b"%PDF-"
