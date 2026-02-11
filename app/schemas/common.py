"""Schema commun d'enveloppe de reponse API."""

from typing import Any

from pydantic import BaseModel


class APIResponse(BaseModel):
    """Enveloppe de reponse API uniforme.

    Succes : {"success": true, "error": null, "message": null, "data": {...}}
    Erreur : {"success": false, "error": "CODE", "message": "...", "data": null}
    """

    success: bool
    error: str | None = None
    message: str | None = None
    data: Any = None
