"""Report/retry regressions with a torch double; these do not establish GPU support."""

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch


EXPECTED = [[5.0, 14.0, 23.0], [14.0, 50.0, 86.0], [23.0, 86.0, 149.0]]


class ProbeReports(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.tensor = MagicMock()
        self.tensor.__matmul__.return_value.cpu.return_value.tolist.return_value = EXPECTED
        self.torch = SimpleNamespace(
            __version__="test-double", __file__="/opt/mock/torch/__init__.py",
            float32="float32", cuda=SimpleNamespace(is_available=lambda: True),
            arange=MagicMock(),
        )
        self.torch.arange.return_value.reshape.return_value = self.tensor
        spec = importlib.util.spec_from_file_location("probe_fixture", Path(__file__).with_name("verify.py"))
        self.probe = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"torch": self.torch}):
            spec.loader.exec_module(self.probe)

    def run_probe(self, *args):
        with patch.object(sys, "argv", ["verify.py", *map(str, args)]), contextlib.redirect_stdout(io.StringIO()):
            self.probe.main()

    def test_repeated_runs_preserve_reports_and_user_data(self):
        sentinel = self.root / "user.txt"
        sentinel.write_text("keep my edits", encoding="utf-8")
        reports = self.root / "reports"
        self.run_probe("--device", "cpu", "--output-dir", reports)
        first = next(reports.glob("*.json"))
        original = first.read_bytes()
        self.run_probe("--device", "cpu", "--output-dir", reports)
        self.assertEqual(len(list(reports.glob("*.json"))), 2)
        self.assertEqual(first.read_bytes(), original)
        self.assertEqual(json.loads(original)["result"], EXPECTED)
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep my edits")

    def test_explicit_path_never_overwrites(self):
        report = self.root / "report.json"
        self.run_probe("--device", "cpu", "--output", report)
        original = report.read_bytes()
        with self.assertRaisesRegex(SystemExit, "output exists"):
            self.run_probe("--device", "cpu", "--output", report)
        self.assertEqual(report.read_bytes(), original)

    def test_missing_cuda_fails_without_cpu_fallback_or_report(self):
        self.torch.cuda.is_available = lambda: False
        with self.assertRaisesRegex(SystemExit, "CUDA is not available"):
            self.run_probe("--output-dir", self.root)
        self.torch.arange.assert_not_called()
        self.assertEqual(list(self.root.iterdir()), [])

    def test_incorrect_matrix_fails_without_report(self):
        self.tensor.__matmul__.return_value.cpu.return_value.tolist.return_value = [[0.0]]
        with self.assertRaisesRegex(SystemExit, "unexpected matrix result"):
            self.run_probe("--device", "cpu", "--output-dir", self.root)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_cuda_selection_remains_explicit_in_report(self):
        self.run_probe("--output-dir", self.root)
        self.torch.arange.assert_called_once_with(9, dtype="float32", device="cuda")
        report = json.loads(next(self.root.glob("*.json")).read_text(encoding="utf-8"))
        self.assertEqual(report["device"], "cuda")
        self.assertEqual(report["torch_path"], "/opt/mock/torch/__init__.py")


if __name__ == "__main__":
    unittest.main()
