"""Filtre L8 Detection d'Import -- detecte les signaux de vehicules importes."""

import logging
import re
from datetime import datetime, timezone
from typing import Any

from app.filters.base import BaseFilter, FilterResult

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

# Signaux fiscaux / TVA (import pro)
TAX_KEYWORDS = [
    "hors taxe",
    "ht",
    "tva récupérable",
    "tva recuperable",
    "tva deductible",
    "exportation",
    "hors tva",
    "malus payé",
    "malus paye",
    "malus ecologique",
    "malus écologique",
    "malus inclus",
    "taxe co2",
]

# Signaux de carte grise / immatriculation suspecte
REGISTRATION_KEYWORDS = [
    "carte grise en cours",
    "carte grise a faire",
    "plaque provisoire",
    "plaque ww",
    "immatriculation ww",
    "certificat de conformite",
    "coc",
    "homologation",
    "reception a titre isole",
    "rti",
]


class L8ImportDetectionFilter(BaseFilter):
    """Detecte les signaux indiquant qu'un vehicule pourrait etre importe."""

    filter_id = "L8"

    def run(self, data: dict[str, Any]) -> FilterResult:
        signals = []

        # Signal 1 : Telephone etranger (recoupement avec les donnees L6)
        phone = data.get("phone") or ""
        cleaned_phone = re.sub(r"[\s\-.]", "", phone)
        if cleaned_phone and re.match(r"^\+(?!33)\d", cleaned_phone):
            signals.append("Numéro de téléphone avec indicatif étranger")

        # Signal 2 : Mots-cles d'import dans la description
        description = (data.get("description") or "").lower()
        title = (data.get("title") or "").lower()
        text = f"{title} {description}"

        found_import = [kw for kw in IMPORT_KEYWORDS_FR if kw in text]
        found_countries = [kw for kw in IMPORT_COUNTRIES if kw in text]
        if found_import:
            signals.append(f"Mention d'import dans l'annonce ({', '.join(found_import[:3])})")
        if found_countries:
            signals.append(f"Pays d'origine mentionné ({', '.join(found_countries[:3])})")

        # Signal 3 : Texte en langue etrangere (copier-coller de site etranger)
        found_foreign = [kw for kw in IMPORT_KEYWORDS_FOREIGN if kw in text]
        if found_foreign:
            signals.append(f"Texte en langue étrangère détecté ({', '.join(found_foreign[:3])})")

        # Signal 4 : Signaux fiscaux (malus, TVA, export)
        found_tax = [kw for kw in TAX_KEYWORDS if kw in text]
        if found_tax:
            signals.append(f"Signal fiscal/TVA ({', '.join(found_tax[:3])})")

        # Signal 5 : Carte grise en cours / immatriculation provisoire
        found_reg = [kw for kw in REGISTRATION_KEYWORDS if kw in text]
        if found_reg:
            signals.append(f"Immatriculation provisoire ou en cours ({', '.join(found_reg[:2])})")

        # Signal 6 : Anomalie de prix (tres bas pour le type)
        price = data.get("price_eur")
        year_str = data.get("year_model")
        if price is not None and year_str:
            try:
                year = int(year_str)
                age = datetime.now(timezone.utc).year - year
                if age < 8 and price < 3000:
                    signals.append(f"Prix très bas ({price} EUR) pour un véhicule de {age} ans")
            except (ValueError, TypeError):
                pass

        # Signal 7 : Vendeur professionnel sans SIRET
        owner_type = data.get("owner_type")
        siret = data.get("siret")
        if owner_type == "pro" and not siret:
            signals.append("Vendeur professionnel sans SIRET")

        # Verdict final
        if not signals:
            return FilterResult(
                filter_id=self.filter_id,
                status="pass",
                score=1.0,
                message="Aucun signal d'import détecté",
                details={"signals": []},
            )

        if len(signals) == 1:
            return FilterResult(
                filter_id=self.filter_id,
                status="warning",
                score=0.4,
                message=signals[0],
                details={"signals": signals},
            )

        return FilterResult(
            filter_id=self.filter_id,
            status="fail",
            score=0.1,
            message=f"Véhicule potentiellement importé ({len(signals)} signaux)",
            details={"signals": signals},
        )
