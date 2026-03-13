"""Blueprint du tableau de bord d'administration.

Sert toute l'interface admin (dashboard, referentiel vehicules, argus,
pipelines, monitoring, config LLM, etc.). Protege par flask-login.
Templates dans app/admin/templates/admin/, assets statiques dans app/admin/static/.
"""

from flask import Blueprint

# Le static_url_path explicite evite un conflit avec le static/ principal de l'app.
admin_bp = Blueprint(
    "admin",
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="/admin/static",
)

# Import en bas de fichier pour eviter l'import circulaire
# (routes.py importe admin_bp depuis ce module).
from app.admin import routes  # noqa: E402, F401
