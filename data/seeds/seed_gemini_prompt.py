#!/usr/bin/env python3
"""Seed du prompt Gemini par defaut pour la generation d'emails vendeur.

Script idempotent : ne cree pas de doublons si relance.
Usage : python data/seeds/seed_gemini_prompt.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models.gemini_config import GeminiPromptConfig  # noqa: E402

DEFAULT_PROMPT_NAME = "email_vendeur_v1"

SYSTEM_PROMPT = """Tu es un assistant specialise dans la redaction d'emails \
pour l'achat de vehicules d'occasion en France.

Ton role est de rediger un email professionnel, direct et courtois \
a destination du vendeur, en te basant uniquement sur les donnees fournies.

Regles absolues:
- NE MENTIONNE JAMAIS que tu es une IA ou que tu utilises un outil d'analyse
- NE FABRIQUE AUCUNE information: utilise exclusivement les donnees fournies
- Ecris en francais courant, sans fautes, sans emojis
- Ton: acheteur averti, direct, sans etre agressif"""

TASK_PROMPT_TEMPLATE = """Redige un email au vendeur pour le vehicule suivant.

VEHICULE:
- Marque: {make}
- Modele: {model}
- Annee: {year}
- Carburant: {fuel}
- Kilometrage: {mileage_km} km
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
- Pose des questions precises basees sur les signaux d'analyse
- Si le prix est bas + annonce ancienne, mentionne-le subtilement
- Si peu de photos, demande des photos supplementaires
- Termine par une proposition de rendez-vous ou appel
- Maximum {max_sentences} phrases"""

HALLUCINATION_GUARD = """RAPPEL CRITIQUE: tu ne dois inventer AUCUNE donnee.
Si une information est manquante (marquee '?' ou vide), \
ne la mentionne pas dans l'email.
Ne fais aucune supposition sur l'etat du vehicule, \
son historique ou ses defauts sauf si les signaux d'analyse le mentionnent."""


def seed():
    """Insere le prompt par defaut s'il n'existe pas deja."""
    existing = GeminiPromptConfig.query.filter_by(name=DEFAULT_PROMPT_NAME).first()
    if existing:
        print(f"  Prompt '{DEFAULT_PROMPT_NAME}' existe deja (id={existing.id}), skip.")
        return

    prompt = GeminiPromptConfig(
        name=DEFAULT_PROMPT_NAME,
        system_prompt=SYSTEM_PROMPT,
        task_prompt_template=TASK_PROMPT_TEMPLATE,
        max_output_tokens=500,
        temperature=0.3,
        top_p=0.9,
        response_format_hint="email_text",
        hallucination_guard=HALLUCINATION_GUARD,
        max_sentences=12,
        is_active=True,
        version=1,
    )
    db.session.add(prompt)
    db.session.commit()
    print(f"  Prompt '{DEFAULT_PROMPT_NAME}' cree (id={prompt.id}).")


if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        db.create_all()
        seed()
        print("Done.")
