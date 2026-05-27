# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Vinay Umrethe. See the LICENSE file for details.

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from filelock import FileLock

from .config import KnowledgeBaseConfig


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def session_index_lock(
    config: KnowledgeBaseConfig,
    timeout_seconds: float = 30.0,
) -> FileLock:
    config.index_dir.mkdir(parents=True, exist_ok=True)
    lock_path = config.index_dir / ".sessions.lock"
    return FileLock(lock_path, timeout=timeout_seconds)


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    """Write JSONL through a temp file so interruptions do not corrupt the index.

    Args:
        path: Destination JSONL path.
        records: Records to serialize.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temp_path.open("w", encoding="utf-8") as file:
            for record in records:
                file.write(json.dumps(record, ensure_ascii=False) + "\n")
        os.replace(temp_path, path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    records = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            if line.strip():
                records.append(json.loads(line))
    return records


def sessions_index_path(config: KnowledgeBaseConfig) -> Path:
    return config.index_dir / "sessions.jsonl"


def load_session_records(config: KnowledgeBaseConfig) -> list[dict[str, Any]]:
    return read_jsonl(sessions_index_path(config))


def latest_snapshot(record: dict[str, Any]) -> dict[str, Any]:
    updates = record.get("updates")
    if isinstance(updates, list) and updates:
        latest = dict(record)
        latest.update(updates[-1])
        return latest
    return record


def upsert_session_record(
    config: KnowledgeBaseConfig,
    archive_path: Path,
    record: dict[str, Any],
    update: dict[str, Any] | None = None,
    locked: bool = False,
) -> dict[str, Any]:
    if not locked:
        with session_index_lock(config):
            return upsert_session_record(
                config, archive_path, record, update, locked=True
            )

    index_path = sessions_index_path(config)
    target = str(archive_path.resolve())
    records = load_session_records(config)

    for existing in records:
        if existing.get("archive_path") == target:
            existing.setdefault("updates", [])
            if update is not None:
                existing["updates"].append(update)
            write_jsonl(index_path, records)
            return existing

    record.setdefault("updates", [])
    records.append(record)
    write_jsonl(index_path, records)
    return record


def find_latest_record_for_target(
    config: KnowledgeBaseConfig, target_path: Path
) -> dict[str, Any] | None:
    target = str(target_path.resolve())
    matches = [
        record
        for record in load_session_records(config)
        if record.get("archive_path") == target
    ]
    return latest_snapshot(matches[-1]) if matches else None
