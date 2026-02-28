"""Tests for L8 Import Detection Filter (multi-country)."""

from app.filters.l8_reputation import L8ImportDetectionFilter


class TestL8ImportDetectionFilter:
    def setup_method(self):
        self.filt = L8ImportDetectionFilter()

    # ── France (default) ─────────────────────────────────────────────

    def test_clean_ad_passes(self):
        data = {
            "phone": "0612345678",
            "description": "Vehicule en excellent etat, revision complete.",
            "price_eur": 18000,
            "year_model": "2020",
            "owner_type": "private",
        }
        result = self.filt.run(data)
        assert result.status == "pass"
        assert result.score == 1.0

    def test_foreign_phone_warns_in_france(self):
        data = {
            "phone": "+48612345678",
            "description": "Belle voiture.",
            "price_eur": 18000,
            "year_model": "2020",
            "country": "FR",
        }
        result = self.filt.run(data)
        assert result.status == "warning"
        assert len(result.details["signals"]) == 1

    def test_import_keywords_warns(self):
        data = {
            "description": "Vehicule importé, carnet entretien complet.",
            "price_eur": 18000,
            "year_model": "2020",
        }
        result = self.filt.run(data)
        assert result.status == "warning"
        assert any("import" in s.lower() for s in result.details["signals"])

    def test_import_keyword_and_country_fails(self):
        data = {
            "description": "Vehicule importé d'Allemagne, carnet entretien complet.",
            "price_eur": 18000,
            "year_model": "2020",
        }
        result = self.filt.run(data)
        assert result.status == "fail"
        assert len(result.details["signals"]) >= 2
        assert any("import" in s.lower() for s in result.details["signals"])
        assert any("allemagne" in s.lower() for s in result.details["signals"])

    def test_multiple_signals_fails(self):
        data = {
            "phone": "+49612345678",
            "description": "Importée d'Allemagne, excellent prix.",
            "price_eur": 2000,
            "year_model": "2022",
            "country": "FR",
        }
        result = self.filt.run(data)
        assert result.status == "fail"
        assert len(result.details["signals"]) >= 2

    def test_pro_without_siret_warns(self):
        data = {
            "owner_type": "pro",
            "siret": None,
            "description": "Vehicule de flotte.",
            "price_eur": 15000,
            "year_model": "2019",
            "country": "FR",
        }
        result = self.filt.run(data)
        assert result.status == "warning"
        assert any("SIRET" in s for s in result.details["signals"])

    def test_empty_data_passes(self):
        result = self.filt.run({})
        assert result.status == "pass"

    # ── Suisse (.ch) ─────────────────────────────────────────────────

    def test_swiss_phone_not_foreign_on_ch(self):
        """Un +41 sur .ch ne doit PAS declencher le signal d'import."""
        data = {
            "phone": "+41791234567",
            "description": "Vehicule en bon etat.",
            "price_eur": 20000,
            "year_model": "2020",
            "country": "CH",
        }
        result = self.filt.run(data)
        assert result.status == "pass"
        assert not any("étranger" in s for s in result.details.get("signals", []))

    def test_french_phone_foreign_on_ch(self):
        """Un +33 sur .ch EST un signal d'import."""
        data = {
            "phone": "+33612345678",
            "description": "Belle auto.",
            "country": "CH",
        }
        result = self.filt.run(data)
        assert any("étranger" in s for s in result.details["signals"])

    def test_pro_without_uid_on_ch(self):
        """Pro sans UID sur .ch (source non-verifiee) : signal d'import."""
        data = {
            "owner_type": "pro",
            "siret": None,
            "description": "Vehicule professionnel.",
            "country": "CH",
        }
        result = self.filt.run(data)
        assert any("UID" in s for s in result.details["signals"])
        assert not any("SIRET" in s for s in result.details["signals"])

    def test_pro_without_uid_on_as24_not_flagged(self):
        """Pro sans UID sur AS24 : pas de signal (plateforme verifie les pros)."""
        data = {
            "owner_type": "pro",
            "siret": None,
            "description": "Vehicule professionnel.",
            "country": "CH",
            "source": "autoscout24",
        }
        result = self.filt.run(data)
        assert not any("UID" in s for s in result.details.get("signals", []))

    def test_suisse_not_flagged_as_import_country_on_ch(self):
        """'suisse' dans la description sur .ch ne doit PAS etre un signal d'import."""
        data = {
            "description": "Vehicule suisse, premiere main.",
            "country": "CH",
        }
        result = self.filt.run(data)
        assert not any("suisse" in s.lower() for s in result.details.get("signals", []))

    def test_german_text_normal_on_ch(self):
        """Texte allemand sur .ch ne doit PAS declencher 'langue etrangere'."""
        data = {
            "description": "Unfallfrei, Erstbesitzer, Fahrzeug in gutem Zustand.",
            "country": "CH",
        }
        result = self.filt.run(data)
        assert not any("langue" in s.lower() for s in result.details.get("signals", []))

    def test_german_text_flagged_on_fr(self):
        """Texte allemand sur .fr EST un signal d'import."""
        data = {
            "description": "Unfallfrei, Erstbesitzer, Fahrzeug in gutem Zustand.",
            "country": "FR",
        }
        result = self.filt.run(data)
        assert any("langue" in s.lower() for s in result.details["signals"])

    # ── Allemagne (.de) ──────────────────────────────────────────────

    def test_german_phone_not_foreign_on_de(self):
        """Un +49 sur .de ne doit PAS declencher le signal d'import."""
        data = {
            "phone": "+4917112345678",
            "description": "Auto in gutem Zustand.",
            "country": "DE",
        }
        result = self.filt.run(data)
        assert result.status == "pass"

    def test_allemagne_not_flagged_on_de(self):
        """'allemagne' dans la description sur .de ne doit PAS etre flagge."""
        data = {
            "description": "Importé d'allemagne.",
            "country": "DE",
        }
        result = self.filt.run(data)
        # Import keyword still triggers, but allemagne should not
        assert not any("allemagne" in s.lower() for s in result.details["signals"])

    # ── Regressions GPT review ─────────────────────────────────────

    def test_00xx_phone_detected_as_foreign(self):
        """Un numero 0049 (format 00+indicatif) sur .fr doit etre detecte comme etranger."""
        data = {
            "phone": "0049 171 123 4567",
            "description": "Belle voiture.",
            "country": "FR",
        }
        result = self.filt.run(data)
        assert any("étranger" in s for s in result.details["signals"])

    def test_00xx_local_phone_not_flagged(self):
        """Un 0033 sur .fr ne doit PAS etre etranger (c'est local)."""
        data = {
            "phone": "0033612345678",
            "description": "Belle voiture.",
            "country": "FR",
        }
        result = self.filt.run(data)
        assert not any("étranger" in s for s in result.details.get("signals", []))

    def test_ht_no_false_positive(self):
        """'ht' ne doit pas matcher dans des mots normaux comme 'nacht'."""
        data = {
            "description": "Nachtblau metallic, sehr guter Zustand.",
            "country": "FR",
        }
        result = self.filt.run(data)
        assert not any(
            "fiscal" in s.lower() or "TVA" in s for s in result.details.get("signals", [])
        )

    def test_ht_standalone_detected(self):
        """'ht' isole (prix HT) doit declencher le signal fiscal."""
        data = {
            "description": "Prix ht negociable, vehicule professionnel.",
            "country": "FR",
        }
        result = self.filt.run(data)
        assert any("fiscal" in s.lower() or "TVA" in s for s in result.details["signals"])
