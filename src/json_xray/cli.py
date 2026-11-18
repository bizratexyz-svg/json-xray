"""CLI entry point for json-xray."""

from __future__ import annotations

import argparse
import json
import keyword
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import __version__


@dataclass
class SchemaNode:
    """Aggregated schema statistics for a JSON value or field."""

    types: set[str] = field(default_factory=set)
    count: int = 0
    null_count: int = 0
    sample: Any = None
    has_sample: bool = False
    properties: dict[str, SchemaNode] = field(default_factory=dict)
    items: SchemaNode | None = None

    def observe(self, value: Any) -> None:
        self.count += 1
        if value is None:
            self.null_count += 1
            self.types.add("null")
            return
        if isinstance(value, bool):
            self.types.add("boolean")
            self._set_sample(value)
        elif isinstance(value, int):
            self.types.add("integer")
            self._set_sample(value)
        elif isinstance(value, float):
            self.types.add("number")
            self._set_sample(value)
        elif isinstance(value, str):
            self.types.add("string")
            self._set_sample(value)
        elif isinstance(value, list):
            self.types.add("array")
            if self.items is None:
                self.items = SchemaNode()
            for elem in value:
                self.items.observe(elem)
            if not self.has_sample:
                self._set_sample(value[:2])
        elif isinstance(value, dict):
            self.types.add("object")
            for k, v in value.items():
                key = str(k)
                if key not in self.properties:
                    self.properties[key] = SchemaNode()
                self.properties[key].observe(v)
            if not self.has_sample:
                self._set_sample(f"{{{len(value)} keys}}")

    def _set_sample(self, value: Any) -> None:
        if not self.has_sample:
            self.sample = value
            self.has_sample = True


def load_records(raw: str) -> tuple[list[Any], str]:
    """Parse JSON or JSONL text and return (records, format_label)."""
    stripped = raw.strip()
    if not stripped:
        sys.exit("error: input is empty.")
    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, list):
            return parsed, "json-array"
        return [parsed], "json"
    except json.JSONDecodeError:
        records: list[Any] = []
        for idx, line in enumerate(stripped.splitlines(), start=1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                sys.exit(f"error: invalid JSON on line {idx}: {exc.msg}")
        if not records:
            sys.exit("error: no valid JSON records found.")
        return records, "jsonl"


def infer_schema(records: list[Any]) -> SchemaNode:
    root = SchemaNode()
    for rec in records:
        root.observe(rec)
    return root


def _fmt_sample(val: Any, max_len: int = 36) -> str:
    if val is None:
        return "null"
    text = json.dumps(val, ensure_ascii=False) if not isinstance(val, str) else repr(val)
    if len(text) > max_len:
        return text[: max_len - 3] + "..."
    return text


def _collect_rows(
    node: SchemaNode,
    prefix: str,
    parent_count: int,
    rows: list[tuple[str, str, str, str]],
) -> None:
    if node.properties:
        for key, child in node.properties.items():
            path = f"{prefix}.{key}" if prefix else key
            missing = max(0, parent_count - child.count)
            null_or_missing = child.null_count + missing
            rate = (null_or_missing / parent_count * 100.0) if parent_count else 0.0
            non_null_types = sorted(t for t in child.types if t != "null")
            type_str = " | ".join(non_null_types) if non_null_types else "null"
            if "null" in child.types or missing > 0:
                type_str += "?"
            sample_str = _fmt_sample(child.sample) if child.has_sample else "null"
            rows.append((path, type_str, f"{rate:.1f}%", sample_str))
            if child.properties:
                _collect_rows(child, path, child.count - child.null_count, rows)
            elif child.items and child.items.properties:
                _collect_rows(
                    child.items,
                    f"{path}[]",
                    child.items.count - child.items.null_count,
                    rows,
                )


def render_table(root: SchemaNode, record_count: int, fmt: str) -> str:
    rows: list[tuple[str, str, str, str]] = []
    if root.properties:
        _collect_rows(root, "", root.count - root.null_count, rows)
    else:
        types_str = " | ".join(sorted(root.types)) or "unknown"
        rate = (root.null_count / root.count * 100.0) if root.count else 0.0
        rows.append(("$", types_str, f"{rate:.1f}%", _fmt_sample(root.sample)))

    headers = ("Field", "Type", "Null/Missing", "Sample")
    widths = [
        max(len(headers[i]), *(len(r[i]) for r in rows))
        for i in range(len(headers))
    ]

    def fmt_row(cells: tuple[str, ...]) -> str:
        return "  ".join(
            cells[i].rjust(widths[i]) if i == 2 else cells[i].ljust(widths[i])
            for i in range(len(cells))
        )

    lines = [
        f"Format: {fmt} | Records: {record_count:,} | Fields: {len(rows):,}",
        "",
        fmt_row(headers),
        "  ".join("-" * w for w in widths),
    ]
    lines.extend(fmt_row(r) for r in rows)
    return "\n".join(lines)


def _pascal_case(name: str) -> str:
    parts = re.split(r"[^0-9a-zA-Z]+", name)
    cleaned = "".join(p[:1].upper() + p[1:] for p in parts if p)
    if not cleaned or cleaned[0].isdigit():
        cleaned = "Item" + cleaned
    return cleaned


def _ts_key(key: str) -> str:
    return key if re.match(r"^[A-Za-z_$][A-Za-z0-9_$]*$", key) else json.dumps(key)


def render_typescript(root: SchemaNode, root_name: str = "Root") -> str:
    """Generate clean TypeScript interfaces from an inferred schema."""
    interfaces: list[str] = []
    used_names: set[str] = set()

    def alloc_name(base: str) -> str:
        candidate = _pascal_case(base)
        if candidate not in used_names:
            used_names.add(candidate)
            return candidate
        i = 2
        while f"{candidate}{i}" in used_names:
            i += 1
        used_names.add(f"{candidate}{i}")
        return f"{candidate}{i}"

    def ts_type(node: SchemaNode, hint: str) -> str:
        non_null = sorted(t for t in node.types if t != "null")
        parts: list[str] = []
        for t in non_null:
            if t in ("integer", "number"):
                if "number" not in parts:
                    parts.append("number")
            elif t == "string":
                parts.append("string")
            elif t == "boolean":
                parts.append("boolean")
            elif t == "array":
                if node.items and node.items.types:
                    inner = ts_type(node.items, f"{hint}Item")
                    parts.append(f"({inner})[]" if " | " in inner else f"{inner}[]")
                else:
                    parts.append("unknown[]")
            elif t == "object":
                if node.properties:
                    iface_name = emit_interface(node, hint)
                    parts.append(iface_name)
                else:
                    parts.append("Record<string, unknown>")
        if not parts:
            return "null"
        if "null" in node.types:
            parts.append("null")
        return " | ".join(parts)

    def emit_interface(node: SchemaNode, hint: str) -> str:
        name = alloc_name(hint)
        parent_total = node.count - node.null_count
        body: list[str] = []
        for key, child in node.properties.items():
            optional = child.count < parent_total
            opt_mark = "?" if optional else ""
            field_type = ts_type(child, key)
            body.append(f"  {_ts_key(key)}{opt_mark}: {field_type};")
        block = f"export interface {name} {{\n" + "\n".join(body) + "\n}"
        interfaces.append(block)
        return name

    if root.properties:
        emit_interface(root, root_name)
        return "\n\n".join(interfaces)
    return f"export type {_pascal_case(root_name)} = {ts_type(root, root_name)};"


def _py_field_name(key: str) -> tuple[str, str | None]:
    sanitized = re.sub(r"[^0-9a-zA-Z_]", "_", key)
    if not sanitized or sanitized[0].isdigit():
        sanitized = f"field_{sanitized}"
    if keyword.iskeyword(sanitized):
        sanitized += "_"
    alias = key if sanitized != key else None
    return sanitized, alias


def render_pydantic(root: SchemaNode, root_name: str = "Root") -> str:
    """Generate Pydantic v2 BaseModel classes from an inferred schema."""
    models: list[str] = []
    used_names: set[str] = set()
    needs_any = False
    needs_field = False

    def alloc_name(base: str) -> str:
        candidate = _pascal_case(base)
        if candidate not in used_names:
            used_names.add(candidate)
            return candidate
        i = 2
        while f"{candidate}{i}" in used_names:
            i += 1
        used_names.add(f"{candidate}{i}")
        return f"{candidate}{i}"

    def py_type(node: SchemaNode, hint: str) -> str:
        nonlocal needs_any
        non_null = sorted(t for t in node.types if t != "null")
        parts: list[str] = []
        if "integer" in non_null and "number" in non_null:
            non_null = [t for t in non_null if t != "integer"]
        for t in non_null:
            if t == "integer":
                parts.append("int")
            elif t == "number":
                parts.append("float")
            elif t == "string":
                parts.append("str")
            elif t == "boolean":
                parts.append("bool")
            elif t == "array":
                if node.items and node.items.types:
                    parts.append(f"list[{py_type(node.items, f'{hint}Item')}]")
                else:
                    needs_any = True
                    parts.append("list[Any]")
            elif t == "object":
                if node.properties:
                    parts.append(emit_model(node, hint))
                else:
                    needs_any = True
                    parts.append("dict[str, Any]")
        if not parts:
            needs_any = True
            return "Any | None"
        joined = " | ".join(parts)
        if "null" in node.types:
            joined += " | None"
        return joined

    def emit_model(node: SchemaNode, hint: str) -> str:
        nonlocal needs_field
        name = alloc_name(hint)
        parent_total = node.count - node.null_count
        lines = [f"class {name}(BaseModel):"]
        if not node.properties:
            lines.append("    pass")
        for key, child in node.properties.items():
            py_name, alias = _py_field_name(key)
            optional = child.count < parent_total or "null" in child.types
            t_str = py_type(child, key)
            if optional and not t_str.endswith("| None"):
                t_str += " | None"
            if alias is not None:
                needs_field = True
                default_arg = "default=None, " if optional else ""
                lines.append(
                    f"    {py_name}: {t_str} = Field({default_arg}alias={alias!r})"
                )
            elif optional:
                lines.append(f"    {py_name}: {t_str} = None")
            else:
                lines.append(f"    {py_name}: {t_str}")
        models.append("\n".join(lines))
        return name

    if root.properties:
        emit_model(root, root_name)
    else:
        t_str = py_type(root, root_name)
        models.append(f"class {_pascal_case(root_name)}(BaseModel):\n    value: {t_str}")

    imports = ["from __future__ import annotations", ""]
    if needs_any:
        imports.append("from typing import Any")
    pydantic_imports = "BaseModel, Field" if needs_field else "BaseModel"
    imports.append(f"from pydantic import {pydantic_imports}")
    return "\n".join(imports) + "\n\n\n" + "\n\n\n".join(models)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="json-xray",
        description="Inspect JSON/JSONL schemas and generate TypeScript or Pydantic v2 models.",
    )
    parser.add_argument(
        "file",
        nargs="?",
        help="Path to a JSON or JSONL file (use '-' or pipe stdin if omitted).",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--ts",
        action="store_true",
        help="Output TypeScript interface definitions.",
    )
    mode.add_argument(
        "--pydantic",
        action="store_true",
        help="Output Pydantic v2 BaseModel classes.",
    )
    parser.add_argument(
        "--name",
        default="Root",
        help="Root type/model name for --ts or --pydantic (default: Root).",
    )
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser


def _read_input(args: argparse.Namespace) -> str:
    if args.file and args.file != "-":
        path = Path(args.file)
        if not path.is_file():
            sys.exit(f"error: file not found: {args.file}")
        return path.read_text(encoding="utf-8")
    if not sys.stdin.isatty():
        return sys.stdin.read()
    sys.exit("error: provide a JSON/JSONL file path or pipe data via stdin.")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    raw = _read_input(args)
    records, fmt = load_records(raw)
    schema = infer_schema(records)

    if args.ts:
        print(render_typescript(schema, root_name=args.name))
    elif args.pydantic:
        print(render_pydantic(schema, root_name=args.name))
    else:
        print(render_table(schema, len(records), fmt))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
