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

    def test_ht_standalone_not_import_signal(self):
        """'ht' (prix HT) est du pricing pro standard, pas un signal d'import."""
        data = {
            "description": "Prix ht negociable, vehicule professionnel.",
            "country": "FR",
        }
        result = self.filt.run(data)
        assert not any(
            "fiscal" in s.lower() or "TVA" in s for s in result.details.get("signals", [])
        )

    # ── Corrections faux positifs L8 ──────────────────────────────────

    def test_tva_recuperable_not_import_signal(self):
        """'TVA recuperable' est de la comptabilite pro, pas un signal d'import."""
        data = {
            "description": "Prix TTC, TVA récupérable pour les professionnels.",
            "country": "FR",
        }
        result = self.filt.run(data)
        assert result.status == "pass"
        assert not any("fiscal" in s.lower() or "TVA" in s for s in result.details["signals"])

    def test_tva_deductible_not_import_signal(self):
        """'TVA deductible' est de la comptabilite pro, pas un signal d'import."""
        data = {
            "description": "TVA deductible sur ce vehicule professionnel.",
            "country": "FR",
        }
        result = self.filt.run(data)
        assert result.status == "pass"

    def test_plaque_provisoire_alone_passes(self):
        """'plaque provisoire' seul est un signal faible (0.5) -- ne declenche PAS de warning."""
        data = {
            "description": "Vehicule en bon etat, plaque provisoire en attente.",
            "country": "FR",
        }
        result = self.filt.run(data)
        assert result.status == "pass"
        assert result.details["weak_count"] == 1
        assert result.details["strong_count"] == 0

    def test_carte_grise_en_cours_alone_passes(self):
        """'carte grise en cours' seul est un signal faible -- ne declenche PAS de warning."""
        data = {
            "description": "Carte grise en cours de refaire, vehicule propre.",
            "country": "FR",
        }
        result = self.filt.run(data)
        assert result.status == "pass"

    def test_plaque_provisoire_with_strong_signal_warns(self):
        """Signal faible + signal fort = warning (pas fail)."""
        data = {
            "phone": "+49612345678",
            "description": "Vehicule en bon etat, plaque provisoire.",
            "country": "FR",
        }
        result = self.filt.run(data)
        assert result.status == "warning"
        assert result.details["strong_count"] == 1
        assert result.details["weak_count"] == 1

    def test_two_weak_registration_keywords_still_passes(self):
        """Meme 2 keywords faibles d'immatriculation = 1 signal faible (0.5) → pass."""
        data = {
            "description": "Carte grise en cours, plaque provisoire en attente.",
            "country": "FR",
        }
        result = self.filt.run(data)
        assert result.status == "pass"
        assert result.details["weak_count"] == 1

    def test_import_word_boundary_no_false_positive(self):
        """'important' ne doit PAS matcher le keyword 'import'."""
        data = {
            "description": "Element important pour l'acheteur, vehicule propre.",
            "country": "FR",
        }
        result = self.filt.run(data)
        assert result.status == "pass"
        assert not any("import" in s.lower() for s in result.details["signals"])

    def test_import_standalone_detected(self):
        """'import' isole doit toujours matcher."""
        data = {
            "description": "Vehicule d'import, papiers en regle.",
            "country": "FR",
        }
        result = self.filt.run(data)
        assert any("import" in s.lower() for s in result.details["signals"])

    def test_plaque_ww_still_strong(self):
        """'plaque ww' reste un signal fort (specifique a l'import)."""
        data = {
            "description": "Vehicule avec plaque ww, en attente de carte grise.",
            "country": "FR",
        }
        result = self.filt.run(data)
        assert result.status == "warning"
        assert result.details["strong_count"] >= 1
        assert any("suspecte" in s.lower() for s in result.details["signals"])

    def test_coc_word_boundary(self):
        """'coc' doit matcher en mot isole, pas dans 'cocorico'."""
        data = {
            "description": "Cocorico, vehicule francais de qualite.",
            "country": "FR",
        }
        result = self.filt.run(data)
        assert not any("suspecte" in s.lower() for s in result.details["signals"])

    def test_rti_word_boundary(self):
        """'rti' ne doit PAS matcher dans 'parti' ou 'sortir'."""
        data = {
            "description": "Ce vehicule est parti du garage apres sortir de revision.",
            "country": "FR",
        }
        result = self.filt.run(data)
        assert not any("suspecte" in s.lower() for s in result.details["signals"])

    # ── Nouveaux keywords FR (douane, technique) ─────────────────────

    def test_dedouane_detected(self):
        """'dédouané' est un signal d'import fort."""
        data = {"description": "Vehicule dédouané, papiers en regle.", "country": "FR"}
        result = self.filt.run(data)
        assert result.status == "warning"
        assert any("import" in s.lower() for s in result.details["signals"])

    def test_quitus_fiscal_detected(self):
        """'quitus fiscal' est un signal d'import fort."""
        data = {"description": "Quitus fiscal obtenu.", "country": "FR"}
        result = self.filt.run(data)
        assert result.status == "warning"
        assert any("import" in s.lower() for s in result.details["signals"])

    def test_compteur_en_miles_detected(self):
        """'compteur en miles' signale un import UK/US."""
        data = {"description": "Attention compteur en miles.", "country": "FR"}
        result = self.filt.run(data)
        assert result.status == "warning"
        assert any("import" in s.lower() for s in result.details["signals"])

    def test_volant_a_droite_detected(self):
        """'volant à droite' signale un import UK."""
        data = {"description": "Volant à droite, conduite anglaise.", "country": "FR"}
        result = self.filt.run(data)
        assert result.status == "warning"

    # ── Keywords multi-langues enrichis ──────────────────────────────

    def test_spanish_text_flagged_on_fr(self):
        """Texte espagnol sur .fr = signal d'import."""
        data = {
            "description": "Vehículo en buen estado, propietario unico.",
            "country": "FR",
        }
        result = self.filt.run(data)
        assert any("langue" in s.lower() for s in result.details["signals"])

    def test_spanish_text_normal_on_es(self):
        """Texte espagnol sur .es ne doit PAS declencher 'langue etrangere'."""
        data = {
            "description": "Vehículo en buen estado, propietario unico.",
            "country": "ES",
        }
        result = self.filt.run(data)
        assert not any("langue" in s.lower() for s in result.details.get("signals", []))

    def test_italian_text_flagged_on_fr(self):
        """Texte italien sur .fr = signal d'import."""
        data = {
            "description": "Veicolo in ottime condizioni, primo proprietario.",
            "country": "FR",
        }
        result = self.filt.run(data)
        assert any("langue" in s.lower() for s in result.details["signals"])

    def test_italian_text_normal_on_it(self):
        """Texte italien sur .it ne doit PAS declencher 'langue etrangere'."""
        data = {
            "description": "Veicolo in ottime condizioni, primo proprietario.",
            "country": "IT",
        }
        result = self.filt.run(data)
        assert not any("langue" in s.lower() for s in result.details.get("signals", []))

    # ── Import-specific par langue (toujours detectes) ───────────────

    def test_importiert_detected_on_de(self):
        """'importiert' est un signal d'import meme sur .de."""
        data = {"description": "Fahrzeug importiert aus Japan.", "country": "DE"}
        result = self.filt.run(data)
        assert any("langue" in s.lower() for s in result.details["signals"])

    def test_importado_detected_on_es(self):
        """'importado' est un signal d'import meme sur .es."""
        data = {"description": "Vehiculo importado de Alemania.", "country": "ES"}
        result = self.filt.run(data)
        assert any("langue" in s.lower() for s in result.details["signals"])

    def test_dogana_detected_on_it(self):
        """'dogana' est un signal d'import meme sur .it."""
        data = {"description": "Veicolo sdoganato, dogana completata.", "country": "IT"}
        result = self.filt.run(data)
        assert any("langue" in s.lower() for s in result.details["signals"])

    def test_einfuhr_detected_on_fr(self):
        """'einfuhr' (import allemand) detecte sur .fr."""
        data = {"description": "Einfuhr aus Deutschland.", "country": "FR"}
        result = self.filt.run(data)
        assert any("langue" in s.lower() for s in result.details["signals"])
