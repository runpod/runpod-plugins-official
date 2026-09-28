"""Table-driven unit tests for the pure helpers extracted from the two scripts.

Part 2 of the ComfyUI model-metadata refactor pulled several small, importable
private helpers out of ``inventory_workflow_models`` and ``apply_model_metadata``.
These functions are pure (no filesystem, no network), so each gets a CASES table
covering positive, negative, boundary and corner rows. Every case carries a
``description`` and an ``expected`` value — a concrete result, or an exception
type when the helper is meant to reject the input.
"""

from __future__ import annotations

import sys
import unittest
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from apply_model_metadata import (
    ApplyError,
    _eligible_requirements,
    _existing_entry_satisfies,
    _existing_matches_resolution,
    _plan_attachments,
    _validated_sha256,
)
from inventory_workflow_models import (
    InventoryError,
    NodeKind,
    RequirementAccumulator,
    _detect_format,
    _matching_consumers,
    _metadata_directory_hints,
    _metadata_status,
    _unique_occurrences,
    _validate_huggingface_path,
)

HF_REVISION = "a" * 40


def hf_url(filename: str, *, revision: str = HF_REVISION) -> str:
    return f"https://huggingface.co/example/models/resolve/{revision}/{filename}"


def _assert_expected(test: unittest.TestCase, expected: object, func: Callable[[], object]) -> None:
    """Assert ``func()`` equals ``expected``, or raises it when it is an exception type."""

    if isinstance(expected, type) and issubclass(expected, BaseException):
        with test.assertRaises(expected):
            func()
    else:
        test.assertEqual(func(), expected)


# --------------------------------------------------------------------------
# inventory_workflow_models._matching_consumers
# --------------------------------------------------------------------------


def _accumulator(specs: list[tuple[str, str, list[dict[str, Any]]]]) -> RequirementAccumulator:
    acc = RequirementAccumulator()
    for key, filename, occurrences in specs:
        for occurrence in occurrences:
            acc.add(key, filename, set(), occurrence)
    return acc


@dataclass(frozen=True)
class MatchingConsumersCase:
    description: str
    accumulator: RequirementAccumulator = field(compare=False)
    filename: str
    node_id: str | None
    metadata_node_path: str | None
    exact: bool
    expected: list[str]


_WIDGET = {"source": "widget", "node_path": "/nodes/0"}

MATCHING_CONSUMERS_CASES: list[MatchingConsumersCase] = [
    MatchingConsumersCase(
        description="positive: exact filename and matching node path",
        accumulator=_accumulator([("k1", "base.safetensors", [dict(_WIDGET)])]),
        filename="base.safetensors",
        node_id="0",
        metadata_node_path="/nodes/0",
        exact=True,
        expected=["k1"],
    ),
    MatchingConsumersCase(
        description="positive: node_id None matches any consumer regardless of path",
        accumulator=_accumulator([("k1", "base.safetensors", [dict(_WIDGET)])]),
        filename="base.safetensors",
        node_id=None,
        metadata_node_path=None,
        exact=True,
        expected=["k1"],
    ),
    MatchingConsumersCase(
        description="negative: filename does not match under exact",
        accumulator=_accumulator([("k1", "base.safetensors", [dict(_WIDGET)])]),
        filename="other.safetensors",
        node_id=None,
        metadata_node_path=None,
        exact=True,
        expected=[],
    ),
    MatchingConsumersCase(
        description="negative: case mismatch is rejected under exact",
        accumulator=_accumulator([("k1", "Base.safetensors", [dict(_WIDGET)])]),
        filename="base.safetensors",
        node_id=None,
        metadata_node_path=None,
        exact=True,
        expected=[],
    ),
    MatchingConsumersCase(
        description="corner: case mismatch matches under non-exact",
        accumulator=_accumulator([("k1", "Base.safetensors", [dict(_WIDGET)])]),
        filename="base.safetensors",
        node_id=None,
        metadata_node_path=None,
        exact=False,
        expected=["k1"],
    ),
    MatchingConsumersCase(
        description="negative: only metadata occurrences give no loader node path",
        accumulator=_accumulator(
            [("k1", "base.safetensors", [{"source": "metadata", "node_path": "/nodes/0"}])]
        ),
        filename="base.safetensors",
        node_id="0",
        metadata_node_path="/nodes/0",
        exact=True,
        expected=[],
    ),
    MatchingConsumersCase(
        description="negative: node_id set but its path is not among the consumer paths",
        accumulator=_accumulator([("k1", "base.safetensors", [dict(_WIDGET)])]),
        filename="base.safetensors",
        node_id="9",
        metadata_node_path="/nodes/9",
        exact=True,
        expected=[],
    ),
    MatchingConsumersCase(
        description="boundary: empty accumulator yields no matches",
        accumulator=_accumulator([]),
        filename="base.safetensors",
        node_id=None,
        metadata_node_path=None,
        exact=True,
        expected=[],
    ),
    MatchingConsumersCase(
        description="corner: two consumers share a filename and both match with node_id None",
        accumulator=_accumulator(
            [
                ("k1", "base.safetensors", [{"source": "widget", "node_path": "/nodes/0"}]),
                ("k2", "base.safetensors", [{"source": "widget", "node_path": "/nodes/1"}]),
            ]
        ),
        filename="base.safetensors",
        node_id=None,
        metadata_node_path=None,
        exact=True,
        expected=["k1", "k2"],
    ),
]


# --------------------------------------------------------------------------
# inventory_workflow_models._metadata_directory_hints
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class DirectoryHintsCase:
    description: str
    entry: dict[str, Any]
    expected: set[str]


DIRECTORY_HINTS_CASES: list[DirectoryHintsCase] = [
    DirectoryHintsCase(
        description="positive: a plain folder key becomes a single hint",
        entry={"directory": "loras"},
        expected={"loras"},
    ),
    DirectoryHintsCase(
        description="positive: surrounding whitespace is stripped",
        entry={"directory": "  loras  "},
        expected={"loras"},
    ),
    DirectoryHintsCase(
        description="corner: underscores and mixed case are allowed",
        entry={"directory": "text_encoders"},
        expected={"text_encoders"},
    ),
    DirectoryHintsCase(
        description="boundary: empty string yields no hint",
        entry={"directory": ""},
        expected=set(),
    ),
    DirectoryHintsCase(
        description="negative: a traversal-looking value is rejected",
        entry={"directory": "../evil"},
        expected=set(),
    ),
    DirectoryHintsCase(
        description="negative: an embedded space is rejected",
        entry={"directory": "a b"},
        expected=set(),
    ),
    DirectoryHintsCase(
        description="negative: a non-string directory yields no hint",
        entry={"directory": 5},
        expected=set(),
    ),
    DirectoryHintsCase(
        description="negative: a missing directory key yields no hint",
        entry={},
        expected=set(),
    ),
    DirectoryHintsCase(
        description="boundary: a 128-character name is at the length limit",
        entry={"directory": "a" * 128},
        expected={"a" * 128},
    ),
    DirectoryHintsCase(
        description="boundary: a 129-character name is over the length limit",
        entry={"directory": "a" * 129},
        expected=set(),
    ),
]


# --------------------------------------------------------------------------
# inventory_workflow_models._metadata_status
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class MetadataStatusCase:
    description: str
    entries: list[dict[str, Any]]
    expected: str


METADATA_STATUS_CASES: list[MetadataStatusCase] = [
    MetadataStatusCase(
        description="boundary: no metadata entries is missing",
        entries=[],
        expected="missing",
    ),
    MetadataStatusCase(
        description="positive: a single issue-free entry is complete",
        entries=[{"issues": []}],
        expected="complete",
    ),
    MetadataStatusCase(
        description="negative: a single entry with issues is partial",
        entries=[{"issues": ["invalid_hash"]}],
        expected="partial",
    ),
    MetadataStatusCase(
        description="corner: any issue-free entry makes the requirement complete",
        entries=[{"issues": ["invalid_hash"]}, {"issues": []}],
        expected="complete",
    ),
    MetadataStatusCase(
        description="negative: all entries carrying issues stays partial",
        entries=[{"issues": ["a"]}, {"issues": ["b"]}],
        expected="partial",
    ),
]


# --------------------------------------------------------------------------
# inventory_workflow_models._unique_occurrences
# --------------------------------------------------------------------------

_OCC_A = {"path": "/a", "source": "widget", "node_id": "1"}
_OCC_B = {"path": "/b", "source": "widget", "node_id": "1"}
_OCC_NO_PATH = {"source": "widget"}
_OCC_A_X = {"path": "/a", "source": "widget", "node_id": "1", "selected_value": "x"}
_OCC_A_Y = {"path": "/a", "source": "widget", "node_id": "1", "selected_value": "y"}


@dataclass(frozen=True)
class UniqueOccurrencesCase:
    description: str
    occurrences: list[dict[str, Any]]
    expected: list[dict[str, Any]]


UNIQUE_OCCURRENCES_CASES: list[UniqueOccurrencesCase] = [
    UniqueOccurrencesCase(
        description="boundary: no occurrences",
        occurrences=[],
        expected=[],
    ),
    UniqueOccurrencesCase(
        description="positive: a single occurrence is returned unchanged",
        occurrences=[dict(_OCC_A)],
        expected=[dict(_OCC_A)],
    ),
    UniqueOccurrencesCase(
        description="corner: identical duplicates collapse to one",
        occurrences=[dict(_OCC_A), dict(_OCC_A)],
        expected=[dict(_OCC_A)],
    ),
    UniqueOccurrencesCase(
        description="positive: distinct occurrences are sorted by path",
        occurrences=[dict(_OCC_B), dict(_OCC_A)],
        expected=[dict(_OCC_A), dict(_OCC_B)],
    ),
    UniqueOccurrencesCase(
        description="corner: a missing path sorts before a present one",
        occurrences=[dict(_OCC_A), dict(_OCC_NO_PATH)],
        expected=[dict(_OCC_NO_PATH), dict(_OCC_A)],
    ),
    UniqueOccurrencesCase(
        description="boundary: same sort key but distinct content keeps both, stably",
        occurrences=[dict(_OCC_A_X), dict(_OCC_A_Y)],
        expected=[dict(_OCC_A_X), dict(_OCC_A_Y)],
    ),
]


# --------------------------------------------------------------------------
# inventory_workflow_models._validate_huggingface_path
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class HuggingFacePathCase:
    description: str
    path_parts: list[str]
    filename: str | None
    allow_mutable: bool
    expected: object  # None on success, or InventoryError when rejected


HUGGINGFACE_PATH_CASES: list[HuggingFacePathCase] = [
    HuggingFacePathCase(
        description="positive: pinned commit with a matching filename",
        path_parts=["owner", "repo", "resolve", HF_REVISION, "model.safetensors"],
        filename="model.safetensors",
        allow_mutable=False,
        expected=None,
    ),
    HuggingFacePathCase(
        description="positive: pinned commit and no filename to check",
        path_parts=["owner", "repo", "resolve", HF_REVISION, "model.safetensors"],
        filename=None,
        allow_mutable=False,
        expected=None,
    ),
    HuggingFacePathCase(
        description="negative: no resolve segment",
        path_parts=["owner", "repo", "blob", HF_REVISION, "model.safetensors"],
        filename=None,
        allow_mutable=False,
        expected=InventoryError,
    ),
    HuggingFacePathCase(
        description="negative: resolve is not the third path segment",
        path_parts=["a", "b", "c", "resolve", HF_REVISION, "model.safetensors"],
        filename=None,
        allow_mutable=False,
        expected=InventoryError,
    ),
    HuggingFacePathCase(
        description="boundary: too few segments to name a file",
        path_parts=["owner", "repo", "resolve", HF_REVISION],
        filename=None,
        allow_mutable=False,
        expected=InventoryError,
    ),
    HuggingFacePathCase(
        description="negative: mutable revision without permission is rejected",
        path_parts=["owner", "repo", "resolve", "main", "model.safetensors"],
        filename="model.safetensors",
        allow_mutable=False,
        expected=InventoryError,
    ),
    HuggingFacePathCase(
        description="positive: mutable revision allowed when a SHA-256 binds the bytes",
        path_parts=["owner", "repo", "resolve", "main", "model.safetensors"],
        filename="model.safetensors",
        allow_mutable=True,
        expected=None,
    ),
    HuggingFacePathCase(
        description="corner: a dot-segment revision is unsafe even when mutable is allowed",
        path_parts=["owner", "repo", "resolve", ".", "model.safetensors"],
        filename="model.safetensors",
        allow_mutable=True,
        expected=InventoryError,
    ),
    HuggingFacePathCase(
        description="negative: a revision with an unsafe character is rejected",
        path_parts=["owner", "repo", "resolve", "bad rev", "model.safetensors"],
        filename="model.safetensors",
        allow_mutable=True,
        expected=InventoryError,
    ),
    HuggingFacePathCase(
        description="boundary: a 129-character revision exceeds the mutable length cap",
        path_parts=["owner", "repo", "resolve", "a" * 129, "model.safetensors"],
        filename="model.safetensors",
        allow_mutable=True,
        expected=InventoryError,
    ),
    HuggingFacePathCase(
        description="negative: URL filename does not match the manifest filename",
        path_parts=["owner", "repo", "resolve", HF_REVISION, "other.safetensors"],
        filename="model.safetensors",
        allow_mutable=False,
        expected=InventoryError,
    ),
    HuggingFacePathCase(
        description="corner: a nested subdirectory file under a pinned commit is accepted",
        path_parts=["owner", "repo", "resolve", HF_REVISION, "sub", "model.safetensors"],
        filename="model.safetensors",
        allow_mutable=False,
        expected=None,
    ),
]


# --------------------------------------------------------------------------
# inventory_workflow_models._detect_format
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class DetectFormatCase:
    description: str
    node_kinds: set[NodeKind]
    expected: str


DETECT_FORMAT_CASES: list[DetectFormatCase] = [
    DetectFormatCase(
        description="positive: only UI nodes is a ui workflow",
        node_kinds={NodeKind.UI},
        expected="ui",
    ),
    DetectFormatCase(
        description="positive: only API nodes is an api workflow",
        node_kinds={NodeKind.API},
        expected="api",
    ),
    DetectFormatCase(
        description="corner: both kinds together is hybrid",
        node_kinds={NodeKind.UI, NodeKind.API},
        expected="hybrid",
    ),
    DetectFormatCase(
        description="boundary: no nodes is unknown",
        node_kinds=set(),
        expected="unknown",
    ),
]


# --------------------------------------------------------------------------
# apply_model_metadata._validated_sha256
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ValidatedSha256Case:
    description: str
    raw: dict[str, Any]
    expected: object  # str, None, or ApplyError


VALIDATED_SHA256_CASES: list[ValidatedSha256Case] = [
    ValidatedSha256Case(
        description="boundary: absent sha256 is None",
        raw={},
        expected=None,
    ),
    ValidatedSha256Case(
        description="boundary: explicit None sha256 is None",
        raw={"sha256": None},
        expected=None,
    ),
    ValidatedSha256Case(
        description="positive: a lowercase 64-hex digest is returned",
        raw={"sha256": "a" * 64},
        expected="a" * 64,
    ),
    ValidatedSha256Case(
        description="corner: an uppercase digest is casefolded",
        raw={"sha256": "A" * 64},
        expected="a" * 64,
    ),
    ValidatedSha256Case(
        description="corner: a mixed-case digest is casefolded",
        raw={"sha256": "AbCd" * 16},
        expected=("abcd" * 16),
    ),
    ValidatedSha256Case(
        description="negative: 63 characters is too short",
        raw={"sha256": "a" * 63},
        expected=ApplyError,
    ),
    ValidatedSha256Case(
        description="negative: 65 characters is too long",
        raw={"sha256": "a" * 65},
        expected=ApplyError,
    ),
    ValidatedSha256Case(
        description="negative: a non-hex digest is rejected",
        raw={"sha256": "g" * 64},
        expected=ApplyError,
    ),
    ValidatedSha256Case(
        description="negative: a non-string sha256 is rejected",
        raw={"sha256": 123},
        expected=ApplyError,
    ),
]


# --------------------------------------------------------------------------
# apply_model_metadata._existing_entry_satisfies
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ExistingSatisfiesCase:
    description: str
    entry: dict[str, Any]
    requirement: dict[str, Any]
    expected: bool


def _requirement(*, filename: str, hints: list[str], ambiguous: bool = False) -> dict[str, Any]:
    return {
        "filename": filename,
        "directory_hints": hints,
        "directory_ambiguous": ambiguous,
    }


EXISTING_SATISFIES_CASES: list[ExistingSatisfiesCase] = [
    ExistingSatisfiesCase(
        description="positive: valid entry whose directory matches the loader hint",
        entry={
            "name": "base.safetensors",
            "directory": "checkpoints",
            "url": hf_url("base.safetensors"),
        },
        requirement=_requirement(filename="base.safetensors", hints=["checkpoints"]),
        expected=True,
    ),
    ExistingSatisfiesCase(
        description="positive: no directory hints imposes no directory constraint",
        entry={
            "name": "base.safetensors",
            "directory": "anywhere",
            "url": hf_url("base.safetensors"),
        },
        requirement=_requirement(filename="base.safetensors", hints=[]),
        expected=True,
    ),
    ExistingSatisfiesCase(
        description="corner: aliased directories (clip == text_encoders) are equivalent",
        entry={"name": "clip.safetensors", "directory": "clip", "url": hf_url("clip.safetensors")},
        requirement=_requirement(filename="clip.safetensors", hints=["text_encoders"]),
        expected=True,
    ),
    ExistingSatisfiesCase(
        description="negative: filename does not match the requirement",
        entry={
            "name": "other.safetensors",
            "directory": "checkpoints",
            "url": hf_url("other.safetensors"),
        },
        requirement=_requirement(filename="base.safetensors", hints=["checkpoints"]),
        expected=False,
    ),
    ExistingSatisfiesCase(
        description="negative: an ambiguous requirement can never be satisfied",
        entry={
            "name": "base.safetensors",
            "directory": "checkpoints",
            "url": hf_url("base.safetensors"),
        },
        requirement=_requirement(
            filename="base.safetensors", hints=["checkpoints"], ambiguous=True
        ),
        expected=False,
    ),
    ExistingSatisfiesCase(
        description="negative: directory conflicts with the loader hint",
        entry={"name": "base.safetensors", "directory": "loras", "url": hf_url("base.safetensors")},
        requirement=_requirement(filename="base.safetensors", hints=["checkpoints"]),
        expected=False,
    ),
    ExistingSatisfiesCase(
        description="negative: an unsafe URL disqualifies the entry",
        entry={
            "name": "base.safetensors",
            "directory": "checkpoints",
            "url": "http://evil.example/base.safetensors",
        },
        requirement=_requirement(filename="base.safetensors", hints=["checkpoints"]),
        expected=False,
    ),
    ExistingSatisfiesCase(
        description="negative: a non-model filename disqualifies the entry",
        entry={"name": "notes.txt", "directory": "checkpoints", "url": hf_url("notes.txt")},
        requirement=_requirement(filename="notes.txt", hints=["checkpoints"]),
        expected=False,
    ),
    ExistingSatisfiesCase(
        description="negative: an unsafe directory disqualifies the entry",
        entry={
            "name": "base.safetensors",
            "directory": "../escape",
            "url": hf_url("base.safetensors"),
        },
        requirement=_requirement(filename="base.safetensors", hints=["checkpoints"]),
        expected=False,
    ),
    ExistingSatisfiesCase(
        description="corner: a SHA-256 lets a mutable-revision URL validate",
        entry={
            "name": "base.safetensors",
            "directory": "checkpoints",
            "url": hf_url("base.safetensors", revision="main"),
            "hash": "b" * 64,
            "hash_type": "sha256",
        },
        requirement=_requirement(filename="base.safetensors", hints=["checkpoints"]),
        expected=True,
    ),
]


# --------------------------------------------------------------------------
# apply_model_metadata._existing_matches_resolution
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class MatchesResolutionCase:
    description: str
    model: dict[str, Any]
    metadata_by_path: dict[str, dict[str, Any]]
    expected: bool


def _model(
    *,
    replace_existing: bool = False,
    filename: str = "base.safetensors",
    directory: str = "checkpoints",
    url: str | None = None,
    sha256: str | None = None,
    occurrences: list[dict[str, Any]],
) -> dict[str, Any]:
    model: dict[str, Any] = {
        "replace_existing": replace_existing,
        "filename": filename,
        "directory": directory,
        "url": url if url is not None else hf_url(filename),
        "requirement": {"occurrences": occurrences},
    }
    if sha256 is not None:
        model["sha256"] = sha256
    return model


def _existing(
    *,
    name: str = "base.safetensors",
    directory: str = "checkpoints",
    url: str | None = None,
    issues: list[str] | None = None,
    hash_value: str | None = None,
    hash_type: str | None = None,
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "name": name,
        "directory": directory,
        "url": url if url is not None else hf_url(name),
        "issues": issues if issues is not None else [],
    }
    if hash_value is not None:
        entry["hash"] = hash_value
    if hash_type is not None:
        entry["hash_type"] = hash_type
    return entry


_META_OCC = {"source": "metadata", "path": "/p"}
_WIDGET_OCC = {"source": "widget", "path": "/w"}

MATCHES_RESOLUTION_CASES: list[MatchesResolutionCase] = [
    MatchesResolutionCase(
        description="positive: associated entry already equals the resolution",
        model=_model(occurrences=[dict(_META_OCC)]),
        metadata_by_path={"/p": _existing()},
        expected=True,
    ),
    MatchesResolutionCase(
        description="negative: replace_existing forces a recreate",
        model=_model(replace_existing=True, occurrences=[dict(_META_OCC)]),
        metadata_by_path={"/p": _existing()},
        expected=False,
    ),
    MatchesResolutionCase(
        description="negative: no metadata occurrence means nothing to keep",
        model=_model(occurrences=[dict(_WIDGET_OCC)]),
        metadata_by_path={"/p": _existing()},
        expected=False,
    ),
    MatchesResolutionCase(
        description="negative: the existing entry carries issues",
        model=_model(occurrences=[dict(_META_OCC)]),
        metadata_by_path={"/p": _existing(issues=["invalid_hash"])},
        expected=False,
    ),
    MatchesResolutionCase(
        description="negative: name differs from the resolution",
        model=_model(occurrences=[dict(_META_OCC)]),
        metadata_by_path={"/p": _existing(name="other.safetensors")},
        expected=False,
    ),
    MatchesResolutionCase(
        description="negative: directory differs from the resolution",
        model=_model(occurrences=[dict(_META_OCC)]),
        metadata_by_path={"/p": _existing(directory="loras")},
        expected=False,
    ),
    MatchesResolutionCase(
        description="negative: url differs from the resolution",
        model=_model(occurrences=[dict(_META_OCC)]),
        metadata_by_path={"/p": _existing(url=hf_url("base.safetensors", revision="b" * 40))},
        expected=False,
    ),
    MatchesResolutionCase(
        description="negative: model expects a sha256 the existing entry lacks",
        model=_model(sha256="a" * 64, occurrences=[dict(_META_OCC)]),
        metadata_by_path={"/p": _existing()},
        expected=False,
    ),
    MatchesResolutionCase(
        description="positive: model and existing entry agree on sha256",
        model=_model(sha256="a" * 64, occurrences=[dict(_META_OCC)]),
        metadata_by_path={"/p": _existing(hash_value="a" * 64, hash_type="sha256")},
        expected=True,
    ),
    MatchesResolutionCase(
        description="corner: one of two associated entries mismatches",
        model=_model(
            occurrences=[{"source": "metadata", "path": "/p"}, {"source": "metadata", "path": "/q"}]
        ),
        metadata_by_path={"/p": _existing(), "/q": _existing(directory="loras")},
        expected=False,
    ),
    MatchesResolutionCase(
        description="boundary: the occurrence path is not present in the metadata map",
        model=_model(occurrences=[{"source": "metadata", "path": "/missing"}]),
        metadata_by_path={"/p": _existing()},
        expected=False,
    ),
]


# --------------------------------------------------------------------------
# apply_model_metadata._plan_attachments
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class PlanAttachmentsCase:
    description: str
    models: list[dict[str, Any]]
    fallback_target: dict[str, Any] | None
    expected: object  # (attachments: dict[str, list[str]], root: list[str]) or ApplyError


def _attach_model(filename: str, node_paths: list[str | None]) -> dict[str, Any]:
    return {
        "filename": filename,
        "requirement": {"occurrences": [{"node_path": pointer} for pointer in node_paths]},
    }


PLAN_ATTACHMENTS_CASES: list[PlanAttachmentsCase] = [
    PlanAttachmentsCase(
        description="positive: a single consumer node path attaches there",
        models=[_attach_model("base.safetensors", ["/nodes/0"])],
        fallback_target=None,
        expected=({"/nodes/0": ["base.safetensors"]}, []),
    ),
    PlanAttachmentsCase(
        description="corner: a model consumed at two nodes attaches to both",
        models=[_attach_model("base.safetensors", ["/nodes/0", "/nodes/1"])],
        fallback_target=None,
        expected=(
            {"/nodes/0": ["base.safetensors"], "/nodes/1": ["base.safetensors"]},
            [],
        ),
    ),
    PlanAttachmentsCase(
        description="corner: two models sharing a node path both attach there",
        models=[
            _attach_model("a.safetensors", ["/nodes/0"]),
            _attach_model("b.safetensors", ["/nodes/0"]),
        ],
        fallback_target=None,
        expected=({"/nodes/0": ["a.safetensors", "b.safetensors"]}, []),
    ),
    PlanAttachmentsCase(
        description="positive: a metadata-only model goes to the root fallback target",
        models=[_attach_model("legacy.safetensors", [None])],
        fallback_target={"nodes": []},
        expected=({}, ["legacy.safetensors"]),
    ),
    PlanAttachmentsCase(
        description="negative: a metadata-only model with no fallback target is an error",
        models=[_attach_model("legacy.safetensors", [None])],
        fallback_target=None,
        expected=ApplyError,
    ),
    PlanAttachmentsCase(
        description="boundary: no models yields empty attachments and root",
        models=[],
        fallback_target={"nodes": []},
        expected=({}, []),
    ),
    PlanAttachmentsCase(
        description="corner: a mix of a real node path and None attaches to the node",
        models=[_attach_model("base.safetensors", ["/nodes/0", None])],
        fallback_target={"nodes": []},
        expected=({"/nodes/0": ["base.safetensors"]}, []),
    ),
]


# --------------------------------------------------------------------------
# apply_model_metadata._eligible_requirements
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class EligibleRequirementsCase:
    description: str
    inventory: dict[str, Any]
    workflow_format: str
    expected: list[str]


def _req(requirement_id: str, node_kinds: list[str | None]) -> dict[str, Any]:
    return {
        "requirement_id": requirement_id,
        "occurrences": [{"node_kind": kind} for kind in node_kinds],
    }


ELIGIBLE_REQUIREMENTS_CASES: list[EligibleRequirementsCase] = [
    EligibleRequirementsCase(
        description="positive: ui format keeps every requirement",
        inventory={"requirements": [_req("r1", ["ui"]), _req("r2", ["api"])]},
        workflow_format="ui",
        expected=["r1", "r2"],
    ),
    EligibleRequirementsCase(
        description="positive: api format keeps every requirement",
        inventory={"requirements": [_req("r1", ["api"])]},
        workflow_format="api",
        expected=["r1"],
    ),
    EligibleRequirementsCase(
        description="negative: hybrid drops an API-only requirement",
        inventory={"requirements": [_req("r1", ["api"])]},
        workflow_format="hybrid",
        expected=[],
    ),
    EligibleRequirementsCase(
        description="positive: hybrid keeps a UI requirement",
        inventory={"requirements": [_req("r1", ["ui"])]},
        workflow_format="hybrid",
        expected=["r1"],
    ),
    EligibleRequirementsCase(
        description="corner: hybrid keeps a requirement consumed by both kinds",
        inventory={"requirements": [_req("r1", ["ui", "api"])]},
        workflow_format="hybrid",
        expected=["r1"],
    ),
    EligibleRequirementsCase(
        description="corner: hybrid keeps a requirement with no node kind at all",
        inventory={"requirements": [_req("r1", [None])]},
        workflow_format="hybrid",
        expected=["r1"],
    ),
    EligibleRequirementsCase(
        description="boundary: no requirements yields an empty list",
        inventory={"requirements": []},
        workflow_format="hybrid",
        expected=[],
    ),
]


class InventoryHelperTests(unittest.TestCase):
    def test_matching_consumers(self) -> None:
        for case in MATCHING_CONSUMERS_CASES:
            with self.subTest(case.description):
                self.assertEqual(
                    _matching_consumers(
                        case.accumulator,
                        case.filename,
                        case.node_id,
                        case.metadata_node_path,
                        exact=case.exact,
                    ),
                    case.expected,
                )

    def test_metadata_directory_hints(self) -> None:
        for case in DIRECTORY_HINTS_CASES:
            with self.subTest(case.description):
                self.assertEqual(_metadata_directory_hints(case.entry), case.expected)

    def test_metadata_status(self) -> None:
        for case in METADATA_STATUS_CASES:
            with self.subTest(case.description):
                self.assertEqual(_metadata_status(case.entries), case.expected)

    def test_unique_occurrences(self) -> None:
        for case in UNIQUE_OCCURRENCES_CASES:
            with self.subTest(case.description):
                self.assertEqual(_unique_occurrences(case.occurrences), case.expected)

    def test_validate_huggingface_path(self) -> None:
        for case in HUGGINGFACE_PATH_CASES:
            with self.subTest(case.description):
                _assert_expected(
                    self,
                    case.expected,
                    partial(
                        _validate_huggingface_path,
                        case.path_parts,
                        case.filename,
                        case.allow_mutable,
                    ),
                )

    def test_detect_format(self) -> None:
        for case in DETECT_FORMAT_CASES:
            with self.subTest(case.description):
                self.assertEqual(_detect_format(case.node_kinds), case.expected)


class ApplyHelperTests(unittest.TestCase):
    def test_validated_sha256(self) -> None:
        for case in VALIDATED_SHA256_CASES:
            with self.subTest(case.description):
                _assert_expected(
                    self, case.expected, partial(_validated_sha256, case.raw, "models[0]")
                )

    def test_existing_entry_satisfies(self) -> None:
        for case in EXISTING_SATISFIES_CASES:
            with self.subTest(case.description):
                self.assertEqual(
                    _existing_entry_satisfies(case.entry, case.requirement), case.expected
                )

    def test_existing_matches_resolution(self) -> None:
        for case in MATCHES_RESOLUTION_CASES:
            with self.subTest(case.description):
                self.assertEqual(
                    _existing_matches_resolution(case.model, case.metadata_by_path), case.expected
                )

    def test_plan_attachments(self) -> None:
        for case in PLAN_ATTACHMENTS_CASES:
            with self.subTest(case.description):
                if isinstance(case.expected, type) and issubclass(case.expected, BaseException):
                    with self.assertRaises(case.expected):
                        _plan_attachments(case.models, case.fallback_target)
                    continue
                attachments, root = _plan_attachments(case.models, case.fallback_target)
                actual = (
                    {
                        pointer: [model["filename"] for model in models]
                        for pointer, models in attachments.items()
                    },
                    [model["filename"] for model in root],
                )
                self.assertEqual(actual, case.expected)

    def test_eligible_requirements(self) -> None:
        for case in ELIGIBLE_REQUIREMENTS_CASES:
            with self.subTest(case.description):
                eligible = _eligible_requirements(case.inventory, case.workflow_format)
                self.assertEqual(
                    [requirement["requirement_id"] for requirement in eligible], case.expected
                )


if __name__ == "__main__":
    unittest.main()
