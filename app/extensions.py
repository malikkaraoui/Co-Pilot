"""Extensions Flask -- instanciees ici, initialisees dans create_app()."""

from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect

db = SQLAlchemy()
login_manager = LoginManager()
cors = CORS()
csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address, storage_uri="memory://")
