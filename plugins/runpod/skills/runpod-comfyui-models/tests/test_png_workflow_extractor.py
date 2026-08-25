from __future__ import annotations

import json
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import extract_png_workflow as extractor  # noqa: E402
from apply_model_metadata import ApplyError, apply_manifest_to_document  # noqa: E402
from inventory_workflow_models import build_inventory  # noqa: E402


def png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(chunk_type)
    crc = zlib.crc32(data, crc) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", crc)


def png_bytes(*text_chunks: bytes) -> bytes:
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    image_data = zlib.compress(b"\x00\x00\x00\x00")
    return b"".join(
        (
            extractor.PNG_SIGNATURE,
            png_chunk(b"IHDR", ihdr),
            *text_chunks,
            png_chunk(b"IDAT", image_data),
            png_chunk(b"IEND", b""),
        )
    )


def text_chunk(keyword: str, value: str) -> bytes:
    return png_chunk(b"tEXt", keyword.encode("latin-1") + b"\x00" + value.encode("latin-1"))


def ztext_chunk(keyword: str, value: bytes) -> bytes:
    return png_chunk(
        b"zTXt", keyword.encode("latin-1") + b"\x00\x00" + zlib.compress(value)
    )


def itext_chunk(
    keyword: str,
    value: str,
    *,
    compressed: bool = False,
    compression_method: int = 0,
    translated_keyword: bytes = b"",
) -> bytes:
    text = value.encode("utf-8")
    if compressed:
        text = zlib.compress(text)
    return png_chunk(
        b"iTXt",
        keyword.encode("latin-1")
        + b"\x00"
        + bytes((int(compressed), compression_method))
        + b"en\x00"
        + translated_keyword
        + b"\x00"
        + text,
    )


class PngWorkflowExtractorTests(unittest.TestCase):
    def test_reads_comfyui_text_workflow_and_prompt(self) -> None:
        workflow = {"nodes": [{"id": 1, "type": "CheckpointLoaderSimple"}]}
        prompt = {"1": {"class_type": "CheckpointLoaderSimple", "inputs": {}}}
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "output.png"
            path.write_bytes(
                png_bytes(
                    text_chunk("workflow", json.dumps(workflow)),
                    text_chunk("prompt", json.dumps(prompt)),
                    text_chunk("parameters", "ignored but listed"),
                )
            )
            parsed, text_values = extractor.embedded_json(path)

        self.assertEqual(parsed, {"workflow": workflow, "prompt": prompt})
        self.assertEqual(set(text_values), {"workflow", "prompt", "parameters"})

    def test_reads_compressed_ztxt_and_itxt(self) -> None:
        workflow = {"nodes": []}
        prompt = {"1": {"class_type": "EmptyLatentImage", "inputs": {}}}
        ztxt = png_chunk(
            b"zTXt",
            b"prompt\x00\x00" + zlib.compress(json.dumps(prompt).encode("latin-1")),
        )
        itxt = png_chunk(
            b"iTXt",
            b"workflow\x00\x01\x00en\x00\x00"
            + zlib.compress(json.dumps(workflow).encode("utf-8")),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "output.png"
            path.write_bytes(png_bytes(ztxt, itxt))
            parsed, _ = extractor.embedded_json(path)

        self.assertEqual(parsed["workflow"], workflow)
        self.assertEqual(parsed["prompt"], prompt)

    def test_reads_uncompressed_itxt_unicode_and_ignores_method_byte(self) -> None:
        workflow = {"nodes": [], "extra": {"label": "zażółć 🚀"}}
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "output.png"
            path.write_bytes(
                png_bytes(
                    itext_chunk(
                        "workflow",
                        json.dumps(workflow, ensure_ascii=False),
                        compression_method=255,
                        translated_keyword="przepływ".encode("utf-8"),
                    )
                )
            )
            parsed, _ = extractor.embedded_json(path, "workflow")

        self.assertEqual(parsed["workflow"], workflow)

    def test_selected_workflow_is_not_blocked_by_invalid_prompt_json(self) -> None:
        workflow = {"nodes": [{"id": 1, "type": "CheckpointLoaderSimple"}]}
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "output.png"
            path.write_bytes(
                png_bytes(
                    text_chunk("prompt", "{"),
                    text_chunk("workflow", json.dumps(workflow)),
                )
            )
            parsed, keys = extractor.embedded_json(path, "workflow")
            self.assertEqual(parsed, {"workflow": workflow})
            self.assertEqual(keys, {"prompt", "workflow"})
            with self.assertRaisesRegex(extractor.PngWorkflowError, "invalid JSON"):
                extractor.embedded_json(path, "prompt")

    def test_selected_workflow_does_not_decompress_invalid_prompt(self) -> None:
        workflow = {"nodes": [{"id": 1, "type": "CheckpointLoaderSimple"}]}
        invalid_prompt = png_chunk(b"zTXt", b"prompt\x00\x00not-zlib")
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "output.png"
            path.write_bytes(
                png_bytes(
                    invalid_prompt,
                    text_chunk("workflow", json.dumps(workflow)),
                )
            )
            parsed, keys = extractor.embedded_json(path, "workflow")
            self.assertEqual(parsed, {"workflow": workflow})
            self.assertEqual(keys, {"prompt", "workflow"})
            with self.assertRaisesRegex(
                extractor.PngWorkflowError, "invalid compressed PNG text"
            ):
                extractor.embedded_json(path, "prompt")

    def test_prompt_only_remains_api_inventory_only(self) -> None:
        prompt = {
            "1": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": "base.safetensors"},
            }
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "output.png"
            path.write_bytes(png_bytes(text_chunk("prompt", json.dumps(prompt))))
            parsed, _ = extractor.embedded_json(path, "prompt")

        inventory = build_inventory(parsed["prompt"])
        self.assertEqual(inventory["workflow_format"], "api")
        manifest = {
            "models": [],
            "schema_version": 1,
            "workflow_sha256": inventory["workflow_sha256"],
        }
        with self.assertRaisesRegex(ApplyError, "API prompt JSON"):
            apply_manifest_to_document(parsed["prompt"], manifest)

    def test_rejects_bad_crc_and_conflicting_duplicate_metadata(self) -> None:
        good = text_chunk("workflow", json.dumps({"nodes": []}))
        bad_crc = good[:-1] + bytes([good[-1] ^ 0xFF])
        conflicting = text_chunk("workflow", json.dumps({"nodes": [{"id": 2}]}))
        cases = {
            "bad CRC": png_bytes(bad_crc),
            "conflicting duplicate": png_bytes(good, conflicting),
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            for name, value in cases.items():
                with self.subTest(name=name):
                    path = Path(temp_dir) / f"{name}.png"
                    path.write_bytes(value)
                    with self.assertRaises(extractor.PngWorkflowError):
                        extractor.read_png_text(path)

    def test_rejects_identical_and_cross_encoding_duplicate_metadata(self) -> None:
        value = json.dumps({"nodes": []})
        duplicate_cases = {
            "identical": (text_chunk("workflow", value), text_chunk("workflow", value)),
            "cross encoding": (
                text_chunk("workflow", value),
                ztext_chunk("workflow", value.encode("latin-1")),
            ),
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            for name, chunks in duplicate_cases.items():
                with self.subTest(name=name):
                    path = Path(temp_dir) / f"{name}.png"
                    path.write_bytes(png_bytes(*chunks))
                    with self.assertRaisesRegex(
                        extractor.PngWorkflowError, "duplicate 'workflow'"
                    ):
                        extractor.read_png_text(path)

    def test_rejects_compressed_text_expansion_over_limit(self) -> None:
        compressed = png_chunk(
            b"zTXt",
            b"workflow\x00\x00" + zlib.compress(b"x" * 129),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "output.png"
            path.write_bytes(png_bytes(compressed))
            with mock.patch.object(extractor, "MAX_TEXT_VALUE_BYTES", 128):
                with self.assertRaisesRegex(
                    extractor.PngWorkflowError, "safety limit"
                ):
                    extractor.read_png_text(path)

    def test_does_not_decompress_unrecognized_text(self) -> None:
        compressed = ztext_chunk("parameters", b"x" * 4096)
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "output.png"
            path.write_bytes(png_bytes(compressed))
            with mock.patch.object(extractor, "MAX_TEXT_VALUE_BYTES", 16):
                values, keys = extractor.read_png_text(path)

        self.assertEqual(values, {})
        self.assertEqual(keys, {"parameters"})

    def test_enforces_input_recognized_chunk_and_aggregate_limits(self) -> None:
        workflow = text_chunk("workflow", json.dumps({"nodes": []}))
        prompt = text_chunk("prompt", json.dumps({"1": {"class_type": "Test"}}))
        png = png_bytes(workflow, prompt)
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "output.png"
            path.write_bytes(png)
            with mock.patch.object(extractor, "MAX_PNG_BYTES", len(png) - 1):
                with self.assertRaisesRegex(
                    extractor.PngWorkflowError, "input safety limit"
                ):
                    extractor.read_png_text(path)
            with mock.patch.object(
                extractor, "MAX_TEXT_CHUNK_BYTES", len(b"workflow\x00")
            ):
                with self.assertRaisesRegex(
                    extractor.PngWorkflowError, "text chunk exceeds"
                ):
                    extractor.read_png_text(path)
            with mock.patch.object(
                extractor,
                "MAX_TOTAL_TEXT_CHUNK_BYTES",
                len(b"workflow\x00") + len(json.dumps({"nodes": []})),
            ):
                with self.assertRaisesRegex(
                    extractor.PngWorkflowError, "aggregate safety limit"
                ):
                    extractor.read_png_text(path)

    def test_rejects_invalid_itxt_translated_keyword_utf8(self) -> None:
        malformed = itext_chunk(
            "workflow",
            json.dumps({"nodes": []}),
            translated_keyword=b"\xff",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "output.png"
            path.write_bytes(png_bytes(malformed))
            with self.assertRaisesRegex(
                extractor.PngWorkflowError, "ASCII/UTF-8"
            ):
                extractor.read_png_text(path)

    def test_rejects_invalid_png_structure_and_trailing_data(self) -> None:
        ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
        image_data = zlib.compress(b"\x00\x00\x00\x00")
        cases = {
            "missing IDAT": b"".join(
                (
                    extractor.PNG_SIGNATURE,
                    png_chunk(b"IHDR", ihdr),
                    png_chunk(b"IEND", b""),
                )
            ),
            "nonempty IEND": b"".join(
                (
                    extractor.PNG_SIGNATURE,
                    png_chunk(b"IHDR", ihdr),
                    png_chunk(b"IDAT", image_data),
                    png_chunk(b"IEND", b"x"),
                )
            ),
            "trailing data": png_bytes() + b"trailing",
            "oversized declared chunk": b"".join(
                (
                    extractor.PNG_SIGNATURE,
                    png_chunk(b"IHDR", ihdr),
                    struct.pack(">I", 1 << 31),
                    b"abCD",
                )
            ),
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            for name, value in cases.items():
                with self.subTest(name=name):
                    path = Path(temp_dir) / f"{name}.png"
                    path.write_bytes(value)
                    with self.assertRaises(extractor.PngWorkflowError):
                        extractor.read_png_text(path)

    def test_strict_json_rejects_duplicates_nonfinite_and_deep_values(self) -> None:
        cases = {
            "duplicate": '{"nodes": [], "nodes": []}',
            "constant": '{"value": NaN}',
            "overflow": '{"value": 1e999}',
            "non-object": "[]",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            for name, value in cases.items():
                with self.subTest(name=name):
                    path = Path(temp_dir) / f"{name}.png"
                    path.write_bytes(png_bytes(text_chunk("workflow", value)))
                    with self.assertRaises(extractor.PngWorkflowError):
                        extractor.embedded_json(path, "workflow")

            deep_path = Path(temp_dir) / "deep.png"
            deep_path.write_bytes(
                png_bytes(text_chunk("workflow", '{"value": [[[0]]]}'))
            )
            with mock.patch.object(extractor, "MAX_JSON_DEPTH", 3):
                with self.assertRaisesRegex(
                    extractor.PngWorkflowError, "nesting safety limit"
                ):
                    extractor.embedded_json(deep_path, "workflow")

    def test_cli_writes_new_workflow_and_refuses_overwrite(self) -> None:
        workflow = {"nodes": [{"id": 3, "type": "VAELoader"}]}
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "output.png"
            output = root / "workflow.json"
            source.write_bytes(
                png_bytes(text_chunk("workflow", json.dumps(workflow)))
            )
            command = [
                sys.executable,
                "-B",
                str(SCRIPT_DIR / "extract_png_workflow.py"),
                str(source),
                "--output",
                str(output),
            ]
            first = subprocess.run(command, capture_output=True, check=False, text=True)
            second = subprocess.run(command, capture_output=True, check=False, text=True)

            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), workflow)
            self.assertEqual(second.returncode, 2)
            self.assertIn("refusing to overwrite", second.stderr)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), workflow)

    def test_writer_refuses_source_path_and_missing_parent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source.png"
            source.write_bytes(b"original")
            with self.assertRaisesRegex(
                extractor.PngWorkflowError, "must not overwrite"
            ):
                extractor._write_new_json(source, source, {"nodes": []})
            self.assertEqual(source.read_bytes(), b"original")
            with self.assertRaisesRegex(
                extractor.PngWorkflowError, "output directory does not exist"
            ):
                extractor._write_new_json(
                    source, root / "missing" / "workflow.json", {"nodes": []}
                )


if __name__ == "__main__":
    unittest.main()
