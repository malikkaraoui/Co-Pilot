#!/bin/bash
set -e

echo "=== Packaging extension for Chrome Web Store ==="

# Check that production API URL is set
if [ -z "$RENDER_API_URL" ]; then
  echo "ERROR: RENDER_API_URL not set. Example:"
  echo "  export RENDER_API_URL=https://your-app.onrender.com/api/analyze"
  exit 1
fi

# Build with production URL
echo "Building with API_URL=$RENDER_API_URL"
API_URL="$RENDER_API_URL" node extension/build.js

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
  carvertical_logo.png
cd ..

echo ""
echo "=== Done: extension.zip ($(du -h extension.zip | cut -f1)) ==="
echo "Upload this file to: https://chrome.google.com/webstore/devconsole"
