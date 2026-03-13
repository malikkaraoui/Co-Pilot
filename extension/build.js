/**
 * Script de build esbuild pour le content script de l'extension.
 *
 * Bundle content.js + tous ses imports en un seul fichier IIFE
 * (dist/content.bundle.js) que Chrome peut injecter.
 *
 * L'URL du backend est injectee a la compilation via __API_URL__.
 * En dev, on fallback sur localhost. En release, on oblige a
 * specifier API_URL pour eviter de shipper un bundle qui pointe
 * vers localhost par erreur.
 *
 * Usage :
 *   node extension/build.js                    # dev (localhost)
 *   API_URL=https://... RELEASE=1 node extension/build.js  # prod
 */

const esbuild = require('esbuild');

/**
 * Normalise l'URL du backend pour s'assurer qu'on pointe vers /api/analyze.
 * Accepte une URL partielle et complete le chemin manquant.
 *
 * @param {string} raw - URL brute depuis l'env var API_URL
 * @returns {string} URL normalisee
 * @throws {Error} Si l'URL n'est pas absolue (doit commencer par http(s)://)
 */
function normalizeApiUrl(raw) {
  const fallback = 'http://localhost:5001/api/analyze';
  const input = String(raw || '').trim();
  if (!input) return fallback;

  // Doit etre une URL absolue, sinon le fetch de l'extension va faire n'importe quoi
  if (!/^https?:\/\//i.test(input)) {
    throw new Error(`Invalid API_URL (must start with http:// or https://): ${input}`);
  }

  const trimmed = input.replace(/\/+$/g, '');
  if (/\/api\/analyze$/i.test(trimmed)) return trimmed;
  if (/\/analyze$/i.test(trimmed)) return trimmed;
  if (/\/api$/i.test(trimmed)) return trimmed + '/analyze';
  return trimmed + '/api/analyze';
}

/**
 * Detecte si on est en build de release (Chrome Web Store / production).
 * En release, on refuse de builder sans API_URL explicite.
 *
 * @returns {boolean}
 */
function isReleaseBuild() {
  return (
    String(process.env.RELEASE || '').trim() === '1' ||
    String(process.env.CHROME_WEB_STORE || '').trim() === '1' ||
    String(process.env.NODE_ENV || '').trim().toLowerCase() === 'production'
  );
}

// Securite : en release, pas d'API_URL = pas de build.
// On prefere casser le build que shipper un bundle localhost.
const rawApiUrl = process.env.API_URL;
if (isReleaseBuild() && !String(rawApiUrl || '').trim()) {
  throw new Error(
    'Missing API_URL for release build. Refusing to build a bundle that might point to localhost. ' +
      'Set API_URL to your production backend (e.g. https://<service>.onrender.com or /api/analyze).'
  );
}

const apiUrl = normalizeApiUrl(rawApiUrl);

// Build synchrone — rapide (< 100ms), pas besoin d'async
esbuild.buildSync({
  entryPoints: ['extension/content.js'],
  bundle: true,
  outfile: 'extension/dist/content.bundle.js',
  format: 'iife',
  target: ['chrome120'],
  minify: false,
  sourcemap: false,
  define: {
    // Injecte l'URL du backend comme constante globale dans le bundle
    '__API_URL__': JSON.stringify(apiUrl),
  },
});

console.log(`Built extension/dist/content.bundle.js (API_URL=${apiUrl})`);
