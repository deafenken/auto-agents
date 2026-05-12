"""Minimal YAML dump/load for the flat task.yaml schema.

Supports exactly what state-contract.md uses:
  - scalar key: value pairs at top level (str / int / float / bool / null)
  - nested dict (one level) with two-space indent
  - block scalar `key: |` followed by ≥2-space-indented lines

Not a general YAML parser. Round-trip with our own dump → load is the contract.
"""
from __future__ import annotations

import json
import re
from pathlib import Path


def _dump_scalar(v) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)
    raise TypeError(f"unsupported scalar: {type(v).__name__}")


def dump(d: dict) -> str:
    """Serialize a flat dict (one level of nested dict allowed) into our YAML
    subset. Block-scalar (|) is used for multi-line strings or strings > 100
    chars."""
    lines: list[str] = []
    for k, v in d.items():
        if isinstance(v, dict):
            lines.append(f"{k}:")
            for sk, sv in v.items():
                lines.append(f"  {sk}: {_dump_scalar(sv)}")
        elif isinstance(v, str) and ("\n" in v or len(v) > 100):
            lines.append(f"{k}: |")
            for line in v.splitlines():
                lines.append(f"  {line}")
        else:
            lines.append(f"{k}: {_dump_scalar(v)}")
    return "\n".join(lines) + "\n"


def _parse_scalar(s: str):
    s = s.strip()
    if s == "" or s == "~" or s == "null":
        return None
    low = s.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    # JSON handles quoted strings, ints, floats, true/false (lowercase)
    try:
        return json.loads(s)
    except (json.JSONDecodeError, ValueError):
        return s  # unquoted string


def load(text: str) -> dict:
    """Parse our YAML subset. Round-trips with dump()."""
    data: dict = {}
    current_dict_key: str | None = None
    block_key: str | None = None
    block_lines: list[str] = []
    block_indent: int | None = None

    def _flush_block():
        nonlocal block_key, block_lines, block_indent
        if block_key is not None:
            data[block_key] = "\n".join(block_lines).rstrip("\n")
            block_key = None
            block_lines = []
            block_indent = None

    for raw in text.splitlines():
        # block-scalar accumulation
        if block_key is not None:
            if raw.strip() == "":
                block_lines.append("")
                continue
            indent = len(raw) - len(raw.lstrip(" "))
            if block_indent is None:
                # first non-empty line establishes indent
                block_indent = indent
            if indent >= block_indent and indent > 0:
                block_lines.append(raw[block_indent:])
                continue
            else:
                _flush_block()
                # fall through to process this line as a fresh key

        if not raw.strip() or raw.lstrip().startswith("#"):
            continue

        # nested dict entry?
        if raw.startswith("  ") and current_dict_key is not None:
            sk, _, sv = raw.strip().partition(":")
            data[current_dict_key][sk.strip()] = _parse_scalar(sv)
            continue

        # top-level entry
        k, _, v = raw.partition(":")
        k = k.strip()
        v = v.strip()
        if v == "|":
            block_key = k
            block_lines = []
            block_indent = None
            current_dict_key = None
            continue
        if v == "":
            data[k] = {}
            current_dict_key = k
            continue
        current_dict_key = None
        data[k] = _parse_scalar(v)

    _flush_block()
    return data


# Convenience wrappers
def dump_path(path: Path, d: dict) -> None:
    path.write_text(dump(d), encoding="utf-8")


def load_path(path: Path) -> dict:
    return load(path.read_text(encoding="utf-8"))
