# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Vinay Umrethe. See the LICENSE file for details.

from __future__ import annotations

import hashlib
import os
import shutil
from contextlib import suppress
from uuid import uuid4
from pathlib import Path
from typing import Any

from .config import KnowledgeBaseConfig, get_config
from .index import (
    find_latest_record_for_target,
    now_utc,
    session_index_lock,
    upsert_session_record,
)
from .naming import (
    VALID_EXTENSIONS,
    build_session_filename,
    normalize_date,
    normalize_effort,
    normalize_path,
    normalize_session_number,
    normalize_text,
    parse_session_filename,
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_trace_file(path: Path) -> None:
    if not path.exists():
        raise ValueError(f"File does not exist: {path}")
    if not path.is_file():
        raise ValueError(f"Path is not a file: {path}")
    if path.suffix.lower() not in VALID_EXTENSIONS:
        raise ValueError("Trace file must use .json or .jsonl.")


def archive_trace(
    source_path: str,
    session_date: str,
    project: str,
    session_number: int,
    platform: str,
    provider: str,
    model: str,
    effort: str | list[str],
    config: KnowledgeBaseConfig | None = None,
) -> dict[str, Any]:
    config = config or get_config()
    source = normalize_path(source_path).resolve()
    ensure_trace_file(source)

    normalized_date = normalize_date(session_date)
    normalized_project = normalize_text(project, "project")
    normalized_session = normalize_session_number(session_number)
    normalized_platform = normalize_text(platform, "platform")
    normalized_provider = normalize_text(provider, "provider")
    normalized_model = normalize_text(model, "model")
    normalized_effort = normalize_effort(effort)

    target_name = build_session_filename(
        normalized_session,
        normalized_platform,
        normalized_provider,
        normalized_model,
        normalized_effort,
        source.suffix,
    )
    target_dir = config.sessions_dir / normalized_date / normalized_project
    target = target_dir / target_name

    # Keep archive replacement and index mutation serialized across MCP clients.
    with session_index_lock(config):
        source_hash = sha256_file(source)
        target_dir.mkdir(parents=True, exist_ok=True)
        temp_dir = config.staging_dir / source_hash[:12]
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_path = temp_dir / f"{uuid4().hex}{source.suffix.lower()}"
        try:
            shutil.copy2(source, temp_path)

            temp_hash = sha256_file(temp_path)
            if source_hash != temp_hash:
                raise ValueError("Hash mismatch after temporary copy.")

            target_exists = target.exists()
            os.replace(temp_path, target)
        finally:
            temp_path.unlink(missing_ok=True)
            with suppress(OSError):
                temp_dir.rmdir()
            with suppress(OSError):
                config.staging_dir.rmdir()

        target_hash = sha256_file(target)
        if source_hash != target_hash:
            raise ValueError("Hash mismatch after archive copy.")

        archived_at = now_utc()
        record = {
            "status": "archived",
            "platform": normalized_platform,
            "provider": normalized_provider,
            "model": normalized_model,
            "project": normalized_project,
            "date": normalized_date,
            "session": normalized_session,
            "reasoning_effort": normalized_effort,
            "archived_at": archived_at,
            "source_path": str(source),
            "archive_path": str(target.resolve()),
            "sha256": target_hash,
            "size_bytes": target.stat().st_size,
            "updates": [],
        }
        if target_exists:
            update = {
                "status": "updated",
                "updated_at": archived_at,
                "source_path": str(source),
                "reasoning_effort": normalized_effort,
                "sha256": target_hash,
                "size_bytes": target.stat().st_size,
            }
            upsert_session_record(config, target, record, update=update, locked=True)
            updated_record = dict(record)
            updated_record.update(update)
            return updated_record

        upsert_session_record(config, target, record, locked=True)
        return record


def validate_archive(
    path: str, config: KnowledgeBaseConfig | None = None
) -> dict[str, Any]:
    config = config or get_config()
    target = normalize_path(path).resolve()
    ensure_trace_file(target)
    parsed = parse_session_filename(target)
    target_hash = sha256_file(target)
    latest_record = find_latest_record_for_target(config, target)
    hash_matches_index = (
        latest_record is not None and latest_record.get("sha256") == target_hash
    )
    return {
        "status": "valid" if hash_matches_index else "valid_unindexed",
        "archive_path": str(target),
        "parsed": parsed,
        "sha256": target_hash,
        "size_bytes": target.stat().st_size,
        "indexed": latest_record is not None,
        "hash_matches_index": hash_matches_index,
    }
