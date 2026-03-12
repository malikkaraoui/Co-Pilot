#!/usr/bin/env python3
"""Synchronise une base SQLite canonique vers le disque persistant Render.

Usage typique au demarrage Render via variables d'environnement :

    RENDER_DB_SYNC_URL=https://.../okazcar.db
    RENDER_DB_SYNC_METADATA_URL=https://.../okazcar.json
    RENDER_DB_SYNC_VERSION=2026-03-11-canonique
    RENDER_DB_SYNC_SHA256=<sha256 optionnel>

Le script :
- peut lire un manifeste JSON distant pour recuperer version / SHA / URL ;
- telecharge la base vers un fichier temporaire ;
- verifie optionnellement le SHA256 ;
- valide l'integrite SQLite ;
- sauvegarde la base existante ;
- remplace atomiquement la base cible ;
- memorise la version deja appliquee pour eviter les reimports inutiles.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

DEFAULT_TARGET_DB = Path("/app/data/okazcar.db")
DEFAULT_STATE_FILE = Path("/app/data/.render-db-sync.json")
DEFAULT_BACKUP_DIR = Path("/app/data/backups")
REQUIRED_TABLES = ("vehicles", "vehicle_specs")


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _log(message: str) -> None:
    print(f"[render-db-sync] {message}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Synchronise une base SQLite vers le disk Render")
    parser.add_argument("--source-url", default=os.environ.get("RENDER_DB_SYNC_URL", ""))
    parser.add_argument(
        "--metadata-url",
        default=os.environ.get("RENDER_DB_SYNC_METADATA_URL", ""),
    )
    parser.add_argument("--sync-version", default=os.environ.get("RENDER_DB_SYNC_VERSION", ""))
    parser.add_argument("--sha256", default=os.environ.get("RENDER_DB_SYNC_SHA256", ""))
    parser.add_argument(
        "--target-db",
        default=os.environ.get("RENDER_DB_SYNC_TARGET_DB", str(DEFAULT_TARGET_DB)),
    )
    parser.add_argument(
        "--state-file",
        default=os.environ.get("RENDER_DB_SYNC_STATE_FILE", str(DEFAULT_STATE_FILE)),
    )
    parser.add_argument(
        "--backup-dir",
        default=os.environ.get("RENDER_DB_SYNC_BACKUP_DIR", str(DEFAULT_BACKUP_DIR)),
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=int(os.environ.get("RENDER_DB_SYNC_TIMEOUT", "180")),
    )
    return parser.parse_args()


def _load_state(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_state(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _download_to_temp(source_url: str, timeout: int, target_dir: Path) -> tuple[Path, str, int]:
    target_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix="render-db-sync-", suffix=".db", dir=target_dir)
    os.close(fd)
    tmp_path = Path(tmp_name)

    sha = hashlib.sha256()
    size = 0
    try:
        with urlopen(source_url, timeout=timeout) as response, tmp_path.open("wb") as output:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
                sha.update(chunk)
                size += len(chunk)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise

    return tmp_path, sha.hexdigest(), size


def _download_json(url: str, timeout: int) -> dict:
    """Telecharge un JSON distant avec cache-busting pour eviter le CDN GitHub."""
    separator = "&" if "?" in url else "?"
    bust_url = f"{url}{separator}_cb={int(time.time())}"
    request = Request(
        bust_url,
        headers={
            "Accept": "application/json",
            "Cache-Control": "no-cache",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        payload = response.read().decode("utf-8")
    return json.loads(payload)


def _resolve_sync_inputs(
    *,
    source_url: str,
    metadata_url: str,
    sync_version: str,
    expected_sha: str,
    timeout: int,
) -> tuple[str, str, str, dict]:
    remote_metadata: dict = {}
    if metadata_url:
        _log(f"Lecture du manifeste distant: {metadata_url}")
        remote_metadata = _download_json(metadata_url, timeout)
        source_url = (
            source_url
            or str(
                remote_metadata.get("download_url")
                or remote_metadata.get("browser_download_url")
                or remote_metadata.get("source_url")
                or ""
            ).strip()
        )
        sync_version = sync_version or str(remote_metadata.get("version") or "").strip()
        expected_sha = expected_sha or str(remote_metadata.get("sha256") or "").strip().lower()

    return source_url.strip(), sync_version.strip(), expected_sha.strip().lower(), remote_metadata


def _validate_sqlite(db_path: Path) -> None:
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
            raise RuntimeError("snapshot invalide: vehicles ou vehicle_specs vide(s) apres import")
    finally:
        conn.close()


def _backup_existing_db(target_db: Path, backup_dir: Path, sync_version: str) -> Path | None:
    if not target_db.exists():
        return None

    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup_path = backup_dir / f"{target_db.stem}.backup-{timestamp}-{sync_version}.db"
    shutil.copy2(target_db, backup_path)
    return backup_path


def main() -> int:
    args = _parse_args()
    source_url, sync_version, expected_sha, remote_metadata = _resolve_sync_inputs(
        source_url=args.source_url.strip(),
        metadata_url=args.metadata_url.strip(),
        sync_version=args.sync_version.strip(),
        expected_sha=args.sha256.strip().lower(),
        timeout=args.timeout,
    )
    target_db = Path(args.target_db)
    state_file = Path(args.state_file)
    backup_dir = Path(args.backup_dir)

    if not source_url and not args.metadata_url.strip():
        _log("Aucune synchro demandee (RENDER_DB_SYNC_URL / RENDER_DB_SYNC_METADATA_URL absents).")
        return 0

    if not source_url:
        _log("La synchro est configuree mais aucune URL de base n'a pu etre resolue.")
        return 1

    if not sync_version:
        _log("La synchro est configuree mais aucune version n'a pu etre resolue.")
        return 1

    state = _load_state(state_file)
    already_applied = state.get("version") == sync_version and target_db.exists()
    if already_applied:
        _log(f"Version {sync_version} deja appliquee, aucune action.")
        return 0

    _log(f"Telechargement du snapshot {sync_version} depuis {source_url}")
    temp_db, actual_sha, size = _download_to_temp(source_url, args.timeout, target_db.parent)
    _log(f"Snapshot telecharge ({size} octets)")

    try:
        if expected_sha and actual_sha != expected_sha and args.metadata_url.strip():
            _log("SHA256 mismatch (CDN cache probable). Re-fetch du manifeste dans 5s...")
            time.sleep(5)
            fresh_metadata = _download_json(args.metadata_url.strip(), args.timeout)
            fresh_sha = str(fresh_metadata.get("sha256") or "").strip().lower()
            if fresh_sha and fresh_sha == actual_sha:
                _log(f"Manifeste rafraichi: SHA256 correspond maintenant ({actual_sha[:16]}...)")
                expected_sha = fresh_sha
                sync_version = str(fresh_metadata.get("version") or sync_version).strip()
                remote_metadata = fresh_metadata
            else:
                raise RuntimeError(
                    f"SHA256 invalide meme apres re-fetch: attendu {fresh_sha or expected_sha}, obtenu {actual_sha}"
                )
        elif expected_sha and actual_sha != expected_sha:
            raise RuntimeError(f"SHA256 invalide: attendu {expected_sha}, obtenu {actual_sha}")

        _validate_sqlite(temp_db)
        _log("Snapshot SQLite valide (integrity_check + tables critiques)")

        backup_path = _backup_existing_db(target_db, backup_dir, sync_version)
        if backup_path is not None:
            _log(f"Backup cree: {backup_path}")
        else:
            _log("Aucune base existante a sauvegarder")

        target_db.parent.mkdir(parents=True, exist_ok=True)
        os.replace(temp_db, target_db)
        _log(f"Base canonique remplacee: {target_db}")

        _write_state(
            state_file,
            {
                "version": sync_version,
                "source_url": source_url,
                "metadata_url": args.metadata_url.strip(),
                "sha256": actual_sha,
                "size_bytes": size,
                "applied_at": _utc_now(),
                "target_db": str(target_db),
                "remote_metadata": remote_metadata,
            },
        )
        _log(f"Etat memorise dans {state_file}")
        return 0
    except Exception as exc:
        temp_db.unlink(missing_ok=True)
        _log(f"ECHEC: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
