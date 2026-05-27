# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Vinay Umrethe. See the LICENSE file for details.

from __future__ import annotations

import re
from datetime import date
from os import PathLike
from pathlib import Path

VALID_EXTENSIONS = {".json", ".jsonl"}
VALID_EFFORTS = {"LOW", "MEDIUM", "HIGH", "XHIGH"}
FILENAME_PATTERN = re.compile(
    r"^(S\d{4})--(.+)--([A-Z0-9-]+)\.(.+)--(LOW|MEDIUM|HIGH|XHIGH)(?:-(LOW|MEDIUM|HIGH|XHIGH))*\.(jsonl|json)$",
    re.IGNORECASE,
)


def normalize_path(raw_path: str | PathLike[str]) -> Path:
    if isinstance(raw_path, PathLike):
        return Path(raw_path).expanduser()

    path_text = raw_path.strip()
    if (
        len(path_text) >= 2
        and path_text[0] == path_text[-1]
        and path_text[0] in {"'", '"'}
    ):
        path_text = path_text[1:-1]
    return Path(path_text).expanduser()


def normalize_date(raw_date: str) -> str:
    try:
        return date.fromisoformat(raw_date.strip()).isoformat()
    except ValueError as exc:
        raise ValueError("Date must use YYYY-MM-DD format.") from exc


def normalize_text(raw_value: str, label: str) -> str:
    value = re.sub(r"\s+", "-", raw_value.strip().replace("_", "-").upper())
    if not value:
        raise ValueError(f"{label} cannot be empty.")
    if "--" in value:
        raise ValueError(f"{label} cannot contain --.")
    if any(char in value for char in '<>:"/\\|?*'):
        raise ValueError(
            f"{label} contains a character that is invalid in Windows filenames."
        )
    return value


def normalize_session_number(session_number: int) -> str:
    if session_number < 1 or session_number > 10000:
        raise ValueError("session_number must be from 1 to 10000. 1 maps to S0000.")
    return f"S{session_number - 1:04d}"


def normalize_effort(raw_effort: str | list[str]) -> list[str]:
    if isinstance(raw_effort, str):
        effort_text = normalize_text(raw_effort, "effort")
        parts = effort_text.split("-")
    else:
        parts = [normalize_text(value, "effort") for value in raw_effort]

    if not parts:
        raise ValueError("Effort cannot be empty.")

    invalid = [value for value in parts if value not in VALID_EFFORTS]
    if invalid:
        allowed = ", ".join(sorted(VALID_EFFORTS))
        raise ValueError(f"Effort must use only {allowed}.")
    return parts


def effort_token(effort: list[str]) -> str:
    return "-".join(effort)


def build_session_filename(
    session_id: str,
    platform: str,
    provider: str,
    model: str,
    effort: list[str],
    extension: str,
) -> str:
    if extension.lower() not in VALID_EXTENSIONS:
        raise ValueError("Session files must use .json or .jsonl.")
    return f"{session_id}--{platform}--{provider}.{model}--{effort_token(effort)}{extension.lower()}"


def parse_session_filename(path: Path) -> dict[str, object]:
    match = FILENAME_PATTERN.match(path.name)
    if not match:
        raise ValueError("Filename does not match the session convention.")

    stem = path.stem
    session_id, platform, provider_model, effort_text = stem.split("--", maxsplit=3)
    provider, model = provider_model.split(".", maxsplit=1)
    return {
        "session": session_id.upper(),
        "platform": platform.upper(),
        "provider": provider.upper(),
        "model": model.upper(),
        "reasoning_effort": normalize_effort(effort_text),
        "extension": path.suffix.lower(),
    }
