"""Tests de non-regression pour le rapport PDF.

Verrouille les corrections critiques pour eviter toute regression :
- Accents francais corrects dans les titres et textes
- Pas de donnees techniques brutes (delta_eur, recall_count, etc.)
- PDF valide genere par WeasyPrint
- API retourne un vrai PDF binaire
"""

import pytest

from app.models.filter_result import FilterResultDB
from app.models.scan import ScanLog


@pytest.fixture()
def scan_full(app):
    """Scan complet avec filtres warning/fail pour tester les signal cards."""
    from datetime import datetime, timezone

    from app.extensions import db

    with app.app_context():
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        scan = ScanLog(
            url="https://www.leboncoin.fr/voitures/99999.htm",
            score=65,
            is_partial=False,
            vehicle_make="Renault",
            vehicle_model="Clio",
            price_eur=8500,
            source="leboncoin",
            country="FR",
            created_at=now,
            raw_data={
                "year": 2018,
                "km": 120000,
                "phone": "06 99 88 77 66",
                "fuel": "Essence",
                "gearbox": "Manuelle",
            },
        )
        db.session.add(scan)
        db.session.flush()

        filters_data = [
            ("L1", "pass", 1.0, "Données complètes", None),
            ("L2", "pass", 1.0, "Modèle reconnu : Renault Clio", None),
            (
                "L3",
                "pass",
                1.0,
                "Cohérence des données OK",
                {"mileage_km": 120000, "expected_km": 110000, "age": 7},
            ),
            (
                "L4",
                "warning",
                0.5,
                "Prix 15% en dessous de la référence",
                {
                    "price_annonce": 8500,
                    "price_reference": 10000,
                    "delta_eur": -1500,
                    "delta_pct": -15.0,
                    "source": "marche_leboncoin",
                    "sample_count": 42,
                },
            ),
            ("L5", "pass", 1.0, "Valeurs dans la norme statistique", None),
            ("L6", "pass", 1.0, "Numéro de mobile français standard", None),
            ("L7", "skip", 0.0, "Vendeur particulier", None),
            ("L8", "pass", 1.0, "Aucun signal d'import détecté", None),
            ("L9", "pass", 1.0, "Annonce complète et détaillée", None),
            (
                "L10",
                "warning",
                0.5,
                "Annonce en ligne depuis 15 jours",
                {"days_online": 15},
            ),
            (
                "L11",
                "fail",
                0.0,
                "Véhicule concerné par le rappel Airbag Takata",
                {
                    "recall_count": 1,
                    "type": "takata_airbag",
                    "severite": "critical",
                    "takata_airbag": True,
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


class TestAccentsFrancais:
    """Les titres et textes du PDF doivent avoir les accents corrects."""

    def test_titres_sections_avec_accents(self, app, scan_full):
        from app.services.report_html_service import (
            _assemble_html,
            _build_report_sections,
        )

        with app.app_context():
            from app.extensions import db

            scan = db.session.get(ScanLog, scan_full)
            filters = FilterResultDB.query.filter_by(scan_id=scan_full).all()
            sections = _build_report_sections(scan, filters, None)
            html = _assemble_html(scan, sections)

        # Titres avec accents
        assert "Informations véhicule" in html
        assert "Prix vs marché" in html
        assert "Kilométrage" in html
        assert "Résultats des filtres" in html
        assert "Signaux d'alerte" in html

        # Textes avec accents
        assert "Référence :" in html
        assert "Observé :" in html
        assert "Catégorie :" in html or "catégorie" in html.lower()
        assert "Échantillon :" in html

    def test_footer_avec_accent(self, app, scan_full):
        from app.services.report_html_service import (
            _assemble_html,
            _build_report_sections,
        )

        with app.app_context():
            from app.extensions import db

            scan = db.session.get(ScanLog, scan_full)
            filters = FilterResultDB.query.filter_by(scan_id=scan_full).all()
            sections = _build_report_sections(scan, filters, None)
            html = _assemble_html(scan, sections)

        assert "Généré par OKazCar" in html

    def test_pas_de_titres_sans_accents(self, app, scan_full):
        """Regression : aucun titre visible ne doit manquer d'accents."""
        from app.services.report_html_service import (
            _assemble_html,
            _build_report_sections,
        )

        with app.app_context():
            from app.extensions import db

            scan = db.session.get(ScanLog, scan_full)
            filters = FilterResultDB.query.filter_by(scan_id=scan_full).all()
            sections = _build_report_sections(scan, filters, None)
            html = _assemble_html(scan, sections)

        # Ces formes sans accent ne doivent JAMAIS apparaitre dans les titres h2
        assert ">Informations vehicule<" not in html
        assert ">Prix vs marche<" not in html
        assert ">Kilometrage<" not in html
        assert ">Resultats des filtres<" not in html
        assert ">Fiabilite moteur<" not in html
        assert "Genere par OKazCar" not in html


class TestPasDeDonneesTechniques:
    """Les donnees internes (clefs JSON) ne doivent jamais apparaitre dans le HTML."""

    def test_signal_cards_sans_clefs_techniques(self, app, scan_full):
        from app.services.report_html_service import (
            _assemble_html,
            _build_report_sections,
        )

        with app.app_context():
            from app.extensions import db

            scan = db.session.get(ScanLog, scan_full)
            filters = FilterResultDB.query.filter_by(scan_id=scan_full).all()
            sections = _build_report_sections(scan, filters, None)
            html = _assemble_html(scan, sections)

        # Aucune clef technique brute ne doit apparaitre
        assert "delta_eur" not in html
        assert "delta_pct" not in html
        assert "recall_count" not in html
        assert "days_online" not in html
        assert "mileage_km" not in html
        assert "expected_km" not in html
        assert "takata_airbag" not in html
        assert "km_per_year" not in html
        assert "phone_type" not in html
        assert "import_risk" not in html
        assert "etat_administratif" not in html


def _weasyprint_available() -> bool:
    try:
        from weasyprint import HTML  # noqa: F401

        return True
    except OSError:
        return False


_skip_no_weasyprint = pytest.mark.skipif(
    not _weasyprint_available(),
    reason="WeasyPrint native libs non disponibles",
)


class TestPdfValide:
    """Le PDF genere doit etre un vrai document PDF valide."""

    @_skip_no_weasyprint
    def test_pdf_header_et_taille(self, app, scan_full):
        from app.services.report_html_service import generate_scan_report_pdf

        with app.app_context():
            pdf = generate_scan_report_pdf(scan_full)

        assert pdf[:5] == b"%PDF-", "Le fichier doit commencer par %PDF-"
        assert b"%%EOF" in pdf, "Le fichier doit contenir %%EOF"
        assert len(pdf) > 1000, "Un vrai PDF fait plus de 1KB"

    @_skip_no_weasyprint
    def test_pdf_api_content_type(self, app, client, scan_full):
        """L'API retourne bien application/pdf avec le bon Content-Disposition."""
        from unittest.mock import patch

        fake_pdf = b"%PDF-1.7\nfake content\n%%EOF\n"
        with app.app_context():
            with patch(
                "app.services.report_html_service.generate_scan_report_pdf",
                return_value=fake_pdf,
            ):
                resp = client.post("/api/scan-report", json={"scan_id": scan_full})

        assert resp.status_code == 200
        assert resp.headers["Content-Type"].startswith("application/pdf")
        assert resp.data == fake_pdf, "L'API doit retourner les bytes exacts du PDF"
