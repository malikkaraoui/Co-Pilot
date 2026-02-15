# Correction bug GitHub CI (2026-02-15)

## Contexte

Les pushes échouaient sur GitHub Actions dans le job `lint-and-test`, étape **Run extension tests**.

Erreur observée :

- `ERR_REQUIRE_ESM`
- chargement de `vitest.config.js` avec un conflit ESM/CJS (`require()` d'un module ESM)

> Note de suivi : **Claude Code n'avait pas réussi à corriger ce bug CI** de manière effective.

## Cause racine

Le projet utilisait une config Vitest écrite en syntaxe ESM (`import/export`) dans un fichier
`vitest.config.js`, alors que le chargement côté CI se faisait dans un contexte CommonJS.

## Correctif appliqué

1. Renommage de la config Vitest en `vitest.config.mjs`
2. Mise à jour du script npm :
   - `test:extension` → `vitest run --config vitest.config.mjs`
3. Suppression de `vitest.config.js` (ancienne config ambiguë)
4. Alignement d'un test extension sur la sortie réelle de `extractVehicleFromNextData` (`fuel: ''`)
5. Alignement CI Node.js sur version `20` (workflow)

## Vérification

- Exécution locale: `npm run test:extension`
- Résultat: **55/55 tests passés**
- Push effectué sur `main`, workflow CI relançable côté GitHub

## Impact

- Les pushes ne devraient plus être bloqués par cette erreur ESM/CJS dans la partie tests extension.
- Le pipeline GitHub Actions retrouve un comportement stable sur la phase JS/Vitest.
