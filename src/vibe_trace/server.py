# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Vinay Umrethe. See the LICENSE file for details.

from __future__ import annotations

import json
import sys
from email.parser import Parser
from importlib.metadata import distribution, version
from typing import Any

from mcp.server.fastmcp import FastMCP
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .archive import archive_trace, validate_archive
from .config import get_config
from .discovery import find_recent_traces
from .index import load_session_records
from .inspect import inspect_target
from .naming import normalize_effort, normalize_path, normalize_text

mcp = FastMCP("vibe_trace")
BANNER = """██╗   ██╗██╗██████╗ ███████╗    ████████╗██████╗  █████╗  ██████╗███████╗
██║   ██║██║██╔══██╗██╔════╝    ╚══██╔══╝██╔══██╗██╔══██╗██╔════╝██╔════╝
██║   ██║██║██████╔╝█████╗         ██║   ██████╔╝███████║██║     █████╗  
╚██╗ ██╔╝██║██╔══██╗██╔══╝         ██║   ██╔══██╗██╔══██║██║     ██╔══╝  
 ╚████╔╝ ██║██████╔╝███████╗       ██║   ██║  ██║██║  ██║╚██████╗███████╗
  ╚═══╝  ╚═╝╚═════╝ ╚══════╝       ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝╚══════╝"""
AUTHOR = "Vinay Umrethe <umrethevinay@gmail.com>"
VIBE_TRACE_SKILL_MD = """---
name: vibe-trace
description: Use Vibe Trace to discover, archive, validate, list, and inspect local coding-agent session traces.
---

# Vibe Trace

Use this MCP when you need to preserve or understand local coding-agent session traces.

## Purpose

Vibe Trace archives raw agent traces into a stable local structure and indexes them so future
agents or the user can find sessions by project, date, platform, provider, model, and reasoning effort.

## When To Use

- Use it after a meaningful coding session that should be preserved.
- Use it when a user asks to find recent Codex, Claude Code, Cursor, or PI-Agent traces.
- Use it when validating whether an archived trace still matches its index hash.

## Archive Workflow

1. Call `vt_find_recent_traces` for the platform unless the user already gave `source_path`.
2. Ask for missing archive metadata: `session_date`, `project`, `session_number`,
   `platform`, `provider`, `model`, and `reasoning_effort`. (if you are not aware of metadata, ask the user)
3. Call `vt_archive_trace` with the selected source file and metadata.
4. Call `vt_validate_archive` on the returned `archive_path`.
5. Report the archive path, validation status, SHA-256, and whether this was a new archive
   or an update to an existing resumed session.

## Listing Workflow

Use `vt_list_sessions` when the user wants archived history. Apply only the filters the user
gave. Use pagination when more results are available.

## Inspection Workflow

Use `vt_inspect_file` for `.json`, `.jsonl`, `.parquet`, or folders containing those files.
Set `include_example` only when examples help the user understand the data.

## Rules

- Never delete, move, or rewrite the original source trace.
- Do not guess uncertain metadata. Ask the user for missing date, project, model, or effort.
- `session_number` is one-based: `1` becomes `S0000`.
- `reasoning_effort` must be chronological and use only `LOW`, `MEDIUM`, `HIGH`, or `XHIGH`.
- For resumed sessions, keep the original session date and archive to the same target path.
- Prefer `vt_validate_archive` after every archive operation.
"""


@mcp.tool(
    name="vt_find_recent_traces",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def vt_find_recent_traces(
    platform: str,
    limit: int = 10,
    search_roots: list[str] | None = None,
) -> dict[str, Any]:
    """Find recent raw trace candidates for a supported platform.

    Args:
        platform: Platform name such as CODEX.
        limit: Maximum number of trace candidates to return.
        search_roots: Optional folders to search instead of default platform roots.

    Returns:
        Candidate trace paths and file metadata.
    """
    traces = find_recent_traces(
        platform=platform, limit=limit, search_roots=search_roots
    )
    return {
        "status": "ok",
        "platform": normalize_text(platform, "platform"),
        "traces": traces,
    }


@mcp.tool(
    name="vt_archive_trace",
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def vt_archive_trace(
    source_path: str,
    session_date: str,
    project: str,
    session_number: int,
    platform: str,
    provider: str,
    model: str,
    reasoning_effort: str | list[str],
) -> dict[str, Any]:
    """Archive one raw trace into the configured Vibe Trace data root.

    Args:
        source_path: Raw JSON or JSONL trace file to archive.
        session_date: Original session date in YYYY-MM-DD format.
        project: Project name to store under.
        session_number: Human one-based session number where 1 maps to S0000.
        platform: Agent platform name.
        provider: Model provider name.
        model: Model name and version.
        reasoning_effort: Chronological reasoning effort sequence.

    Returns:
        Archive metadata including path, hash, size, and status.
    """
    return archive_trace(
        source_path=source_path,
        session_date=session_date,
        project=project,
        session_number=session_number,
        platform=platform,
        provider=provider,
        model=model,
        effort=reasoning_effort,
    )


@mcp.tool(
    name="vt_validate_archive",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def vt_validate_archive(path: str) -> dict[str, Any]:
    """Validate an archived trace against its filename convention and index record.

    Args:
        path: Archived trace path.

    Returns:
        Parsed filename metadata, SHA-256, size, and index match status.
    """
    return validate_archive(path)


@mcp.tool(
    name="vt_list_sessions",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def vt_list_sessions(
    session_date: str | None = None,
    project: str | None = None,
    platform: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    reasoning_effort: str | list[str] | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """List archived sessions with optional filters and pagination.

    Args:
        session_date: Optional session date filter.
        project: Optional project filter.
        platform: Optional platform filter.
        provider: Optional provider filter.
        model: Optional model filter.
        reasoning_effort: Optional chronological reasoning effort filter.
        limit: Maximum number of sessions to return.
        offset: Zero-based pagination offset.

    Returns:
        Matching session records and pagination metadata.
    """
    if limit < 1 or limit > 500:
        raise ValueError("Limit must be from 1 to 500.")
    if offset < 0:
        raise ValueError("Offset must be 0 or greater.")

    records = load_session_records(get_config())
    filters = {
        "date": session_date,
        "project": normalize_text(project, "project") if project else None,
        "platform": normalize_text(platform, "platform") if platform else None,
        "provider": normalize_text(provider, "provider") if provider else None,
        "model": normalize_text(model, "model") if model else None,
    }
    effort_filter = normalize_effort(reasoning_effort) if reasoning_effort else None

    filtered = []
    for record in records:
        if any(
            value is not None and record.get(key) != value
            for key, value in filters.items()
        ):
            continue
        if (
            effort_filter is not None
            and record.get("reasoning_effort") != effort_filter
        ):
            continue
        filtered.append(record)

    total_count = len(filtered)
    page = filtered[offset : offset + limit]
    next_offset = offset + len(page)
    has_more = next_offset < total_count
    return {
        "status": "ok",
        "count": len(page),
        "total_count": total_count,
        "limit": limit,
        "offset": offset,
        "has_more": has_more,
        "next_offset": next_offset if has_more else None,
        "sessions": page,
    }


@mcp.tool(
    name="vt_inspect_file",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def vt_inspect_file(
    path: str,
    include_example: bool = False,
    recursive: bool = True,
    max_files: int = 50,
    max_records_per_file: int = 1000,
) -> dict[str, Any]:
    """Inspect supported data files and infer their schema structure.

    Args:
        path: File or folder path to inspect.
        include_example: Whether to include representative example values.
        recursive: Whether folder inspection descends into subfolders.
        max_files: Maximum number of files to inspect.
        max_records_per_file: Maximum number of records to inspect per file.

    Returns:
        Schema summary, inspection counts, errors, and optional examples.
    """
    return inspect_target(
        normalize_path(path),
        include_example=include_example,
        recursive=recursive,
        max_files=max_files,
        max_records_per_file=max_records_per_file,
    )


def package_readme() -> str:
    metadata_text = distribution("vibe-trace").read_text("METADATA")
    if metadata_text is None:
        raise FileNotFoundError("Installed package metadata does not include METADATA.")
    readme_text = Parser().parsestr(metadata_text).get_payload()
    if not isinstance(readme_text, str) or not readme_text.strip():
        raise ValueError("Installed package metadata does not include README content.")
    return readme_text


def sync_data_root_readme(readme_text: str) -> None:
    readme_path = get_config().root / "README.md"
    readme_path.parent.mkdir(parents=True, exist_ok=True)
    if readme_path.exists() and readme_path.read_text(encoding="utf-8") == readme_text:
        return
    readme_path.write_text(readme_text, encoding="utf-8")


# Sync the installed latest README into the data root.
sync_data_root_readme(package_readme())


def print_header(console: Console) -> None:
    console.print(BANNER, style="bold orange3")
    console.print(AUTHOR, style="bold")


def show_help() -> None:
    console = Console()
    print_header(console)
    console.print()
    console.print(
        Panel.fit(
            "Run [bold]vibe-trace[/bold] without arguments to start the stdio MCP server.",
            title="Usage",
            border_style="orange3",
        )
    )
    table = Table(show_header=True, header_style="bold orange3")
    table.add_column("Command")
    table.add_column("Purpose")
    table.add_row("vibe-trace", "Start the stdio MCP server.")
    table.add_row("vibe-trace --help", "Show this help.")
    table.add_row("vibe-trace --version", "Show installed package version.")
    table.add_row("vibe-trace status", "Show local data root and MCP tool summary.")
    console.print(table)


def show_version() -> None:
    console = Console()
    console.print(f"vibe-trace [bold]{version('vibe-trace')}[/bold]")


def show_status() -> None:
    console = Console()
    config = get_config()

    table = Table(show_header=True, header_style="bold orange3")
    table.add_column("Item")
    table.add_column("Value")
    table.add_row("Data root", str(config.root))
    table.add_row("Sessions", str(config.sessions_dir))
    table.add_row("Index", str(config.index_dir / "sessions.jsonl"))
    table.add_row("Staging temp", str(config.staging_dir))
    table.add_row(
        "Tools",
        "vt_find_recent_traces, vt_archive_trace, vt_validate_archive, vt_list_sessions, vt_inspect_file",
    )
    table.add_row(
        "Resources",
        "vt://skill.md, vt://readme, vt://convention, vt://sessions/index",
    )
    console.print(table)


def main() -> None:
    """Route helper commands while keeping no-argument MCP stdio silent."""
    args = sys.argv[1:]
    if not args:
        mcp.run()
        return
    if args == ["--help"]:
        show_help()
        return
    if args == ["--version"]:
        show_version()
        return
    if args == ["status"]:
        show_status()
        return

    console = Console(stderr=True)
    console.print(f"[red]Unknown argument:[/] {' '.join(args)}")
    console.print("Use [bold]vibe-trace --help[/bold].")
    raise SystemExit(2)


@mcp.resource(
    "vt://skill.md",
    name="View Vibe Trace Agent Skill",
    description="Short Markdown guide that tells agents when and how to use Vibe Trace.",
)
async def vt_skill() -> str:
    return VIBE_TRACE_SKILL_MD


@mcp.resource(
    "vt://readme",
    name="View Vibe Trace README",
    description="Usage guide for Vibe Trace and its MCP tools.",
)
async def vt_readme() -> str:
    readme_text = package_readme()
    return readme_text


@mcp.resource(
    "vt://convention",
    name="View Vibe Trace Naming Convention",
    description="Session archive path and filename convention used by Vibe Trace.",
)
async def vt_convention() -> str:
    return """sessions/YYYY-MM-DD/PROJECT-FULL-NAME/S0000--PLATFORM--PROVIDER.MODEL--EFFORT.jsonl
SESSION is zero-based in the filename. A human session number of 1 maps to S0000.
EFFORT is stored as a hyphen sequence in filenames and as reasoning_effort list in indexes.
The structural filename delimiter is --."""


@mcp.resource(
    "vt://sessions/index",
    name="View Vibe Trace Sessions Index",
    description="Current JSONL index of archived Vibe Trace sessions.",
)
async def vt_sessions_index() -> str:
    records = load_session_records(get_config())
    return json.dumps(records, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
