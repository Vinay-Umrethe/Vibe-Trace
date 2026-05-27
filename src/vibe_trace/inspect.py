# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Vinay Umrethe. See the LICENSE file for details.

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

VALID_EXTENSIONS = {".json", ".jsonl", ".parquet"}


def truncate_value(value: Any, max_len: int = 250) -> Any:
    if value is None or isinstance(value, int | float | bool):
        return value

    value_text = str(value).replace("\n", " ").replace("\r", "")
    if len(value_text) > max_len:
        return f"{value_text[: max_len - 3]}..."
    return value_text


def format_examples(example_data: Any) -> Any:
    if isinstance(example_data, dict):
        return {key: format_examples(value) for key, value in example_data.items()}
    if isinstance(example_data, list):
        return [format_examples(value) for value in example_data]
    return truncate_value(example_data)


def get_type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "str"
    if isinstance(value, bytes):
        return "binary"
    if isinstance(value, tuple):
        return "tuple"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "dict"
    return type(value).__name__


def extract_schema_and_example(data: Any) -> tuple[Any, Any]:
    if isinstance(data, dict):
        schema = {}
        example = {}
        for key, value in data.items():
            child_schema, child_example = extract_schema_and_example(value)
            schema[key] = child_schema
            example[key] = child_example
        return schema, example

    if isinstance(data, list | tuple):
        if not data:
            return ["unknown"], []
        child_schema, child_example = extract_schema_and_example(data[0])
        return [child_schema], [child_example]

    return get_type_name(data), data


def merge_schemas_and_examples(
    schema_a: Any, example_a: Any, schema_b: Any, example_b: Any
) -> tuple[Any, Any]:
    """Merge two inferred schemas while preserving one representative example.

    Args:
        schema_a: Existing inferred schema.
        example_a: Existing representative example.
        schema_b: Incoming inferred schema.
        example_b: Incoming representative example.

    Returns:
        Merged schema and representative example.
    """
    if schema_a is None or schema_a == "unknown":
        return schema_b, example_b
    if schema_b is None or schema_b == "unknown":
        return schema_a, example_a

    if isinstance(schema_a, dict) and isinstance(schema_b, dict):
        merged_schema = {}
        merged_example = {}
        for key in set(schema_a) | set(schema_b):
            child_schema_a = schema_a.get(key)
            child_example_a = (
                example_a.get(key) if isinstance(example_a, dict) else None
            )
            child_schema_b = schema_b.get(key)
            child_example_b = (
                example_b.get(key) if isinstance(example_b, dict) else None
            )
            merged_schema[key], merged_example[key] = merge_schemas_and_examples(
                child_schema_a,
                child_example_a,
                child_schema_b,
                child_example_b,
            )
        return merged_schema, merged_example

    if isinstance(schema_a, list) and isinstance(schema_b, list):
        if not schema_a:
            return schema_b, example_b
        if not schema_b:
            return schema_a, example_a

        example_value_a = (
            example_a[0] if isinstance(example_a, list) and example_a else None
        )
        example_value_b = (
            example_b[0] if isinstance(example_b, list) and example_b else None
        )
        merged_schema, merged_example = merge_schemas_and_examples(
            schema_a[0],
            example_value_a,
            schema_b[0],
            example_value_b,
        )
        return [merged_schema], [merged_example]

    if schema_a == schema_b:
        return (
            schema_a,
            example_a
            if example_a is not None and example_a != "" and example_a != []
            else example_b,
        )

    union_types = set(
        schema_a.split(" | ") if isinstance(schema_a, str) else [str(schema_a)]
    )
    union_types.update(
        schema_b.split(" | ") if isinstance(schema_b, str) else [str(schema_b)]
    )
    example = (
        example_a if example_a is not None and str(example_a).strip() else example_b
    )
    return " | ".join(sorted(union_types)), example


def iter_jsonl_records(path: Path, max_records: int):
    with path.open("r", encoding="utf-8") as file:
        records_seen = 0
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue
            try:
                yield json.loads(line)
                records_seen += 1
                if records_seen >= max_records:
                    return
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"{path} has invalid JSON on line {line_number}: {exc.msg}"
                ) from exc


def iter_json_records(path: Path, max_records: int):
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if isinstance(data, list):
        yield from data[:max_records]
    else:
        yield data


def iter_parquet_records(path: Path, max_records: int):
    parquet_file = pq.ParquetFile(path)
    records_seen = 0
    for batch in parquet_file.iter_batches(batch_size=1000):
        for record in batch.to_pylist():
            yield record
            records_seen += 1
            if records_seen >= max_records:
                return


def process_file(path: Path, max_records: int) -> tuple[Any, Any, int]:
    file_schema = None
    file_example = None
    records_seen = 0

    if path.suffix.lower() == ".jsonl":
        records = iter_jsonl_records(path, max_records)
    elif path.suffix.lower() == ".json":
        records = iter_json_records(path, max_records)
    elif path.suffix.lower() == ".parquet":
        records = iter_parquet_records(path, max_records)
    else:
        return None, None, records_seen

    for record in records:
        records_seen += 1
        schema, example = extract_schema_and_example(record)
        file_schema, file_example = merge_schemas_and_examples(
            file_schema, file_example, schema, example
        )

    return file_schema, file_example, records_seen


def collect_files(target_path: Path, recursive: bool) -> list[Path]:
    if target_path.is_file() and target_path.suffix.lower() in VALID_EXTENSIONS:
        return [target_path]
    if target_path.is_dir():
        candidates = target_path.rglob("*") if recursive else target_path.glob("*")
        return sorted(
            [
                path
                for path in candidates
                if path.is_file() and path.suffix.lower() in VALID_EXTENSIONS
            ],
            key=lambda path: str(path).lower(),
        )
    return []


def inspect_target(
    path: Path,
    include_example: bool = False,
    recursive: bool = True,
    max_files: int = 50,
    max_records_per_file: int = 1000,
) -> dict[str, Any]:
    """Inspect supported files with bounded file and record counts.

    Supports:
        JSON, JSONL, Parquet, and folders containing those file types.

    Returns:
        Schema summary, inspection counts, errors, and optional examples.
    """
    if max_files < 1 or max_files > 500:
        raise ValueError("max_files must be from 1 to 500.")
    if max_records_per_file < 1 or max_records_per_file > 100000:
        raise ValueError("max_records_per_file must be from 1 to 100000.")

    files = collect_files(path, recursive=recursive)
    if not files:
        raise ValueError(
            "Path must be a supported file or folder containing supported files."
        )

    selected_files = files[:max_files]
    unique_schemas: dict[str, tuple[Any, Any, int]] = {}
    errors = []
    records_seen = 0
    for file_path in selected_files:
        try:
            schema, example, file_records_seen = process_file(
                file_path, max_records_per_file
            )
            records_seen += file_records_seen
        except Exception as exc:
            errors.append({"path": str(file_path), "error": str(exc)})
            continue

        if schema is None:
            continue

        schema_hash = json.dumps(schema, sort_keys=True)
        if schema_hash in unique_schemas:
            current_schema, current_example, count = unique_schemas[schema_hash]
            unique_schemas[schema_hash] = (current_schema, current_example, count + 1)
        else:
            unique_schemas[schema_hash] = (schema, example, 1)

    if not unique_schemas:
        raise ValueError("No valid records or schemas found.")

    schemas = []
    examples = []
    for schema, example, _ in unique_schemas.values():
        schemas.append(schema)
        examples.append(format_examples(example))

    result: dict[str, Any] = {
        "status": "inspected",
        "files_seen": len(files),
        "files_inspected": len(selected_files),
        "files_skipped": max(0, len(files) - len(selected_files)),
        "records_seen": records_seen,
        "recursive": recursive,
        "max_files": max_files,
        "max_records_per_file": max_records_per_file,
        "unique_schema_count": len(schemas),
        "schema": schemas[0] if len(schemas) == 1 else schemas,
        "errors": errors,
    }
    if include_example:
        result["example"] = examples[0] if len(examples) == 1 else examples
    return result
