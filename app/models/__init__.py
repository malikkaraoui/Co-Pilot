"""Modeles ORM SQLAlchemy -- importe tous les modeles pour les enregistrer dans les metadonnees."""

from app.models.argus import ArgusPrice  # noqa: F401
from app.models.collection_job import CollectionJob  # noqa: F401
from app.models.email_draft import EmailDraft  # noqa: F401
from app.models.failed_search import FailedSearch  # noqa: F401
from app.models.filter_result import FilterResultDB  # noqa: F401
from app.models.gemini_config import GeminiConfig, GeminiPromptConfig  # noqa: F401
from app.models.llm_usage import LLMUsage  # noqa: F401
from app.models.log import AppLog  # noqa: F401
from app.models.market_price import MarketPrice  # noqa: F401
from app.models.pipeline_run import PipelineRun  # noqa: F401
from app.models.scan import ScanLog  # noqa: F401
from app.models.user import User  # noqa: F401
from app.models.vehicle import Vehicle, VehicleSpec  # noqa: F401
from app.models.vehicle_observed_spec import VehicleObservedSpec  # noqa: F401
from app.models.vehicle_synthesis import VehicleSynthesis  # noqa: F401
from app.models.youtube import YouTubeTranscript, YouTubeVideo  # noqa: F401
