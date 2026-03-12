#!/usr/bin/env python3
"""Prépare un snapshot SQLite publiable pour Render.

Le script crée une copie cohérente de la base source via l'API SQLite backup,
valide l'intégrité du snapshot, calcule son SHA256 et écrit un manifeste JSON.

Exemple :
    python scripts/prepare_render_snapshot.py --version 2026-03-11-canonique-v1
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_SOURCE_DB = Path("data/okazcar.db")
DEFAULT_OUTPUT_DIR = Path("releases/render-db")
REQUIRED_TABLES = ("vehicles", "vehicle_specs")


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _log(message: str) -> None:
    print(f"[prepare-render-snapshot] {message}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prépare un snapshot SQLite publiable pour Render")
    parser.add_argument(
        "--source",
        default=str(DEFAULT_SOURCE_DB),
        help="Chemin de la base source SQLite",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Répertoire de sortie pour le snapshot et le manifeste",
    )
    parser.add_argument(
        "--version",
        required=True,
        help="Version logique du snapshot (ex: 2026-03-11-canonique-v1)",
    )
    return parser.parse_args()


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip())
    slug = re.sub(r"-+", "-", slug).strip("-._")
    if not slug:
        raise ValueError("Version invalide après normalisation")
    return slug


def _validate_snapshot(db_path: Path) -> dict:
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        integrity = cur.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise RuntimeError(f"integrity_check non valide: {integrity}")

        tables = {
            row[0]
            for row in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        missing = [table for table in REQUIRED_TABLES if table not in tables]
        if missing:
            raise RuntimeError(f"tables manquantes dans le snapshot: {', '.join(missing)}")

        vehicle_count = cur.execute("SELECT COUNT(*) FROM vehicles").fetchone()[0]
        spec_count = cur.execute("SELECT COUNT(*) FROM vehicle_specs").fetchone()[0]
        if vehicle_count <= 0 or spec_count <= 0:
            raise RuntimeError("snapshot invalide: vehicles ou vehicle_specs vide(s)")

        journal_mode = cur.execute("PRAGMA journal_mode").fetchone()[0]
        return {
            "integrity_check": integrity,
            "vehicle_count": vehicle_count,
            "vehicle_spec_count": spec_count,
            "journal_mode": journal_mode,
        }
    finally:
        conn.close()


def _sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _build_snapshot(source_db: Path, output_db: Path) -> None:
    output_db.parent.mkdir(parents=True, exist_ok=True)
    temp_db = output_db.with_suffix(output_db.suffix + ".tmp")
    temp_db.unlink(missing_ok=True)

    source_uri = f"file:{source_db.resolve()}?mode=ro"
    source_conn = sqlite3.connect(source_uri, uri=True)
    dest_conn = sqlite3.connect(str(temp_db))
    try:
        source_conn.execute("PRAGMA busy_timeout = 5000")
        source_conn.backup(dest_conn)
        dest_conn.commit()
    finally:
        dest_conn.close()
        source_conn.close()

    temp_db.replace(output_db)


def prepare_snapshot(source_db: Path, output_dir: Path, version: str) -> dict:
    version = _slugify(version)

    if not source_db.exists():
        raise FileNotFoundError(f"Base source introuvable: {source_db}")

    output_db = output_dir / f"okazcar-{version}.db"
    manifest_path = output_dir / f"okazcar-{version}.json"

    _log(f"Création du snapshot depuis {source_db}")
    _build_snapshot(source_db, output_db)
    validation = _validate_snapshot(output_db)
    sha256 = _sha256(output_db)
    size_bytes = output_db.stat().st_size

    manifest = {
        "version": version,
        "generated_at": _utc_now(),
        "source_db": str(source_db.resolve()),
        "snapshot_db": str(output_db.resolve()),
        "snapshot_filename": output_db.name,
        "manifest_path": str(manifest_path.resolve()),
        "manifest_filename": manifest_path.name,
        "sha256": sha256,
        "size_bytes": size_bytes,
        **validation,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    _log(f"Snapshot prêt: {output_db}")
    _log(f"Manifeste écrit: {manifest_path}")
    _log(f"SHA256: {sha256}")
    _log(f"Taille: {size_bytes} octets")
    return manifest


def main() -> int:
    args = _parse_args()
    source_db = Path(args.source)
    output_dir = Path(args.output_dir)
    manifest = prepare_snapshot(source_db=source_db, output_dir=output_dir, version=args.version)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
