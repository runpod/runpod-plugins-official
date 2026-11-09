"""Unit tests for the pure helpers in scripts/test_endpoint.py (no network, no openai SDK)."""

import importlib.util
import pathlib
import types
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "test_endpoint.py"
spec = importlib.util.spec_from_file_location("test_endpoint", SCRIPT)
te = importlib.util.module_from_spec(spec)
spec.loader.exec_module(te)


class ReasoningOf(unittest.TestCase):
    def test_reads_reasoning(self):
        self.assertEqual(te.reasoning_of(types.SimpleNamespace(reasoning="think")), "think")

    def test_falls_back_to_reasoning_content(self):
        self.assertEqual(te.reasoning_of(types.SimpleNamespace(reasoning_content="old")), "old")

    def test_reasoning_wins_over_reasoning_content(self):
        obj = types.SimpleNamespace(reasoning="new", reasoning_content="old")
        self.assertEqual(te.reasoning_of(obj), "new")

    def test_empty_when_absent_or_none(self):
        self.assertEqual(te.reasoning_of(types.SimpleNamespace()), "")
        self.assertEqual(te.reasoning_of(types.SimpleNamespace(reasoning=None, reasoning_content=None)), "")


class ToolCallOk(unittest.TestCase):
    def test_valid_call(self):
        self.assertTrue(te.tool_call_ok("get_weather", '{"city": "Reykjavik"}'))

    def test_city_match_is_case_insensitive_substring(self):
        self.assertTrue(te.tool_call_ok("get_weather", '{"city": "reykjavik, Iceland", "unit": "c"}'))

    def test_malformed_json(self):
        self.assertFalse(te.tool_call_ok("get_weather", "not JSON: Reykjavik"))

    def test_none_arguments(self):
        self.assertFalse(te.tool_call_ok("get_weather", None))

    def test_wrong_key(self):
        self.assertFalse(te.tool_call_ok("get_weather", '{"wrong_key": "Reykjavik"}'))

    def test_non_object_json(self):
        self.assertFalse(te.tool_call_ok("get_weather", '["Reykjavik"]'))

    def test_non_string_city(self):
        self.assertFalse(te.tool_call_ok("get_weather", '{"city": 42}'))

    def test_wrong_function(self):
        self.assertFalse(te.tool_call_ok("get_time", '{"city": "Reykjavik"}'))


if __name__ == "__main__":
    unittest.main()
