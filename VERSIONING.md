# Politique de Versionnement

Ce projet utilise le **Versionnement Sémantique 2.0.0** (SemVer).

## Format : MAJOR.MINOR.PATCH

| Composant | Quand incrémenter |
|-----------|-------------------|
| **MAJOR** | Changements incompatibles avec les versions précédentes |
| **MINOR** | Ajout de fonctionnalités rétrocompatibles |
| **PATCH** | Corrections de bugs rétrocompatibles |

## Sources de vérité

La version est maintenue de manière synchronisée dans :

- `package.json` — source principale
- `VERSION` — fichier plat pour scripts CI/CD

## Commandes

```bash
# Bump patch (0.1.0 → 0.1.1) — corrections de bugs
npm run version:patch

# Bump minor (0.1.0 → 0.2.0) — nouvelles fonctionnalités
npm run version:minor

# Bump major (0.1.0 → 1.0.0) — changements majeurs
npm run version:major

# Créer un tag git après le bump
npm run version:tag

# Release complète (bump + tag en une commande)
npm run release:patch
npm run release:minor
npm run release:major
```

## Workflow de release

1. Terminer le développement sur la branche de feature
2. Mettre à jour `CHANGELOG.md` avec les changements
3. Exécuter `npm run release:{patch|minor|major}`
4. Commiter : `git commit -am "release: vX.Y.Z"`
5. Pousser : `git push && git push --tags`

## Convention de tags git

- Format : `vMAJOR.MINOR.PATCH` (ex: `v0.1.0`)
- Chaque release est accompagnée d'un tag annoté
- Les tags sont poussés vers le dépôt distant

## Convention de commits

| Préfixe | Description | Impact version |
|---------|-------------|---------------|
| `feat:` | Nouvelle fonctionnalité | MINOR |
| `fix:` | Correction de bug | PATCH |
| `breaking:` | Changement incompatible | MAJOR |
| `docs:` | Documentation | Aucun |
| `refactor:` | Refactoring | Aucun |
| `test:` | Tests | Aucun |
| `chore:` | Maintenance | Aucun |
| `release:` | Release | Tag git |
