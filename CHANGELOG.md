# Changelog

Toutes les modifications notables de ce projet seront documentées dans ce fichier.

Le format est basé sur [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/),
et ce projet adhère au [Versionnement Sémantique](https://semver.org/lang/fr/).

## [1.0.0] - 2026-03-06

### Changé

- Rebranding complet : Co-Pilot / Vehicore / Okaz → **OKazCar**
- Classes CSS `.copilot-*` → `.okazcar-*` (1000+ occurrences)
- Exception `CoPilotError` → `OKazCarError`
- Base de données `copilot.db` → `okazcar.db`
- Service Render `vehicore-api` → `okazcar-api`
- localStorage `copilot_last_collect` → `okazcar_last_collect`
- DOM ID `__copilot_next_data__` → `__okazcar_next_data__`
- 79 fichiers modifiés, 817 tests Python + 366 tests JS passants

## [0.1.0] - 2026-02-09

### Ajouté

- Initialisation du projet OKazCar
- Installation de la méthode BMAD v6.0.0-Beta.8 (module BMM)
- Configuration des 41 commandes slash pour Claude Code
- 9 agents IA spécialisés (PM, Architecte, Dev, QA, UX, Scrum Master, Tech Writer, Analyste, Solo Dev)
- Workflows de développement en 4 phases (Analyse, Planification, Solutioning, Implémentation)
- Système de versionnement sémantique (SemVer)
- Script de bump de version automatisé
- Suivi des changements via CHANGELOG.md

[1.0.0]: https://github.com/malikkaraoui/OKazCar/compare/v0.1.0...v1.0.0
[Non publié]: https://github.com/malikkaraoui/OKazCar/compare/v1.0.0...HEAD
[0.1.0]: https://github.com/malikkaraoui/OKazCar/releases/tag/v0.1.0
