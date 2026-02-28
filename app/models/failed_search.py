"""Modele FailedSearch -- recherches qui ont retourne trop peu d'annonces."""

import json
from datetime import datetime, timezone

from app.extensions import db

# Statuts du workflow de prise en charge
FAILED_SEARCH_STATUSES = ("new", "investigating", "resolved", "wont_fix", "auto_resolved")

# Severites auto-calculees
FAILED_SEARCH_SEVERITIES = ("critical", "high", "medium", "low")


class FailedSearch(db.Model):
    """Recherche echouee (< seuil d'annonces sur toutes les strategies).

    Workflow :
        new -> investigating -> resolved | wont_fix
        new -> wont_fix
        * -> auto_resolved (quand MarketPrice arrive pour ce vehicule)
    """

    __tablename__ = "failed_searches"

    id = db.Column(db.Integer, primary_key=True)
    make = db.Column(db.String(80), nullable=False, index=True)
    model = db.Column(db.String(120), nullable=False, index=True)
    year = db.Column(db.Integer, nullable=False)
    region = db.Column(db.String(80), nullable=False)
    fuel = db.Column(db.String(30))
    hp_range = db.Column(db.String(20))
    country = db.Column(db.String(5), default="FR")  # ISO 2 lettres

    # Tokens utilises pour construire l'URL (diagnostic LBC)
    brand_token_used = db.Column(db.String(120))
    model_token_used = db.Column(db.String(200))
    token_source = db.Column(db.String(20))  # "DOM", "serveur", "fallback"

    # Log complet des strategies tentees (JSON)
    search_log = db.Column(db.Text)
    # Nombre total d'annonces trouvees (0 = echec total)
    total_ads_found = db.Column(db.Integer, default=0)

    # Workflow status (remplace l'ancien boolean `resolved`)
    status = db.Column(db.String(20), default="new", nullable=False, index=True)
    severity = db.Column(db.String(20), default="medium", nullable=False)

    # Compatibilite arriere : resolved reste en tant que colonne legacy
    resolved = db.Column(db.Boolean, default=False, nullable=False)
    resolved_note = db.Column(db.Text)

    # Timestamps
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    resolved_at = db.Column(db.DateTime, nullable=True)
    status_changed_at = db.Column(db.DateTime, nullable=True)

    # Activity log (JSON array of {timestamp, action, message})
    notes = db.Column(db.Text)

    def get_search_log(self) -> list[dict] | None:
        """Deserialise le search_log JSON."""
        if not self.search_log:
            return None
        try:
            return json.loads(self.search_log)
        except (json.JSONDecodeError, TypeError):
            return None

    def get_notes(self) -> list[dict]:
        """Deserialise les notes (activity log) JSON."""
        if not self.notes:
            return []
        try:
            return json.loads(self.notes)
        except (json.JSONDecodeError, TypeError):
            return []

    def add_note(self, action: str, message: str) -> None:
        """Ajoute une entree au journal d'activite."""
        entries = self.get_notes()
        entries.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "action": action,
                "message": message,
            }
        )
        self.notes = json.dumps(entries, ensure_ascii=False)

    def set_status(self, new_status: str, message: str = "") -> None:
        """Change le statut et journalise la transition."""
        old_status = self.status
        self.status = new_status
        self.status_changed_at = datetime.now(timezone.utc)

        # Synchroniser le champ legacy `resolved`
        self.resolved = new_status in ("resolved", "wont_fix", "auto_resolved")
        if self.resolved and not self.resolved_at:
            self.resolved_at = datetime.now(timezone.utc)

        self.add_note(
            action=f"status:{old_status}->{new_status}",
            message=message or f"Statut change de {old_status} a {new_status}",
        )

    @staticmethod
    def compute_severity(occurrence_count: int, token_source: str | None = None) -> str:
        """Calcule la severite en fonction du nombre d'occurrences et de la source token."""
        if occurrence_count >= 5:
            return "critical"
        if occurrence_count >= 3 or token_source == "fallback":
            return "high"
        if occurrence_count >= 2:
            return "medium"
        return "low"

    def __repr__(self):
        return f"<FailedSearch {self.make} {self.model} {self.year} {self.region} [{self.status}]>"
