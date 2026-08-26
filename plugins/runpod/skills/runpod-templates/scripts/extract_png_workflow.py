#!/usr/bin/env python3
"""Extract embedded ComfyUI workflow or prompt JSON from a PNG without Pillow."""

from __future__ import annotations

import argparse
import json
import math
import os
import struct
import sys
import zlib
from pathlib import Path
from typing import Any, BinaryIO


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
TEXT_CHUNK_TYPES = {b"tEXt", b"zTXt", b"iTXt"}
JSON_TEXT_KEYS = ("workflow", "prompt")
MAX_PNG_BYTES = 1024 * 1024 * 1024
MAX_PNG_CHUNK_BYTES = (1 << 31) - 1
MAX_TEXT_CHUNK_BYTES = 32 * 1024 * 1024
MAX_TEXT_VALUE_BYTES = 64 * 1024 * 1024
MAX_TOTAL_TEXT_CHUNK_BYTES = len(JSON_TEXT_KEYS) * MAX_TEXT_CHUNK_BYTES
MAX_TOTAL_TEXT_VALUE_BYTES = len(JSON_TEXT_KEYS) * MAX_TEXT_VALUE_BYTES
MAX_CHUNKS = 100_000
MAX_JSON_DEPTH = 256


class PngWorkflowError(ValueError):
    """Raised when PNG metadata cannot be extracted safely."""


def _read_exact(handle: BinaryIO, length: int, context: str) -> bytes:
    value = handle.read(length)
    if len(value) != length:
        raise PngWorkflowError(f"truncated PNG while reading {context}")
    return value


def _decode_keyword(raw: bytes) -> tuple[str, bytes]:
    keyword_raw, separator, remainder = raw.partition(b"\x00")
    if not separator or not 1 <= len(keyword_raw) <= 79:
        raise PngWorkflowError("PNG text chunk has an invalid keyword")
    if any(
        not (0x20 <= value <= 0x7E or 0xA1 <= value <= 0xFF)
        for value in keyword_raw
    ):
        raise PngWorkflowError("PNG text keyword contains a non-printing character")
    if keyword_raw.startswith(b" ") or keyword_raw.endswith(b" ") or b"  " in keyword_raw:
        raise PngWorkflowError("PNG text keyword contains invalid spacing")
    return keyword_raw.decode("latin-1"), remainder


def _decompress_limited(raw: bytes) -> bytes:
    decompressor = zlib.decompressobj()
    value = bytearray()
    pending = raw
    try:
        while pending:
            remaining = MAX_TEXT_VALUE_BYTES - len(value)
            decoded = decompressor.decompress(pending, remaining + 1)
            value.extend(decoded)
            if len(value) > MAX_TEXT_VALUE_BYTES:
                raise PngWorkflowError("decompressed PNG text exceeds the safety limit")
            pending = decompressor.unconsumed_tail
            if decompressor.eof:
                break
        if not decompressor.eof and not pending:
            remaining = MAX_TEXT_VALUE_BYTES - len(value)
            decoded = decompressor.decompress(b"", remaining + 1)
            value.extend(decoded)
    except zlib.error as exc:
        raise PngWorkflowError(f"invalid compressed PNG text: {exc}") from exc
    if len(value) > MAX_TEXT_VALUE_BYTES:
        raise PngWorkflowError("decompressed PNG text exceeds the safety limit")
    if not decompressor.eof or decompressor.unused_data or decompressor.unconsumed_tail:
        raise PngWorkflowError("compressed PNG text has an invalid stream boundary")
    return bytes(value)


def _decode_text_chunk(chunk_type: bytes, raw: bytes) -> tuple[str, str]:
    keyword, remainder = _decode_keyword(raw)
    if chunk_type == b"tEXt":
        return keyword, remainder.decode("latin-1")

    if chunk_type == b"zTXt":
        if not remainder or remainder[0] != 0:
            raise PngWorkflowError("zTXt chunk uses an unsupported compression method")
        return keyword, _decompress_limited(remainder[1:]).decode("latin-1")

    if len(remainder) < 2:
        raise PngWorkflowError("iTXt chunk is missing compression fields")
    compression_flag, compression_method = remainder[0], remainder[1]
    if compression_flag not in {0, 1} or (
        compression_flag == 1 and compression_method != 0
    ):
        raise PngWorkflowError("iTXt chunk uses unsupported compression fields")
    language, separator, remainder = remainder[2:].partition(b"\x00")
    if not separator:
        raise PngWorkflowError("iTXt chunk is missing the language separator")
    translated_keyword, separator, text_raw = remainder.partition(b"\x00")
    if not separator:
        raise PngWorkflowError("iTXt chunk is missing the translated-keyword separator")
    try:
        language.decode("ascii")
        translated_keyword.decode("utf-8")
        decoded = _decompress_limited(text_raw) if compression_flag else text_raw
        if len(decoded) > MAX_TEXT_VALUE_BYTES:
            raise PngWorkflowError("PNG text exceeds the safety limit")
        return keyword, decoded.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PngWorkflowError("iTXt fields are not valid ASCII/UTF-8") from exc


def read_png_text(
    path: Path, selected_keys: set[str] | None = None
) -> tuple[dict[str, str], set[str]]:
    """Read recognized PNG JSON text and list all valid text keywords."""

    capture_keys = set(JSON_TEXT_KEYS) if selected_keys is None else set(selected_keys)
    if not capture_keys.issubset(JSON_TEXT_KEYS):
        raise PngWorkflowError("selected PNG text key is not supported")

    try:
        if path.stat().st_size > MAX_PNG_BYTES:
            raise PngWorkflowError("PNG exceeds the input safety limit")
        handle = path.open("rb")
    except OSError as exc:
        raise PngWorkflowError(f"cannot read {path}: {exc}") from exc

    values: dict[str, str] = {}
    text_keys: set[str] = set()
    seen_json_keys: set[str] = set()
    total_captured = 0
    total_decoded = 0
    with handle:
        if _read_exact(handle, len(PNG_SIGNATURE), "signature") != PNG_SIGNATURE:
            raise PngWorkflowError("input is not a PNG file")

        saw_ihdr = False
        saw_idat = False
        saw_iend = False
        for chunk_index in range(MAX_CHUNKS):
            raw_length = handle.read(4)
            if not raw_length:
                break
            if len(raw_length) != 4:
                raise PngWorkflowError("truncated PNG chunk length")
            length = struct.unpack(">I", raw_length)[0]
            chunk_type = _read_exact(handle, 4, "chunk type")
            if length > MAX_PNG_CHUNK_BYTES:
                raise PngWorkflowError("PNG chunk exceeds the format length limit")
            if any(
                not (ord("A") <= value <= ord("Z") or ord("a") <= value <= ord("z"))
                for value in chunk_type
            ):
                raise PngWorkflowError("PNG chunk type contains a non-letter byte")
            if handle.tell() + length + 4 > MAX_PNG_BYTES:
                raise PngWorkflowError("PNG exceeds the input safety limit")
            if chunk_index == 0:
                if chunk_type != b"IHDR" or length != 13:
                    raise PngWorkflowError("PNG must begin with a 13-byte IHDR chunk")
                saw_ihdr = True
            elif chunk_type == b"IHDR":
                raise PngWorkflowError("PNG contains more than one IHDR chunk")
            if chunk_type == b"IDAT":
                saw_idat = True
            if chunk_type == b"IEND" and length != 0:
                raise PngWorkflowError("PNG IEND chunk must be empty")

            crc = zlib.crc32(chunk_type)
            remaining = length
            captured = bytearray()
            capture = False
            keyword: str | None = None
            if chunk_type in TEXT_CHUNK_TYPES:
                prefix_length = min(length, 80)
                prefix = _read_exact(handle, prefix_length, "text chunk keyword")
                crc = zlib.crc32(prefix, crc)
                remaining -= prefix_length
                keyword, _partial_remainder = _decode_keyword(prefix)
                text_keys.add(keyword)
                if keyword in JSON_TEXT_KEYS:
                    if keyword in seen_json_keys:
                        raise PngWorkflowError(
                            f"PNG contains duplicate {keyword!r} metadata"
                        )
                    seen_json_keys.add(keyword)
                capture = keyword in capture_keys
                if capture:
                    if length > MAX_TEXT_CHUNK_BYTES:
                        raise PngWorkflowError("PNG text chunk exceeds the safety limit")
                    total_captured += length
                    if total_captured > MAX_TOTAL_TEXT_CHUNK_BYTES:
                        raise PngWorkflowError(
                            "recognized PNG text exceeds the aggregate safety limit"
                        )
                    captured.extend(prefix)
            while remaining:
                block = _read_exact(handle, min(remaining, 64 * 1024), "chunk data")
                crc = zlib.crc32(block, crc)
                if capture:
                    captured.extend(block)
                remaining -= len(block)
            expected_crc = struct.unpack(">I", _read_exact(handle, 4, "chunk CRC"))[0]
            if crc & 0xFFFFFFFF != expected_crc:
                name = chunk_type.decode("latin-1", errors="replace")
                raise PngWorkflowError(f"PNG chunk {name!r} has an invalid CRC")

            if capture and keyword is not None:
                decoded_keyword, text = _decode_text_chunk(chunk_type, bytes(captured))
                if decoded_keyword != keyword:
                    raise PngWorkflowError("PNG text keyword changed while reading chunk")
                total_decoded += len(text.encode("utf-8"))
                if total_decoded > MAX_TOTAL_TEXT_VALUE_BYTES:
                    raise PngWorkflowError(
                        "decoded PNG text exceeds the aggregate safety limit"
                    )
                values[keyword] = text
            if chunk_type == b"IEND":
                saw_iend = True
                break
        else:
            raise PngWorkflowError("PNG contains too many chunks")

        if not saw_iend:
            raise PngWorkflowError("PNG is missing IEND")
        if not saw_ihdr or not saw_idat:
            raise PngWorkflowError("PNG is missing required image chunks")
        if handle.read(1):
            raise PngWorkflowError("PNG contains trailing data after IEND")
    return values, text_keys


def _check_json_depth(value: str) -> None:
    depth = 0
    in_string = False
    escaped = False
    for character in value:
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character in "[{":
            depth += 1
            if depth > MAX_JSON_DEPTH:
                raise PngWorkflowError("embedded JSON exceeds the nesting safety limit")
        elif character in "]}":
            depth -= 1


def _parse_embedded_json(key: str, raw: str) -> dict[str, Any]:
    _check_json_depth(raw)

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for name, value in pairs:
            if name in result:
                raise PngWorkflowError(
                    f"embedded {key!r} JSON contains duplicate key {name!r}"
                )
            result[name] = value
        return result

    def reject_constant(value: str) -> Any:
        raise PngWorkflowError(
            f"embedded {key!r} JSON contains non-finite number {value!r}"
        )

    def finite_float(value: str) -> float:
        parsed = float(value)
        if not math.isfinite(parsed):
            reject_constant(value)
        return parsed

    try:
        value = json.loads(
            raw,
            object_pairs_hook=reject_duplicates,
            parse_constant=reject_constant,
            parse_float=finite_float,
        )
    except PngWorkflowError:
        raise
    except (json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise PngWorkflowError(f"embedded {key!r} metadata is invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise PngWorkflowError(f"embedded {key!r} JSON root must be an object")
    return value


def embedded_json(
    path: Path, kind: str | None = None
) -> tuple[dict[str, Any], set[str]]:
    selected_keys = set(JSON_TEXT_KEYS) if kind is None else {kind}
    text_values, text_keys = read_png_text(path, selected_keys)
    parsed: dict[str, Any] = {}
    ordered_selected_keys = JSON_TEXT_KEYS if kind is None else (kind,)
    for key in ordered_selected_keys:
        if key not in text_values:
            continue
        parsed[key] = _parse_embedded_json(key, text_values[key])
    return parsed, text_keys


def _write_new_json(source: Path, output: Path, value: Any) -> None:
    source_resolved = source.resolve()
    output_resolved = output.resolve()
    if os.path.normcase(str(source_resolved)) == os.path.normcase(str(output_resolved)):
        raise PngWorkflowError("output path must not overwrite the source PNG")
    if output.exists():
        raise PngWorkflowError(f"refusing to overwrite existing output: {output}")
    if not output.parent.exists():
        raise PngWorkflowError(f"output directory does not exist: {output.parent}")
    try:
        rendered = (
            json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise PngWorkflowError(f"cannot serialize extracted JSON safely: {exc}") from exc
    created = False
    try:
        with output.open("xb") as handle:
            created = True
            handle.write(rendered)
    except OSError as exc:
        if created:
            try:
                output.unlink()
            except OSError:
                pass
        raise PngWorkflowError(f"cannot write {output}: {exc}") from exc


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect or extract ComfyUI JSON embedded in a PNG output image."
    )
    parser.add_argument("png", type=Path, help="ComfyUI-generated PNG")
    parser.add_argument(
        "--kind",
        choices=("workflow", "prompt"),
        default="workflow",
        help="embedded JSON record to extract (default: workflow)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        help="write the selected JSON record to a new file; omit to inspect only",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        parsed, text_keys = embedded_json(args.png, args.kind)
        if args.output:
            if args.kind not in parsed:
                available = ", ".join(
                    sorted(set(JSON_TEXT_KEYS).intersection(text_keys))
                ) or "none"
                raise PngWorkflowError(
                    f"PNG has no embedded {args.kind!r} JSON (available: {available})"
                )
            _write_new_json(args.png, args.output, parsed[args.kind])
        summary = {
            "available_json": sorted(set(JSON_TEXT_KEYS).intersection(text_keys)),
            "output": str(args.output) if args.output else None,
            "selected_kind": args.kind,
            "source": str(args.png),
            "text_keys": sorted(text_keys),
        }
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    except PngWorkflowError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
