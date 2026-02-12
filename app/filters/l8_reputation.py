"""Filtre L8 Detection d'Import -- detecte les signaux de vehicules importes."""

import logging
import re
from datetime import datetime, timezone
from typing import Any

from app.filters.base import BaseFilter, FilterResult

logger = logging.getLogger(__name__)

IMPORT_KEYWORDS = [
    "import", "importé", "importee", "etranger", "étrangère", "etrangere",
    "provenance", "allemagne", "belgique", "espagne", "italie", "pologne",
    "roumanie", "pays-bas", "hollande",
]


class L8ImportDetectionFilter(BaseFilter):
    """Detecte les signaux indiquant qu'un vehicule pourrait etre importe (historique incomplet, anomalie de prix)."""

    filter_id = "L8"

    def run(self, data: dict[str, Any]) -> FilterResult:
        signals = []

        # Signal 1 : Telephone etranger (recoupement avec les donnees L6)
        phone = data.get("phone") or ""
        cleaned_phone = re.sub(r"[\s\-.]", "", phone)
        if cleaned_phone and re.match(r"^\+(?!33)\d", cleaned_phone):
            signals.append("Numero de telephone avec indicatif etranger")

        # Signal 2 : Mots-cles d'import dans la description
        description = (data.get("description") or "").lower()
        title = (data.get("title") or "").lower()
        text = f"{title} {description}"
        found_keywords = [kw for kw in IMPORT_KEYWORDS if kw in text]
        if found_keywords:
            signals.append(f"Mention d'import dans l'annonce ({', '.join(found_keywords[:3])})")

        # Signal 3 : Anomalie de prix (tres bas pour le type)
        price = data.get("price_eur")
        year_str = data.get("year_model")
        if price is not None and year_str:
            try:
                year = int(year_str)
                age = datetime.now(timezone.utc).year - year
                # Heuristique tres approximative : si prix < 2000EUR pour un vehicule < 8 ans
                if age < 8 and price < 3000:
                    signals.append(
                        f"Prix tres bas ({price} EUR) pour un vehicule de {age} ans"
                    )
            except (ValueError, TypeError):
                pass

        # Signal 4 : Vendeur professionnel sans SIRET
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
                message="Aucun signal d'import detecte",
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
            message=f"Vehicule potentiellement importe ({len(signals)} signaux)",
            details={"signals": signals},
        )
