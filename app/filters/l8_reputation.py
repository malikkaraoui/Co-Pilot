"""Filtre L8 Detection d'Import -- detecte les signaux de vehicules importes."""

import logging
import re
from datetime import datetime, timezone
from typing import Any

from app.filters.base import VERIFIED_PRO_PLATFORMS, BaseFilter, FilterResult

logger = logging.getLogger(__name__)

# Keywords d'import en francais
IMPORT_KEYWORDS_FR = [
    "import",
    "importé",
    "importee",
    "importation",
    "etranger",
    "étrangère",
    "etrangere",
    "provenance",
    "en provenance",
]

# Pays source d'import frequents
IMPORT_COUNTRIES = [
    "allemagne",
    "belgique",
    "espagne",
    "italie",
    "pologne",
    "roumanie",
    "pays-bas",
    "hollande",
    "portugal",
    "luxembourg",
    "autriche",
    "suisse",
    "bulgarie",
    "republique tcheque",
    "slovaquie",
    "hongrie",
    "croatie",
]

# Noms locaux par pays -- a exclure de la detection d'import sur le site du pays
_COUNTRY_LOCAL_NAMES: dict[str, set[str]] = {
    "FR": {"france"},
    "CH": {"suisse"},
    "DE": {"allemagne"},
    "AT": {"autriche"},
    "IT": {"italie"},
    "NL": {"pays-bas", "hollande"},
    "BE": {"belgique"},
    "ES": {"espagne"},
}

# Keywords multi-langues (descriptions copiees-collees de sites etrangers)
IMPORT_KEYWORDS_FOREIGN = [
    # Allemand
    "unfallwagen",
    "fahrzeug",
    "kilometerstand",
    "gebraucht",
    "automatik",
    "schaltgetriebe",
    "erstbesitzer",
    "unfallfrei",
    # Espagnol
    "vehículo",
    "vehiculo",
    "kilómetros",
    "kilometros",
    # Italien
    "veicolo",
    "chilometri",
    "cambio automatico",
    # Anglais (annonces internationales)
    "left hand drive",
    "lhd",
    "imported from",
]

# Sous-ensemble allemand (normal sur sites CH/DE/AT)
_GERMAN_KEYWORDS = {
    "unfallwagen",
    "fahrzeug",
    "kilometerstand",
    "gebraucht",
    "automatik",
    "schaltgetriebe",
    "erstbesitzer",
    "unfallfrei",
}

# Signaux fiscaux specifiques a l'import (malus, export, taxe CO2)
# Note: "ht", "hors taxe", "hors tva", "tva recuperable/deductible" RETIRES
# — c'est du pricing professionnel standard, pas un signal d'import.
TAX_KEYWORDS = [
    "exportation",
    "malus payé",
    "malus paye",
    "malus ecologique",
    "malus écologique",
    "malus inclus",
    "taxe co2",
]

# Signaux de carte grise / immatriculation -- FORTS (specifiques a l'import)
REGISTRATION_STRONG = [
    "plaque ww",
    "immatriculation ww",
    "certificat de conformite",
    "reception a titre isole",
]

# Tokens courts d'immatriculation necessitant word boundary
_SHORT_REGISTRATION_TOKENS = ["coc", "rti"]

# Signaux de carte grise / immatriculation -- FAIBLES (ambigus: import OU admin/ministeriel/leasing)
REGISTRATION_WEAK = [
    "carte grise en cours",
    "carte grise a faire",
    "plaque provisoire",
    "homologation",
]


class L8ImportDetectionFilter(BaseFilter):
    """Detecte les signaux indiquant qu'un vehicule pourrait etre importe."""

    filter_id = "L8"

    # Indicatifs locaux par pays (meme mapping que L6)
    _LOCAL_PREFIXES: dict[str, str] = {
        "FR": "33",
        "CH": "41",
        "DE": "49",
        "AT": "43",
        "IT": "39",
        "NL": "31",
        "BE": "32",
        "ES": "34",
    }

    def run(self, data: dict[str, Any]) -> FilterResult:
        strong_signals: list[str] = []
        weak_signals: list[str] = []
        country = (data.get("country") or "FR").upper()

        # Signal 1 : Telephone etranger (recoupement avec les donnees L6)
        # Adapte au pays : +41 n'est pas etranger en Suisse, +49 en Allemagne, etc.
        phone = data.get("phone") or ""
        cleaned_phone = re.sub(r"[\s\-.]", "", phone)
        # Normaliser le format 00XX en +XX (ex: 0049 → +49)
        if cleaned_phone.startswith("00") and len(cleaned_phone) > 4:
            cleaned_phone = "+" + cleaned_phone[2:]
        local_prefix = self._LOCAL_PREFIXES.get(country, "33")
        if cleaned_phone and cleaned_phone.startswith("+"):
            if not cleaned_phone.startswith("+" + local_prefix):
                strong_signals.append("Numéro de téléphone avec indicatif étranger")

        # Signal 2 : Mots-cles d'import dans la description
        description = (data.get("description") or "").lower()
        title = (data.get("title") or "").lower()
        text = f"{title} {description}"

        # Word boundary sur "import" (evite "important", "importateur" --
        # les formes specifiques "importé", "importation" sont des entrees separees)
        found_import = []
        for kw in IMPORT_KEYWORDS_FR:
            if kw == "import":
                if re.search(r"\bimport\b", text):
                    found_import.append(kw)
            else:
                if kw in text:
                    found_import.append(kw)
        # Exclure le pays local de la liste d'import (ex: "suisse" sur .ch)
        local_country_names = _COUNTRY_LOCAL_NAMES.get(country, set())
        import_countries = [c for c in IMPORT_COUNTRIES if c not in local_country_names]
        found_countries = [kw for kw in import_countries if kw in text]
        if found_import:
            strong_signals.append(
                f"Mention d'import dans l'annonce ({', '.join(found_import[:3])})"
            )
        if found_countries:
            strong_signals.append(f"Pays d'origine mentionné ({', '.join(found_countries[:3])})")

        # Signal 3 : Texte en langue etrangere (copier-coller de site etranger)
        # Sur les sites CH/DE/AT, l'allemand est normal -- ne pas flagger
        if country in ("CH", "DE", "AT"):
            foreign_keywords = [kw for kw in IMPORT_KEYWORDS_FOREIGN if kw not in _GERMAN_KEYWORDS]
        else:
            foreign_keywords = IMPORT_KEYWORDS_FOREIGN
        found_foreign = [kw for kw in foreign_keywords if kw in text]
        if found_foreign:
            strong_signals.append(
                f"Texte en langue étrangère détecté ({', '.join(found_foreign[:3])})"
            )

        # Signal 4 : Signaux fiscaux (malus, TVA, export)
        # Word boundary pour les tokens courts (ex: "ht") pour eviter les faux positifs
        found_tax = [
            kw
            for kw in TAX_KEYWORDS
            if (len(kw) <= 3 and re.search(rf"\b{re.escape(kw)}\b", text))
            or (len(kw) > 3 and kw in text)
        ]
        if found_tax:
            strong_signals.append(f"Signal fiscal/TVA ({', '.join(found_tax[:3])})")

        # Signal 5 : Carte grise / immatriculation
        # Forts : specifiques a l'import (WW, COC, RTI)
        found_reg_strong = [kw for kw in REGISTRATION_STRONG if kw in text]
        found_reg_strong += [
            kw for kw in _SHORT_REGISTRATION_TOKENS if re.search(rf"\b{re.escape(kw)}\b", text)
        ]
        # Faibles : ambigus (carte grise en cours, plaque provisoire, homologation)
        found_reg_weak = [kw for kw in REGISTRATION_WEAK if kw in text]
        if found_reg_strong:
            strong_signals.append(f"Immatriculation suspecte ({', '.join(found_reg_strong[:2])})")
        if found_reg_weak:
            weak_signals.append(
                f"Immatriculation provisoire ou en cours ({', '.join(found_reg_weak[:2])})"
            )

        # Signal 6 : Anomalie de prix (tres bas pour le type)
        price = data.get("price_eur")
        year_str = data.get("year_model")
        if price is not None and year_str:
            try:
                year = int(year_str)
                age = datetime.now(timezone.utc).year - year
                if age < 8 and price < 3000:
                    strong_signals.append(
                        f"Prix très bas ({price} EUR) pour un véhicule de {age} ans"
                    )
            except (ValueError, TypeError):
                pass

        # Signal 7 : Vendeur professionnel sans numero d'entreprise
        # Skip sur plateformes verifiees (AS24 verifie le statut pro)
        owner_type = data.get("owner_type")
        siret = data.get("siret")
        source = (data.get("source") or "").lower()
        if owner_type == "pro" and not siret and source not in VERIFIED_PRO_PLATFORMS:
            if country == "CH":
                strong_signals.append("Vendeur professionnel sans UID")
            elif country == "FR":
                strong_signals.append("Vendeur professionnel sans SIRET")
            else:
                strong_signals.append("Vendeur professionnel sans numéro d'entreprise")

        # Verdict final -- ponderation: signaux forts = 1.0, signaux faibles = 0.5
        all_signals = strong_signals + weak_signals
        signal_weight = len(strong_signals) + 0.5 * len(weak_signals)

        if signal_weight < 1.0:
            return FilterResult(
                filter_id=self.filter_id,
                status="pass",
                score=1.0,
                message="Aucun signal d'import détecté",
                details={
                    "signals": all_signals or [],
                    "strong_count": len(strong_signals),
                    "weak_count": len(weak_signals),
                },
            )

        if signal_weight < 2.0:
            msg = (
                all_signals[0]
                if len(all_signals) == 1
                else f"Signal d'import possible ({len(all_signals)} indices)"
            )
            return FilterResult(
                filter_id=self.filter_id,
                status="warning",
                score=0.4,
                message=msg,
                details={
                    "signals": all_signals,
                    "strong_count": len(strong_signals),
                    "weak_count": len(weak_signals),
                },
            )

        return FilterResult(
            filter_id=self.filter_id,
            status="fail",
            score=0.1,
            message=f"Véhicule potentiellement importé ({len(all_signals)} signaux)",
            details={
                "signals": all_signals,
                "strong_count": len(strong_signals),
                "weak_count": len(weak_signals),
            },
        )
