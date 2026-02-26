# Gemini Flash 2.5 + Email Vendeur Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Integrate Google Gemini Flash 2.5 as cloud LLM provider for generating personalized seller emails based on scan analysis data, with full cost tracking and admin configuration.

**Architecture:** New `gemini_service.py` wrapper around `google-genai` SDK, `email_service.py` for business logic, 4 new DB models (LLMUsage, EmailDraft, GeminiConfig, GeminiPromptConfig), 2 new admin pages (/admin/llm, /admin/email), and extension email button with copy-to-clipboard.

**Tech Stack:** google-genai SDK, Flask/SQLAlchemy, Bootstrap 5 (admin), Plotly (cost charts), Chrome extension JS

---

### Task 1: Install google-genai SDK and add config

**Files:**
- Modify: `requirements.txt`
- Modify: `config.py`

**Step 1: Add google-genai to requirements**

In `requirements.txt`, add after line 19 (`yt-dlp`):

```
google-genai>=1.0.0
```

**Step 2: Add Gemini config variables**

In `config.py`, after line 36 (`OLLAMA_URL`), add:

```python
    # Google Gemini LLM (cloud)
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
    GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    GEMINI_TIMEOUT = int(os.environ.get("GEMINI_TIMEOUT", "30"))
```

**Step 3: Install the dependency**

Run: `pip install google-genai>=1.0.0`

**Step 4: Commit**

```bash
git add requirements.txt config.py
git commit -m "feat: add google-genai SDK dependency and Gemini config"
```

---

### Task 2: Create LLMUsage model (cost tracking)

**Files:**
- Create: `app/models/llm_usage.py`
- Modify: `app/models/__init__.py` (line 14, add import)
- Test: `tests/test_models/test_llm_usage.py`

**Step 1: Write the failing test**

Create `tests/test_models/test_llm_usage.py`:

```python
"""Tests for LLMUsage model."""

from app.models.llm_usage import LLMUsage


class TestLLMUsage:
    def test_create_usage_record(self, app, db):
        """LLMUsage stores token counts and cost."""
        with app.app_context():
            usage = LLMUsage(
                request_id="req-abc-123",
                provider="gemini",
                model="gemini-2.5-flash",
                feature="email_draft",
                prompt_tokens=150,
                completion_tokens=80,
                total_tokens=230,
                estimated_cost_eur=0.0001,
            )
            db.session.add(usage)
            db.session.commit()

            saved = LLMUsage.query.first()
            assert saved.request_id == "req-abc-123"
            assert saved.provider == "gemini"
            assert saved.total_tokens == 230
            assert saved.estimated_cost_eur == 0.0001
            assert saved.created_at is not None

    def test_repr(self, app, db):
        """LLMUsage repr includes provider and feature."""
        with app.app_context():
            usage = LLMUsage(
                request_id="req-1",
                provider="gemini",
                model="gemini-2.5-flash",
                feature="email_draft",
                prompt_tokens=10,
                completion_tokens=5,
                total_tokens=15,
                estimated_cost_eur=0.0,
            )
            assert "gemini" in repr(usage)
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_models/test_llm_usage.py -v`
Expected: FAIL (ImportError, module not found)

**Step 3: Write the model**

Create `app/models/llm_usage.py`:

```python
"""Modele LLMUsage -- suivi des couts et tokens LLM."""

from datetime import datetime, timezone

from app.extensions import db


class LLMUsage(db.Model):
    """Enregistrement de chaque appel LLM pour suivi des couts."""

    __tablename__ = "llm_usages"

    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.String(100), nullable=False, index=True)
    provider = db.Column(db.String(30), nullable=False)  # "gemini", "ollama"
    model = db.Column(db.String(80), nullable=False)
    feature = db.Column(db.String(50), nullable=False)  # "email_draft", "youtube_synthesis"
    prompt_tokens = db.Column(db.Integer, nullable=False, default=0)
    completion_tokens = db.Column(db.Integer, nullable=False, default=0)
    total_tokens = db.Column(db.Integer, nullable=False, default=0)
    estimated_cost_eur = db.Column(db.Float, nullable=False, default=0.0)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<LLMUsage {self.provider}/{self.feature} {self.total_tokens}tok>"
```

**Step 4: Register model in `app/models/__init__.py`**

After line 14 (after VehicleSynthesis import), add:

```python
from app.models.llm_usage import LLMUsage  # noqa: F401
```

**Step 5: Run test to verify it passes**

Run: `pytest tests/test_models/test_llm_usage.py -v`
Expected: PASS (2 tests)

**Step 6: Commit**

```bash
git add app/models/llm_usage.py app/models/__init__.py tests/test_models/test_llm_usage.py
git commit -m "feat: add LLMUsage model for cost tracking"
```

---

### Task 3: Create EmailDraft model

**Files:**
- Create: `app/models/email_draft.py`
- Modify: `app/models/__init__.py`
- Test: `tests/test_models/test_email_draft.py`

**Step 1: Write the failing test**

Create `tests/test_models/test_email_draft.py`:

```python
"""Tests for EmailDraft model."""

from app.models.email_draft import EmailDraft


class TestEmailDraft:
    def test_create_draft(self, app, db):
        """EmailDraft stores generated email with seller info."""
        with app.app_context():
            draft = EmailDraft(
                scan_id=1,
                listing_url="https://www.leboncoin.fr/voitures/12345.htm",
                vehicle_make="Peugeot",
                vehicle_model="308",
                seller_type="private",
                seller_name="Jean Dupont",
                seller_phone="0612345678",
                prompt_used="Tu es un acheteur averti...",
                generated_text="Bonjour, je suis interesse...",
                llm_model="gemini-2.5-flash",
                tokens_used=230,
            )
            db.session.add(draft)
            db.session.commit()

            saved = EmailDraft.query.first()
            assert saved.listing_url == "https://www.leboncoin.fr/voitures/12345.htm"
            assert saved.seller_type == "private"
            assert saved.status == "draft"
            assert saved.edited_text is None

    def test_status_transitions(self, app, db):
        """EmailDraft status can be updated."""
        with app.app_context():
            draft = EmailDraft(
                scan_id=1,
                listing_url="https://example.com",
                vehicle_make="Renault",
                vehicle_model="Clio",
                seller_type="pro",
                prompt_used="test",
                generated_text="Bonjour...",
                llm_model="gemini-2.5-flash",
                tokens_used=100,
            )
            db.session.add(draft)
            db.session.commit()

            draft.status = "approved"
            draft.edited_text = "Version editee..."
            db.session.commit()

            saved = EmailDraft.query.first()
            assert saved.status == "approved"
            assert saved.edited_text == "Version editee..."
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_models/test_email_draft.py -v`
Expected: FAIL

**Step 3: Write the model**

Create `app/models/email_draft.py`:

```python
"""Modele EmailDraft -- brouillons d'emails vendeur generes par LLM."""

from datetime import datetime, timezone

from app.extensions import db


class EmailDraft(db.Model):
    """Brouillon d'email genere pour un vendeur a partir d'une analyse."""

    __tablename__ = "email_drafts"

    id = db.Column(db.Integer, primary_key=True)
    scan_id = db.Column(db.Integer, db.ForeignKey("scan_logs.id"), nullable=False, index=True)
    listing_url = db.Column(db.String(500), nullable=False)
    vehicle_make = db.Column(db.String(100))
    vehicle_model = db.Column(db.String(100))
    seller_type = db.Column(db.String(20))  # "pro" / "private"
    seller_name = db.Column(db.String(200))
    seller_phone = db.Column(db.String(50))
    seller_email = db.Column(db.String(200))
    prompt_used = db.Column(db.Text, nullable=False)
    generated_text = db.Column(db.Text, nullable=False)
    edited_text = db.Column(db.Text)
    status = db.Column(db.String(20), nullable=False, default="draft")
    llm_model = db.Column(db.String(80), nullable=False)
    tokens_used = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    scan = db.relationship("ScanLog", backref="email_drafts")

    def __repr__(self):
        return f"<EmailDraft {self.vehicle_make} {self.vehicle_model} [{self.status}]>"
```

**Step 4: Register in `app/models/__init__.py`**

Add after LLMUsage import:

```python
from app.models.email_draft import EmailDraft  # noqa: F401
```

**Step 5: Run test to verify it passes**

Run: `pytest tests/test_models/test_email_draft.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add app/models/email_draft.py app/models/__init__.py tests/test_models/test_email_draft.py
git commit -m "feat: add EmailDraft model for seller email drafts"
```

---

### Task 4: Create GeminiConfig and GeminiPromptConfig models

**Files:**
- Create: `app/models/gemini_config.py`
- Modify: `app/models/__init__.py`
- Test: `tests/test_models/test_gemini_config.py`

**Step 1: Write the failing test**

Create `tests/test_models/test_gemini_config.py`:

```python
"""Tests for GeminiConfig and GeminiPromptConfig models."""

from app.models.gemini_config import GeminiConfig, GeminiPromptConfig


class TestGeminiConfig:
    def test_create_config(self, app, db):
        """GeminiConfig stores API settings."""
        with app.app_context():
            cfg = GeminiConfig(
                api_key_encrypted="encrypted-key-here",
                model_name="gemini-2.5-flash",
                max_daily_requests=500,
                max_daily_cost_eur=1.0,
                is_active=True,
            )
            db.session.add(cfg)
            db.session.commit()

            saved = GeminiConfig.query.first()
            assert saved.model_name == "gemini-2.5-flash"
            assert saved.is_active is True
            assert saved.max_daily_requests == 500


class TestGeminiPromptConfig:
    def test_create_prompt_config(self, app, db):
        """GeminiPromptConfig stores prompt templates with parameters."""
        with app.app_context():
            prompt = GeminiPromptConfig(
                name="email_vendeur_v1",
                system_prompt="Tu es un acheteur averti et direct.",
                task_prompt_template="Vehicule: {make} {model}\nPrix: {price}",
                max_output_tokens=500,
                temperature=0.3,
                top_p=0.9,
                hallucination_guard="Ne mentionne que les faits issus des donnees fournies.",
                is_active=True,
                version=1,
            )
            db.session.add(prompt)
            db.session.commit()

            saved = GeminiPromptConfig.query.first()
            assert saved.name == "email_vendeur_v1"
            assert saved.temperature == 0.3
            assert saved.is_active is True
            assert saved.version == 1

    def test_only_one_active_prompt(self, app, db):
        """Deactivating old prompt when activating new one is business logic, not model constraint."""
        with app.app_context():
            p1 = GeminiPromptConfig(
                name="v1", system_prompt="a", task_prompt_template="b",
                max_output_tokens=100, temperature=0.5, is_active=True, version=1,
            )
            p2 = GeminiPromptConfig(
                name="v2", system_prompt="c", task_prompt_template="d",
                max_output_tokens=200, temperature=0.7, is_active=True, version=2,
            )
            db.session.add_all([p1, p2])
            db.session.commit()

            # Both can be active at DB level (business logic enforces single active)
            active = GeminiPromptConfig.query.filter_by(is_active=True).all()
            assert len(active) == 2
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_models/test_gemini_config.py -v`
Expected: FAIL

**Step 3: Write the models**

Create `app/models/gemini_config.py`:

```python
"""Modeles GeminiConfig et GeminiPromptConfig -- parametrage LLM Google."""

from datetime import datetime, timezone

from app.extensions import db


class GeminiConfig(db.Model):
    """Configuration singleton pour l'API Gemini."""

    __tablename__ = "gemini_config"

    id = db.Column(db.Integer, primary_key=True)
    api_key_encrypted = db.Column(db.String(500), nullable=False)
    model_name = db.Column(db.String(80), nullable=False, default="gemini-2.5-flash")
    max_daily_requests = db.Column(db.Integer, nullable=False, default=500)
    max_daily_cost_eur = db.Column(db.Float, nullable=False, default=1.0)
    is_active = db.Column(db.Boolean, nullable=False, default=False)
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self):
        status = "ON" if self.is_active else "OFF"
        return f"<GeminiConfig {self.model_name} [{status}]>"


class GeminiPromptConfig(db.Model):
    """Template de prompt configurable pour Gemini."""

    __tablename__ = "gemini_prompt_configs"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    system_prompt = db.Column(db.Text, nullable=False)
    task_prompt_template = db.Column(db.Text, nullable=False)
    max_output_tokens = db.Column(db.Integer, nullable=False, default=500)
    temperature = db.Column(db.Float, nullable=False, default=0.3)
    top_p = db.Column(db.Float, nullable=True, default=0.9)
    response_format_hint = db.Column(db.String(50), default="email_text")
    hallucination_guard = db.Column(db.Text, default="")
    max_sentences = db.Column(db.Integer, nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=False)
    version = db.Column(db.Integer, nullable=False, default=1)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<GeminiPromptConfig {self.name} v{self.version}>"
```

**Step 4: Register in `app/models/__init__.py`**

Add:

```python
from app.models.gemini_config import GeminiConfig, GeminiPromptConfig  # noqa: F401
```

**Step 5: Run test to verify it passes**

Run: `pytest tests/test_models/test_gemini_config.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add app/models/gemini_config.py app/models/__init__.py tests/test_models/test_gemini_config.py
git commit -m "feat: add GeminiConfig and GeminiPromptConfig models"
```

---

### Task 5: Create gemini_service.py (Gemini SDK wrapper)

**Files:**
- Create: `app/services/gemini_service.py`
- Test: `tests/test_services/test_gemini_service.py`

**Reference:** Mirror pattern from `app/services/llm_service.py` (Ollama wrapper)

**Step 1: Write the failing tests**

Create `tests/test_services/test_gemini_service.py`:

```python
"""Tests for gemini_service (Google Gemini wrapper)."""

from unittest.mock import MagicMock, patch

import pytest

from app.models.llm_usage import LLMUsage
from app.services.gemini_service import check_health, generate_text


class TestCheckHealth:
    def test_returns_true_when_api_reachable(self, app, db):
        """check_health returns True when Gemini API responds."""
        with app.app_context():
            mock_response = MagicMock()
            mock_response.text = "OK"
            mock_client = MagicMock()
            mock_client.models.generate_content.return_value = mock_response

            with patch("app.services.gemini_service._get_client", return_value=mock_client):
                assert check_health() is True

    def test_returns_false_when_no_api_key(self, app, db):
        """check_health returns False when API key is empty."""
        with app.app_context():
            with patch("app.services.gemini_service._get_api_key", return_value=""):
                assert check_health() is False

    def test_returns_false_on_error(self, app, db):
        """check_health returns False when API raises."""
        with app.app_context():
            with patch(
                "app.services.gemini_service._get_client",
                side_effect=Exception("auth failed"),
            ):
                assert check_health() is False


class TestGenerateText:
    def test_returns_generated_text(self, app, db):
        """generate_text returns LLM response and logs usage."""
        with app.app_context():
            mock_usage = MagicMock()
            mock_usage.prompt_token_count = 100
            mock_usage.candidates_token_count = 50
            mock_usage.total_token_count = 150

            mock_response = MagicMock()
            mock_response.text = "Bonjour, je suis interesse par votre vehicule."
            mock_response.usage_metadata = mock_usage

            mock_client = MagicMock()
            mock_client.models.generate_content.return_value = mock_response

            with patch("app.services.gemini_service._get_client", return_value=mock_client):
                result = generate_text(
                    prompt="Redige un email",
                    feature="email_draft",
                    temperature=0.3,
                    max_output_tokens=500,
                )

            assert "interesse" in result
            # Verify usage was logged
            usage = LLMUsage.query.first()
            assert usage is not None
            assert usage.provider == "gemini"
            assert usage.feature == "email_draft"
            assert usage.prompt_tokens == 100
            assert usage.completion_tokens == 50

    def test_raises_on_empty_api_key(self, app, db):
        """generate_text raises ValueError when no API key configured."""
        with app.app_context():
            with patch("app.services.gemini_service._get_api_key", return_value=""):
                with pytest.raises(ValueError, match="API key"):
                    generate_text(prompt="test", feature="test")

    def test_raises_on_api_error(self, app, db):
        """generate_text raises ConnectionError on API failure."""
        with app.app_context():
            mock_client = MagicMock()
            mock_client.models.generate_content.side_effect = Exception("rate limited")

            with patch("app.services.gemini_service._get_client", return_value=mock_client):
                with pytest.raises(ConnectionError, match="Gemini"):
                    generate_text(prompt="test", feature="test")
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_services/test_gemini_service.py -v`
Expected: FAIL (ImportError)

**Step 3: Write the service**

Create `app/services/gemini_service.py`:

```python
"""Service Gemini -- wrapper pour le SDK Google Gen AI."""

import logging
import uuid

from flask import current_app
from google import genai

from app.extensions import db
from app.models.llm_usage import LLMUsage

logger = logging.getLogger(__name__)

# Grille tarifaire Gemini 2.5 Flash (EUR, approx)
_COST_PER_1M_INPUT = 0.14  # ~0.15 USD
_COST_PER_1M_OUTPUT = 0.55  # ~0.60 USD


def _get_api_key() -> str:
    """Recupere la cle API Gemini depuis la config Flask."""
    return current_app.config.get("GEMINI_API_KEY", "")


def _get_model() -> str:
    """Nom du modele Gemini a utiliser."""
    return current_app.config.get("GEMINI_MODEL", "gemini-2.5-flash")


def _get_client() -> genai.Client:
    """Cree un client Gemini avec la cle API."""
    api_key = _get_api_key()
    if not api_key:
        raise ValueError("Gemini API key non configuree")
    return genai.Client(api_key=api_key)


def _estimate_cost(prompt_tokens: int, completion_tokens: int) -> float:
    """Estime le cout en EUR d'un appel Gemini."""
    input_cost = (prompt_tokens / 1_000_000) * _COST_PER_1M_INPUT
    output_cost = (completion_tokens / 1_000_000) * _COST_PER_1M_OUTPUT
    return round(input_cost + output_cost, 6)


def check_health() -> bool:
    """Verifie que l'API Gemini est accessible.

    Envoie un prompt minimal et retourne True si la reponse est recue.
    """
    api_key = _get_api_key()
    if not api_key:
        return False
    try:
        client = _get_client()
        client.models.generate_content(
            model=_get_model(),
            contents="ping",
        )
        return True
    except Exception:
        logger.warning("Gemini health check echoue")
        return False


def generate_text(
    prompt: str,
    feature: str,
    system_prompt: str | None = None,
    temperature: float = 0.3,
    max_output_tokens: int = 500,
    top_p: float | None = None,
) -> str:
    """Envoie un prompt a Gemini et retourne le texte genere.

    Enregistre automatiquement un LLMUsage pour le suivi des couts.

    Args:
        prompt: Le texte du prompt a envoyer.
        feature: Identifiant du use case ("email_draft", "youtube_synthesis").
        system_prompt: Instructions systeme optionnelles.
        temperature: Creativite (0.0 = deterministe, 2.0 = creatif).
        max_output_tokens: Limite de tokens en sortie.
        top_p: Nucleus sampling (optionnel).

    Returns:
        Le texte genere par Gemini.

    Raises:
        ValueError: Si la cle API n'est pas configuree.
        ConnectionError: Si l'API Gemini est injoignable.
    """
    api_key = _get_api_key()
    if not api_key:
        raise ValueError("Gemini API key non configuree")

    model = _get_model()
    request_id = str(uuid.uuid4())

    config_dict = {
        "temperature": temperature,
        "max_output_tokens": max_output_tokens,
    }
    if top_p is not None:
        config_dict["top_p"] = top_p
    if system_prompt:
        config_dict["system_instruction"] = system_prompt

    try:
        client = _get_client()
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=config_dict,
        )
    except Exception as exc:
        raise ConnectionError(f"Gemini erreur: {exc}") from exc

    # Extraire les metriques de tokens
    usage = response.usage_metadata
    prompt_tokens = getattr(usage, "prompt_token_count", 0) or 0
    completion_tokens = getattr(usage, "candidates_token_count", 0) or 0
    total_tokens = getattr(usage, "total_token_count", 0) or 0

    # Persister le suivi des couts
    llm_usage = LLMUsage(
        request_id=request_id,
        provider="gemini",
        model=model,
        feature=feature,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        estimated_cost_eur=_estimate_cost(prompt_tokens, completion_tokens),
    )
    db.session.add(llm_usage)
    db.session.commit()

    logger.info(
        "Gemini %s: %d tok (in=%d, out=%d) cost=%.6f EUR [%s]",
        feature, total_tokens, prompt_tokens, completion_tokens,
        llm_usage.estimated_cost_eur, request_id,
    )

    return response.text or ""
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_services/test_gemini_service.py -v`
Expected: PASS (6 tests)

**Step 5: Commit**

```bash
git add app/services/gemini_service.py tests/test_services/test_gemini_service.py
git commit -m "feat: add gemini_service.py wrapper for Google Gen AI SDK"
```

---

### Task 6: Create email_service.py (business logic)

**Files:**
- Create: `app/services/email_service.py`
- Test: `tests/test_services/test_email_service.py`

**Step 1: Write the failing tests**

Create `tests/test_services/test_email_service.py`:

```python
"""Tests for email_service (seller email generation)."""

from unittest.mock import MagicMock, patch

import pytest

from app.models.email_draft import EmailDraft
from app.models.filter_result import FilterResultDB
from app.models.scan import ScanLog
from app.services.email_service import build_email_prompt, generate_email_draft


class TestBuildEmailPrompt:
    def test_includes_vehicle_info(self):
        """Prompt includes vehicle make, model, price."""
        scan_data = {
            "make": "Peugeot", "model": "308", "price": 15000,
            "year": 2019, "mileage_km": 85000, "fuel": "Diesel",
            "owner_type": "private", "owner_name": "Jean",
            "days_online": 25, "url": "https://example.com",
        }
        filters = [
            {"filter_id": "L4", "status": "warning", "message": "Prix 10% sous argus"},
        ]
        prompt = build_email_prompt(scan_data, filters)
        assert "Peugeot" in prompt
        assert "308" in prompt
        assert "15000" in prompt or "15 000" in prompt

    def test_includes_filter_signals(self):
        """Prompt mentions warning/fail filter signals."""
        scan_data = {
            "make": "Renault", "model": "Clio", "price": 8000,
            "owner_type": "pro", "days_online": 45,
            "url": "https://example.com",
        }
        filters = [
            {"filter_id": "L4", "status": "fail", "message": "Prix tres bas"},
            {"filter_id": "L8", "status": "warning", "message": "Signaux import"},
        ]
        prompt = build_email_prompt(scan_data, filters)
        assert "L4" in prompt or "prix" in prompt.lower()
        assert "L8" in prompt or "import" in prompt.lower()

    def test_adapts_to_seller_type(self):
        """Prompt adapts language for pro vs private sellers."""
        base = {
            "make": "BMW", "model": "Serie 3", "price": 25000,
            "url": "https://example.com", "days_online": 10,
        }
        pro_prompt = build_email_prompt({**base, "owner_type": "pro"}, [])
        private_prompt = build_email_prompt({**base, "owner_type": "private"}, [])
        # Pro and private should produce different prompts
        assert pro_prompt != private_prompt


class TestGenerateEmailDraft:
    def test_creates_draft_from_scan(self, app, db):
        """generate_email_draft creates an EmailDraft from a ScanLog."""
        with app.app_context():
            # Create a scan
            scan = ScanLog(
                url="https://www.leboncoin.fr/voitures/12345.htm",
                raw_data={
                    "make": "Peugeot", "model": "308", "price": 15000,
                    "year": 2019, "mileage_km": 85000, "fuel": "Diesel",
                    "owner_type": "private", "owner_name": "Jean",
                    "days_online": 25,
                },
                score=65,
                vehicle_make="Peugeot",
                vehicle_model="308",
                price_eur=15000,
                days_online=25,
            )
            db.session.add(scan)
            db.session.commit()
            scan_id = scan.id

            # Add filter results
            fr = FilterResultDB(
                scan_id=scan_id, filter_id="L4", status="warning",
                score=0.5, message="Prix 10% sous argus",
            )
            db.session.add(fr)
            db.session.commit()

            # Mock Gemini
            with patch(
                "app.services.email_service.gemini_service.generate_text",
                return_value="Bonjour Jean, je suis interesse par votre 308...",
            ):
                draft = generate_email_draft(scan_id)

            assert draft.scan_id == scan_id
            assert draft.vehicle_make == "Peugeot"
            assert draft.vehicle_model == "308"
            assert draft.seller_type == "private"
            assert draft.status == "draft"
            assert "308" in draft.generated_text

    def test_raises_on_unknown_scan(self, app, db):
        """generate_email_draft raises ValueError for non-existent scan."""
        with app.app_context():
            with pytest.raises(ValueError, match="Scan introuvable"):
                generate_email_draft(99999)
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_services/test_email_service.py -v`
Expected: FAIL

**Step 3: Write the service**

Create `app/services/email_service.py`:

```python
"""Service email -- generation d'emails vendeur via Gemini."""

import logging

from app.extensions import db
from app.models.email_draft import EmailDraft
from app.models.filter_result import FilterResultDB
from app.models.scan import ScanLog
from app.services import gemini_service

logger = logging.getLogger(__name__)


def build_email_prompt(scan_data: dict, filters: list[dict]) -> str:
    """Construit le prompt pour Gemini a partir des donnees d'analyse.

    Args:
        scan_data: Dictionnaire des donnees extraites de l'annonce.
        filters: Liste des resultats de filtres (filter_id, status, message).

    Returns:
        Le prompt complet a envoyer a Gemini.
    """
    make = scan_data.get("make", "?")
    model = scan_data.get("model", "?")
    price = scan_data.get("price", "?")
    year = scan_data.get("year", "")
    mileage = scan_data.get("mileage_km", "")
    fuel = scan_data.get("fuel", "")
    owner_type = scan_data.get("owner_type", "private")
    owner_name = scan_data.get("owner_name", "")
    days_online = scan_data.get("days_online", "")
    url = scan_data.get("url", "")

    # Signaux d'alerte (filtres warning/fail)
    signals = []
    for f in filters:
        if f.get("status") in ("warning", "fail"):
            signals.append(f"- {f['filter_id']}: {f.get('message', 'Signal detecte')}")

    signals_text = "\n".join(signals) if signals else "Aucun signal d'alerte majeur."

    # Adapter le contexte vendeur
    if owner_type == "pro":
        seller_context = (
            "Le vendeur est un professionnel. "
            "Adapte le ton en consequence: pose des questions precises sur l'historique "
            "du vehicule en flotte, le carnet d'entretien, et les garanties professionnelles."
        )
    else:
        seller_context = (
            "Le vendeur est un particulier. "
            "Sois cordial mais direct. Pose des questions concretes sur l'utilisation "
            "quotidienne, les factures d'entretien, et les raisons de la vente."
        )

    prompt = f"""Redige un email a un vendeur pour le vehicule suivant.

VEHICULE:
- Marque: {make}
- Modele: {model}
- Annee: {year}
- Carburant: {fuel}
- Kilometrage: {mileage} km
- Prix demande: {price} EUR
- En ligne depuis: {days_online} jours
- URL: {url}

VENDEUR:
- Type: {owner_type}
- Nom: {owner_name}

SIGNAUX D'ANALYSE:
{signals_text}

CONTEXTE VENDEUR:
{seller_context}

CONSIGNES:
- Ton: acheteur averti et direct, sans etre agressif
- Pose des questions precises basees sur les signaux d'analyse
- Si le prix est bas + annonce ancienne, mentionne-le subtilement
- Si peu de photos, demande des photos supplementaires
- Termine par une proposition de rendez-vous ou appel
- NE MENTIONNE PAS que tu utilises un outil d'analyse
- NE FABRIQUE PAS d'informations: utilise uniquement les donnees fournies ci-dessus
"""
    return prompt


def generate_email_draft(scan_id: int) -> EmailDraft:
    """Genere un brouillon d'email vendeur a partir d'un scan.

    Args:
        scan_id: ID du ScanLog source.

    Returns:
        L'EmailDraft cree et persiste.

    Raises:
        ValueError: Si le scan_id n'existe pas.
        ConnectionError: Si Gemini est injoignable.
    """
    scan = ScanLog.query.get(scan_id)
    if not scan:
        raise ValueError(f"Scan introuvable: {scan_id}")

    raw = scan.raw_data or {}

    # Recuperer les resultats de filtres
    filter_results = FilterResultDB.query.filter_by(scan_id=scan_id).all()
    filters = [
        {
            "filter_id": fr.filter_id,
            "status": fr.status,
            "message": fr.message,
        }
        for fr in filter_results
    ]

    # Construire les donnees pour le prompt
    scan_data = {
        "make": scan.vehicle_make or raw.get("make", ""),
        "model": scan.vehicle_model or raw.get("model", ""),
        "price": scan.price_eur or raw.get("price", ""),
        "year": raw.get("year", ""),
        "mileage_km": raw.get("mileage_km", ""),
        "fuel": raw.get("fuel", ""),
        "owner_type": raw.get("owner_type", "private"),
        "owner_name": raw.get("owner_name", ""),
        "days_online": scan.days_online or raw.get("days_online", ""),
        "url": scan.url or "",
    }

    prompt = build_email_prompt(scan_data, filters)

    # Appel Gemini
    generated_text = gemini_service.generate_text(
        prompt=prompt,
        feature="email_draft",
    )

    # Creer le brouillon
    draft = EmailDraft(
        scan_id=scan_id,
        listing_url=scan.url or "",
        vehicle_make=scan_data["make"],
        vehicle_model=scan_data["model"],
        seller_type=scan_data["owner_type"],
        seller_name=scan_data["owner_name"],
        seller_phone=raw.get("phone", ""),
        seller_email=raw.get("email", ""),
        prompt_used=prompt,
        generated_text=generated_text,
        llm_model=gemini_service._get_model(),
        tokens_used=0,  # Updated by LLMUsage
    )
    db.session.add(draft)
    db.session.commit()

    logger.info("Email draft #%d cree pour scan #%d", draft.id, scan_id)
    return draft
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_services/test_email_service.py -v`
Expected: PASS (5 tests)

**Step 5: Commit**

```bash
git add app/services/email_service.py tests/test_services/test_email_service.py
git commit -m "feat: add email_service.py for seller email generation via Gemini"
```

---

### Task 7: Add API endpoint for email draft generation

**Files:**
- Modify: `app/api/routes.py`
- Test: `tests/test_api/test_email_api.py`

**Step 1: Write the failing test**

Create `tests/test_api/test_email_api.py`:

```python
"""Tests for /api/email-draft endpoint."""

from unittest.mock import MagicMock, patch

from app.models.scan import ScanLog


class TestEmailDraftAPI:
    def test_generate_draft_success(self, app, client, db):
        """POST /api/email-draft creates a draft and returns it."""
        with app.app_context():
            scan = ScanLog(
                url="https://example.com/voiture",
                raw_data={"make": "Peugeot", "model": "308", "price": 15000,
                          "owner_type": "private"},
                score=70,
                vehicle_make="Peugeot",
                vehicle_model="308",
            )
            db.session.add(scan)
            db.session.commit()

            mock_draft = MagicMock()
            mock_draft.id = 1
            mock_draft.generated_text = "Bonjour..."
            mock_draft.status = "draft"
            mock_draft.vehicle_make = "Peugeot"
            mock_draft.vehicle_model = "308"
            mock_draft.tokens_used = 150

            with patch(
                "app.api.routes.email_service.generate_email_draft",
                return_value=mock_draft,
            ):
                resp = client.post("/api/email-draft", json={"scan_id": scan.id})

            assert resp.status_code == 200
            data = resp.get_json()
            assert data["success"] is True
            assert data["data"]["generated_text"] == "Bonjour..."

    def test_returns_400_without_scan_id(self, app, client):
        """POST /api/email-draft without scan_id returns 400."""
        with app.app_context():
            resp = client.post("/api/email-draft", json={})
            assert resp.status_code == 400

    def test_returns_404_for_unknown_scan(self, app, client, db):
        """POST /api/email-draft with unknown scan_id returns 404."""
        with app.app_context():
            with patch(
                "app.api.routes.email_service.generate_email_draft",
                side_effect=ValueError("Scan introuvable: 99999"),
            ):
                resp = client.post("/api/email-draft", json={"scan_id": 99999})
            assert resp.status_code == 404

    def test_returns_503_when_gemini_down(self, app, client, db):
        """POST /api/email-draft returns 503 if Gemini unreachable."""
        with app.app_context():
            scan = ScanLog(
                url="https://example.com",
                raw_data={"make": "Renault", "model": "Clio"},
                score=50,
                vehicle_make="Renault",
                vehicle_model="Clio",
            )
            db.session.add(scan)
            db.session.commit()

            with patch(
                "app.api.routes.email_service.generate_email_draft",
                side_effect=ConnectionError("Gemini erreur"),
            ):
                resp = client.post("/api/email-draft", json={"scan_id": scan.id})
            assert resp.status_code == 503
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_api/test_email_api.py -v`
Expected: FAIL

**Step 3: Add the endpoint to `app/api/routes.py`**

At the top of the file, add import:

```python
from app.services import email_service
```

At the end of the file, add:

```python
@api_bp.route("/email-draft", methods=["POST"])
def email_draft():
    """Genere un brouillon d'email vendeur via Gemini."""
    data = request.get_json(silent=True) or {}
    scan_id = data.get("scan_id")

    if not scan_id:
        return jsonify({"success": False, "error": "scan_id requis"}), 400

    try:
        draft = email_service.generate_email_draft(scan_id)
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 404
    except ConnectionError as exc:
        return jsonify({"success": False, "error": str(exc)}), 503

    return jsonify({
        "success": True,
        "error": None,
        "data": {
            "draft_id": draft.id,
            "generated_text": draft.generated_text,
            "status": draft.status,
            "vehicle_make": draft.vehicle_make,
            "vehicle_model": draft.vehicle_model,
            "tokens_used": draft.tokens_used,
        },
    })
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_api/test_email_api.py -v`
Expected: PASS (4 tests)

**Step 5: Commit**

```bash
git add app/api/routes.py tests/test_api/test_email_api.py
git commit -m "feat: add POST /api/email-draft endpoint"
```

---

### Task 8: Add /admin/llm page (LLM configuration)

**Files:**
- Modify: `app/admin/routes.py` (add routes)
- Create: `app/admin/templates/admin/llm.html`
- Modify: `app/admin/templates/admin/base.html` (add sidebar link)

**Step 1: Add sidebar navigation link**

In `app/admin/templates/admin/base.html`, after line 79 (YouTube Recherche link), add:

```html
          <a class="nav-link {% if request.endpoint and 'llm' in request.endpoint %}active{% endif %}"
             href="{{ url_for('admin.llm_config') }}">LLM Google</a>
          <a class="nav-link {% if request.endpoint and 'email' in request.endpoint %}active{% endif %}"
             href="{{ url_for('admin.email_list') }}">Emails Vendeur</a>
```

**Step 2: Add admin routes**

In `app/admin/routes.py`, add imports at the top:

```python
from app.models.llm_usage import LLMUsage
from app.models.gemini_config import GeminiConfig, GeminiPromptConfig
```

At the end of the file, add the /admin/llm route:

```python
@admin_bp.route("/llm")
@login_required
def llm_config():
    """Page de configuration et monitoring du LLM Google Gemini."""
    from datetime import datetime, timezone, timedelta
    from sqlalchemy import func

    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    # Stats du jour
    today_usage = db.session.query(
        func.count(LLMUsage.id),
        func.coalesce(func.sum(LLMUsage.total_tokens), 0),
        func.coalesce(func.sum(LLMUsage.estimated_cost_eur), 0.0),
    ).filter(LLMUsage.created_at >= today).first()

    requests_today = today_usage[0]
    tokens_today = today_usage[1]
    cost_today = today_usage[2]

    # Config Gemini
    config = GeminiConfig.query.first()

    # Prompts
    prompts = GeminiPromptConfig.query.order_by(GeminiPromptConfig.created_at.desc()).all()

    # Health check
    api_ok = False
    if config and config.is_active:
        from app.services import gemini_service
        api_ok = gemini_service.check_health()

    # Historique 7 jours
    week_ago = today - timedelta(days=7)
    daily_usage = db.session.query(
        func.date(LLMUsage.created_at),
        func.sum(LLMUsage.total_tokens),
        func.sum(LLMUsage.estimated_cost_eur),
        func.count(LLMUsage.id),
    ).filter(
        LLMUsage.created_at >= week_ago,
    ).group_by(func.date(LLMUsage.created_at)).all()

    return render_template(
        "admin/llm.html",
        requests_today=requests_today,
        tokens_today=tokens_today,
        cost_today=round(cost_today, 4),
        api_ok=api_ok,
        gemini_config=config,
        prompts=prompts,
        daily_usage=daily_usage,
        max_daily_requests=config.max_daily_requests if config else 500,
        max_daily_cost=config.max_daily_cost_eur if config else 1.0,
    )
```

**Step 3: Create the template**

Create `app/admin/templates/admin/llm.html` with Bootstrap 5 layout:
- 4 stat cards (requests, tokens, cost, API status)
- Config section (API key, model, quotas)
- Prompts list with "New prompt" button
- Cost history chart (Plotly bar chart)

*(Full template implementation - follows existing admin page patterns from youtube.html)*

**Step 4: Add POST routes for config save and prompt CRUD**

Add in `app/admin/routes.py`:

```python
@admin_bp.route("/llm/config", methods=["POST"])
@login_required
def llm_config_save():
    """Sauvegarde la configuration Gemini."""
    # ... save GeminiConfig to DB ...
    flash("Configuration Gemini sauvegardee.", "success")
    return redirect(url_for("admin.llm_config"))


@admin_bp.route("/llm/prompt/new", methods=["POST"])
@login_required
def llm_prompt_new():
    """Cree un nouveau prompt Gemini."""
    # ... create GeminiPromptConfig ...
    flash("Prompt cree.", "success")
    return redirect(url_for("admin.llm_config"))


@admin_bp.route("/llm/prompt/<int:prompt_id>/activate", methods=["POST"])
@login_required
def llm_prompt_activate(prompt_id):
    """Active un prompt et desactive les autres."""
    # ... toggle is_active ...
    flash("Prompt active.", "success")
    return redirect(url_for("admin.llm_config"))


@admin_bp.route("/llm/test", methods=["POST"])
@login_required
def llm_test():
    """Teste l'API Gemini avec un prompt de test."""
    # ... call gemini_service.generate_text with test prompt ...
    # return JSON with response text + tokens used
```

**Step 5: Commit**

```bash
git add app/admin/routes.py app/admin/templates/admin/llm.html app/admin/templates/admin/base.html
git commit -m "feat: add /admin/llm page for Gemini configuration and monitoring"
```

---

### Task 9: Add /admin/email page (email drafts management)

**Files:**
- Modify: `app/admin/routes.py`
- Create: `app/admin/templates/admin/email_list.html`
- Create: `app/admin/templates/admin/email_detail.html`

**Step 1: Add routes**

In `app/admin/routes.py`, add:

```python
from app.models.email_draft import EmailDraft


@admin_bp.route("/email")
@login_required
def email_list():
    """Liste des brouillons d'emails vendeur."""
    from sqlalchemy import func

    status_filter = request.args.get("status", "")
    seller_filter = request.args.get("seller_type", "")

    query = EmailDraft.query

    if status_filter:
        query = query.filter_by(status=status_filter)
    if seller_filter:
        query = query.filter_by(seller_type=seller_filter)

    drafts = query.order_by(EmailDraft.created_at.desc()).limit(100).all()

    # Stats
    total_drafts = EmailDraft.query.filter_by(status="draft").count()
    total_approved = EmailDraft.query.filter_by(status="approved").count()
    total_sent = EmailDraft.query.filter_by(status="sent").count()

    avg_tokens = db.session.query(func.avg(EmailDraft.tokens_used)).scalar() or 0

    return render_template(
        "admin/email_list.html",
        drafts=drafts,
        total_drafts=total_drafts,
        total_approved=total_approved,
        total_sent=total_sent,
        avg_tokens=round(avg_tokens),
        status_filter=status_filter,
        seller_filter=seller_filter,
    )


@admin_bp.route("/email/<int:draft_id>")
@login_required
def email_detail(draft_id):
    """Detail d'un brouillon d'email."""
    draft = EmailDraft.query.get_or_404(draft_id)
    scan = ScanLog.query.get(draft.scan_id)
    filters = FilterResultDB.query.filter_by(scan_id=draft.scan_id).all() if scan else []

    return render_template(
        "admin/email_detail.html",
        draft=draft,
        scan=scan,
        filters=filters,
    )


@admin_bp.route("/email/<int:draft_id>/regenerate", methods=["POST"])
@login_required
def email_regenerate(draft_id):
    """Regenere un email avec Gemini."""
    draft = EmailDraft.query.get_or_404(draft_id)
    from app.services import email_service
    new_draft = email_service.generate_email_draft(draft.scan_id)
    flash("Email regenere.", "success")
    return redirect(url_for("admin.email_detail", draft_id=new_draft.id))


@admin_bp.route("/email/<int:draft_id>/approve", methods=["POST"])
@login_required
def email_approve(draft_id):
    """Approuve un brouillon."""
    draft = EmailDraft.query.get_or_404(draft_id)
    edited = request.form.get("edited_text", "").strip()
    if edited:
        draft.edited_text = edited
    draft.status = "approved"
    db.session.commit()
    flash("Email approuve.", "success")
    return redirect(url_for("admin.email_detail", draft_id=draft_id))


@admin_bp.route("/email/<int:draft_id>/archive", methods=["POST"])
@login_required
def email_archive(draft_id):
    """Archive un brouillon."""
    draft = EmailDraft.query.get_or_404(draft_id)
    draft.status = "archived"
    db.session.commit()
    flash("Email archive.", "success")
    return redirect(url_for("admin.email_list"))
```

**Step 2: Create templates**

Create `app/admin/templates/admin/email_list.html`:
- 4 stat cards (drafts pending, approved, sent, avg tokens)
- Filters (status, seller type)
- Table: vehicle, seller, score, status, date, link to detail

Create `app/admin/templates/admin/email_detail.html`:
- Listing info card (make, model, price, URL clickable)
- Filter results summary (10 rows, colored by status)
- Email text (editable textarea)
- Action buttons: Regenerer, Approuver, Copier, Archiver

**Step 3: Commit**

```bash
git add app/admin/routes.py app/admin/templates/admin/email_list.html app/admin/templates/admin/email_detail.html
git commit -m "feat: add /admin/email pages for email draft management"
```

---

### Task 10: Add email button to Chrome extension popup

**Files:**
- Modify: `extension/content.js`

**Step 1: Add email banner in popup**

In `extension/content.js`, in `buildResultsPopup()` (around line 498, after the YouTube banner), add:

```javascript
        ${buildEmailBanner()}
```

**Step 2: Create buildEmailBanner function**

After `buildYouTubeBanner()` function, add:

```javascript
  /**
   * Construit le bandeau "Rediger un email" dans la popup.
   */
  function buildEmailBanner() {
    return `
      <div class="copilot-email-banner" id="copilot-email-section">
        <button class="copilot-email-btn" id="copilot-email-btn">
          &#x2709; Rédiger un email au vendeur
        </button>
        <div class="copilot-email-result" id="copilot-email-result" style="display:none;">
          <textarea class="copilot-email-textarea" id="copilot-email-text" rows="8" readonly></textarea>
          <button class="copilot-email-copy" id="copilot-email-copy">
            &#x1F4CB; Copier
          </button>
          <span class="copilot-email-copied" id="copilot-email-copied" style="display:none;">
            Copie !
          </span>
        </div>
        <div class="copilot-email-loading" id="copilot-email-loading" style="display:none;">
          Generation en cours...
        </div>
        <div class="copilot-email-error" id="copilot-email-error" style="display:none;"></div>
      </div>
    `;
  }
```

**Step 3: Add click handler**

In the event listener setup section (after popup is injected into DOM), add:

```javascript
    // Email button handler
    const emailBtn = document.getElementById("copilot-email-btn");
    if (emailBtn) {
      emailBtn.addEventListener("click", async () => {
        const loading = document.getElementById("copilot-email-loading");
        const result = document.getElementById("copilot-email-result");
        const errorDiv = document.getElementById("copilot-email-error");
        const textArea = document.getElementById("copilot-email-text");

        emailBtn.style.display = "none";
        loading.style.display = "block";
        errorDiv.style.display = "none";

        try {
          const resp = await fetch(`${API_BASE}/api/email-draft`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ scan_id: lastScanId }),
          });
          const data = await resp.json();

          if (data.success) {
            textArea.value = data.data.generated_text;
            result.style.display = "block";
          } else {
            errorDiv.textContent = data.error || "Erreur de generation";
            errorDiv.style.display = "block";
            emailBtn.style.display = "block";
          }
        } catch (err) {
          errorDiv.textContent = "Service indisponible";
          errorDiv.style.display = "block";
          emailBtn.style.display = "block";
        }
        loading.style.display = "none";
      });

      // Copy button
      const copyBtn = document.getElementById("copilot-email-copy");
      if (copyBtn) {
        copyBtn.addEventListener("click", () => {
          const textArea = document.getElementById("copilot-email-text");
          navigator.clipboard.writeText(textArea.value).then(() => {
            const copied = document.getElementById("copilot-email-copied");
            copied.style.display = "inline";
            setTimeout(() => { copied.style.display = "none"; }, 2000);
          });
        });
      }
    }
```

**Step 4: Store scan_id for email generation**

Ensure `lastScanId` is set after successful analysis. In the analyze response handler, add:

```javascript
let lastScanId = null;
// ... after successful /api/analyze response:
lastScanId = data.data.scan_id;
```

Note: The `/api/analyze` endpoint must also return `scan_id` in its response. Add it in `app/api/routes.py` analyze endpoint response.

**Step 5: Add CSS for email section**

In the styles section of content.js, add:

```css
.copilot-email-banner { padding: 12px 16px; border-top: 1px solid #e5e7eb; }
.copilot-email-btn { width: 100%; padding: 10px; background: #2563eb; color: #fff; border: none; border-radius: 8px; cursor: pointer; font-size: 14px; font-weight: 600; }
.copilot-email-btn:hover { background: #1d4ed8; }
.copilot-email-textarea { width: 100%; padding: 8px; border: 1px solid #d1d5db; border-radius: 6px; font-size: 13px; resize: vertical; margin: 8px 0; }
.copilot-email-copy { padding: 6px 12px; background: #10b981; color: #fff; border: none; border-radius: 6px; cursor: pointer; font-size: 13px; }
.copilot-email-loading { text-align: center; color: #6b7280; font-size: 13px; padding: 8px; }
.copilot-email-error { color: #ef4444; font-size: 13px; padding: 4px; }
.copilot-email-copied { color: #10b981; font-size: 12px; margin-left: 8px; }
```

**Step 6: Commit**

```bash
git add extension/content.js
git commit -m "feat: add email generation button to Chrome extension popup"
```

---

### Task 11: Return scan_id in /api/analyze response

**Files:**
- Modify: `app/api/routes.py` (analyze endpoint)

**Step 1: In the analyze response construction, add scan_id**

Find the response dict construction in the analyze function and add `scan_id`:

```python
# In the response data, add:
"scan_id": scan.id,
```

**Step 2: Commit**

```bash
git add app/api/routes.py
git commit -m "feat: include scan_id in /api/analyze response for email draft"
```

---

### Task 12: Run full test suite and fix

**Step 1: Run all tests**

Run: `pytest tests/ -v --tb=short`
Expected: All existing tests pass + all new tests pass

**Step 2: Run ruff**

Run: `ruff check . && ruff format --check .`
Expected: Clean (no errors)

**Step 3: Fix any failures**

Address any import errors, missing fixtures, or ruff warnings.

**Step 4: Final commit**

```bash
git add -A
git commit -m "chore: fix test and lint issues for Gemini email integration"
```

---

### Task 13: Seed default prompt config

**Files:**
- Modify: `start.sh` or create seed script

**Step 1: Add default email prompt**

Create a default `GeminiPromptConfig` in the DB init or seed:

```python
GeminiPromptConfig(
    name="email_vendeur_v1",
    system_prompt="""Tu es un acheteur automobile averti et direct.
Tu rediges des emails professionnels mais accessibles.
Tu ne fabriques JAMAIS d'information: tu utilises uniquement les donnees fournies.
Tu ne mentionnes JAMAIS que tu utilises un outil d'analyse automatique.""",
    task_prompt_template="(see build_email_prompt output)",
    max_output_tokens=600,
    temperature=0.3,
    top_p=0.9,
    hallucination_guard="Ne mentionne que les faits issus des donnees fournies. En cas de doute, pose une question au vendeur plutot que d'affirmer.",
    max_sentences=15,
    is_active=True,
    version=1,
)
```

**Step 2: Commit**

```bash
git commit -m "feat: seed default email prompt config"
```
