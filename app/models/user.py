"""Modele User pour l'authentification admin via Flask-Login."""

from flask_login import UserMixin

from app.extensions import db


class User(UserMixin, db.Model):
    """Utilisateur administrateur pour l'acces au tableau de bord."""

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return f"<User {self.username}>"
