const esbuild = require('esbuild');

const apiUrl = process.env.API_URL || 'http://localhost:5001/api/analyze';

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
