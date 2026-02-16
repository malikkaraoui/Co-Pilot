"""Tests end-to-end : simule le parcours complet extension → API → filtres → score.

Chaque scenario reproduit une vraie annonce Leboncoin avec des donnees credibles.
Zero appel reseau -- tout est en local (mocks JSON + SQLite in-memory + L7 SIRET mocke).
Les resultats sont analyses pour valider la pertinence du scoring.
"""

import json
import logging

import pytest

from tests.mocks.mock_scenarios import (
    ALL_SCENARIOS,
    SCENARIO_INCOMPLET,
    SCENARIO_KM_INCOHERENT,
    SCENARIO_PRO_SIRET,
    SCENARIO_SAIN_3008,
    SCENARIO_SUSPECT_IMPORT,
)

logger = logging.getLogger(__name__)


# ── Helpers ─────────────────────────────────────────────────────────────


def _analyze(client, scenario):
    """Envoie le payload d'un scenario a POST /api/analyze et retourne la reponse."""
    resp = client.post(
        "/api/analyze",
        data=json.dumps(
            {
                "url": f"https://www.leboncoin.fr/ad/voitures/{scenario['payload']['props']['pageProps']['ad']['list_id']}",
                "next_data": scenario["payload"],
            }
        ),
        content_type="application/json",
    )
    return resp


def _get_filter(filters, filter_id):
    """Retourne le filtre avec le filter_id donne, ou None."""
    return next((f for f in filters if f["filter_id"] == filter_id), None)


# ── Tests parametres sur tous les scenarios ─────────────────────────────


class TestAllScenariosE2E:
    """Chaque scenario passe par le flux complet et retourne un score valide."""

    @pytest.mark.parametrize(
        "scenario",
        ALL_SCENARIOS,
        ids=[s["name"] for s in ALL_SCENARIOS],
    )
    def test_scenario_returns_valid_response(self, client, scenario):
        """L'API retourne 200 avec un score entre 0 et 100 pour chaque scenario."""
        resp = _analyze(client, scenario)
        assert resp.status_code == 200, (
            f"Scenario '{scenario['name']}' a retourne {resp.status_code}"
        )

        body = resp.get_json()
        assert body["success"] is True
        assert 0 <= body["data"]["score"] <= 100

    @pytest.mark.parametrize(
        "scenario",
        ALL_SCENARIOS,
        ids=[s["name"] for s in ALL_SCENARIOS],
    )
    def test_scenario_has_nine_filters(self, client, scenario):
        """Les 9 filtres L1-L9 sont presents dans chaque reponse."""
        resp = _analyze(client, scenario)
        body = resp.get_json()
        filter_ids = sorted(f["filter_id"] for f in body["data"]["filters"])
        assert filter_ids == ["L1", "L2", "L3", "L4", "L5", "L6", "L7", "L8", "L9"]

    @pytest.mark.parametrize(
        "scenario",
        ALL_SCENARIOS,
        ids=[s["name"] for s in ALL_SCENARIOS],
    )
    def test_scenario_score_in_expected_range(self, client, scenario):
        """Le score tombe dans la fourchette attendue du scenario."""
        resp = _analyze(client, scenario)
        body = resp.get_json()
        score = body["data"]["score"]
        low, high = scenario["expected_score_range"]
        assert low <= score <= high, (
            f"Scenario '{scenario['name']}': score {score} hors fourchette [{low}, {high}]"
        )

    @pytest.mark.parametrize(
        "scenario",
        ALL_SCENARIOS,
        ids=[s["name"] for s in ALL_SCENARIOS],
    )
    def test_scenario_expected_filter_statuses(self, client, scenario):
        """Les filtres critiques retournent le statut attendu."""
        resp = _analyze(client, scenario)
        body = resp.get_json()
        filters = body["data"]["filters"]

        for filter_id, expected_status in scenario["expected_status"].items():
            filt = _get_filter(filters, filter_id)
            assert filt is not None, f"Filtre {filter_id} absent de la reponse"
            assert filt["status"] == expected_status, (
                f"Scenario '{scenario['name']}', filtre {filter_id}: "
                f"attendu '{expected_status}', obtenu '{filt['status']}' "
                f"(message: {filt['message']})"
            )


# ── Tests specifiques par scenario ──────────────────────────────────────


class TestScenarioSain:
    """Annonce saine : Peugeot 3008 particulier, tout est OK."""

    def test_extraction_complete(self, client):
        resp = _analyze(client, SCENARIO_SAIN_3008)
        body = resp.get_json()
        vehicle = body["data"]["vehicle"]
        assert vehicle["make"] == "Peugeot"
        assert vehicle["model"] == "3008"
        assert vehicle["year"] == "2019"
        assert vehicle["price"] == 22500
        assert vehicle["mileage"] == 92000

    def test_l1_completude_pass(self, client):
        resp = _analyze(client, SCENARIO_SAIN_3008)
        body = resp.get_json()
        l1 = _get_filter(body["data"]["filters"], "L1")
        assert l1["status"] == "pass"
        assert l1["score"] >= 0.9

    def test_high_score(self, client):
        resp = _analyze(client, SCENARIO_SAIN_3008)
        body = resp.get_json()
        # En env de test sans seeds, L2/L4/L5 skip → score ~51 (scoring pondere)
        assert body["data"]["score"] >= 40


class TestScenarioImportSuspect:
    """Annonce suspecte : telephone etranger + mots-cles import."""

    def test_foreign_phone_detected(self, client):
        resp = _analyze(client, SCENARIO_SUSPECT_IMPORT)
        body = resp.get_json()
        l6 = _get_filter(body["data"]["filters"], "L6")
        assert l6["status"] == "warning"
        assert "+48" in l6["message"]

    def test_import_signals_detected(self, client):
        resp = _analyze(client, SCENARIO_SUSPECT_IMPORT)
        body = resp.get_json()
        l8 = _get_filter(body["data"]["filters"], "L8")
        assert l8["status"] in ("warning", "fail")

    def test_score_lower_than_sain(self, client):
        sain = _analyze(client, SCENARIO_SAIN_3008).get_json()
        suspect = _analyze(client, SCENARIO_SUSPECT_IMPORT).get_json()
        assert suspect["data"]["score"] < sain["data"]["score"], (
            f"Annonce suspecte ({suspect['data']['score']}) devrait scorer "
            f"moins que annonce saine ({sain['data']['score']})"
        )


class TestScenarioProSiret:
    """Annonce pro avec SIRET."""

    def test_extraction_pro_fields(self, client):
        resp = _analyze(client, SCENARIO_PRO_SIRET)
        body = resp.get_json()
        vehicle = body["data"]["vehicle"]
        assert vehicle["make"] == "Renault"
        assert vehicle["model"] == "Clio"

    def test_l7_siret_passes(self, client):
        """Le filtre SIRET retourne pass (API mockee, entreprise active)."""
        resp = _analyze(client, SCENARIO_PRO_SIRET)
        body = resp.get_json()
        l7 = _get_filter(body["data"]["filters"], "L7")
        assert l7 is not None
        assert l7["status"] == "pass"


class TestScenarioIncomplet:
    """Annonce minimaliste : peu de donnees."""

    def test_l1_warns_on_missing_fields(self, client):
        resp = _analyze(client, SCENARIO_INCOMPLET)
        body = resp.get_json()
        l1 = _get_filter(body["data"]["filters"], "L1")
        assert l1["status"] in ("warning", "fail")
        assert l1["score"] < 1.0

    def test_l6_skips_no_phone(self, client):
        resp = _analyze(client, SCENARIO_INCOMPLET)
        body = resp.get_json()
        l6 = _get_filter(body["data"]["filters"], "L6")
        assert l6["status"] == "skip"

    def test_l9_low_score(self, client):
        """L'evaluation globale penalise le manque d'infos."""
        resp = _analyze(client, SCENARIO_INCOMPLET)
        body = resp.get_json()
        l9 = _get_filter(body["data"]["filters"], "L9")
        assert l9["score"] < 0.7


class TestScenarioKmIncoherent:
    """Kilometrage aberrant pour l'age du vehicule."""

    def test_l3_detects_km_anomaly(self, client):
        resp = _analyze(client, SCENARIO_KM_INCOHERENT)
        body = resp.get_json()
        l3 = _get_filter(body["data"]["filters"], "L3")
        assert l3["status"] in ("warning", "fail")
        assert l3["score"] < 0.8

    def test_coherence_details_present(self, client):
        resp = _analyze(client, SCENARIO_KM_INCOHERENT)
        body = resp.get_json()
        l3 = _get_filter(body["data"]["filters"], "L3")
        assert l3["details"] is not None
        # Les details doivent contenir les calculs de coherence
        details = l3["details"]
        assert "km_ratio" in details or "mileage_km" in details or "expected_km" in details


# ── Test de non-regression : stale data (le bug qu'on a corrige) ────────


class TestStaleDataProtection:
    """Verifie que le backend rejette les donnees sans payload d'annonce valide."""

    def test_search_results_page_rejected(self, client):
        """Un __NEXT_DATA__ de page de recherche (pas d'annonce) est rejete."""
        stale_data = {
            "props": {
                "pageProps": {
                    "searchData": {
                        "ads": [
                            {
                                "attributes": [{"key": "Marque", "value": "Audi"}],
                                "subject": "Audi Q3",
                                "price": [25000],
                            }
                        ]
                    }
                }
            }
        }
        resp = client.post(
            "/api/analyze",
            data=json.dumps({"next_data": stale_data}),
            content_type="application/json",
        )
        # Doit etre rejete car pas de props.pageProps.ad et pas de list_id
        assert resp.status_code == 422
        body = resp.get_json()
        assert body["success"] is False
        assert body["error"] == "EXTRACTION_ERROR"

    def test_empty_next_data_rejected(self, client):
        resp = client.post(
            "/api/analyze",
            data=json.dumps({"next_data": {}}),
            content_type="application/json",
        )
        assert resp.status_code == 422

    def test_valid_ad_with_list_id_accepted(self, client):
        """Une annonce avec list_id dans le fallback est acceptee."""
        data_with_list_id = {
            "props": {
                "pageProps": {
                    "someWeirdKey": {
                        "ad_data": {
                            "list_id": 12345,
                            "subject": "Peugeot 208",
                            "price": [12000],
                            "attributes": [
                                {"key": "Marque", "value": "Peugeot"},
                                {"key": "Modèle", "value": "208"},
                                {"key": "Année modèle", "value": "2020"},
                                {"key": "Kilométrage", "value": "50 000 km"},
                            ],
                        }
                    }
                }
            }
        }
        resp = client.post(
            "/api/analyze",
            data=json.dumps({"next_data": data_with_list_id}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        assert body["data"]["vehicle"]["make"] == "Peugeot"
