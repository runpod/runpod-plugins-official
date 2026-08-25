from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from apply_model_metadata import (  # noqa: E402
    ApplyError,
    _validate_url,
    apply_manifest_to_document,
    write_new_workflow,
)
from inventory_workflow_models import build_inventory  # noqa: E402


HF_REVISION = "a" * 40


def hf_url(filename: str) -> str:
    return f"https://huggingface.co/example/models/resolve/{HF_REVISION}/{filename}"


def manifest_for(workflow: dict, resolutions: dict[str, dict]) -> dict:
    inventory = build_inventory(workflow)
    by_name = {item["filename"]: item for item in inventory["requirements"]}
    models = []
    for filename, resolution in resolutions.items():
        item = {
            "ambiguous": False,
            "directory": resolution["directory"],
            "filename": filename,
            "requirement_id": by_name[filename]["requirement_id"],
            "reviewed": True,
            "url": resolution.get("url", hf_url(filename)),
            "verified": True,
        }
        if "sha256" in resolution:
            item["sha256"] = resolution["sha256"]
        models.append(item)
    return {
        "models": models,
        "schema_version": 1,
        "workflow_sha256": inventory["workflow_sha256"],
    }


class InventoryTests(unittest.TestCase):
    def test_ui_nodes_nested_subgraphs_and_metadata_are_stable(self) -> None:
        workflow = {
            "definitions": {
                "subgraphs": [
                    {
                        "id": "subgraph-one",
                        "nodes": [
                            {
                                "id": 7,
                                "type": "VAELoader",
                                "widgets_values": ["nested-vae.safetensors"],
                            }
                        ],
                    }
                ]
            },
            "models": [
                {
                    "directory": "checkpoints",
                    "name": "base.safetensors",
                    "url": hf_url("base.safetensors"),
                }
            ],
            "nodes": [
                {
                    "id": 1,
                    "properties": {"keep": "unchanged"},
                    "type": "CheckpointLoaderSimple",
                    "widgets_values": ["base.safetensors"],
                },
                {
                    "id": 2,
                    "properties": {
                        "models": [
                            {
                                "directory": "loras",
                                "name": "metadata-only.safetensors",
                                "url": hf_url("metadata-only.safetensors"),
                            }
                        ]
                    },
                    "type": "LoraLoader",
                    "widgets_values": ["style.safetensors"],
                },
            ],
        }

        first = build_inventory(workflow, source_name="workflow.json")
        second = build_inventory(copy.deepcopy(workflow), source_name="workflow.json")
        self.assertEqual(first, second)
        self.assertEqual(first["workflow_format"], "ui")
        self.assertEqual(first["summary"]["nodes_scanned"], 3)
        requirements = {item["filename"]: item for item in first["requirements"]}
        self.assertEqual(
            set(requirements),
            {
                "base.safetensors",
                "metadata-only.safetensors",
                "nested-vae.safetensors",
                "style.safetensors",
            },
        )
        self.assertEqual(requirements["base.safetensors"]["metadata_status"], "complete")
        self.assertEqual(requirements["style.safetensors"]["directory_hints"], ["loras"])
        self.assertEqual(requirements["nested-vae.safetensors"]["directory_hints"], ["vae"])

    def test_api_input_names_provide_directory_hints(self) -> None:
        workflow = {
            "3": {
                "class_type": "LoraLoader",
                "inputs": {
                    "lora_name": "styles/ink.safetensors",
                    "model": ["1", 0],
                },
            }
        }
        inventory = build_inventory(workflow)
        self.assertEqual(inventory["workflow_format"], "api")
        self.assertEqual(inventory["requirements"][0]["filename"], "ink.safetensors")
        self.assertEqual(inventory["requirements"][0]["directory_hints"], ["loras"])
        occurrence = inventory["requirements"][0]["occurrences"][0]
        self.assertEqual(occurrence["node_id"], "3")
        self.assertEqual(occurrence["node_path"], "/3")

    def test_non_model_strings_and_traversal_are_not_candidates(self) -> None:
        workflow = {
            "nodes": [
                {
                    "id": 1,
                    "type": "CheckpointLoaderSimple",
                    "widgets_values": [
                        "not-a-model.png",
                        "../escape.safetensors",
                        "C:\\models\\absolute.safetensors",
                        "normal.safetensors",
                    ],
                }
            ]
        }
        names = [item["filename"] for item in build_inventory(workflow)["requirements"]]
        self.assertEqual(names, ["normal.safetensors"])

    def test_model_like_text_and_unsupported_extensions_are_warnings(self) -> None:
        workflow = {
            "nodes": [
                {
                    "id": 1,
                    "type": "CLIPTextEncode",
                    "widgets_values": ["describe x.safetensors"],
                },
                {
                    "id": 2,
                    "type": "UnetLoaderGGUF",
                    "widgets_values": ["model.gguf"],
                },
            ]
        }
        inventory = build_inventory(workflow)
        self.assertEqual(inventory["requirements"], [])
        self.assertEqual(
            {warning["code"] for warning in inventory["warnings"]},
            {
                "unqualified_model_like_string",
                "unsupported_runpoddirect_extension",
            },
        )

    def test_generic_loader_and_note_fields_are_not_model_requirements(self) -> None:
        workflow = {
            "1": {
                "class_type": "ImageLoader",
                "inputs": {"caption": "photo.safetensors"},
            },
            "2": {
                "class_type": "CLIPTextEncode",
                "inputs": {"model_notes": "draft.safetensors"},
            },
            "3": {
                "class_type": "DataLoader",
                "inputs": {"source": "table.pt"},
            },
        }
        inventory = build_inventory(workflow)
        self.assertEqual(inventory["requirements"], [])
        self.assertEqual(len(inventory["warnings"]), 3)
        self.assertEqual(
            {warning["code"] for warning in inventory["warnings"]},
            {"unqualified_model_like_string"},
        )

    def test_same_filename_in_distinct_consumers_has_distinct_requirements(self) -> None:
        workflow = {
            "nodes": [
                {
                    "id": 1,
                    "type": "CheckpointLoaderSimple",
                    "widgets_values": ["same.safetensors"],
                },
                {
                    "id": 2,
                    "type": "LoraLoader",
                    "widgets_values": ["same.safetensors"],
                },
            ]
        }
        inventory = build_inventory(workflow)
        requirements = inventory["requirements"]
        self.assertEqual(len(requirements), 2)
        self.assertNotEqual(requirements[0]["requirement_id"], requirements[1]["requirement_id"])
        by_node = {
            requirement["occurrences"][0]["node_id"]: requirement
            for requirement in requirements
        }
        manifest = {
            "schema_version": 1,
            "workflow_sha256": inventory["workflow_sha256"],
            "models": [
                {
                    "ambiguous": False,
                    "directory": "checkpoints",
                    "filename": "same.safetensors",
                    "requirement_id": by_node["1"]["requirement_id"],
                    "reviewed": True,
                    "url": hf_url("same.safetensors"),
                    "verified": True,
                },
                {
                    "ambiguous": False,
                    "directory": "loras",
                    "filename": "same.safetensors",
                    "requirement_id": by_node["2"]["requirement_id"],
                    "reviewed": True,
                    "url": (
                        "https://huggingface.co/another/artifact/resolve/"
                        f"{'b' * 40}/same.safetensors"
                    ),
                    "verified": True,
                },
            ],
        }
        output, applied = apply_manifest_to_document(workflow, manifest)
        self.assertEqual(applied, ["same.safetensors", "same.safetensors"])
        first = output["nodes"][0]["properties"]["models"][0]
        second = output["nodes"][1]["properties"]["models"][0]
        self.assertEqual(first["directory"], "checkpoints")
        self.assertEqual(second["directory"], "loras")
        self.assertNotEqual(first["url"], second["url"])

    def test_subfoldered_ui_selection_is_reported_and_not_flattened(self) -> None:
        workflow = {
            "nodes": [
                {
                    "id": 1,
                    "type": "LoraLoader",
                    "widgets_values": ["styles/ink.safetensors"],
                }
            ]
        }
        inventory = build_inventory(workflow)
        requirement = inventory["requirements"][0]
        self.assertTrue(requirement["subfoldered"])
        self.assertEqual(
            requirement["occurrences"][0]["selected_value"],
            "styles/ink.safetensors",
        )
        manifest = {
            "models": [
                {
                    "ambiguous": False,
                    "directory": "loras",
                    "filename": "ink.safetensors",
                    "requirement_id": requirement["requirement_id"],
                    "reviewed": True,
                    "url": hf_url("ink.safetensors"),
                    "verified": True,
                }
            ],
            "schema_version": 1,
            "workflow_sha256": inventory["workflow_sha256"],
        }
        with self.assertRaisesRegex(ApplyError, "subfolder"):
            apply_manifest_to_document(workflow, manifest)

    def test_unsafe_existing_metadata_url_is_partial(self) -> None:
        unsafe_urls = {
            "attacker_suffix_host": (
                "https://huggingface.co.attacker.example/example/models/resolve/"
                f"{HF_REVISION}/base.safetensors"
            ),
            "plain_http": (
                "http://huggingface.co/example/models/resolve/"
                f"{HF_REVISION}/base.safetensors"
            ),
            "ip_literal_host": (
                f"https://192.0.2.1/example/models/resolve/{HF_REVISION}/base.safetensors"
            ),
            "userinfo_credentials": (
                f"https://user:secret@huggingface.co/example/models/resolve/"
                f"{HF_REVISION}/base.safetensors"
            ),
            "credential_query": (
                "https://huggingface.co/example/models/resolve/"
                f"{HF_REVISION}/base.safetensors?token=abc123"
            ),
            "unparseable_ipv6_brackets": "https://[::1/base.safetensors",
        }
        for label, url in unsafe_urls.items():
            with self.subTest(label=label):
                workflow = {
                    "nodes": [
                        {
                            "id": 1,
                            "properties": {
                                "models": [
                                    {
                                        "directory": "checkpoints",
                                        "name": "base.safetensors",
                                        "url": url,
                                    }
                                ]
                            },
                            "type": "CheckpointLoaderSimple",
                            "widgets_values": ["base.safetensors"],
                        }
                    ]
                }
                inventory = build_inventory(workflow)
                self.assertEqual(
                    inventory["existing_metadata"][0]["issues"],
                    ["unsafe_url"],
                )
                self.assertEqual(
                    inventory["requirements"][0]["metadata_status"],
                    "partial",
                )


class ApplyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workflow = {
            "last_node_id": 2,
            "links": [[1, 1, 0, 2, 0, "MODEL"]],
            "nodes": [
                {
                    "id": 1,
                    "pos": [10, 20],
                    "type": "CheckpointLoaderSimple",
                    "widgets_values": ["base.safetensors"],
                },
                {
                    "id": 2,
                    "type": "LoraLoader",
                    "widgets_values": ["style.safetensors"],
                },
            ],
        }

    def test_applies_node_metadata_and_preserves_graph_fields(self) -> None:
        original = copy.deepcopy(self.workflow)
        manifest = manifest_for(
            self.workflow,
            {
                "base.safetensors": {
                    "directory": "checkpoints",
                    "sha256": "b" * 64,
                },
                "style.safetensors": {
                    "directory": "loras",
                    "url": "https://civitai.com/api/download/models/12345",
                },
            },
        )
        output, applied = apply_manifest_to_document(self.workflow, manifest)

        self.assertEqual(self.workflow, original)
        self.assertEqual(applied, ["base.safetensors", "style.safetensors"])
        self.assertEqual(output["links"], original["links"])
        self.assertEqual(output["nodes"][0]["pos"], original["nodes"][0]["pos"])
        self.assertNotIn("models", output)
        checkpoint_metadata = output["nodes"][0]["properties"]["models"][0]
        lora_metadata = output["nodes"][1]["properties"]["models"][0]
        self.assertEqual(checkpoint_metadata["name"], "base.safetensors")
        self.assertEqual(lora_metadata["name"], "style.safetensors")
        self.assertEqual(checkpoint_metadata["hash"], "b" * 64)
        self.assertEqual(checkpoint_metadata["hash_type"], "SHA256")

    def test_pure_api_workflow_is_inventory_only(self) -> None:
        workflow = {
            "9": {
                "class_type": "UNETLoader",
                "inputs": {"unet_name": "flux.safetensors", "weight_dtype": "default"},
            }
        }
        manifest = manifest_for(
            workflow,
            {"flux.safetensors": {"directory": "diffusion_models"}},
        )
        with self.assertRaisesRegex(ApplyError, "API prompt JSON can be inventoried"):
            apply_manifest_to_document(workflow, manifest)

    def test_refuses_stale_unreviewed_ambiguous_and_unsafe_resolutions(self) -> None:
        good = manifest_for(
            self.workflow,
            {
                "base.safetensors": {"directory": "checkpoints"},
                "style.safetensors": {"directory": "loras"},
            },
        )
        cases = []

        stale = copy.deepcopy(good)
        stale["workflow_sha256"] = "0" * 64
        cases.append(stale)

        unreviewed = copy.deepcopy(good)
        unreviewed["models"][0]["reviewed"] = False
        cases.append(unreviewed)

        ambiguous = copy.deepcopy(good)
        ambiguous["models"][0]["ambiguous"] = True
        cases.append(ambiguous)

        unsafe_host = copy.deepcopy(good)
        unsafe_host["models"][0]["url"] = (
            f"https://huggingface.co.evil.example/example/resolve/{HF_REVISION}/base.safetensors"
        )
        cases.append(unsafe_host)

        traversal = copy.deepcopy(good)
        traversal["models"][0]["directory"] = "../checkpoints"
        cases.append(traversal)

        unpinned = copy.deepcopy(good)
        unpinned["models"][0]["url"] = (
            "https://huggingface.co/example/models/resolve/main/base.safetensors"
        )
        cases.append(unpinned)

        for case in cases:
            with self.subTest(case=case):
                with self.assertRaises(ApplyError):
                    apply_manifest_to_document(self.workflow, case)

    def test_filename_case_must_match_loader_exactly(self) -> None:
        workflow = {
            "nodes": [
                {
                    "id": 1,
                    "type": "CheckpointLoaderSimple",
                    "widgets_values": ["Base.safetensors"],
                }
            ]
        }
        inventory = build_inventory(workflow)
        manifest = {
            "models": [
                {
                    "ambiguous": False,
                    "directory": "checkpoints",
                    "filename": "base.safetensors",
                    "requirement_id": inventory["requirements"][0]["requirement_id"],
                    "reviewed": True,
                    "url": hf_url("base.safetensors"),
                    "verified": True,
                }
            ],
            "schema_version": 1,
            "workflow_sha256": inventory["workflow_sha256"],
        }
        with self.assertRaisesRegex(ApplyError, "filename does not match"):
            apply_manifest_to_document(workflow, manifest)

    def test_invalid_existing_hash_type_is_not_complete(self) -> None:
        workflow = {
            "nodes": [
                {
                    "id": 1,
                    "properties": {
                        "models": [
                            {
                                "directory": "checkpoints",
                                "hash": "c" * 64,
                                "hash_type": "md5",
                                "name": "base.safetensors",
                                "url": hf_url("base.safetensors"),
                            }
                        ]
                    },
                    "type": "CheckpointLoaderSimple",
                    "widgets_values": ["base.safetensors"],
                }
            ]
        }
        inventory = build_inventory(workflow)
        self.assertEqual(inventory["requirements"][0]["metadata_status"], "partial")
        self.assertIn("invalid_hash_type", inventory["existing_metadata"][0]["issues"])
        empty_manifest = {
            "models": [],
            "schema_version": 1,
            "workflow_sha256": inventory["workflow_sha256"],
        }
        with self.assertRaisesRegex(ApplyError, "unresolved models"):
            apply_manifest_to_document(workflow, empty_manifest)

    def test_existing_metadata_name_case_mismatch_requires_reviewed_replacement(self) -> None:
        workflow = {
            "nodes": [
                {
                    "id": 1,
                    "properties": {
                        "models": [
                            {
                                "directory": "checkpoints",
                                "name": "base.safetensors",
                                "url": hf_url("base.safetensors"),
                            }
                        ]
                    },
                    "type": "CheckpointLoaderSimple",
                    "widgets_values": ["Base.safetensors"],
                }
            ]
        }
        inventory = build_inventory(workflow)
        self.assertEqual(len(inventory["requirements"]), 1)
        requirement = inventory["requirements"][0]
        self.assertEqual(requirement["filename"], "Base.safetensors")
        self.assertEqual(requirement["metadata_status"], "partial")
        self.assertIn(
            "name_mismatch_with_loader",
            inventory["existing_metadata"][0]["issues"],
        )
        manifest = manifest_for(
            workflow,
            {
                "Base.safetensors": {
                    "directory": "checkpoints",
                    "url": hf_url("Base.safetensors"),
                }
            },
        )
        with self.assertRaisesRegex(ApplyError, "replace_existing=true"):
            apply_manifest_to_document(workflow, manifest)
        manifest["models"][0]["replace_existing"] = True
        output, _ = apply_manifest_to_document(workflow, manifest)
        self.assertEqual(
            output["nodes"][0]["properties"]["models"],
            [
                {
                    "directory": "checkpoints",
                    "name": "Base.safetensors",
                    "url": hf_url("Base.safetensors"),
                }
            ],
        )

    def test_existing_metadata_directory_mismatch_cannot_satisfy_loader(self) -> None:
        workflow = {
            "nodes": [
                {
                    "id": 1,
                    "properties": {
                        "models": [
                            {
                                "directory": "loras",
                                "name": "base.safetensors",
                                "url": hf_url("base.safetensors"),
                            }
                        ]
                    },
                    "type": "CheckpointLoaderSimple",
                    "widgets_values": ["base.safetensors"],
                }
            ]
        }
        inventory = build_inventory(workflow)
        requirement = inventory["requirements"][0]
        self.assertEqual(requirement["directory_hints"], ["checkpoints"])
        self.assertFalse(requirement["directory_ambiguous"])
        self.assertEqual(requirement["metadata_status"], "partial")
        self.assertIn(
            "directory_mismatch_with_loader",
            inventory["existing_metadata"][0]["issues"],
        )
        empty_manifest = {
            "models": [],
            "schema_version": 1,
            "workflow_sha256": inventory["workflow_sha256"],
        }
        with self.assertRaisesRegex(ApplyError, "unresolved models"):
            apply_manifest_to_document(workflow, empty_manifest)

    def test_flattened_existing_metadata_cannot_satisfy_non_simple_selection(self) -> None:
        for selected in (" base.safetensors ", "styles/base.safetensors"):
            with self.subTest(selected=selected):
                workflow = {
                    "nodes": [
                        {
                            "id": 1,
                            "properties": {
                                "models": [
                                    {
                                        "directory": "checkpoints",
                                        "name": "base.safetensors",
                                        "url": hf_url("base.safetensors"),
                                    }
                                ]
                            },
                            "type": "CheckpointLoaderSimple",
                            "widgets_values": [selected],
                        }
                    ]
                }
                inventory = build_inventory(workflow)
                requirement = next(
                    item
                    for item in inventory["requirements"]
                    if any(
                        occurrence.get("source") != "metadata"
                        for occurrence in item["occurrences"]
                    )
                )
                empty_manifest = {
                    "models": [],
                    "schema_version": 1,
                    "workflow_sha256": inventory["workflow_sha256"],
                }
                self.assertTrue(
                    requirement["selection_mismatch"] or requirement["subfoldered"]
                )
                with self.assertRaisesRegex(ApplyError, "unresolved models"):
                    apply_manifest_to_document(workflow, empty_manifest)

    def test_manifest_must_resolve_every_missing_requirement(self) -> None:
        incomplete = manifest_for(
            self.workflow,
            {"base.safetensors": {"directory": "checkpoints"}},
        )
        with self.assertRaisesRegex(ApplyError, "style.safetensors"):
            apply_manifest_to_document(self.workflow, incomplete)

    def test_existing_safe_metadata_can_satisfy_requirement(self) -> None:
        workflow = copy.deepcopy(self.workflow)
        workflow["models"] = [
            {
                "directory": "loras",
                "name": "style.safetensors",
                "url": hf_url("style.safetensors"),
            }
        ]
        manifest = manifest_for(
            workflow,
            {"base.safetensors": {"directory": "checkpoints"}},
        )
        output, applied = apply_manifest_to_document(workflow, manifest)
        self.assertEqual(applied, ["base.safetensors"])
        self.assertEqual([item["name"] for item in output["models"]], ["style.safetensors"])
        self.assertEqual(
            output["nodes"][0]["properties"]["models"][0]["name"],
            "base.safetensors",
        )

    def test_hf_branch_url_requires_and_accepts_reviewed_sha256(self) -> None:
        manifest = manifest_for(
            self.workflow,
            {
                "base.safetensors": {
                    "directory": "checkpoints",
                    "sha256": "d" * 64,
                    "url": (
                        "https://huggingface.co/example/models/resolve/"
                        "main/base.safetensors?download=true"
                    ),
                },
                "style.safetensors": {"directory": "loras"},
            },
        )
        output, applied = apply_manifest_to_document(self.workflow, manifest)
        self.assertEqual(applied, ["base.safetensors", "style.safetensors"])
        self.assertEqual(
            output["nodes"][0]["properties"]["models"][0]["hash"],
            "d" * 64,
        )

    def test_replaces_only_metadata_associated_with_target_consumer(self) -> None:
        workflow = {
            "nodes": [
                {
                    "id": 1,
                    "properties": {
                        "models": [
                            {
                                "directory": "checkpoints",
                                "name": "same.safetensors",
                                "url": hf_url("same.safetensors"),
                            }
                        ]
                    },
                    "type": "CheckpointLoaderSimple",
                    "widgets_values": ["same.safetensors"],
                },
                {
                    "id": 2,
                    "properties": {
                        "models": [
                            {
                                "directory": "loras",
                                "name": "same.safetensors",
                                "url": (
                                    "https://huggingface.co/second/repo/resolve/"
                                    f"{'c' * 40}/same.safetensors"
                                ),
                            }
                        ]
                    },
                    "type": "LoraLoader",
                    "widgets_values": ["same.safetensors"],
                },
            ]
        }
        inventory = build_inventory(workflow)
        by_node = {
            item["occurrences"][0]["node_id"]: item
            for item in inventory["requirements"]
        }
        replacement_url = (
            "https://huggingface.co/reviewed/repo/resolve/"
            f"{'d' * 40}/same.safetensors"
        )
        manifest = {
            "models": [
                {
                    "ambiguous": False,
                    "directory": "checkpoints",
                    "filename": "same.safetensors",
                    "requirement_id": by_node["1"]["requirement_id"],
                    "reviewed": True,
                    "url": replacement_url,
                    "verified": True,
                }
            ],
            "schema_version": 1,
            "workflow_sha256": inventory["workflow_sha256"],
        }
        with self.assertRaisesRegex(ApplyError, "replace_existing=true"):
            apply_manifest_to_document(workflow, manifest)
        manifest["models"][0]["replace_existing"] = True
        output, _ = apply_manifest_to_document(workflow, manifest)
        first_url = output["nodes"][0]["properties"]["models"][0]["url"]
        second_url = output["nodes"][1]["properties"]["models"][0]["url"]
        self.assertEqual(first_url, replacement_url)
        self.assertEqual(second_url, workflow["nodes"][1]["properties"]["models"][0]["url"])

    def test_file_writer_never_overwrites_input_or_existing_output(self) -> None:
        manifest = manifest_for(
            self.workflow,
            {
                "base.safetensors": {"directory": "checkpoints"},
                "style.safetensors": {"directory": "loras"},
            },
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workflow_path = root / "workflow.json"
            manifest_path = root / "manifest.json"
            output_path = root / "repaired.json"
            workflow_path.write_text(json.dumps(self.workflow), encoding="utf-8")
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            with self.assertRaisesRegex(ApplyError, "must not overwrite"):
                write_new_workflow(workflow_path, manifest_path, workflow_path)

            applied = write_new_workflow(workflow_path, manifest_path, output_path)
            self.assertEqual(applied, ["base.safetensors", "style.safetensors"])
            with self.assertRaisesRegex(ApplyError, "existing output"):
                write_new_workflow(workflow_path, manifest_path, output_path)

    def test_file_writer_validates_before_publishing_final_output(self) -> None:
        workflow = self.workflow
        manifest = manifest_for(
            workflow,
            {
                "base.safetensors": {"directory": "checkpoints"},
                "style.safetensors": {"directory": "loras"},
            },
        )
        initial_inventory = build_inventory(workflow)
        failed_inventory = copy.deepcopy(initial_inventory)
        failed_inventory["summary"]["unresolved_requirements"] = 1
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workflow_path = root / "workflow.json"
            manifest_path = root / "manifest.json"
            output_path = root / "must-not-exist.repaired.json"
            workflow_path.write_text(json.dumps(workflow), encoding="utf-8")
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            with patch(
                "apply_model_metadata.build_inventory",
                side_effect=[initial_inventory, failed_inventory],
            ):
                with self.assertRaisesRegex(ApplyError, "failed validation"):
                    write_new_workflow(workflow_path, manifest_path, output_path)
            self.assertFalse(output_path.exists())

    def test_file_writer_publishes_complete_workflow_with_empty_manifest(self) -> None:
        initial_manifest = manifest_for(
            self.workflow,
            {
                "base.safetensors": {"directory": "checkpoints"},
                "style.safetensors": {"directory": "loras"},
            },
        )
        complete_workflow, _ = apply_manifest_to_document(
            self.workflow,
            initial_manifest,
        )
        complete_inventory = build_inventory(complete_workflow)
        empty_manifest = {
            "models": [],
            "schema_version": 1,
            "workflow_sha256": complete_inventory["workflow_sha256"],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workflow_path = root / "complete.json"
            manifest_path = root / "empty-manifest.json"
            output_path = root / "complete.repaired.json"
            workflow_path.write_text(json.dumps(complete_workflow), encoding="utf-8")
            manifest_path.write_text(json.dumps(empty_manifest), encoding="utf-8")

            applied = write_new_workflow(workflow_path, manifest_path, output_path)

            self.assertEqual(applied, [])
            self.assertEqual(
                json.loads(output_path.read_text(encoding="utf-8")),
                complete_workflow,
            )
            self.assertEqual(
                json.loads(workflow_path.read_text(encoding="utf-8")),
                complete_workflow,
            )

    def test_file_writer_can_publish_partial_workflow_without_touching_source(self) -> None:
        partial_manifest = manifest_for(
            self.workflow,
            {"base.safetensors": {"directory": "checkpoints"}},
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workflow_path = root / "workflow.json"
            manifest_path = root / "partial-manifest.json"
            output_path = root / "workflow.repaired.json"
            workflow_path.write_text(json.dumps(self.workflow), encoding="utf-8")
            manifest_path.write_text(json.dumps(partial_manifest), encoding="utf-8")

            applied = write_new_workflow(
                workflow_path,
                manifest_path,
                output_path,
                allow_unresolved=True,
            )

            self.assertEqual(applied, ["base.safetensors"])
            self.assertTrue(output_path.exists())
            self.assertEqual(
                build_inventory(
                    json.loads(output_path.read_text(encoding="utf-8"))
                )["summary"]["unresolved_requirements"],
                1,
            )
            self.assertEqual(
                json.loads(workflow_path.read_text(encoding="utf-8")),
                self.workflow,
            )

    def test_partial_output_removes_known_invalid_metadata(self) -> None:
        workflow = {
            "nodes": [
                {
                    "id": 1,
                    "properties": {
                        "models": [
                            {
                                "directory": "checkpoints",
                                "hash": "c" * 64,
                                "hash_type": "md5",
                                "name": "base.safetensors",
                                "url": hf_url("base.safetensors"),
                            }
                        ]
                    },
                    "type": "CheckpointLoaderSimple",
                    "widgets_values": ["base.safetensors"],
                }
            ]
        }
        inventory = build_inventory(workflow)
        manifest = {
            "models": [],
            "schema_version": 1,
            "workflow_sha256": inventory["workflow_sha256"],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workflow_path = root / "workflow.json"
            manifest_path = root / "manifest.json"
            output_path = root / "workflow.repaired.json"
            workflow_path.write_text(json.dumps(workflow), encoding="utf-8")
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            write_new_workflow(
                workflow_path,
                manifest_path,
                output_path,
                allow_unresolved=True,
            )

            output = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(output["nodes"][0]["properties"]["models"], [])
            self.assertEqual(
                json.loads(workflow_path.read_text(encoding="utf-8")),
                workflow,
            )

    def test_hf_mutable_revision_rejects_dot_segments(self) -> None:
        url = (
            "https://huggingface.co/example/models/resolve/"
            "{revision}/base.safetensors"
        )
        for revision in (".", "..", "%2e%2e", "%2E%2E"):
            with self.subTest(revision=revision):
                with self.assertRaisesRegex(ApplyError, "unsafe revision"):
                    _validate_url(
                        url.format(revision=revision),
                        "base.safetensors",
                        allow_mutable_hf_revision=True,
                    )
        branch_url = url.format(revision="feature-branch_1.2")
        self.assertEqual(
            _validate_url(
                branch_url,
                "base.safetensors",
                allow_mutable_hf_revision=True,
            ),
            branch_url,
        )

    def test_identical_existing_metadata_is_kept_verbatim(self) -> None:
        existing = {
            "directory": "checkpoints",
            "name": "base.safetensors",
            "note": "picked by the reviewer",
            "size": 123456789,
            "url": hf_url("base.safetensors"),
        }
        workflow = {
            "nodes": [
                {
                    "id": 1,
                    "properties": {"models": [existing]},
                    "type": "CheckpointLoaderSimple",
                    "widgets_values": ["base.safetensors"],
                }
            ]
        }
        manifest = manifest_for(
            workflow,
            {"base.safetensors": {"directory": "checkpoints"}},
        )
        output, applied = apply_manifest_to_document(workflow, manifest)
        self.assertEqual(applied, ["base.safetensors"])
        entries = output["nodes"][0]["properties"]["models"]
        self.assertEqual(len(entries), 1)
        self.assertEqual(list(entries[0].items()), list(existing.items()))


class CliRoundTripTests(unittest.TestCase):
    def test_cli_always_outputs_valid_ui_workflow_when_models_are_unresolved(self) -> None:
        workflow = {
            "nodes": [
                {
                    "id": 1,
                    "type": "CheckpointLoaderSimple",
                    "widgets_values": ["unknown.safetensors"],
                }
            ]
        }
        inventory = build_inventory(workflow)
        manifest = {
            "models": [],
            "schema_version": 1,
            "workflow_sha256": inventory["workflow_sha256"],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workflow_path = root / "workflow.json"
            manifest_path = root / "manifest.json"
            output_path = root / "workflow.repaired.json"
            workflow_path.write_text(json.dumps(workflow), encoding="utf-8")
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(SCRIPT_DIR / "apply_model_metadata.py"),
                    str(workflow_path),
                    str(manifest_path),
                    "--output",
                    str(output_path),
                    "--allow-unresolved",
                ],
                capture_output=True,
                check=False,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "partial")
            self.assertEqual(payload["unresolved_requirements"], 1)
            self.assertEqual(payload["output"], str(output_path.resolve()))
            self.assertTrue(output_path.exists())
            self.assertEqual(
                json.loads(workflow_path.read_text(encoding="utf-8")),
                workflow,
            )

    def test_inventory_apply_and_reinventory_through_cli(self) -> None:
        workflow = {
            "nodes": [
                {
                    "id": 1,
                    "type": "CheckpointLoaderSimple",
                    "widgets_values": ["aurora-v1.safetensors"],
                }
            ]
        }
        baseline_bytecode = {
            path.resolve() for path in SCRIPT_DIR.rglob("*.pyc")
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workflow_path = root / "workflow.json"
            inventory_path = root / "inventory.json"
            manifest_path = root / "manifest.json"
            repaired_path = root / "workflow.repaired.json"
            repaired_inventory_path = root / "inventory.repaired.json"
            workflow_path.write_text(json.dumps(workflow), encoding="utf-8")

            inventory_result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(SCRIPT_DIR / "inventory_workflow_models.py"),
                    str(workflow_path),
                    "--output",
                    str(inventory_path),
                ],
                capture_output=True,
                check=False,
                text=True,
            )
            self.assertEqual(inventory_result.returncode, 0, inventory_result.stderr)
            inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
            requirement = inventory["requirements"][0]
            manifest = {
                "models": [
                    {
                        "ambiguous": False,
                        "directory": "checkpoints",
                        "filename": "aurora-v1.safetensors",
                        "requirement_id": requirement["requirement_id"],
                        "reviewed": True,
                        "sha256": "e" * 64,
                        "url": hf_url("aurora-v1.safetensors"),
                        "verified": True,
                    }
                ],
                "schema_version": 1,
                "workflow_sha256": inventory["workflow_sha256"],
            }
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            apply_result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(SCRIPT_DIR / "apply_model_metadata.py"),
                    str(workflow_path),
                    str(manifest_path),
                    "--output",
                    str(repaired_path),
                ],
                capture_output=True,
                check=False,
                text=True,
            )
            self.assertEqual(apply_result.returncode, 0, apply_result.stderr)
            self.assertEqual(
                json.loads(apply_result.stdout)["applied_models"],
                ["aurora-v1.safetensors"],
            )
            self.assertEqual(
                json.loads(apply_result.stdout)["output"],
                str(repaired_path.resolve()),
            )
            self.assertEqual(json.loads(apply_result.stdout)["status"], "complete")
            self.assertEqual(
                json.loads(apply_result.stdout)["unresolved_requirements"],
                0,
            )

            reinventory_result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(SCRIPT_DIR / "inventory_workflow_models.py"),
                    str(repaired_path),
                    "--output",
                    str(repaired_inventory_path),
                ],
                capture_output=True,
                check=False,
                text=True,
            )
            self.assertEqual(
                reinventory_result.returncode,
                0,
                reinventory_result.stderr,
            )
            repaired_inventory = json.loads(
                repaired_inventory_path.read_text(encoding="utf-8")
            )
            repaired = json.loads(repaired_path.read_text(encoding="utf-8"))
            original = json.loads(workflow_path.read_text(encoding="utf-8"))
            self.assertNotIn("properties", original["nodes"][0])
            self.assertEqual(
                repaired["nodes"][0]["properties"]["models"][0]["hash_type"],
                "SHA256",
            )
            self.assertEqual(
                repaired_inventory["summary"]["unresolved_requirements"],
                0,
            )

        self.assertEqual(
            {path.resolve() for path in SCRIPT_DIR.rglob("*.pyc")},
            baseline_bytecode,
        )

    def test_cli_refuses_to_publish_unsafe_preexisting_metadata_url(self) -> None:
        workflow = {
            "nodes": [
                {
                    "id": 1,
                    "properties": {
                        "models": [
                            {
                                "directory": "checkpoints",
                                "name": "base.safetensors",
                                "url": (
                                    "https://huggingface.co.attacker.example/example/"
                                    f"models/resolve/{HF_REVISION}/base.safetensors"
                                ),
                            }
                        ]
                    },
                    "type": "CheckpointLoaderSimple",
                    "widgets_values": ["base.safetensors"],
                }
            ]
        }
        inventory = build_inventory(workflow)
        manifest = {
            "models": [],
            "schema_version": 1,
            "workflow_sha256": inventory["workflow_sha256"],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workflow_path = root / "workflow.json"
            manifest_path = root / "manifest.json"
            output_path = root / "workflow.repaired.json"
            workflow_path.write_text(json.dumps(workflow), encoding="utf-8")
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(SCRIPT_DIR / "apply_model_metadata.py"),
                    str(workflow_path),
                    str(manifest_path),
                    "--output",
                    str(output_path),
                ],
                capture_output=True,
                check=False,
                text=True,
            )

            self.assertEqual(result.returncode, 2)
            self.assertTrue(result.stderr.startswith("error:"))
            self.assertIn("unresolved models: base.safetensors", result.stderr)
            self.assertNotIn("Traceback", result.stderr)
            self.assertFalse(output_path.exists())
            self.assertEqual(
                json.loads(workflow_path.read_text(encoding="utf-8")),
                workflow,
            )

    def test_cli_allow_unresolved_strips_unsafe_preexisting_metadata_url(self) -> None:
        workflow = {
            "nodes": [
                {
                    "id": 1,
                    "properties": {
                        "models": [
                            {
                                "directory": "checkpoints",
                                "name": "base.safetensors",
                                "url": (
                                    "https://huggingface.co.attacker.example/example/"
                                    f"models/resolve/{HF_REVISION}/base.safetensors"
                                ),
                            }
                        ]
                    },
                    "type": "CheckpointLoaderSimple",
                    "widgets_values": ["base.safetensors"],
                }
            ]
        }
        inventory = build_inventory(workflow)
        manifest = {
            "models": [],
            "schema_version": 1,
            "workflow_sha256": inventory["workflow_sha256"],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workflow_path = root / "workflow.json"
            manifest_path = root / "manifest.json"
            output_path = root / "workflow.repaired.json"
            workflow_path.write_text(json.dumps(workflow), encoding="utf-8")
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(SCRIPT_DIR / "apply_model_metadata.py"),
                    str(workflow_path),
                    str(manifest_path),
                    "--output",
                    str(output_path),
                    "--allow-unresolved",
                ],
                capture_output=True,
                check=False,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["applied_models"], [])
            self.assertEqual(payload["status"], "partial")
            self.assertEqual(payload["unresolved_requirements"], 1)
            raw_output = output_path.read_text(encoding="utf-8")
            self.assertNotIn("attacker", raw_output)
            self.assertEqual(
                json.loads(raw_output)["nodes"][0]["properties"]["models"],
                [],
            )
            self.assertEqual(
                json.loads(workflow_path.read_text(encoding="utf-8")),
                workflow,
            )

    def test_inventory_cli_rejects_non_finite_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workflow_path = root / "workflow.json"
            for constant in ("NaN", "Infinity", "-Infinity", "1e400"):
                with self.subTest(constant=constant):
                    workflow_path.write_text(
                        '{"nodes": [], "value": ' + constant + "}",
                        encoding="utf-8",
                    )
                    result = subprocess.run(
                        [
                            sys.executable,
                            "-B",
                            str(SCRIPT_DIR / "inventory_workflow_models.py"),
                            str(workflow_path),
                        ],
                        capture_output=True,
                        check=False,
                        text=True,
                    )
                    self.assertEqual(result.returncode, 2)
                    self.assertTrue(result.stderr.startswith("error:"))
                    self.assertIn("non-finite", result.stderr)
                    self.assertNotIn("Traceback", result.stderr)

    def test_inventory_cli_requires_existing_output_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workflow_path = root / "workflow.json"
            workflow_path.write_text(json.dumps({"nodes": []}), encoding="utf-8")
            missing_dir = root / "no-such-dir"

            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(SCRIPT_DIR / "inventory_workflow_models.py"),
                    str(workflow_path),
                    "--output",
                    str(missing_dir / "report.json"),
                ],
                capture_output=True,
                check=False,
                text=True,
            )

            self.assertEqual(result.returncode, 2)
            self.assertTrue(result.stderr.startswith("error:"))
            self.assertIn("output directory does not exist", result.stderr)
            self.assertNotIn("Traceback", result.stderr)
            self.assertFalse(missing_dir.exists())


if __name__ == "__main__":
    unittest.main()
