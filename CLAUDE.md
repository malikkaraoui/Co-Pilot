# OKazCar — Instructions Claude

## Langue
Toujours communiquer en francais.

## Conventions code
- PEP 8 strict, snake_case partout en Python
- Jamais de bare `except Exception` — toujours des types specifiques
- Logger par module : `logger = logging.getLogger(__name__)`
- API envelope : `{success, error, message, data}`
- FilterResult dataclass : filter_id, status, score, message, details

## Tests & qualite
- Toujours `npm run verify` (ruff + pytest + vitest) avant de suggerer un commit
- Jamais commit si verify n'est pas vert

## Workflow prod (Chrome Web Store)
- Voir `memory/prod-workflow.md` pour la procedure complete
- Version coherente : `package.json`, `VERSION`, `extension/manifest.json`
- Bundle release = `RELEASE=1`, pas de fallback localhost
- ZIP via `scripts/package-extension.sh` + verification `scripts/verify-extension-zip.py`

## Workflow deploy DB Render
Quand on pousse sur `render-prod` avec des changements DB :

1. Mettre a jour la DB locale (seeds, migrations)
2. `npm run render:publish-db` (publie la DB sur GitHub Release)
3. Commit + push sur `render-prod`

**DB d'abord, code ensuite.** Si seul le code change, pas besoin de publish-db.

Doc complete : `docs/render-db-workflow.md`

## Architecture
- Backend : Python 3.12 / Flask / SQLAlchemy / Pydantic
- Deploiement : Render (Starter, Frankfurt, Docker)
- Extension : Chrome Web Store (OKazCar)
- DB : SQLite locale (source de verite) → GitHub Release → Render (sync au demarrage)
