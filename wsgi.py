"""Point d'entree WSGI pour OKazCar.

C'est ce fichier que Gunicorn charge en prod (wsgi:app).
En local, ``flask run`` ou ``python wsgi.py`` fait la meme chose.
"""

from app import create_app

# L'instance globale est creee au niveau du module pour que Gunicorn
# la trouve directement via ``wsgi:app``
app = create_app()

if __name__ == "__main__":
    app.run()
