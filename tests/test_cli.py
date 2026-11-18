"""Unit tests for json-xray CLI."""

from __future__ import annotations

from pathlib import Path

import pytest

from json_xray.cli import (
    infer_schema,
    load_records,
    main,
    render_pydantic,
    render_table,
    render_typescript,
)


def test_load_records_json_object() -> None:
    records, fmt = load_records('{"id": 1, "name": "Alice"}')
    assert fmt == "json"
    assert records == [{"id": 1, "name": "Alice"}]


def test_load_records_json_array() -> None:
    records, fmt = load_records('[{"id": 1}, {"id": 2}]')
    assert fmt == "json-array"
    assert len(records) == 2


def test_load_records_jsonl() -> None:
    raw = '{"id": 1, "ok": true}\n{"id": 2, "ok": false}\n'
    records, fmt = load_records(raw)
    assert fmt == "jsonl"
    assert len(records) == 2


def test_load_records_empty_exits() -> None:
    with pytest.raises(SystemExit):
        load_records("   \n  ")


def test_infer_schema_nested_and_nullable() -> None:
    records = [
        {"id": 1, "score": 9.5, "email": "a@example.com", "meta": {"role": "admin"}},
        {"id": 2, "score": 10, "email": None, "meta": {"role": "user", "active": True}},
    ]
    schema = infer_schema(records)
    assert schema.count == 2
    assert schema.properties["id"].types == {"integer"}
    assert schema.properties["score"].types == {"integer", "number"}
    assert schema.properties["email"].null_count == 1
    assert "null" in schema.properties["email"].types
    meta = schema.properties["meta"]
    assert meta.properties["role"].count == 2
    assert meta.properties["active"].count == 1


def test_render_table_summary() -> None:
    records = [
        {"id": 1, "email": "a@example.com"},
        {"id": 2, "email": None},
    ]
    schema = infer_schema(records)
    table = render_table(schema, len(records), "jsonl")
    assert "Format: jsonl | Records: 2 | Fields: 2" in table
    assert "email" in table
    assert "string?" in table
    assert "50.0%" in table


def test_render_typescript_nested_and_optional() -> None:
    records = [
        {"id": 1, "user": {"name": "Alice"}, "tags": ["a"]},
        {"id": 2, "user": {"name": "Bob", "nick": "b"}, "tags": [], "note": None},
    ]
    schema = infer_schema(records)
    ts = render_typescript(schema, root_name="Event")
    assert "export interface Event {" in ts
    assert "export interface User {" in ts
    assert "id: number;" in ts
    assert "nick?: string;" in ts
    assert "tags: string[];" in ts
    assert "note?: null;" in ts


def test_render_pydantic_models_and_aliases() -> None:
    records = [
        {"user-id": 1, "class": "A", "score": 1.5, "tags": ["x"]},
        {"user-id": 2, "class": "B", "score": 2, "tags": ["y"], "extra": None},
    ]
    schema = infer_schema(records)
    code = render_pydantic(schema, root_name="Record")
    assert "from pydantic import BaseModel, Field" in code
    assert "class Record(BaseModel):" in code
    assert "user_id: int = Field(alias='user-id')" in code
    assert "class_: str = Field(alias='class')" in code
    assert "score: float" in code
    assert "tags: list[str]" in code
    assert "extra: Any | None = None" in code


def test_cli_file_ts_and_pydantic(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    sample = tmp_path / "users.json"
    sample.write_text('[{"id": 1, "name": "Alice"}]', encoding="utf-8")

    assert main([str(sample), "--ts", "--name", "User"]) == 0
    ts_out = capsys.readouterr().out
    assert "export interface User {" in ts_out

    assert main([str(sample), "--pydantic", "--name", "User"]) == 0
    py_out = capsys.readouterr().out
    assert "class User(BaseModel):" in py_out
