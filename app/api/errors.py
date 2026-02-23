"""Gestionnaires d'erreurs API -- retournent du JSON, n'exposent jamais les stack traces (NFR10)."""

import logging

from flask import jsonify

from app.api import api_bp
from app.errors import CoPilotError, ValidationError

logger = logging.getLogger(__name__)


@api_bp.errorhandler(ValidationError)
def handle_validation_error(exc):
    logger.warning("Validation error: %s", exc)
    return jsonify(
        {
            "success": False,
            "error": "VALIDATION_ERROR",
            "message": str(exc),
            "data": None,
        }
    ), 400


@api_bp.errorhandler(CoPilotError)
def handle_copilot_error(exc):
    logger.error("CoPilot error: %s", exc)
    return jsonify(
        {
            "success": False,
            "error": "INTERNAL_ERROR",
            "message": "Une erreur est survenue. Nos mécaniciens sont sur le coup ! 🔧",
            "data": None,
        }
    ), 500


@api_bp.errorhandler(404)
def handle_not_found(exc):
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
    logger.error("Unhandled error: %s", exc)
    return jsonify(
        {
            "success": False,
            "error": "INTERNAL_ERROR",
            "message": "Oh mince, on a crevé ! On répare le moteur, réessayez dans un instant.",
            "data": None,
        }
    ), 500
