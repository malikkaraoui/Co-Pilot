const esbuild = require('esbuild');

function normalizeApiUrl(raw) {
  const fallback = 'http://localhost:5001/api/analyze';
  const input = String(raw || '').trim();
  if (!input) return fallback;

  // Must be an absolute URL; otherwise the extension might end up doing relative fetches.
  if (!/^https?:\/\//i.test(input)) {
    throw new Error(`Invalid API_URL (must start with http:// or https://): ${input}`);
  }

  const trimmed = input.replace(/\/+$/g, '');
  if (/\/api\/analyze$/i.test(trimmed)) return trimmed;
  if (/\/analyze$/i.test(trimmed)) return trimmed;
  if (/\/api$/i.test(trimmed)) return trimmed + '/analyze';
  return trimmed + '/api/analyze';
}

function isReleaseBuild() {
  return (
    String(process.env.RELEASE || '').trim() === '1' ||
    String(process.env.CHROME_WEB_STORE || '').trim() === '1' ||
    String(process.env.NODE_ENV || '').trim().toLowerCase() === 'production'
  );
}

const rawApiUrl = process.env.API_URL;
if (isReleaseBuild() && !String(rawApiUrl || '').trim()) {
  throw new Error(
    'Missing API_URL for release build. Refusing to build a bundle that might point to localhost. ' +
      'Set API_URL to your production backend (e.g. https://<service>.onrender.com or /api/analyze).'
  );
}

const apiUrl = normalizeApiUrl(rawApiUrl);

esbuild.buildSync({
  entryPoints: ['extension/content.js'],
  bundle: true,
  outfile: 'extension/dist/content.bundle.js',
  format: 'iife',
  target: ['chrome120'],
  minify: false,
  sourcemap: false,
  define: {
    '__API_URL__': JSON.stringify(apiUrl),
  },
});

console.log(`Built extension/dist/content.bundle.js (API_URL=${apiUrl})`);
