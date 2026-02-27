const esbuild = require('esbuild');

esbuild.buildSync({
  entryPoints: ['extension/content.js'],
  bundle: true,
  outfile: 'extension/dist/content.bundle.js',
  format: 'iife',
  target: ['chrome120'],
  minify: false,
  sourcemap: false,
});

console.log('Built extension/dist/content.bundle.js');
