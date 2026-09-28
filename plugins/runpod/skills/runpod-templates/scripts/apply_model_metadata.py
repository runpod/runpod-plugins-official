#!/usr/bin/env python3
"""Apply a reviewed model-resolution manifest to a new ComfyUI workflow."""

from __future__ import annotations

import argparse
import contextlib
import copy
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

if not sys.dont_write_bytecode:
    # Avoid writing __pycache__ beside the vendored sibling scripts when this
    # module is imported (e.g. via the CLI) without python's -B flag.
    sys.dont_write_bytecode = True

from inventory_workflow_models import (
    _SHA256,
    InventoryError,
    _metadata_has_sha256,
    _metadata_sha256,
    _model_filename,
    build_inventory,
    load_json,
)
from inventory_workflow_models import (
    _validate_url as _check_url_policy,
)

_SAFE_DIRECTORY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


class ApplyError(ValueError):
    """Raised when applying metadata would be ambiguous or unsafe."""


def _parse_pointer(pointer: str) -> tuple[str, ...]:
    if pointer == "":
        return ()
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        raise ApplyError(f"invalid JSON pointer: {pointer!r}")
    return tuple(part.replace("~1", "/").replace("~0", "~") for part in pointer[1:].split("/"))


def _resolve_pointer(document: object, pointer: str) -> object:
    value = document
    for part in _parse_pointer(pointer):
        if isinstance(value, list):
            if not part.isdigit():
                raise ApplyError(f"invalid list index in JSON pointer: {pointer}")
            index = int(part)
            if index >= len(value):
                raise ApplyError(f"JSON pointer is outside workflow: {pointer}")
            value = value[index]
        elif isinstance(value, dict) and part in value:
            value = value[part]
        else:
            raise ApplyError(f"JSON pointer is outside workflow: {pointer}")
    return value


def _validate_directory(raw: object) -> str:
    if not isinstance(raw, str):
        raise ApplyError("model directory must be a string folder key")
    directory = raw.strip()
    if not _SAFE_DIRECTORY.fullmatch(directory) or directory in {".", ".."}:
        raise ApplyError(f"unsafe model directory: {raw!r}")
    return directory


def _validate_filename(raw: object) -> str:
    filename = _model_filename(raw)
    if not filename or filename != raw:
        raise ApplyError(f"unsafe or non-basename model filename: {raw!r}")
    return filename


def _validate_url(
    raw: object,
    filename: str,
    *,
    allow_mutable_hf_revision: bool = False,
) -> str:
    """Validate against the shared policy (inventory_workflow_models._validate_url)."""

    try:
        return _check_url_policy(
            raw,
            filename,
            allow_mutable_hf_revision=allow_mutable_hf_revision,
        )
    except InventoryError as exc:
        raise ApplyError(str(exc)) from exc


def _directories_equivalent(first: str, second: str) -> bool:
    aliases = {
        "clip": "text_encoders",
        "text_encoders": "text_encoders",
        "diffusion_models": "diffusion_models",
        "unet": "diffusion_models",
    }
    return aliases.get(first.casefold(), first.casefold()) == aliases.get(
        second.casefold(), second.casefold()
    )


def _eligible_requirements(inventory: dict[str, Any], workflow_format: str) -> list[dict[str, Any]]:
    """Requirements a UI manifest may address (drop API-only in hybrid graphs)."""

    eligible: list[dict[str, Any]] = []
    for requirement in inventory["requirements"]:
        node_kinds = {
            occurrence.get("node_kind")
            for occurrence in requirement["occurrences"]
            if occurrence.get("node_kind")
        }
        if workflow_format == "hybrid" and node_kinds and "ui" not in node_kinds:
            continue
        eligible.append(requirement)
    return eligible


def _require_reviewed_shape(raw: object, prefix: str) -> dict[str, Any]:
    """Assert an entry is an object carrying the explicit review attestations."""

    if not isinstance(raw, dict):
        raise ApplyError(f"{prefix} must be an object")
    if raw.get("reviewed") is not True:
        raise ApplyError(f"{prefix} is not explicitly reviewed")
    if raw.get("verified") is not True:
        raise ApplyError(f"{prefix} is not verified")
    if raw.get("ambiguous") is not False:
        raise ApplyError(f"{prefix} is ambiguous or lacks an explicit ambiguity decision")
    return raw


def _resolve_requirement(
    raw: dict[str, Any],
    prefix: str,
    by_id: dict[str, dict[str, Any]],
    seen_ids: set[str],
) -> dict[str, Any]:
    """Look up the (unique, repairable) requirement an entry claims to resolve."""

    requirement_id = raw.get("requirement_id")
    if not isinstance(requirement_id, str) or requirement_id not in by_id:
        raise ApplyError(f"{prefix} has an unknown requirement_id")
    if requirement_id in seen_ids:
        raise ApplyError(f"duplicate requirement_id: {requirement_id}")
    requirement = by_id[requirement_id]
    if requirement.get("subfoldered"):
        raise ApplyError(
            f"{prefix} selects a model through a subfolder; refusing to flatten it "
            "to a simple RunpodDirect filename"
        )
    if requirement.get("selection_mismatch"):
        raise ApplyError(
            f"{prefix} loader selection is not an exact simple filename; "
            "refusing to rewrite its identity implicitly"
        )
    return requirement


def _validate_directory_against_hints(
    directory: str, requirement: dict[str, Any], prefix: str
) -> None:
    """Reject a directory the inventory's loader hints cannot accommodate."""

    if requirement.get("directory_ambiguous"):
        raise ApplyError(
            f"{prefix} maps one filename to conflicting model directories; "
            "automatic annotation is unsafe"
        )
    hints = requirement["directory_hints"]
    if hints and not any(_directories_equivalent(directory, hint) for hint in hints):
        raise ApplyError(
            f"{prefix} directory {directory!r} conflicts with inventory hints {hints!r}"
        )


def _validated_sha256(raw: dict[str, Any], prefix: str) -> str | None:
    sha256 = raw.get("sha256")
    if sha256 is None:
        return None
    if not isinstance(sha256, str) or not _SHA256.fullmatch(sha256):
        raise ApplyError(f"{prefix} sha256 must be 64 hexadecimal characters")
    return sha256.casefold()


def _assert_no_stale_conflict(
    raw: dict[str, Any],
    requirement: dict[str, Any],
    metadata_by_path: dict[str, dict[str, Any]],
    prefix: str,
    *,
    filename: str,
    directory: str,
    url: str,
    sha256: str | None,
) -> None:
    """Refuse to silently overwrite mismatched existing metadata."""

    associated_existing = [
        metadata_by_path[occurrence["path"]]
        for occurrence in requirement["occurrences"]
        if occurrence.get("source") == "metadata" and occurrence.get("path") in metadata_by_path
    ]
    conflicts = [
        existing
        for existing in associated_existing
        if existing.get("issues")
        or not (
            existing.get("name") == filename
            and existing.get("directory") == directory
            and existing.get("url") == url
            and _metadata_sha256(existing) == sha256
        )
    ]
    if conflicts and raw.get("replace_existing") is not True:
        conflict_paths = ", ".join(entry["path"] for entry in conflicts)
        raise ApplyError(
            f"{prefix} conflicts with existing metadata at {conflict_paths}; "
            "review the diff and set replace_existing=true"
        )


def _validated_model_entry(
    raw: object,
    index: int,
    by_id: dict[str, dict[str, Any]],
    metadata_by_path: dict[str, dict[str, Any]],
    seen_ids: set[str],
) -> dict[str, Any]:
    """Validate one reviewed manifest entry into an applicable model record."""

    prefix = f"models[{index}]"
    reviewed = _require_reviewed_shape(raw, prefix)
    requirement = _resolve_requirement(reviewed, prefix, by_id, seen_ids)

    filename = _validate_filename(reviewed.get("filename"))
    if filename != requirement["filename"]:
        raise ApplyError(f"{prefix} filename does not match its requirement")
    directory = _validate_directory(reviewed.get("directory"))
    _validate_directory_against_hints(directory, requirement, prefix)
    sha256 = _validated_sha256(reviewed, prefix)
    url = _validate_url(
        reviewed.get("url"),
        filename,
        allow_mutable_hf_revision=bool(sha256),
    )
    _assert_no_stale_conflict(
        reviewed,
        requirement,
        metadata_by_path,
        prefix,
        filename=filename,
        directory=directory,
        url=url,
        sha256=sha256,
    )

    model: dict[str, Any] = {
        "directory": directory,
        "filename": filename,
        "replace_existing": reviewed.get("replace_existing") is True,
        "requirement": requirement,
        "requirement_id": requirement["requirement_id"],
        "url": url,
    }
    if sha256:
        model["sha256"] = sha256
    return model


def _existing_entry_satisfies(entry: dict[str, Any], requirement: dict[str, Any]) -> bool:
    """Whether a complete existing entry safely resolves ``requirement``."""

    try:
        filename = _validate_filename(entry["name"])
        directory = _validate_directory(entry["directory"])
        _validate_url(
            entry["url"],
            filename,
            allow_mutable_hf_revision=_metadata_has_sha256(entry),
        )
    except ApplyError:
        return False
    if filename != requirement["filename"]:
        return False
    if requirement.get("directory_ambiguous"):
        return False
    return not (
        requirement["directory_hints"]
        and not any(
            _directories_equivalent(directory, hint) for hint in requirement["directory_hints"]
        )
    )


def _unresolved_requirements(
    eligible_requirements: list[dict[str, Any]],
    manifest_ids: set[str],
    metadata_by_path: dict[str, dict[str, Any]],
) -> list[str]:
    """Requirements the manifest neither addresses nor leaves safely satisfied.

    A structurally complete existing entry can satisfy only the requirement to
    which inventory associated it. Filename equality alone is insufficient.
    """

    unresolved: list[str] = []
    for requirement in eligible_requirements:
        if requirement["requirement_id"] in manifest_ids:
            continue
        if requirement.get("subfoldered") or requirement.get("selection_mismatch"):
            unresolved.append(f"{requirement['filename']} ({requirement['requirement_id']})")
            continue
        metadata_paths = {
            occurrence["path"]
            for occurrence in requirement["occurrences"]
            if occurrence.get("source") == "metadata"
        }
        complete = [
            metadata_by_path[path]
            for path in metadata_paths
            if path in metadata_by_path and not metadata_by_path[path]["issues"]
        ]
        if not any(_existing_entry_satisfies(entry, requirement) for entry in complete):
            unresolved.append(f"{requirement['filename']} ({requirement['requirement_id']})")
    return unresolved


def _validate_manifest(
    document: object,
    manifest: object,
    *,
    allow_unresolved: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not isinstance(manifest, dict):
        raise ApplyError("manifest root must be an object")
    if manifest.get("schema_version") != 1:
        raise ApplyError("manifest schema_version must be 1")

    inventory = build_inventory(document)
    if manifest.get("workflow_sha256") != inventory["workflow_sha256"]:
        raise ApplyError("manifest workflow_sha256 does not match this workflow")
    workflow_format = inventory["workflow_format"]
    if workflow_format == "api":
        raise ApplyError(
            "API prompt JSON can be inventoried but cannot be portably repaired with "
            "ComfyUI UI workflow model metadata"
        )
    if workflow_format == "unknown":
        raise ApplyError("workflow does not contain a recognizable ComfyUI UI graph")
    raw_models = manifest.get("models")
    if not isinstance(raw_models, list):
        raise ApplyError("manifest models must be an array")

    eligible_requirements = _eligible_requirements(inventory, workflow_format)
    by_id = {item["requirement_id"]: item for item in eligible_requirements}
    metadata_by_path = {existing["path"]: existing for existing in inventory["existing_metadata"]}

    seen_ids: set[str] = set()
    validated: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_models):
        model = _validated_model_entry(raw, index, by_id, metadata_by_path, seen_ids)
        validated.append(model)
        seen_ids.add(model["requirement_id"])

    manifest_ids = {item["requirement_id"] for item in validated}
    unresolved = _unresolved_requirements(eligible_requirements, manifest_ids, metadata_by_path)
    if unresolved and not allow_unresolved:
        raise ApplyError(
            "manifest leaves unresolved models: " + ", ".join(sorted(unresolved, key=str.casefold))
        )

    validated.sort(
        key=lambda item: (
            item["filename"].casefold(),
            item["filename"],
            item["requirement_id"],
        )
    )
    return validated, inventory


def _ui_metadata_target(document: object) -> dict[str, Any] | None:
    candidates: list[tuple[int, str, dict[str, Any]]] = []

    def walk(value: object, path: str, depth: int) -> None:
        if isinstance(value, dict):
            if isinstance(value.get("nodes"), list):
                candidates.append((depth, path, value))
            for key, child in value.items():
                walk(child, f"{path}/{key}", depth + 1)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{path}/{index}", depth + 1)

    walk(document, "", 0)
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1]))
    best_depth = candidates[0][0]
    shallow = [item for item in candidates if item[0] == best_depth]
    if len(shallow) != 1:
        raise ApplyError("workflow contains multiple equally plausible UI graph roots")
    return shallow[0][2]


def _metadata_entry(model: dict[str, Any]) -> dict[str, str]:
    entry = {
        "directory": model["directory"],
        "name": model["filename"],
        "url": model["url"],
    }
    if model.get("sha256"):
        entry["hash"] = model["sha256"]
        entry["hash_type"] = "SHA256"
    return entry


def _associated_metadata_paths(models: list[dict[str, Any]]) -> set[str]:
    paths: set[str] = set()
    for model in models:
        for occurrence in model["requirement"]["occurrences"]:
            if occurrence.get("source") != "metadata":
                continue
            pointer = occurrence.get("path")
            if not isinstance(pointer, str) or "/" not in pointer:
                raise ApplyError("associated metadata has an invalid JSON pointer")
            paths.add(pointer)
    return paths


def _remove_metadata_paths(document: object, paths: set[str]) -> None:
    removals: dict[str, set[int]] = {}
    for pointer in paths:
        if not isinstance(pointer, str) or "/" not in pointer:
            raise ApplyError("metadata has an invalid JSON pointer")
        parent_pointer, raw_index = pointer.rsplit("/", 1)
        if not raw_index.isdigit():
            raise ApplyError(f"metadata pointer does not end in an array index: {pointer}")
        removals.setdefault(parent_pointer, set()).add(int(raw_index))

    for parent_pointer, indexes in sorted(removals.items()):
        model_array = _resolve_pointer(document, parent_pointer)
        if not isinstance(model_array, list):
            raise ApplyError(f"metadata parent is not an array: {parent_pointer}")
        for index in sorted(indexes, reverse=True):
            if index >= len(model_array):
                raise ApplyError(f"metadata pointer is outside workflow: {parent_pointer}/{index}")
            del model_array[index]


def _existing_matches_resolution(
    model: dict[str, Any], metadata_by_path: dict[str, dict[str, Any]]
) -> bool:
    """Whether every associated existing entry already equals the resolution.

    An existing entry whose canonical fields already match the reviewed
    resolution carries no conflict: keep it verbatim (unknown keys survive)
    instead of dropping it through remove + recreate.
    """

    associated_existing = [
        metadata_by_path[occurrence["path"]]
        for occurrence in model["requirement"]["occurrences"]
        if occurrence.get("source") == "metadata" and occurrence.get("path") in metadata_by_path
    ]
    return (
        model["replace_existing"] is not True
        and bool(associated_existing)
        and all(
            not existing.get("issues")
            and existing.get("name") == model["filename"]
            and existing.get("directory") == model["directory"]
            and existing.get("url") == model["url"]
            and _metadata_sha256(existing) == model.get("sha256")
            for existing in associated_existing
        )
    )


def _plan_attachments(
    recreated_models: list[dict[str, Any]], fallback_target: dict[str, Any] | None
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    """Group recreated models by consuming node pointer, or the UI graph root."""

    attachments: dict[str, list[dict[str, Any]]] = {}
    root_attachments: list[dict[str, Any]] = []
    for model in recreated_models:
        node_paths = sorted(
            {
                occurrence["node_path"]
                for occurrence in model["requirement"]["occurrences"]
                if occurrence.get("node_path") is not None
            }
        )
        if node_paths:
            for pointer in node_paths:
                attachments.setdefault(pointer, []).append(model)
            continue

        # Metadata-only legacy/root entries do not identify a consumer. Keep
        # those at the UI graph root rather than inventing a node association.
        if fallback_target is None:
            raise ApplyError(f"cannot locate a consuming node for {model['filename']}")
        root_attachments.append(model)
    return attachments, root_attachments


def _apply_node_attachments(output: object, attachments: dict[str, list[dict[str, Any]]]) -> None:
    for pointer, node_models in sorted(attachments.items()):
        node = _resolve_pointer(output, pointer)
        if not isinstance(node, dict) or not (
            isinstance(node.get("type"), str) or isinstance(node.get("class_type"), str)
        ):
            raise ApplyError(f"node pointer is not a ComfyUI node: {pointer}")
        properties = node.setdefault("properties", {})
        if not isinstance(properties, dict):
            raise ApplyError(f"node properties is not an object: {pointer}")
        models = properties.setdefault("models", [])
        if not isinstance(models, list):
            raise ApplyError(f"node properties.models is not an array: {pointer}")
        models.extend(_metadata_entry(model) for model in node_models)


def _apply_root_attachments(
    fallback_target: dict[str, Any] | None, root_attachments: list[dict[str, Any]]
) -> None:
    if not root_attachments:
        return
    if fallback_target is None:
        # Unreachable: _plan_attachments refuses to add a root attachment
        # without a fallback target. Kept for type-safety.
        raise ApplyError("cannot locate a UI graph root for legacy model metadata")
    root_models = fallback_target.get("models")
    if root_models is None:
        fallback_target["models"] = []
        root_models = fallback_target["models"]
    elif not isinstance(root_models, list):
        raise ApplyError("UI workflow root models field is not an array")
    root_models.extend(_metadata_entry(model) for model in root_attachments)


def apply_manifest_to_document(
    document: object,
    manifest: object,
    *,
    allow_unresolved: bool = False,
) -> tuple[dict[str, Any], list[str]]:
    validated, inventory = _validate_manifest(
        document,
        manifest,
        allow_unresolved=allow_unresolved,
    )
    output = copy.deepcopy(document)
    if not isinstance(output, dict):
        # Unreachable: _validate_manifest builds an inventory that already
        # rejects a non-object workflow root.
        raise ApplyError("workflow JSON root must be an object")
    metadata_by_path = {existing["path"]: existing for existing in inventory["existing_metadata"]}
    recreated_models = [
        model for model in validated if not _existing_matches_resolution(model, metadata_by_path)
    ]
    removals = _associated_metadata_paths(recreated_models)
    if allow_unresolved:
        removals.update(
            entry["path"] for entry in inventory["existing_metadata"] if entry.get("issues")
        )
    _remove_metadata_paths(output, removals)
    fallback_target = _ui_metadata_target(output)
    attachments, root_attachments = _plan_attachments(recreated_models, fallback_target)
    _apply_node_attachments(output, attachments)
    _apply_root_attachments(fallback_target, root_attachments)

    return output, [item["filename"] for item in validated]


def _write_new_workflow(
    input_path: Path,
    manifest_path: Path,
    output_path: Path,
    *,
    allow_unresolved: bool = False,
) -> tuple[list[str], dict[str, Any]]:
    input_resolved = input_path.resolve()
    output_resolved = output_path.resolve()
    if os.path.normcase(str(input_resolved)) == os.path.normcase(str(output_resolved)):
        raise ApplyError("output path must not overwrite the input workflow")
    if output_path.exists():
        raise ApplyError(f"refusing to overwrite existing output: {output_path}")
    if not output_path.parent.exists():
        raise ApplyError(f"output directory does not exist: {output_path.parent}")

    try:
        document = load_json(input_path)
        manifest = load_json(manifest_path)
    except InventoryError as exc:
        raise ApplyError(str(exc)) from exc
    output, applied = apply_manifest_to_document(
        document,
        manifest,
        allow_unresolved=allow_unresolved,
    )
    try:
        repaired_inventory = build_inventory(output, source_name=str(output_path.resolve()))
    except InventoryError as exc:
        raise ApplyError(f"repaired workflow failed validation: {exc}") from exc
    if repaired_inventory["workflow_format"] not in {"ui", "hybrid"}:
        raise ApplyError("repaired output is not a ComfyUI UI workflow")
    unresolved = repaired_inventory["summary"]["unresolved_requirements"]
    if unresolved and not allow_unresolved:
        raise ApplyError(
            f"repaired workflow failed validation: {unresolved} unresolved model requirement(s)"
        )
    rendered = json.dumps(output, ensure_ascii=False, indent=2) + "\n"

    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "x",
            encoding="utf-8",
            newline="\n",
            dir=output_path.parent,
            prefix=f".{output_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_name = handle.name
            handle.write(rendered)
            handle.flush()
            os.fsync(handle.fileno())
        if os.path.lexists(output_path):
            raise ApplyError(f"refusing to overwrite existing output: {output_path}")
        Path(temporary_name).replace(output_path)
        temporary_name = None
    except (OSError, UnicodeError) as exc:
        raise ApplyError(f"cannot write {output_path}: {exc}") from exc
    finally:
        if temporary_name:
            with contextlib.suppress(FileNotFoundError):
                Path(temporary_name).unlink()
    return applied, repaired_inventory


def write_new_workflow(
    input_path: Path,
    manifest_path: Path,
    output_path: Path,
    *,
    allow_unresolved: bool = False,
) -> list[str]:
    applied, _inventory = _write_new_workflow(
        input_path,
        manifest_path,
        output_path,
        allow_unresolved=allow_unresolved,
    )
    return applied


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Apply reviewed, verified model metadata to a new ComfyUI workflow."
    )
    parser.add_argument("workflow", type=Path, help="source ComfyUI workflow JSON")
    parser.add_argument("manifest", type=Path, help="reviewed resolution manifest JSON")
    parser.add_argument("--output", "-o", type=Path, required=True, help="new workflow path")
    parser.add_argument(
        "--allow-unresolved",
        action="store_true",
        help=(
            "publish a valid UI workflow even when some model requirements remain "
            "unresolved; unresolved requirements are preserved and reported"
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        applied, output_inventory = _write_new_workflow(
            args.workflow,
            args.manifest,
            args.output,
            allow_unresolved=args.allow_unresolved,
        )
    except ApplyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    unresolved = output_inventory["summary"]["unresolved_requirements"]
    print(
        json.dumps(
            {
                "applied_models": applied,
                "output": str(args.output.resolve()),
                "status": "partial" if unresolved else "complete",
                "unresolved_requirements": unresolved,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
