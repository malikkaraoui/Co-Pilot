"""Modeles ORM SQLAlchemy -- importe tous les modeles pour les enregistrer dans les metadonnees."""

from app.models.argus import ArgusPrice  # noqa: F401
from app.models.filter_result import FilterResultDB  # noqa: F401
from app.models.log import AppLog  # noqa: F401
from app.models.scan import ScanLog  # noqa: F401
from app.models.user import User  # noqa: F401
from app.models.vehicle import Vehicle, VehicleSpec  # noqa: F401
