#!/usr/bin/env node

/**
 * Synchronise le numéro de version entre package.json et VERSION.
 * Affiche un résumé du bump effectué.
 *
 * Usage : node scripts/update-version.mjs [patch|minor|major]
 */

import { readFileSync, writeFileSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const root = resolve(__dirname, '..');

const pkg = JSON.parse(readFileSync(resolve(root, 'package.json'), 'utf-8'));
const newVersion = pkg.version;

// Mettre à jour le fichier VERSION
writeFileSync(resolve(root, 'VERSION'), newVersion + '\n');

// Lire l'ancienne version depuis le fichier VERSION (avant ce script)
const bumpType = process.argv[2] || 'patch';

console.log(`\n  ╔══════════════════════════════════════╗`);
console.log(`  ║  Version bump: ${bumpType.padEnd(20)}║`);
console.log(`  ║  Nouvelle version: v${newVersion.padEnd(15)}║`);
console.log(`  ╚══════════════════════════════════════╝\n`);
console.log(`  Fichiers mis à jour :`);
console.log(`    - package.json`);
console.log(`    - VERSION`);
console.log(`\n  Prochaines étapes :`);
console.log(`    1. Mettre à jour CHANGELOG.md`);
console.log(`    2. git add -A && git commit -m "release: v${newVersion}"`);
console.log(`    3. npm run version:tag`);
console.log(`    4. git push && git push --tags\n`);
