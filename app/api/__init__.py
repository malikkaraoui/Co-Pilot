"""Blueprint API -- points d'acces REST consommes par l'extension Chrome."""

from flask import Blueprint

api_bp = Blueprint("api", __name__)

from app.api import routes  # noqa: E402, F401
