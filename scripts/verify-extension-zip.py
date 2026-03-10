#!/usr/bin/env python3
"""Verify a Chrome Web Store extension ZIP before submission.

This is a lightweight, deterministic preflight tool meant to prevent
shipping a broken bundle (e.g. wrong API URL injected).

Usage:
  .venv/bin/python scripts/verify-extension-zip.py releases/okazcar-v1.1.0.zip

Checks:
- ZIP contains manifest.json and dist/content.bundle.js
- manifest version matches package.json version
- bundle contains an injected https?://.../api/analyze URL (release branch)

Note: The bundle may still contain the localhost fallback string; we only
require that a production URL is present and normalized.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys
import zipfile

API_URL_PATTERN = re.compile(r'var\s+API_URL\s*=\s*true\s*\?\s*"(https?://[^"]+/api/analyze)"')


def die(msg: str, code: int = 1) -> None:
    print(f"ERROR: {msg}")
    raise SystemExit(code)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("Usage: python scripts/verify-extension-zip.py <path/to/zip>")
        return 2

    zip_path = pathlib.Path(argv[1])
    if not zip_path.exists():
        die(f"ZIP not found: {zip_path}")

    root = pathlib.Path(__file__).resolve().parents[1]
    pkg_path = root / "package.json"
    if not pkg_path.exists():
        die(f"package.json not found at: {pkg_path}")

    pkg = json.loads(pkg_path.read_text(encoding="utf-8"))
    expected_version = str(pkg.get("version") or "").strip()
    if not expected_version:
        die("package.json has no version")

    with zipfile.ZipFile(zip_path) as z:
        names = set(z.namelist())

        if "manifest.json" not in names:
            die("ZIP missing manifest.json")
        if "dist/content.bundle.js" not in names:
            die("ZIP missing dist/content.bundle.js")

        manifest = json.loads(z.read("manifest.json"))
        manifest_version = str(manifest.get("version") or "").strip()
        if manifest_version != expected_version:
            die(
                f"Version mismatch: manifest.json={manifest_version!r} vs package.json={expected_version!r}"
            )

        bundle = z.read("dist/content.bundle.js").decode("utf-8", errors="ignore")
        m = API_URL_PATTERN.search(bundle)
        if not m:
            die(
                "Could not find an injected production API_URL in bundle. "
                'Expected pattern like var API_URL = true ? "https://.../api/analyze"'
            )
        api_url = m.group(1)

    print("OK: ZIP looks ready for submission")
    print(f"- version: {expected_version}")
    print(f"- injected API_URL: {api_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
