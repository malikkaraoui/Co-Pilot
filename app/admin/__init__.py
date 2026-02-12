"""Blueprint du tableau de bord d'administration."""

from flask import Blueprint

admin_bp = Blueprint(
    "admin",
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="/admin/static",
)

from app.admin import routes  # noqa: E402, F401
