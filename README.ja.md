# json-xray

[English](README.md) | **日本語**

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

任意の JSON / JSONL ファイル（または標準入力）を解析し、フィールドの型・null/欠損率・サンプル値を含むスキーマを推論して、**TypeScript のインターフェース**や **Pydantic v2 モデル**を生成できる、高速・依存関係ゼロの Python CLI ツールです。

## 特徴

- ファイルまたは `stdin` から **JSON**（オブジェクト／配列）と **JSONL**（改行区切り JSON）を自動判別します。
- **フィールドパス**、**型**、**null/欠損率**、**サンプル値**をまとめた見やすいスキーマ一覧表を表示します。
- `--ts`: ネストされたオブジェクトやオプショナル／nullable フィールドを含む、クリーンな **TypeScript `interface`** 定義を生成します。
- `--pydantic`: Python 3.11+ のモダンなユニオン構文（`X | None`）を用いた **Pydantic v2 `BaseModel`** クラスを生成します。
- 外部ランタイム依存関係ゼロ。

## インストール

```bash
uv tool install .
```

または、インストールせずに直接実行できます：

```bash
uv run json-xray --help
```

## 使い方

```bash
# JSON または JSONL ファイルを解析
json-xray events.jsonl

# TypeScript インターフェースを生成
json-xray users.json --ts --name User

# 標準入力から Pydantic v2 モデルを生成
cat payload.json | json-xray --pydantic --name Payload
```

## 出力例

```text
$ json-xray users.jsonl
Format: jsonl | Records: 2 | Fields: 4

Field  Type     Null/Missing  Sample
-----  -------  ------------  -------------------
id     integer          0.0%  1
name   string           0.0%  'Alice'
email  string?         50.0%  'alice@example.com'
tags   array            0.0%  ["admin"]
```

## ライセンス

MIT
