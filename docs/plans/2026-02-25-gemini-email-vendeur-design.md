# Design : Gemini Flash 2.5 + Email Vendeur

**Date** : 2025-02-25
**Statut** : Approuve
**Approche** : Wrapper leger gemini_service.py (Approche A)

## Contexte

L'extension Chrome Co-Pilot analyse les annonces LBC et produit 10 filtres + score global. L'etape suivante est de generer automatiquement un email au vendeur, base sur les signaux detectes. Gemini Flash 2.5 (API Google gratuite, 500 req/jour) est le provider LLM choisi pour la production (pas de GPU Docker necessaire, reponse rapide).

## Architecture

```
gemini_service.py              email_service.py
  init_client()                  generate_email_draft(scan_id)
  generate_text(prompt, cfg)     build_email_prompt(scan_data, filters)
  count_tokens(text)             get_draft(draft_id)
  check_health()                 update_draft(draft_id, text)
                                        |
                                 +------+------+
                                 | LLMUsage    |  (cost tracking)
                                 | EmailDraft  |  (persistence)
                                 +-------------+
```

- **gemini_service.py** : wrapper pur du SDK `google-genai`. Pas de logique metier. Chaque appel enregistre un `LLMUsage`.
- **email_service.py** : logique metier. Prend un scan_id, recupere extraction + 10 filtres + market data, construit le prompt, appelle gemini_service, stocke le brouillon.

## Modeles DB

### LLMUsage (suivi couts)

| Colonne | Type | Description |
|---------|------|-------------|
| id | Integer PK | Auto-increment |
| request_id | String (UUID) | Identifiant unique pour tracabilite |
| provider | String | "gemini" (futur: "ollama") |
| model | String | "gemini-2.5-flash" |
| feature | String | "email_draft", "youtube_synthesis" |
| prompt_tokens | Integer | Tokens input |
| completion_tokens | Integer | Tokens output |
| total_tokens | Integer | Total |
| estimated_cost_eur | Float | Cout estime (grille tarifaire) |
| created_at | DateTime | UTC |

### EmailDraft (brouillons email)

| Colonne | Type | Description |
|---------|------|-------------|
| id | Integer PK | Auto-increment |
| scan_id | Integer FK -> ScanLog | Lie a l'annonce analysee |
| listing_url | String | URL LBC de l'annonce |
| vehicle_make | String | Pour recherche rapide |
| vehicle_model | String | |
| seller_type | String | "pro" / "private" |
| seller_name | String | Nom du vendeur |
| seller_phone | String | Telephone (si disponible) |
| seller_email | String | Email (si extrait) |
| prompt_used | Text | Le prompt envoye a Gemini |
| generated_text | Text | L'email brut genere |
| edited_text | Text | Nullable, version editee par l'admin |
| status | String | "draft" / "approved" / "sent" / "archived" |
| llm_model | String | Modele utilise |
| tokens_used | Integer | Pour reference |
| created_at | DateTime | UTC |

### GeminiConfig (parametrage API)

| Colonne | Type | Description |
|---------|------|-------------|
| id | Integer PK | Singleton (1 seul row) |
| api_key_encrypted | String | Cle API chiffree |
| model_name | String | Default: "gemini-2.5-flash" |
| max_daily_requests | Integer | Quota max/jour |
| max_daily_cost_eur | Float | Budget max/jour |
| is_active | Boolean | On/Off global |
| updated_at | DateTime | UTC |

### GeminiPromptConfig (prompts configurables)

| Colonne | Type | Description |
|---------|------|-------------|
| id | Integer PK | Auto-increment |
| name | String | Ex: "email_vendeur_v1" |
| system_prompt | Text | Contexte/personnalite du LLM |
| task_prompt_template | Text | Template avec placeholders ({make}, {model}, {price}...) |
| max_output_tokens | Integer | Limite de longueur de reponse |
| temperature | Float | 0.0-2.0 (creativite vs. determinisme) |
| top_p | Float | Nucleus sampling |
| response_format_hint | String | "email_text", "structured_json" |
| hallucination_guard | Text | Instructions anti-hallucination |
| max_sentences | Integer | Nullable, guide de longueur |
| is_active | Boolean | Un seul actif par type a la fois |
| version | Integer | Versioning pour A/B testing |
| created_at | DateTime | UTC |

## Pages Admin

### /admin/llm (Config LLM Google)

**Stat cards (haut de page)** :
- Requetes aujourd'hui / quota max
- Tokens consommes aujourd'hui
- Cout estime aujourd'hui / budget max
- Statut API (vert/rouge)

**Section Config** :
- Champ API Key (masque, bouton "Tester la connexion")
- Selecteur modele (gemini-2.5-flash, gemini-2.5-pro...)
- Quota max/jour + Budget max/jour
- Toggle On/Off

**Section Prompts** :
- Liste des GeminiPromptConfig avec badge "actif"
- Bouton "Nouveau prompt" -> formulaire complet
- Preview : bouton "Tester" qui envoie un prompt test et affiche reponse + tokens

**Section Historique couts** :
- Tableau LLMUsage avec filtres par date/feature
- Graphique conso tokens par jour (7 derniers jours)

### /admin/email (Emails Vendeur)

**Stat cards** :
- Brouillons en attente
- Emails approuves
- Emails envoyes ce mois
- Cout moyen par email (tokens)

**Liste brouillons** :
- Tableau : vehicule, vendeur (pro/particulier), score global, statut, date
- Filtres par statut, par vendeur type
- Clic -> page de detail

**Detail email (/admin/email/<id>)** :
- Infos annonce (make, model, prix, URL cliquable)
- Resume filtres (10 resultats avec couleurs pass/warning/fail)
- Email genere (zone editable)
- Boutons : "Regenerer", "Approuver", "Copier", "Archiver"

## Extension Chrome

- Nouveau bouton "Rediger un email au vendeur" dans la popup (apres analyse)
- Clic -> `POST /api/email-draft` avec scan_id
- Texte email affiche dans la popup
- Bouton "Copier" pour copier-coller en 1 clic
- Si Gemini off ou quota depasse -> message "Service indisponible"

## Ton de l'email

**Acheteur averti, direct** : questions precises basees sur les signaux des filtres. Montre qu'on a fait nos devoirs sans etre agressif.

Exemples de personnalisation :
- `owner_type == "pro"` + km eleve -> demander carnet d'entretien flotte, historique LOA/LLD
- `owner_type == "pro"` + km normal -> demander factures entretien, historique SIRET
- L8 signal import -> poser questions COC, carte grise, malus
- L4 prix < argus + >30j -> mentionner que l'annonce est en ligne depuis longtemps
- Peu de photos -> demander photos supplementaires (moteur, interieur, dessous)

## Dependances

- `google-genai>=1.0.0` (SDK officiel Google Gen AI)
- Env var : `GEMINI_API_KEY` (ou config DB via GeminiConfig)

## SDK Usage

```python
from google import genai

client = genai.Client(api_key=api_key)

response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents=prompt
)

# Token tracking natif
usage = response.usage_metadata
prompt_tokens = usage.prompt_token_count
completion_tokens = usage.candidates_token_count
total_tokens = usage.total_token_count
```

## Grille tarifaire (pour estimation couts)

Gemini 2.5 Flash (free tier) :
- 500 requetes/jour gratuites
- Au-dela : ~0.15$/1M tokens input, ~0.60$/1M tokens output
- Email moyen estime : ~800 tokens input + ~300 tokens output = ~0.0003$

## Cohabitation avec Ollama

- Ollama reste pour YouTube synthese (local, pas de contrainte temps)
- Gemini pour email vendeur (cloud, rapide, production-ready)
- A terme : migration progressive YouTube vers Gemini si le calibrage est bon
