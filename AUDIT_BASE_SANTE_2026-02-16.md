# Audit base technique — 2026-02-16

## Résumé exécutif

État global: **bon** (tests et lint verts), mais la base n’est pas encore "super saine" pour
accélérer les prochaines features sans risque.

- ✅ Lint Python: OK (`ruff check .`)
- ✅ Tests Python: OK (**269 passed**)
- ✅ Tests extension: OK (**55 passed**)
- ✅ Vulnérabilités npm: 0 (niveau moderate+)
- ⚠️ Dette structurelle identifiée sur la reproductibilité et l’hygiène CI

## Vérifications réalisées

- Lecture des configs: `.github/workflows/ci.yml`, `.pre-commit-config.yaml`, `.gitignore`,
  `requirements*.txt`, `package.json`, `Dockerfile`, `docker-compose.yml`
- Exécution des checks:
  - `.venv/bin/python -m ruff check .`
  - `.venv/bin/python -m pytest -v --tb=short`
  - `npm run test:extension`
  - `.venv/bin/python -m pip check`
  - `npm audit --audit-level=moderate`

## Constat détaillé (fond)

### 1) Incohérence docs vs réalité tests (risque de flakiness)

Dans `tests/test_api/test_scenarios_e2e.py`, le commentaire indique "Zero appel reseau", mais les
logs montrent des appels HTTP réels à l’API SIRET (`recherche-entreprises.api.gouv.fr`) via
`L7SiretFilter`.

**Impact:**

- Instabilité potentielle CI (timeout, rate-limit, panne externe)
- Durée de tests variable
- Résultats non déterministes

### 2) Hygiène Git / artefacts

- Un rapport généré `reports/test_report.html` est versionné.
- Un dossier `docs/` est ignoré par `.gitignore`, ce qui bloque l’ajout de nouvelles docs utiles au
  projet.

**Impact:**

- Historique Git bruité et volumineux
- Documentation opérationnelle difficile à maintenir proprement

### 3) Reproductibilité CI perfectible

`ci.yml` utilise `npm install` au lieu de `npm ci`.

**Impact:**

- Installations moins déterministes
- Risque de dérive dépendances

### 4) Process local outillage

Le hook pre-commit pytest utilise un chemin hardcodé `.venv/bin/python`.

**Impact:**

- Friction dev sur machine/environnement non standard
- Échecs locaux inutiles pour nouveaux contributeurs

### 5) Variables d’environnement

Le projet requiert `SECRET_KEY`, `ADMIN_PASSWORD_HASH`, etc. Un squelette `.env` local a été généré
(ignoré par git) pour assainir l’exécution locale.

## Retour ciblé pour Claude Code

Cause probable des difficultés précédentes sur le bug GitHub:

1. **Manque d’isolation stricte du scope** (correctif CI mélangé avec autres changements).
2. **Validation incomplète orientée pipeline** (focus local sans verrouiller le chargement ESM/CJS
   exact du runner CI).
3. **Staging trop large / commit non chirurgical** (inclut artefacts et fichiers annexes).
4. **Absence de garde-fous “repo hygiene”** (artefacts générés committés).

### Recommandations opérables pour Claude Code

- Toujours faire un commit **ciblé** par bug (staging explicite fichier par fichier).
- Exiger une boucle de validation stricte: lint + tests Python + tests extension + check workflow
  impact.
- Refuser de committer les artefacts générés (reports, outputs temporaires).
- Pour la CI JS: privilégier `npm ci` + lockfile comme source de vérité.
- Pour les tests E2E backend: **mocker systématiquement** les appels externes.

## Plan d’assainissement priorisé

### P0 (immédiat, avant nouvelles features)

1. Rendre les tests E2E **100% offline** (mock de `L7SiretFilter._call_api` ou injection d’un client
   mocké).
2. Passer CI de `npm install` à `npm ci`.
3. Décider la politique sur `reports/test_report.html` (idéal: ne plus versionner les artefacts
   générés).
4. Retirer `docs/` de `.gitignore` ou clarifier une stratégie doc versionnée.

### P1 (court terme)

1. Ajouter cache CI pip/npm pour accélérer sans sacrifier la stabilité.
2. Harmoniser la version Python entre docs, local et CI (ex: 3.12 partout ou matrice 3.12/3.13).
3. Adapter hook pre-commit pour éviter hardcode `.venv/bin/python` (utiliser `language: python` ou
   wrapper robuste).

### P2 (stabilisation continue)

1. Ajouter une cible `make verify` (ou script) unique: lint + tests py + tests extension.
2. Ajouter des tests de non-régression CI pour configuration Vitest (ESM/CJS).
3. Nettoyer et standardiser la stratégie de documentation technique (fichiers
   audit/changelog/versioning).

## Décision recommandée avant reprise features

La base est **fonctionnelle**, mais pour la rendre "super saine", il faut au minimum exécuter
**P0**. Sans P0, le risque principal reste la non-déterminisme (surtout tests dépendants réseau +
hygiène repo).
