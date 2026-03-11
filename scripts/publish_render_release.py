#!/usr/bin/env python3
"""Publie un snapshot SQLite local vers une GitHub Release stable pour Render.

Le script :
- genere un snapshot coherent depuis `data/okazcar.db` ;
- cree ou met a jour une GitHub Release stable (par defaut `render-db-prod`) ;
- remplace les assets stables `okazcar-render-prod.db` et `okazcar-render-prod.json` ;
- ecrit dans le manifeste distant l'URL publique stable du snapshot.

Exemple :
    python3 scripts/publish_render_release.py --version 2026-03-11-canonique-v2-engine-reliability
"""

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from prepare_render_snapshot import DEFAULT_OUTPUT_DIR, DEFAULT_SOURCE_DB, prepare_snapshot

DEFAULT_RELEASE_TAG = "render-db-prod"
DEFAULT_RELEASE_NAME = "Render DB (prod)"
DEFAULT_DB_ASSET_NAME = "okazcar-render-prod.db"
DEFAULT_MANIFEST_ASSET_NAME = "okazcar-render-prod.json"
DEFAULT_TARGET_COMMITISH = "render-prod"
GITHUB_API_VERSION = "2022-11-28"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _log(message: str) -> None:
    print(f"[publish-render-release] {message}")


def _load_dotenv(dotenv_path: Path) -> None:
    if not dotenv_path.exists():
        return

    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key.startswith("export "):
            key = key[len("export ") :].strip()
        value = value.strip().strip('"').strip("'")
        if not os.environ.get(key):
            os.environ[key] = value


def _default_version() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d-render-prod-%H%M%S")


def _guess_repo_from_package_json() -> tuple[str, str] | tuple[None, None]:
    package_json = Path("package.json")
    if not package_json.exists():
        return None, None

    try:
        payload = json.loads(package_json.read_text(encoding="utf-8"))
    except Exception:
        return None, None

    repo_url = str(payload.get("repository", {}).get("url") or "")
    match = re.search(r"github\.com[:/](?P<owner>[^/]+)/(?P<repo>[^/.]+)(?:\.git)?$", repo_url)
    if not match:
        return None, None
    return match.group("owner"), match.group("repo")


def _parse_args() -> argparse.Namespace:
    guessed_owner, guessed_repo = _guess_repo_from_package_json()

    parser = argparse.ArgumentParser(
        description="Publie un snapshot SQLite local vers GitHub Release"
    )
    parser.add_argument(
        "--source", default=str(DEFAULT_SOURCE_DB), help="Chemin de la base SQLite source"
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Repertoire ou generer les snapshots locaux",
    )
    parser.add_argument(
        "--version",
        default="auto",
        help="Version logique du snapshot (ou 'auto')",
    )
    parser.add_argument(
        "--owner",
        default=os.environ.get("RENDER_REPO_OWNER") or guessed_owner,
        help="Owner GitHub du repository",
    )
    parser.add_argument(
        "--repo",
        default=os.environ.get("RENDER_REPO_NAME") or guessed_repo,
        help="Nom GitHub du repository",
    )
    parser.add_argument(
        "--release-tag",
        default=os.environ.get("RENDER_DB_RELEASE_TAG", DEFAULT_RELEASE_TAG),
        help="Tag de release GitHub stable",
    )
    parser.add_argument(
        "--release-name",
        default=os.environ.get("RENDER_DB_RELEASE_NAME", DEFAULT_RELEASE_NAME),
        help="Nom lisible de la release GitHub",
    )
    parser.add_argument(
        "--db-asset-name",
        default=os.environ.get("RENDER_DB_ASSET_NAME", DEFAULT_DB_ASSET_NAME),
        help="Nom stable de l'asset .db dans la release",
    )
    parser.add_argument(
        "--manifest-asset-name",
        default=os.environ.get("RENDER_DB_MANIFEST_ASSET_NAME", DEFAULT_MANIFEST_ASSET_NAME),
        help="Nom stable de l'asset .json dans la release",
    )
    parser.add_argument(
        "--target-commitish",
        default=os.environ.get("RENDER_DEPLOY_BRANCH", DEFAULT_TARGET_COMMITISH),
        help="Branche cible associee au tag de release",
    )
    parser.add_argument(
        "--dotenv-path",
        default=".env",
        help="Fichier .env optionnel a charger avant lecture des variables",
    )
    return parser.parse_args()


def _github_request(
    *,
    method: str,
    url: str,
    token: str,
    payload: dict | None = None,
    data: bytes | None = None,
    content_type: str = "application/vnd.github+json",
    expected_statuses: tuple[int, ...] = (200,),
) -> dict | list | None:
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
    }
    body: bytes | None = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    elif data is not None:
        body = data
        headers["Content-Type"] = content_type

    request = Request(url, data=body, headers=headers, method=method)
    try:
        with urlopen(request) as response:
            status = response.getcode()
            raw = response.read()
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API {method} {url} -> {exc.code}: {detail}") from exc

    if status not in expected_statuses:
        raise RuntimeError(f"GitHub API {method} {url} -> statut inattendu {status}")

    if not raw:
        return None

    if content_type == "application/octet-stream":
        return None

    return json.loads(raw.decode("utf-8"))


def _get_release_by_tag(owner: str, repo: str, tag: str, token: str) -> dict | None:
    url = f"https://api.github.com/repos/{owner}/{repo}/releases/tags/{tag}"
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": GITHUB_API_VERSION,
        },
        method="GET",
    )
    try:
        with urlopen(request) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code == 404:
            return None
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API GET release tag {tag} -> {exc.code}: {detail}") from exc


def _ensure_release(
    *,
    owner: str,
    repo: str,
    tag: str,
    name: str,
    target_commitish: str,
    token: str,
) -> dict:
    existing = _get_release_by_tag(owner, repo, tag, token)
    body = (
        "Release stable utilisee par Render pour telecharger le snapshot SQLite canonique.\n\n"
        f"Assets attendus : `{DEFAULT_DB_ASSET_NAME}` et `{DEFAULT_MANIFEST_ASSET_NAME}`."
    )
    if existing is not None:
        release_id = existing["id"]
        _log(f"Release existante trouvee: {tag} (id={release_id})")
        return _github_request(
            method="PATCH",
            url=f"https://api.github.com/repos/{owner}/{repo}/releases/{release_id}",
            token=token,
            payload={
                "tag_name": tag,
                "target_commitish": target_commitish,
                "name": name,
                "body": body,
                "draft": False,
                "prerelease": True,
                "make_latest": "false",
            },
        )

    _log(f"Creation de la release GitHub: {tag}")
    return _github_request(
        method="POST",
        url=f"https://api.github.com/repos/{owner}/{repo}/releases",
        token=token,
        payload={
            "tag_name": tag,
            "target_commitish": target_commitish,
            "name": name,
            "body": body,
            "draft": False,
            "prerelease": True,
            "make_latest": "false",
        },
        expected_statuses=(201,),
    )


def _delete_existing_asset(
    owner: str, repo: str, release: dict, asset_name: str, token: str
) -> None:
    for asset in release.get("assets", []):
        if asset.get("name") != asset_name:
            continue
        asset_id = asset["id"]
        _log(f"Suppression de l'ancien asset {asset_name} (id={asset_id})")
        _github_request(
            method="DELETE",
            url=f"https://api.github.com/repos/{owner}/{repo}/releases/assets/{asset_id}",
            token=token,
            expected_statuses=(204,),
        )
        return


def _upload_asset(
    upload_url: str, asset_name: str, content: bytes, token: str, content_type: str
) -> dict:
    clean_upload_url = upload_url.split("{", 1)[0]
    url = f"{clean_upload_url}?{urlencode({'name': asset_name})}"
    return _github_request(
        method="POST",
        url=url,
        token=token,
        data=content,
        content_type=content_type,
        expected_statuses=(201,),
    )


def main() -> int:
    args = _parse_args()
    _load_dotenv(Path(args.dotenv_path))

    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GH_TOKEN ou GITHUB_TOKEN est requis pour publier la GitHub Release")

    if not args.owner or not args.repo:
        raise RuntimeError("Impossible de determiner owner/repo GitHub automatiquement")

    version = _default_version() if args.version == "auto" else args.version
    source_db = Path(args.source)
    output_dir = Path(args.output_dir)

    manifest = prepare_snapshot(source_db=source_db, output_dir=output_dir, version=version)
    release = _ensure_release(
        owner=args.owner,
        repo=args.repo,
        tag=args.release_tag,
        name=args.release_name,
        target_commitish=args.target_commitish,
        token=token,
    )

    db_path = Path(manifest["snapshot_db"])
    db_download_url = (
        f"https://github.com/{args.owner}/{args.repo}/releases/download/"
        f"{args.release_tag}/{args.db_asset_name}"
    )
    metadata_download_url = (
        f"https://github.com/{args.owner}/{args.repo}/releases/download/"
        f"{args.release_tag}/{args.manifest_asset_name}"
    )

    published_manifest = {
        **manifest,
        "published_at": _utc_now(),
        "release_tag": args.release_tag,
        "release_name": args.release_name,
        "download_url": db_download_url,
        "metadata_url": metadata_download_url,
        "repository": f"{args.owner}/{args.repo}",
    }
    published_manifest_bytes = json.dumps(
        published_manifest,
        ensure_ascii=False,
        indent=2,
    ).encode("utf-8")

    _delete_existing_asset(args.owner, args.repo, release, args.db_asset_name, token)
    _delete_existing_asset(args.owner, args.repo, release, args.manifest_asset_name, token)

    _log(f"Upload de l'asset DB stable: {args.db_asset_name}")
    db_asset = _upload_asset(
        release["upload_url"],
        args.db_asset_name,
        db_path.read_bytes(),
        token,
        "application/octet-stream",
    )
    _log(f"Upload de l'asset manifeste stable: {args.manifest_asset_name}")
    manifest_asset = _upload_asset(
        release["upload_url"],
        args.manifest_asset_name,
        published_manifest_bytes,
        token,
        "application/json",
    )

    summary = {
        "version": published_manifest["version"],
        "release_tag": args.release_tag,
        "repository": published_manifest["repository"],
        "db_asset_name": db_asset["name"],
        "db_download_url": db_asset["browser_download_url"],
        "manifest_asset_name": manifest_asset["name"],
        "manifest_download_url": manifest_asset["browser_download_url"],
        "sha256": published_manifest["sha256"],
        "size_bytes": published_manifest["size_bytes"],
        "target_commitish": args.target_commitish,
    }
    _log("Publication GitHub Release terminee")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
