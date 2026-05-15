# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Vinay Umrethe. See the LICENSE file for details.

from __future__ import annotations

from pathlib import Path
from typing import Any

from .naming import normalize_text

SUPPORTED_PLATFORMS = {"CLAUDE", "CODEX", "CURSOR", "PI-AGENT"}

PLATFORM_GLOBS = {
    "CLAUDE": ("*/*.jsonl",),
    "CODEX": ("**/rollout-*.jsonl",),
    "CURSOR": (
        "*/agent-transcripts/*/transcript.jsonl",
        "*/agent-transcripts/*/*.jsonl",
    ),
    "PI-AGENT": ("*_*.jsonl",),
}


def normalize_platform(platform: str) -> str:
    return normalize_text(platform, "platform")


def supported_platforms_text() -> str:
    return ", ".join(sorted(SUPPORTED_PLATFORMS))


def default_platform_roots(platform: str) -> list[Path]:
    normalized = normalize_platform(platform)
    if normalized not in SUPPORTED_PLATFORMS:
        raise ValueError(f"Automatic trace discovery supports: {supported_platforms_text()}.")

    home = Path.home()
    candidates: dict[str, list[Path]] = {
        "CLAUDE": [home / ".claude" / "projects"],
        "CODEX": [home / ".codex" / "sessions"],
        "CURSOR": [home / ".cursor" / "projects"],
        "PI-AGENT": [home / ".pi" / "agent" / "sessions"],
    }
    return [path for path in candidates.get(normalized, []) if path.exists()]


def candidate_trace_files(root: Path, platform: str) -> list[Path]:
    normalized = normalize_platform(platform)
    if normalized not in SUPPORTED_PLATFORMS:
        raise ValueError(f"Automatic trace discovery supports: {supported_platforms_text()}.")

    files = []
    for pattern in PLATFORM_GLOBS[normalized]:
        files.extend(path for path in root.glob(pattern) if path.is_file())
    return sorted(set(files))


def find_recent_traces(
    platform: str, limit: int = 10, search_roots: list[str] | None = None
) -> list[dict[str, Any]]:
    if limit < 1 or limit > 100:
        raise ValueError("Limit must be from 1 to 100.")

    normalized_platform = normalize_platform(platform)
    if normalized_platform not in SUPPORTED_PLATFORMS:
        raise ValueError(f"Automatic trace discovery supports: {supported_platforms_text()}.")

    roots = (
        [Path(path).expanduser() for path in search_roots]
        if search_roots
        else default_platform_roots(normalized_platform)
    )
    existing_roots = [path for path in roots if path.exists() and path.is_dir()]
    if not existing_roots:
        return []

    files = []
    for root in existing_roots:
        files.extend(candidate_trace_files(root, normalized_platform))

    unique_files = sorted(set(files), key=lambda path: path.stat().st_mtime, reverse=True)
    results = []
    for path in unique_files[:limit]:
        stat = path.stat()
        results.append(
            {
                "path": str(path.resolve()),
                "name": path.name,
                "size_bytes": stat.st_size,
                "modified_time": stat.st_mtime,
            }
        )
    return results
