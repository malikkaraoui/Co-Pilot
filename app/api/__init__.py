"""Blueprint API -- points d'acces REST consommes par l'extension Chrome."""

import logging

from flask import Blueprint, jsonify
from werkzeug.exceptions import HTTPException

from app.extensions import db

api_bp = Blueprint("api", __name__)

logger = logging.getLogger(__name__)


@api_bp.errorhandler(Exception)
def _handle_unexpected_api_error(err):
    """Retourne du JSON pour toute exception non geree dans /api.

    But: eviter les pages HTML 500 qui font echouer resp.json() cote extension.
    """
    # Ne pas intercepter les erreurs HTTP attendues (404, 405, 429, etc.).
    if isinstance(err, HTTPException):
        return err

    try:
        db.session.rollback()
    except Exception:  # rollback best-effort
        pass

    logger.error("Unhandled API exception", exc_info=True)
    return (
        jsonify(
            {
                "success": False,
                "error": "INTERNAL_ERROR",
                "message": "Erreur interne du serveur.",
                "data": None,
            }
        ),
        500,
    )


from app.api import market_routes, routes  # noqa: E402, F401
