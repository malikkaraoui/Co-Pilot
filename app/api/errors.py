"""Gestionnaires d'erreurs API -- retournent du JSON, n'exposent jamais les stack traces (NFR10)."""

import logging

from flask import jsonify

from app.api import api_bp
from app.errors import OKazCarError, ValidationError

logger = logging.getLogger(__name__)

# --- Erreurs metier levees explicitement par notre code ---


@api_bp.errorhandler(ValidationError)
def handle_validation_error(exc):
    """Erreur de validation metier -- on expose le message car c'est une erreur utilisateur."""
    logger.warning("Validation error: %s", exc)
    return jsonify(
        {
            "success": False,
            "error": "VALIDATION_ERROR",
            "message": str(exc),
            "data": None,
        }
    ), 400


@api_bp.errorhandler(OKazCarError)
def handle_okazcar_error(exc):
    """Erreur interne OKazCar -- on masque le detail technique derriere un message generique."""
    logger.error("OKazCar error: %s", exc)
    return jsonify(
        {
            "success": False,
            "error": "INTERNAL_ERROR",
            "message": "Une erreur est survenue. Nos mécaniciens sont sur le coup ! 🔧",
            "data": None,
        }
    ), 500


# --- Erreurs HTTP standard interceptees par le blueprint ---


@api_bp.errorhandler(404)
def handle_not_found(exc):
    """Route inexistante dans /api -- sans ca Flask renverrait du HTML par defaut."""
    return jsonify(
        {
            "success": False,
            "error": "NOT_FOUND",
            "message": "Cette route n'existe pas. ⛔️",
            "data": None,
        }
    ), 404


@api_bp.errorhandler(500)
def handle_internal_error(exc):
    """Filet de securite 500 -- complete le catch-all de __init__.py pour les erreurs Werkzeug."""
    logger.error("Unhandled error: %s", exc)
    return jsonify(
        {
            "success": False,
            "error": "INTERNAL_ERROR",
            "message": "Oh mince, on a crevé ! On répare le moteur, réessayez dans un instant.",
            "data": None,
        }
    ), 500
