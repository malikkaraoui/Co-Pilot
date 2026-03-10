#!/bin/bash
set -e

echo "=== Packaging extension for Chrome Web Store ==="

# Backward-compat: accept the old env var name
if [ -z "${API_URL:-}" ] && [ -n "${RENDER_API_URL:-}" ]; then
  export API_URL="$RENDER_API_URL"
fi

# Check that production API URL is set
if [ -z "${API_URL:-}" ]; then
  echo "ERROR: API_URL not set. Example:"
  echo "  export API_URL=https://your-app.onrender.com/api/analyze"
  echo "(You can also pass a base origin, it will be normalized to /api/analyze)"
  exit 1
fi

# Build with production URL (release build refuses localhost fallback)
echo "Building RELEASE bundle with API_URL=$API_URL"
RELEASE=1 API_URL="$API_URL" node extension/build.js

# Clean previous zip
rm -f extension.zip

# Create zip with only required files
echo "Creating extension.zip..."
cd extension
zip -r ../extension.zip \
  manifest.json \
  background.js \
  content.css \
  dist/content.bundle.js \
  popup/ \
  icons/icon16.png \
  icons/icon48.png \
  icons/icon128.png \
  icons/icon16-light.png \
  icons/icon48-light.png \
  icons/icon128-light.png \
  carvertical_logo.png
cd ..

echo ""
echo "=== Done: extension.zip ($(du -h extension.zip | cut -f1)) ==="
echo "Upload this file to: https://chrome.google.com/webstore/devconsole"
