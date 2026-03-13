#!/usr/bin/env python3
"""Fusion one-shot : copilot.db -> okazcar.db.

Absorbe les donnees terrain de copilot.db dans la base canonique okazcar.db,
puis genere un rapport detaille. Utilise quand on a accumule des donnees
dans l'ancienne base copilot.db et qu'on veut tout consolider.

Le script gere :
- Le remapping des IDs entre les deux bases (vehicle_id, scan_id, video_id)
- La deduplication sur chaque table (pas de doublons)
- Les conflits de donnees (on garde la version la plus recente)
- La generation d'un rapport markdown de synthese

Usage:
    python scripts/merge_copilot_into_okazcar.py --dry-run
    python scripts/merge_copilot_into_okazcar.py
    python scripts/merge_copilot_into_okazcar.py --source-db data/copilot.db --target-db data/okazcar.db
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = PROJECT_ROOT / "data" / "copilot.db"
DEFAULT_TARGET = PROJECT_ROOT / "data" / "okazcar.db"
REPORT_DIR = PROJECT_ROOT / "reports"
TODAY = datetime.now().strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _dict_factory(cursor: sqlite3.Cursor, row: tuple) -> dict:
    """sqlite3 row_factory qui retourne des dicts."""
    return {col[0]: row[i] for i, col in enumerate(cursor.description)}


def _connect(path: Path, *, readonly: bool = False) -> sqlite3.Connection:
    """Ouvre une connexion SQLite avec row_factory dict.

    En ecriture, on active WAL pour eviter les locks pendant la fusion.
    """
    if readonly:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    else:
        conn = sqlite3.connect(str(path))
        conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = _dict_factory
    return conn


def _count(conn: sqlite3.Connection, table: str) -> int:
    return conn.execute(f"SELECT COUNT(*) AS c FROM [{table}]").fetchone()["c"]  # noqa: S608


def _norm(val: str | None) -> str:
    """Normalise une string pour matching case-insensitive."""
    return (val or "").strip().lower()


# ---------------------------------------------------------------------------
# Vehicle ID mapping  (copilot vehicle_id → okazcar vehicle_id)
# ---------------------------------------------------------------------------
def _build_vehicle_map(src: sqlite3.Connection, tgt: sqlite3.Connection) -> dict[int, int | None]:
    """Mappe les vehicle IDs de copilot vers okazcar via brand+model.

    C'est la cle de voute de la fusion : toutes les tables qui referencent
    un vehicle_id doivent passer par ce mapping pour pointer vers le bon
    vehicule dans la base cible.
    """
    src_vehicles = src.execute("SELECT id, brand, model FROM vehicles").fetchall()
    tgt_vehicles = tgt.execute("SELECT id, brand, model FROM vehicles").fetchall()

    # Index target par (brand_lower, model_lower)
    tgt_index: dict[tuple[str, str], int] = {}
    for v in tgt_vehicles:
        key = (_norm(v["brand"]), _norm(v["model"]))
        tgt_index[key] = v["id"]

    mapping: dict[int, int | None] = {}
    for v in src_vehicles:
        key = (_norm(v["brand"]), _norm(v["model"]))
        mapping[v["id"]] = tgt_index.get(key)

    return mapping


# ---------------------------------------------------------------------------
# Import functions per table
# ---------------------------------------------------------------------------


class MergeStats:
    """Compteurs par table pour le rapport de fusion.

    Chaque table a ses propres compteurs : lus, importes, doublons ignores,
    sans mapping vehicule, et conflits detectes.
    """

    def __init__(self) -> None:
        self.tables: dict[str, dict] = {}

    def init_table(self, name: str) -> None:
        self.tables[name] = {
            "read": 0,
            "imported": 0,
            "skipped_dup": 0,
            "skipped_no_mapping": 0,
            "conflicts": [],
        }

    def summary(self) -> str:
        lines = ["# Rapport de fusion copilot.db → okazcar.db", f"_Date_: {TODAY}\n"]
        total_read = total_imported = total_skipped = total_no_map = 0
        for table, s in self.tables.items():
            lines.append(f"## {table}")
            lines.append(f"- Lus : {s['read']}")
            lines.append(f"- Importés : {s['imported']}")
            lines.append(f"- Ignorés (doublon) : {s['skipped_dup']}")
            if s["skipped_no_mapping"]:
                lines.append(f"- Ignorés (pas de véhicule cible) : {s['skipped_no_mapping']}")
            if s["conflicts"]:
                lines.append(f"- Conflits : {len(s['conflicts'])}")
                for c in s["conflicts"][:10]:
                    lines.append(f"  - {c}")
            lines.append("")
            total_read += s["read"]
            total_imported += s["imported"]
            total_skipped += s["skipped_dup"]
            total_no_map += s["skipped_no_mapping"]

        lines.append("## Totaux")
        lines.append(f"- Lus : {total_read}")
        lines.append(f"- Importés : {total_imported}")
        lines.append(f"- Ignorés (doublon) : {total_skipped}")
        lines.append(f"- Ignorés (pas de mapping) : {total_no_map}")
        return "\n".join(lines)


def _merge_scan_logs(
    src: sqlite3.Connection,
    tgt: sqlite3.Connection,
    stats: MergeStats,
    dry_run: bool,
) -> dict[int, int]:
    """Importe scan_logs. Retourne mapping old_id -> new_id.

    Les scan_logs sont la table pivot : filter_results et email_drafts
    referencent un scan_id, donc on doit conserver le mapping old->new
    pour les tables dependantes.
    """
    table = "scan_logs"
    stats.init_table(table)
    scan_map: dict[int, int] = {}

    src_rows = src.execute("SELECT * FROM scan_logs ORDER BY id").fetchall()
    stats.tables[table]["read"] = len(src_rows)

    # Dedup sur le tuple (url, source, make, model, price, created_at)
    # pour eviter d'importer deux fois le meme scan
    existing = set()
    for row in tgt.execute(
        "SELECT url, source, vehicle_make, vehicle_model, price_eur, created_at FROM scan_logs"
    ).fetchall():
        existing.add(
            (
                row["url"],
                row["source"],
                _norm(row["vehicle_make"]),
                _norm(row["vehicle_model"]),
                row["price_eur"],
                row["created_at"],
            )
        )

    cols = [
        "url",
        "raw_data",
        "score",
        "is_partial",
        "vehicle_make",
        "vehicle_model",
        "price_eur",
        "days_online",
        "republished",
        "source",
        "country",
        "created_at",
    ]

    for row in src_rows:
        dedup_key = (
            row["url"],
            row["source"],
            _norm(row["vehicle_make"]),
            _norm(row["vehicle_model"]),
            row["price_eur"],
            row["created_at"],
        )
        if dedup_key in existing:
            stats.tables[table]["skipped_dup"] += 1
            continue

        if not dry_run:
            placeholders = ", ".join("?" for _ in cols)
            col_names = ", ".join(cols)
            values = [row.get(c) for c in cols]
            cursor = tgt.execute(
                f"INSERT INTO scan_logs ({col_names}) VALUES ({placeholders})",
                values,
            )
            scan_map[row["id"]] = cursor.lastrowid
        else:
            # Simulate new ID
            scan_map[row["id"]] = -(row["id"])

        existing.add(dedup_key)
        stats.tables[table]["imported"] += 1

    return scan_map


def _merge_filter_results(
    src: sqlite3.Connection,
    tgt: sqlite3.Connection,
    scan_map: dict[int, int],
    stats: MergeStats,
    dry_run: bool,
) -> None:
    """Importe filter_results avec remap de scan_id.

    Chaque filter_result pointe vers un scan_log via scan_id.
    On utilise scan_map pour relier au bon scan dans la base cible.
    """
    table = "filter_results"
    stats.init_table(table)

    src_rows = src.execute("SELECT * FROM filter_results ORDER BY id").fetchall()
    stats.tables[table]["read"] = len(src_rows)

    # Existing (scan_id, filter_id) pairs in target
    existing = {
        (r["scan_id"], r["filter_id"])
        for r in tgt.execute("SELECT scan_id, filter_id FROM filter_results").fetchall()
    }

    cols = ["scan_id", "filter_id", "status", "score", "message", "details", "created_at"]

    for row in src_rows:
        old_scan_id = row["scan_id"]
        new_scan_id = scan_map.get(old_scan_id)
        if new_scan_id is None:
            stats.tables[table]["skipped_no_mapping"] += 1
            continue

        if (new_scan_id, row["filter_id"]) in existing:
            stats.tables[table]["skipped_dup"] += 1
            continue

        if not dry_run:
            values = [
                new_scan_id,
                row["filter_id"],
                row["status"],
                row["score"],
                row["message"],
                row["details"],
                row["created_at"],
            ]
            placeholders = ", ".join("?" for _ in cols)
            col_names = ", ".join(cols)
            tgt.execute(
                f"INSERT INTO filter_results ({col_names}) VALUES ({placeholders})",
                values,
            )
        existing.add((new_scan_id, row["filter_id"]))
        stats.tables[table]["imported"] += 1


def _merge_market_prices(
    src: sqlite3.Connection,
    tgt: sqlite3.Connection,
    stats: MergeStats,
    dry_run: bool,
) -> None:
    """Importe market_prices avec dedup sur cle UNIQUE.

    En cas de conflit (meme vehicule/annee/region), on garde
    la version la plus recente (collected_at le plus recent).
    """
    table = "market_prices"
    stats.init_table(table)

    src_rows = src.execute("SELECT * FROM market_prices ORDER BY id").fetchall()
    stats.tables[table]["read"] = len(src_rows)

    # Index par cle composite (make, model, year, region, fuel, hp_range, country)
    existing: dict[tuple, dict] = {}
    for row in tgt.execute("SELECT * FROM market_prices").fetchall():
        key = (
            _norm(row["make"]),
            _norm(row["model"]),
            row["year"],
            _norm(row.get("region") or ""),
            _norm(row.get("fuel") or ""),
            _norm(row.get("hp_range") or ""),
            _norm(row.get("country") or "FR"),
        )
        existing[key] = row

    cols = [
        "make",
        "model",
        "year",
        "region",
        "fuel",
        "country",
        "price_min",
        "price_median",
        "price_mean",
        "price_max",
        "price_std",
        "price_iqr_mean",
        "price_p25",
        "price_p75",
        "sample_count",
        "precision",
        "hp_range",
        "fiscal_hp",
        "lbc_estimate_low",
        "lbc_estimate_high",
        "calculation_details",
        "collected_at",
        "refresh_after",
    ]

    for row in src_rows:
        key = (
            _norm(row["make"]),
            _norm(row["model"]),
            row["year"],
            _norm(row.get("region") or ""),
            _norm(row.get("fuel") or ""),
            _norm(row.get("hp_range") or ""),
            _norm(row.get("country") or "FR"),
        )
        if key in existing:
            # Conflit : on compare collected_at pour garder la donnee la plus fraiche
            ex = existing[key]
            if (row.get("collected_at") or "") > (ex.get("collected_at") or ""):
                stats.tables[table]["conflicts"].append(
                    f"{row['make']} {row['model']} {row['year']} {row.get('region')}: "
                    f"source plus récent → remplacé"
                )
                if not dry_run:
                    set_clause = ", ".join(f"{c} = ?" for c in cols)
                    values = [row.get(c) for c in cols]
                    values.append(ex["id"])
                    tgt.execute(f"UPDATE market_prices SET {set_clause} WHERE id = ?", values)
                stats.tables[table]["imported"] += 1
            else:
                stats.tables[table]["skipped_dup"] += 1
            continue

        if not dry_run:
            placeholders = ", ".join("?" for _ in cols)
            col_names = ", ".join(cols)
            values = [row.get(c) for c in cols]
            tgt.execute(
                f"INSERT INTO market_prices ({col_names}) VALUES ({placeholders})",
                values,
            )
        existing[key] = row
        stats.tables[table]["imported"] += 1


def _merge_collection_jobs(
    src: sqlite3.Connection,
    tgt: sqlite3.Connection,
    table: str,
    unique_cols: list[str],
    all_cols: list[str],
    stats: MergeStats,
    dry_run: bool,
) -> None:
    """Importe une table de collection jobs avec dedup sur cle UNIQUE.

    Generique pour collection_jobs_lbc et collection_jobs_as24 qui ont
    la meme structure mais des colonnes de dedup differentes.
    """
    stats.init_table(table)

    src_rows = src.execute(f"SELECT * FROM [{table}] ORDER BY id").fetchall()  # noqa: S608
    stats.tables[table]["read"] = len(src_rows)

    existing = set()
    for row in tgt.execute(f"SELECT * FROM [{table}]").fetchall():  # noqa: S608
        key = tuple(_norm(str(row.get(c) or "")) for c in unique_cols)
        existing.add(key)

    for row in src_rows:
        key = tuple(_norm(str(row.get(c) or "")) for c in unique_cols)
        if key in existing:
            stats.tables[table]["skipped_dup"] += 1
            continue

        if not dry_run:
            insert_cols = [c for c in all_cols if c in row]
            placeholders = ", ".join("?" for _ in insert_cols)
            col_names = ", ".join(insert_cols)
            values = [row.get(c) for c in insert_cols]
            tgt.execute(
                f"INSERT INTO [{table}] ({col_names}) VALUES ({placeholders})",
                values,
            )
        existing.add(key)
        stats.tables[table]["imported"] += 1


def _merge_youtube_videos(
    src: sqlite3.Connection,
    tgt: sqlite3.Connection,
    vehicle_map: dict[int, int | None],
    stats: MergeStats,
    dry_run: bool,
) -> dict[int, int]:
    """Importe youtube_videos avec remap vehicle_id. Retourne mapping old_id -> new_id.

    Meme logique que scan_logs : on retourne un mapping pour que
    youtube_transcripts puisse pointer vers les bons video_db_id.
    """
    table = "youtube_videos"
    stats.init_table(table)
    video_map: dict[int, int] = {}

    src_rows = src.execute("SELECT * FROM youtube_videos ORDER BY id").fetchall()
    stats.tables[table]["read"] = len(src_rows)

    existing_video_ids = {
        r["video_id"] for r in tgt.execute("SELECT video_id FROM youtube_videos").fetchall()
    }

    cols = [
        "video_id",
        "title",
        "channel_name",
        "duration_seconds",
        "published_at",
        "search_query",
        "vehicle_id",
        "is_archived",
        "is_featured",
        "created_at",
    ]

    for row in src_rows:
        if row["video_id"] in existing_video_ids:
            stats.tables[table]["skipped_dup"] += 1
            continue

        # Remap vehicle_id
        new_vehicle_id = None
        if row.get("vehicle_id"):
            new_vehicle_id = vehicle_map.get(row["vehicle_id"])
            if new_vehicle_id is None:
                stats.tables[table]["skipped_no_mapping"] += 1
                stats.tables[table]["conflicts"].append(
                    f"video_id={row['video_id']}: vehicle_id={row['vehicle_id']} "
                    f"sans correspondance dans okazcar.db"
                )
                continue

        if not dry_run:
            values = [
                row["video_id"],
                row["title"],
                row["channel_name"],
                row.get("duration_seconds"),
                row.get("published_at"),
                row.get("search_query"),
                new_vehicle_id,
                row.get("is_archived", 0),
                row.get("is_featured", 0),
                row.get("created_at"),
            ]
            placeholders = ", ".join("?" for _ in cols)
            col_names = ", ".join(cols)
            cursor = tgt.execute(
                f"INSERT INTO youtube_videos ({col_names}) VALUES ({placeholders})",
                values,
            )
            video_map[row["id"]] = cursor.lastrowid
        else:
            video_map[row["id"]] = -(row["id"])

        existing_video_ids.add(row["video_id"])
        stats.tables[table]["imported"] += 1

    return video_map


def _merge_youtube_transcripts(
    src: sqlite3.Connection,
    tgt: sqlite3.Connection,
    video_map: dict[int, int],
    stats: MergeStats,
    dry_run: bool,
) -> None:
    """Importe youtube_transcripts avec remap video_db_id."""
    table = "youtube_transcripts"
    stats.init_table(table)

    src_rows = src.execute("SELECT * FROM youtube_transcripts ORDER BY id").fetchall()
    stats.tables[table]["read"] = len(src_rows)

    existing_video_db_ids = {
        r["video_db_id"]
        for r in tgt.execute("SELECT video_db_id FROM youtube_transcripts").fetchall()
    }

    cols = [
        "video_db_id",
        "language",
        "is_generated",
        "full_text",
        "snippets_json",
        "snippet_count",
        "char_count",
        "status",
        "error_message",
        "extracted_at",
        "created_at",
    ]

    for row in src_rows:
        new_video_id = video_map.get(row["video_db_id"])
        if new_video_id is None:
            stats.tables[table]["skipped_no_mapping"] += 1
            continue

        if new_video_id in existing_video_db_ids:
            stats.tables[table]["skipped_dup"] += 1
            continue

        if not dry_run:
            values = [
                new_video_id,
                row.get("language"),
                row.get("is_generated"),
                row.get("full_text"),
                row.get("snippets_json"),
                row.get("snippet_count"),
                row.get("char_count"),
                row.get("status"),
                row.get("error_message"),
                row.get("extracted_at"),
                row.get("created_at"),
            ]
            placeholders = ", ".join("?" for _ in cols)
            col_names = ", ".join(cols)
            tgt.execute(
                f"INSERT INTO youtube_transcripts ({col_names}) VALUES ({placeholders})",
                values,
            )
        existing_video_db_ids.add(new_video_id)
        stats.tables[table]["imported"] += 1


def _merge_vehicle_syntheses(
    src: sqlite3.Connection,
    tgt: sqlite3.Connection,
    vehicle_map: dict[int, int | None],
    stats: MergeStats,
    dry_run: bool,
) -> None:
    """Importe vehicle_syntheses avec remap vehicle_id."""
    table = "vehicle_syntheses"
    stats.init_table(table)

    src_rows = src.execute("SELECT * FROM vehicle_syntheses ORDER BY id").fetchall()
    stats.tables[table]["read"] = len(src_rows)

    existing = {
        (r["vehicle_id"], r["llm_model"])
        for r in tgt.execute("SELECT vehicle_id, llm_model FROM vehicle_syntheses").fetchall()
    }

    cols = [
        "vehicle_id",
        "make",
        "model",
        "year",
        "fuel",
        "llm_model",
        "prompt_used",
        "source_video_ids",
        "raw_transcript_chars",
        "synthesis_text",
        "status",
        "created_at",
    ]

    for row in src_rows:
        new_vehicle_id = None
        if row.get("vehicle_id"):
            new_vehicle_id = vehicle_map.get(row["vehicle_id"])
            if new_vehicle_id is None:
                stats.tables[table]["skipped_no_mapping"] += 1
                continue

        if (new_vehicle_id, row.get("llm_model")) in existing:
            stats.tables[table]["skipped_dup"] += 1
            continue

        if not dry_run:
            values = [
                new_vehicle_id,
                row.get("make"),
                row.get("model"),
                row.get("year"),
                row.get("fuel"),
                row.get("llm_model"),
                row.get("prompt_used"),
                row.get("source_video_ids"),
                row.get("raw_transcript_chars"),
                row.get("synthesis_text"),
                row.get("status"),
                row.get("created_at"),
            ]
            placeholders = ", ".join("?" for _ in cols)
            col_names = ", ".join(cols)
            tgt.execute(
                f"INSERT INTO vehicle_syntheses ({col_names}) VALUES ({placeholders})",
                values,
            )
        existing.add((new_vehicle_id, row.get("llm_model")))
        stats.tables[table]["imported"] += 1


def _merge_email_drafts(
    src: sqlite3.Connection,
    tgt: sqlite3.Connection,
    scan_map: dict[int, int],
    stats: MergeStats,
    dry_run: bool,
) -> None:
    """Importe email_drafts avec remap scan_id."""
    table = "email_drafts"
    stats.init_table(table)

    src_rows = src.execute("SELECT * FROM email_drafts ORDER BY id").fetchall()
    stats.tables[table]["read"] = len(src_rows)

    existing = {
        (r["listing_url"], r["llm_model"])
        for r in tgt.execute("SELECT listing_url, llm_model FROM email_drafts").fetchall()
    }

    cols = [
        "scan_id",
        "listing_url",
        "vehicle_make",
        "vehicle_model",
        "seller_type",
        "seller_name",
        "seller_phone",
        "seller_email",
        "prompt_used",
        "generated_text",
        "edited_text",
        "status",
        "llm_model",
        "tokens_used",
        "created_at",
    ]

    for row in src_rows:
        old_scan_id = row.get("scan_id")
        new_scan_id = scan_map.get(old_scan_id) if old_scan_id else None

        dedup_key = (row.get("listing_url"), row.get("llm_model"))
        if dedup_key in existing:
            stats.tables[table]["skipped_dup"] += 1
            continue

        if not dry_run:
            values = [
                new_scan_id,
                row.get("listing_url"),
                row.get("vehicle_make"),
                row.get("vehicle_model"),
                row.get("seller_type"),
                row.get("seller_name"),
                row.get("seller_phone"),
                row.get("seller_email"),
                row.get("prompt_used"),
                row.get("generated_text"),
                row.get("edited_text"),
                row.get("status"),
                row.get("llm_model"),
                row.get("tokens_used"),
                row.get("created_at"),
            ]
            placeholders = ", ".join("?" for _ in cols)
            col_names = ", ".join(cols)
            tgt.execute(
                f"INSERT INTO email_drafts ({col_names}) VALUES ({placeholders})",
                values,
            )
        existing.add(dedup_key)
        stats.tables[table]["imported"] += 1


def _merge_simple_table(
    src: sqlite3.Connection,
    tgt: sqlite3.Connection,
    table: str,
    dedup_cols: list[str],
    insert_cols: list[str],
    stats: MergeStats,
    dry_run: bool,
    *,
    vehicle_map: dict[int, int | None] | None = None,
    vehicle_col: str = "vehicle_id",
    defaults: dict[str, object] | None = None,
) -> None:
    """Import generique avec dedup et remap optionnel de vehicle_id.

    Fonction utilitaire pour les tables simples (observed_motorizations,
    vehicle_observed_specs, failed_searches) qui suivent toutes le meme
    pattern : dedup sur N colonnes + remap optionnel du vehicle_id.
    """
    stats.init_table(table)

    src_rows = src.execute(f"SELECT * FROM [{table}] ORDER BY id").fetchall()  # noqa: S608
    stats.tables[table]["read"] = len(src_rows)

    # Build existing keys
    existing = set()
    for row in tgt.execute(f"SELECT * FROM [{table}]").fetchall():  # noqa: S608
        key = tuple(_norm(str(row.get(c) or "")) for c in dedup_cols)
        existing.add(key)

    for row in src_rows:
        # Remap vehicle_id if needed
        new_vehicle_id = row.get(vehicle_col)
        if vehicle_map and row.get(vehicle_col):
            new_vehicle_id = vehicle_map.get(row[vehicle_col])
            if new_vehicle_id is None:
                stats.tables[table]["skipped_no_mapping"] += 1
                continue

        # Dedup
        dedup_values = []
        for c in dedup_cols:
            val = new_vehicle_id if c == vehicle_col and vehicle_map else row.get(c)
            dedup_values.append(_norm(str(val or "")))
        key = tuple(dedup_values)

        if key in existing:
            stats.tables[table]["skipped_dup"] += 1
            continue

        if not dry_run:
            values = []
            for c in insert_cols:
                if c == vehicle_col and vehicle_map:
                    values.append(new_vehicle_id)
                else:
                    val = row.get(c)
                    if val is None and defaults and c in defaults:
                        val = defaults[c]
                    values.append(val)
            placeholders = ", ".join("?" for _ in insert_cols)
            col_names = ", ".join(insert_cols)
            tgt.execute(
                f"INSERT INTO [{table}] ({col_names}) VALUES ({placeholders})",
                values,
            )
        existing.add(key)
        stats.tables[table]["imported"] += 1


def _merge_llm_usages(
    src: sqlite3.Connection,
    tgt: sqlite3.Connection,
    stats: MergeStats,
    dry_run: bool,
) -> None:
    """Importe llm_usages (dédup par request_id + created_at)."""
    table = "llm_usages"
    stats.init_table(table)

    src_rows = src.execute("SELECT * FROM llm_usages ORDER BY id").fetchall()
    stats.tables[table]["read"] = len(src_rows)

    existing = {
        (r["request_id"], r["created_at"])
        for r in tgt.execute("SELECT request_id, created_at FROM llm_usages").fetchall()
    }

    cols = [
        "request_id",
        "provider",
        "model",
        "feature",
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "estimated_cost_eur",
        "created_at",
    ]

    for row in src_rows:
        key = (row.get("request_id"), row.get("created_at"))
        if key in existing:
            stats.tables[table]["skipped_dup"] += 1
            continue

        if not dry_run:
            values = [row.get(c) for c in cols]
            placeholders = ", ".join("?" for _ in cols)
            col_names = ", ".join(cols)
            tgt.execute(
                f"INSERT INTO llm_usages ({col_names}) VALUES ({placeholders})",
                values,
            )
        existing.add(key)
        stats.tables[table]["imported"] += 1


def _merge_gemini_config(
    src: sqlite3.Connection,
    tgt: sqlite3.Connection,
    stats: MergeStats,
    dry_run: bool,
) -> None:
    """Importe gemini_config si absent dans target."""
    table = "gemini_config"
    stats.init_table(table)

    src_rows = src.execute("SELECT * FROM gemini_config").fetchall()
    stats.tables[table]["read"] = len(src_rows)

    tgt_count = _count(tgt, "gemini_config")
    if tgt_count > 0:
        stats.tables[table]["skipped_dup"] = len(src_rows)
        return

    cols = [
        "api_key_encrypted",
        "model_name",
        "max_daily_requests",
        "max_daily_cost_eur",
        "is_active",
        "updated_at",
    ]

    for row in src_rows:
        if not dry_run:
            values = [row.get(c) for c in cols]
            placeholders = ", ".join("?" for _ in cols)
            col_names = ", ".join(cols)
            tgt.execute(
                f"INSERT INTO gemini_config ({col_names}) VALUES ({placeholders})",
                values,
            )
        stats.tables[table]["imported"] += 1


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------


def merge(source_path: Path, target_path: Path, *, dry_run: bool) -> MergeStats:
    """Execute la fusion complete de toutes les tables.

    L'ordre d'import est important : les tables parent (scan_logs, youtube_videos)
    doivent etre importees avant les tables enfant (filter_results, youtube_transcripts)
    car on a besoin des mappings d'IDs.
    """
    stats = MergeStats()

    src = _connect(source_path, readonly=True)
    tgt = _connect(target_path, readonly=dry_run)

    print(f"{'[DRY RUN] ' if dry_run else ''}Fusion {source_path.name} → {target_path.name}")

    # Etape 1 : construire le mapping vehicle_id source -> cible
    vehicle_map = _build_vehicle_map(src, tgt)
    mapped = sum(1 for v in vehicle_map.values() if v is not None)
    unmapped = sum(1 for v in vehicle_map.values() if v is None)
    print(f"  Mapping véhicules : {mapped} trouvés, {unmapped} sans correspondance")

    # 2. scan_logs (base pour filter_results et email_drafts)
    print("  Importing scan_logs...")
    scan_map = _merge_scan_logs(src, tgt, stats, dry_run)
    print(f"    → {stats.tables['scan_logs']['imported']} importés")

    # 3. filter_results (dépend de scan_map)
    print("  Importing filter_results...")
    _merge_filter_results(src, tgt, scan_map, stats, dry_run)
    print(f"    → {stats.tables['filter_results']['imported']} importés")

    # 4. market_prices
    print("  Importing market_prices...")
    _merge_market_prices(src, tgt, stats, dry_run)
    print(f"    → {stats.tables['market_prices']['imported']} importés")

    # 5. collection_jobs_as24
    print("  Importing collection_jobs_as24...")
    _merge_collection_jobs(
        src,
        tgt,
        "collection_jobs_as24",
        unique_cols=[
            "make",
            "model",
            "year",
            "region",
            "fuel",
            "gearbox",
            "hp_range",
            "country",
            "tld",
        ],
        all_cols=[
            "make",
            "model",
            "year",
            "region",
            "fuel",
            "gearbox",
            "hp_range",
            "country",
            "tld",
            "slug_make",
            "slug_model",
            "search_strategy",
            "currency",
            "source_url",
            "priority",
            "status",
            "source_vehicle",
            "attempts",
            "created_at",
            "assigned_at",
            "completed_at",
        ],
        stats=stats,
        dry_run=dry_run,
    )
    print(f"    → {stats.tables['collection_jobs_as24']['imported']} importés")

    # 6. collection_jobs_lbc
    print("  Importing collection_jobs_lbc...")
    _merge_collection_jobs(
        src,
        tgt,
        "collection_jobs_lbc",
        unique_cols=["make", "model", "year", "region", "fuel", "gearbox", "hp_range", "country"],
        all_cols=[
            "make",
            "model",
            "year",
            "region",
            "fuel",
            "gearbox",
            "hp_range",
            "country",
            "priority",
            "status",
            "source_vehicle",
            "attempts",
            "created_at",
            "assigned_at",
            "completed_at",
        ],
        stats=stats,
        dry_run=dry_run,
    )
    print(f"    → {stats.tables['collection_jobs_lbc']['imported']} importés")

    # 7. youtube_videos (dépend de vehicle_map)
    print("  Importing youtube_videos...")
    video_map = _merge_youtube_videos(src, tgt, vehicle_map, stats, dry_run)
    print(f"    → {stats.tables['youtube_videos']['imported']} importés")

    # 8. youtube_transcripts (dépend de video_map)
    print("  Importing youtube_transcripts...")
    _merge_youtube_transcripts(src, tgt, video_map, stats, dry_run)
    print(f"    → {stats.tables['youtube_transcripts']['imported']} importés")

    # 9. vehicle_syntheses (dépend de vehicle_map)
    print("  Importing vehicle_syntheses...")
    _merge_vehicle_syntheses(src, tgt, vehicle_map, stats, dry_run)
    print(f"    → {stats.tables['vehicle_syntheses']['imported']} importés")

    # 10. email_drafts (dépend de scan_map)
    print("  Importing email_drafts...")
    _merge_email_drafts(src, tgt, scan_map, stats, dry_run)
    print(f"    → {stats.tables['email_drafts']['imported']} importés")

    # 11. llm_usages
    print("  Importing llm_usages...")
    _merge_llm_usages(src, tgt, stats, dry_run)
    print(f"    → {stats.tables['llm_usages']['imported']} importés")

    # 12. gemini_config
    print("  Importing gemini_config...")
    _merge_gemini_config(src, tgt, stats, dry_run)
    print(f"    → {stats.tables['gemini_config']['imported']} importés")

    # 13. observed_motorizations (dépend de vehicle_map)
    print("  Importing observed_motorizations...")
    _merge_simple_table(
        src,
        tgt,
        "observed_motorizations",
        dedup_cols=["vehicle_id", "fuel", "transmission", "power_din_hp"],
        insert_cols=[
            "vehicle_id",
            "fuel",
            "transmission",
            "power_din_hp",
            "seats",
            "power_fiscal_cv",
            "count",
            "distinct_sources",
            "source_ids",
            "promoted",
            "promoted_at",
            "last_seen_at",
        ],
        stats=stats,
        dry_run=dry_run,
        vehicle_map=vehicle_map,
    )
    print(f"    → {stats.tables['observed_motorizations']['imported']} importés")

    # 14. vehicle_observed_specs (dépend de vehicle_map)
    print("  Importing vehicle_observed_specs...")
    _merge_simple_table(
        src,
        tgt,
        "vehicle_observed_specs",
        dedup_cols=["vehicle_id", "spec_type", "spec_value"],
        insert_cols=["vehicle_id", "spec_type", "spec_value", "count", "last_seen_at"],
        stats=stats,
        dry_run=dry_run,
        vehicle_map=vehicle_map,
    )
    print(f"    → {stats.tables['vehicle_observed_specs']['imported']} importés")

    # 15. failed_searches
    print("  Importing failed_searches...")
    _merge_simple_table(
        src,
        tgt,
        "failed_searches",
        dedup_cols=["make", "model", "year", "region", "fuel", "hp_range", "country"],
        insert_cols=[
            "make",
            "model",
            "year",
            "region",
            "fuel",
            "hp_range",
            "country",
            "brand_token_used",
            "model_token_used",
            "token_source",
            "search_log",
            "total_ads_found",
            "status",
            "severity",
            "resolved",
            "resolved_note",
            "created_at",
            "resolved_at",
            "status_changed_at",
            "notes",
        ],
        stats=stats,
        dry_run=dry_run,
        defaults={"status": "open", "severity": "low"},
    )
    print(f"    → {stats.tables['failed_searches']['imported']} importés")

    if not dry_run:
        tgt.commit()
        print("\n  ✓ Commit effectué.")
    else:
        print("\n  [DRY RUN] Aucune écriture effectuée.")

    src.close()
    tgt.close()

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Fusion copilot.db → okazcar.db")
    parser.add_argument("--source-db", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--target-db", type=Path, default=DEFAULT_TARGET)
    parser.add_argument("--dry-run", action="store_true", help="Simule sans écrire")
    parser.add_argument(
        "--report-out",
        type=Path,
        default=REPORT_DIR / f"merge_copilot_into_okazcar_report_{TODAY}.md",
    )
    args = parser.parse_args()

    if not args.source_db.exists():
        print(f"ERREUR: {args.source_db} introuvable")
        sys.exit(1)
    if not args.target_db.exists():
        print(f"ERREUR: {args.target_db} introuvable")
        sys.exit(1)

    # Backup de securite avant toute ecriture
    if not args.dry_run:
        for db_path in [args.source_db, args.target_db]:
            backup = db_path.parent / f"{db_path.name}.backup-{TODAY}"
            if not backup.exists():
                print(f"  Backup: {db_path.name} → {backup.name}")
                shutil.copy2(db_path, backup)
            else:
                print(f"  Backup déjà existant : {backup.name}")

    stats = merge(args.source_db, args.target_db, dry_run=args.dry_run)

    # Write report
    report = stats.summary()
    args.report_out.parent.mkdir(parents=True, exist_ok=True)
    args.report_out.write_text(report, encoding="utf-8")
    print(f"\n  Rapport : {args.report_out}")
    print("\n" + report)


if __name__ == "__main__":
    main()
