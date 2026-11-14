"""Tests for scan_cloud_usage.py. Standard library only, Python 3.9+.

Run from the repo root:
    python3 -B -m unittest discover -s plugins/runpod/skills/runpod-cloud-migrate/tests -p "test_*.py"
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "scan_cloud_usage.py"
REFERENCE = SCRIPT.parent.parent / "reference"
spec = importlib.util.spec_from_file_location("scan_cloud_usage", SCRIPT)
scanner = importlib.util.module_from_spec(spec)
sys.modules["scan_cloud_usage"] = scanner
spec.loader.exec_module(scanner)


def write(root: str, rel: str, text: str) -> None:
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def platforms(hits) -> set:
    return {h.platform for h in hits}


def kinds(hits, platform: str) -> set:
    return {h.kind for h in hits if h.platform == platform}


class ScanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def scan(self, **files: str):
        for rel, text in files.items():
            write(self.root, rel.replace("__", "/"), text)
        return scanner.scan(self.root)

    def test_one_signal_per_platform(self) -> None:
        cases = {
            "vast-ai": ("run.sh", "vastai create instance 123 --image img --disk 20\n"),
            "lambda": ("launch.py", 'URL = "https://cloud.lambda.ai/api/v1/instance-operations/launch"\n'),
            "coreweave": ("main.tf", 'resource "coreweave_cks_cluster" "c" {}\n'),
            "paperspace": ("ci.yml", "run: gradient deployments create --name x\n"),
            "modal": ("app.py", "import modal\napp = modal.App('x')\n"),
            "replicate": ("call.py", "import replicate\nout = replicate.run('a/b', input={})\n"),
            "baseten": ("deploy.sh", "truss push --publish\n"),
            "together-ai": ("llm.py", "from together import Together\nclient = Together()\n"),
            "fireworks-ai": ("llm.ts", 'const url = "https://api.fireworks.ai/inference/v1";\n'),
            "fal": ("img.py", "import fal_client\nfal_client.subscribe('fal-ai/flux/dev')\n"),
            "hugging-face": ("call.py", 'URL = "https://abc.us-east-1.aws.endpoints.huggingface.cloud/v1/"\n'),
            "aws": ("infer.py", 'rt = boto3.client("sagemaker-runtime")\n'),
            "google-cloud": ("infer.py", "from google.cloud import aiplatform\n"),
            "azure": ("infer.py", "from azure.ai.ml import MLClient\n"),
        }
        for slug, (name, text) in cases.items():
            with self.subTest(platform=slug), tempfile.TemporaryDirectory() as root:
                write(root, name, text)
                self.assertIn(slug, platforms(scanner.scan(root)))

    def test_every_playbook_platform_has_a_case_above(self) -> None:
        with_reference = {p.slug for p in scanner.PLATFORMS if p.reference and p.slug != "kubernetes"}
        self.assertEqual(len(with_reference), 14)

    def test_gpu_instance_types_and_iac(self) -> None:
        hits = self.scan(
            **{
                "infra__main.tf": (
                    'resource "aws_instance" "g" { instance_type = "g5.2xlarge" }\n'
                    'resource "aws_sagemaker_endpoint" "e" {}\n'
                    'resource "google_compute_instance" "v" { machine_type = "a2-highgpu-1g" }\n'
                    'resource "azurerm_linux_virtual_machine" "v" { size = "Standard_NC24ads_A100_v4" }\n'
                )
            }
        )
        self.assertEqual(platforms(hits), {"aws", "google-cloud", "azure"})
        self.assertEqual(kinds(hits, "aws"), {"config", "iac"})

    def test_cpu_instance_types_are_not_gpu_signals(self) -> None:
        hits = self.scan(**{"main.tf": 'instance_type = "m5.large"\nsize = "Standard_D4s_v5"\nmachine_type = "n2-standard-4"\n'})
        self.assertEqual(hits, [])

    def test_kubernetes_gpu_request(self) -> None:
        hits = self.scan(**{"k8s__deploy.yaml": "resources:\n  limits:\n    nvidia.com/gpu: 1\n"})
        self.assertEqual(platforms(hits), {"kubernetes"})

    def test_skipped_directories_and_lockfiles(self) -> None:
        hits = self.scan(
            **{
                "node_modules__x__a.py": "import modal\n",
                ".venv__lib__b.py": "import replicate\n",
                "package-lock.json": '{"replicate": "1.0.0"}\n',
                "src__ok.py": "import modal\n",
            }
        )
        self.assertEqual({h.path for h in hits}, {os.path.join("src", "ok.py")})

    def test_words_that_only_look_like_a_platform(self) -> None:
        hits = self.scan(
            **{
                "notes.py": (
                    "# a modal dialog, a lambda function, the fal of man\n"
                    "show_modal = True\n"
                    "handler = lambda event: event\n"
                    "together = a + b\n"
                    "replicate_count = 3\n"
                )
            }
        )
        self.assertEqual(hits, [])

    def test_cog_yaml_fires_on_filename(self) -> None:
        hits = self.scan(**{"cog.yaml": "build:\n  gpu: true\npredict: predict.py:Predictor\n"})
        self.assertEqual([(h.platform, h.kind, h.line) for h in hits], [("replicate", "config", 1)])

    def test_openai_base_url_and_existing_runpod_use(self) -> None:
        hits = self.scan(
            **{
                "llm.py": 'client = OpenAI(base_url="https://api.together.xyz/v1", api_key=key)\n',
                "worker.py": "import runpod\nrunpod.serverless.start({'handler': handler})\n",
            }
        )
        self.assertEqual(platforms(hits), {"together-ai", "openai-compatible", "runpod"})

    def test_credential_names_are_reported_without_values(self) -> None:
        hits = self.scan(**{".env.example": "REPLICATE_API_TOKEN=\nFAL_KEY=\n"})
        self.assertEqual(kinds(hits, "replicate"), {"credential"})
        self.assertEqual(kinds(hits, "fal"), {"credential"})

    def test_binary_and_oversized_files_are_skipped(self) -> None:
        with open(os.path.join(self.root, "blob.py"), "wb") as fh:
            fh.write(b"\x00\x01import modal\n")
        write(self.root, "big.py", "import modal\n" + "x = 1\n" * 200_000)
        self.assertEqual(scanner.scan(self.root), [])

    def test_platform_filter(self) -> None:
        for rel, text in {"a.py": "import modal\n", "b.py": "import replicate\n"}.items():
            write(self.root, rel, text)
        self.assertEqual(platforms(scanner.scan(self.root, ["modal"])), {"modal"})

    def test_cli_json_markdown_and_exit_codes(self) -> None:
        write(self.root, "a.py", "import modal\n")
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(scanner.main([self.root, "--json"]), 0)
        data = json.loads(out.getvalue())
        self.assertEqual(data["summary"][0]["platform"], "modal")
        self.assertEqual(data["summary"][0]["reference"], "reference/modal.md")
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(scanner.main([self.root]), 0)
        self.assertIn("| Modal | 1 | 1 | sdk (1) | reference/modal.md |", out.getvalue())
        self.assertEqual(scanner.main([os.path.join(self.root, "missing")]), 2)

    def test_empty_repo_says_to_ask(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out):
            scanner.main([self.root])
        self.assertIn("No platform signals found", out.getvalue())

    def test_every_reference_exists(self) -> None:
        for platform in scanner.PLATFORMS:
            if platform.reference:
                with self.subTest(platform=platform.slug):
                    self.assertTrue((SCRIPT.parent.parent / platform.reference).is_file(), platform.reference)

    def test_every_reference_file_has_a_platform(self) -> None:
        listed = {Path(p.reference).name for p in scanner.PLATFORMS if p.reference}
        on_disk = {p.name for p in REFERENCE.glob("*.md")} - {"runpod-targets.md", "data-transfer.md", "terraform.md"}
        self.assertEqual(on_disk - listed, set())


if __name__ == "__main__":
    unittest.main()
