# json-xray

A fast, zero-dependency Python CLI that inspects any JSON or JSONL file (or stdin), infers its schema with field types, null/missing rates, and sample values, and generates **TypeScript interfaces** or **Pydantic v2 models**.

## Features

- Auto-detects **JSON** (object or array) and **JSONL** (newline-delimited JSON) from files or `stdin`.
- Displays a crisp schema summary table with **field paths**, **types**, **null/missing rates**, and **sample values**.
- `--ts`: Generates clean **TypeScript `interface`** definitions (including nested objects and optional/nullable fields).
- `--pydantic`: Generates **Pydantic v2 `BaseModel`** classes using modern Python 3.11+ union syntax (`X | None`).
- Zero external runtime dependencies.

## Installation

```bash
uv tool install .
```

Or run directly without installing:

```bash
uv run json-xray --help
```

## Usage

```bash
# Inspect a JSON or JSONL file
json-xray events.jsonl

# Generate TypeScript interfaces
json-xray users.json --ts --name User

# Generate Pydantic v2 models from stdin
cat payload.json | json-xray --pydantic --name Payload
```

## License

MIT
