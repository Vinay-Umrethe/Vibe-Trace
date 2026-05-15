# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Vinay Umrethe. See the LICENSE file for details.

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class KnowledgeBaseConfig:
    root: Path
    sessions_dir: Path
    index_dir: Path
    staging_dir: Path

    def to_dict(self) -> dict[str, str]:
        return {key: str(value) for key, value in asdict(self).items()}


def get_config() -> KnowledgeBaseConfig:
    root_value = os.environ.get("VIBE_TRACE_ROOT", Path.home() / ".vibe-trace")
    root = Path(root_value).resolve()
    return KnowledgeBaseConfig(
        root=root,
        sessions_dir=root / "sessions",
        index_dir=root / "index",
        staging_dir=root / ".staging" / "temp",
    )
