"""Point d'entree WSGI pour OKazCar.

C'est ce fichier que Gunicorn charge en prod (wsgi:app).
En local, ``flask run`` ou ``python wsgi.py`` fait la meme chose.
"""

import os
import sys

# WeasyPrint sur macOS a besoin que le linker trouve les libs Homebrew
# (pango, cairo, gobject). On le set avant tout import pour que ctypes
# les trouve au moment du ``from weasyprint import HTML``.
if sys.platform == "darwin" and not os.environ.get("DYLD_FALLBACK_LIBRARY_PATH"):
    homebrew_lib = "/opt/homebrew/lib"
    if os.path.isdir(homebrew_lib):
        os.environ["DYLD_FALLBACK_LIBRARY_PATH"] = homebrew_lib

from app import create_app

# L'instance globale est creee au niveau du module pour que Gunicorn
# la trouve directement via ``wsgi:app``
app = create_app()

if __name__ == "__main__":
    app.run()
