#!/usr/bin/env python3
"""Inventory model requirements in ComfyUI UI and API workflow JSON.

The output is deliberately provider-neutral.  A resolver can add reviewed model
records to a manifest without this script needing network access or credentials.
"""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import math
import os
import re
import sys
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import unquote, urlsplit


SCHEMA_VERSION = 1
MODEL_EXTENSIONS = (
    ".safetensors",
    ".sft",
    ".ckpt",
    ".pth",
    ".pt",
)
UNSUPPORTED_MODEL_EXTENSIONS = (
    ".gguf",
    ".onnx",
    ".engine",
    ".tflite",
    ".bin",
)

_SAFE_FILENAME = re.compile(r"^[^\x00-\x1f<>:\"/\\|?*]+$")
_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
_HF_REVISION = re.compile(r"^[0-9a-fA-F]{40}$")
ALLOWED_HOSTS = {"huggingface.co", "civitai.com", "www.civitai.com"}
_SENSITIVE_QUERY_KEYS = re.compile(
    r"(?:^|_)(?:access_token|api_key|apikey|auth|authorization|key|secret|token)(?:$|_)",
    re.IGNORECASE,
)


class InventoryError(ValueError):
    """Raised for malformed input that cannot be inventoried safely."""


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def workflow_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _pointer(parts: tuple[Any, ...]) -> str:
    if not parts:
        return ""
    encoded = []
    for part in parts:
        encoded.append(str(part).replace("~", "~0").replace("/", "~1"))
    return "/" + "/".join(encoded)


def _filename_with_extensions(
    raw_value: Any, extensions: tuple[str, ...]
) -> str | None:
    """Return a safe basename matching extensions, or None."""

    if not isinstance(raw_value, str):
        return None
    value = raw_value.strip()
    if not value or len(value) > 2048 or "\n" in value or "\r" in value:
        return None

    parsed = urlsplit(value)
    if parsed.scheme:
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
            return None
        value = unquote(parsed.path)
    else:
        value = value.replace("\\", "/")
        if value.startswith("/") or re.match(r"^[A-Za-z]:/", value):
            return None

    parts = value.replace("\\", "/").split("/")
    if any(part in {"", ".", ".."} for part in parts):
        return None
    filename = unquote(parts[-1]).strip()
    if not filename or filename in {".", ".."} or not _SAFE_FILENAME.fullmatch(filename):
        return None
    if not filename.casefold().endswith(extensions):
        return None
    return filename


def _model_filename(raw_value: Any) -> str | None:
    """Return a RunpodDirect-supported model basename, or None."""

    return _filename_with_extensions(raw_value, MODEL_EXTENSIONS)


def _unsupported_model_filename(raw_value: Any) -> str | None:
    """Return a safe model-like basename outside RunpodDirect's scanner contract."""

    return _filename_with_extensions(raw_value, UNSUPPORTED_MODEL_EXTENSIONS)


def _is_subfoldered_selection(raw_value: Any) -> bool:
    """Return whether a local loader selection includes a relative subdirectory."""

    if not isinstance(raw_value, str):
        return False
    value = raw_value.strip()
    if urlsplit(value).scheme:
        return False
    return "/" in value.replace("\\", "/")


def _hints_from_field(field: str) -> set[str]:
    key = re.sub(r"[^a-z0-9]+", "_", field.casefold()).strip("_")
    if not key:
        return set()
    if "clip_vision" in key:
        return {"clip_vision"}
    if "controlnet" in key or "control_net" in key:
        return {"controlnet"}
    if "checkpoint" in key or key.startswith("ckpt") or "_ckpt" in key:
        return {"checkpoints"}
    if "lora" in key:
        return {"loras"}
    if "vae" in key:
        return {"vae"}
    if "upscale" in key and "model" in key:
        return {"upscale_models"}
    if "style_model" in key:
        return {"style_models"}
    if "gligen" in key:
        return {"gligen"}
    if "unet" in key or "diffusion_model" in key:
        return {"diffusion_models", "unet"}
    if "text_encoder" in key or key.startswith("clip_") or key == "clip":
        return {"clip", "text_encoders"}
    return set()


def _hints_from_node_type(node_type: str) -> set[str]:
    value = re.sub(r"[^a-z0-9]+", "", node_type.casefold())
    if "clipvision" in value:
        return {"clip_vision"}
    if "controlnet" in value:
        return {"controlnet"}
    if "checkpoint" in value or "ckptloader" in value:
        return {"checkpoints"}
    if "loraloader" in value or value.startswith("lora"):
        return {"loras"}
    if "vaeloader" in value:
        return {"vae"}
    if "upscalemodelloader" in value:
        return {"upscale_models"}
    if "stylemodelloader" in value:
        return {"style_models"}
    if "gligenloader" in value:
        return {"gligen"}
    if "unetloader" in value or "diffusionmodelloader" in value:
        return {"diffusion_models", "unet"}
    if "cliploader" in value or "textencoderloader" in value:
        return {"clip", "text_encoders"}
    return set()


def _field_may_reference_model(field: str) -> bool:
    key = re.sub(r"[^a-z0-9]+", "_", field.casefold()).strip("_")
    model_subject = (
        r"(?:model|checkpoint|ckpt|weights?|lora|vae|unet|clip|encoder|"
        r"text_encoder|control_?net|diffusion_model|style_model|upscale_model|gligen)"
    )
    locator = r"(?:name|path|file|filename|url|name_or_path)"
    return bool(
        re.fullmatch(
            rf"{model_subject}(?:_{locator})?(?:_?\d+)?",
            key,
        )
    )


def _node_may_reference_model(node_type: str) -> bool:
    value = re.sub(r"[^a-z0-9]+", "", node_type.casefold())
    return ("loader" in value or "load" in value) and any(
        token in value
        for token in (
            "model",
            "checkpoint",
            "ckpt",
            "weight",
            "lora",
            "vae",
            "unet",
            "clip",
            "encoder",
            "controlnet",
            "diffusion",
            "gligen",
        )
    )


def _iter_nodes(
    value: Any, path: tuple[Any, ...] = ()
) -> Iterator[tuple[dict[str, Any], tuple[Any, ...], str, str, str]]:
    """Yield (node, path, kind, id, type), including nodes in subgraphs/envelopes."""

    if isinstance(value, list):
        for index, child in enumerate(value):
            yield from _iter_nodes(child, path + (index,))
        return
    if not isinstance(value, dict):
        return

    ui_type = value.get("type")
    api_type = value.get("class_type")
    if isinstance(ui_type, str) and ui_type and (
        "widgets_values" in value or "inputs" in value or "properties" in value
    ):
        raw_id = value.get("id", path[-1] if path else "")
        yield value, path, "ui", str(raw_id), ui_type
    elif isinstance(api_type, str) and api_type and isinstance(value.get("inputs"), dict):
        raw_id = value.get("id", path[-1] if path else "")
        yield value, path, "api", str(raw_id), api_type

    for key, child in value.items():
        yield from _iter_nodes(child, path + (key,))


def _iter_strings(
    value: Any, path: tuple[Any, ...] = ()
) -> Iterator[tuple[str, tuple[Any, ...], str]]:
    if isinstance(value, str):
        field = str(path[-1]) if path else ""
        yield value, path, field
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _iter_strings(child, path + (index,))
    elif isinstance(value, dict):
        for key, child in value.items():
            yield from _iter_strings(child, path + (key,))


def _metadata_has_sha256(entry: dict[str, Any]) -> bool:
    raw_hash = entry.get("hash")
    if not isinstance(raw_hash, str):
        return False
    normalized = raw_hash.casefold()
    if normalized.startswith("sha256:"):
        return bool(_SHA256.fullmatch(normalized.removeprefix("sha256:")))
    hash_type = entry.get("hash_type")
    return (
        isinstance(hash_type, str)
        and hash_type.strip().casefold() in {"sha256", "sha-256"}
        and bool(_SHA256.fullmatch(normalized))
    )


def _metadata_sha256(entry: dict[str, Any]) -> str | None:
    if not _metadata_has_sha256(entry):
        return None
    normalized = str(entry["hash"]).casefold()
    return normalized.removeprefix("sha256:")


def _validate_url(
    raw: Any,
    filename: str | None,
    *,
    allow_mutable_hf_revision: bool = False,
) -> str:
    """Validate a model URL against the shared inventory/apply safety policy.

    A filename of None binds the URL to no specific file name (used when the
    metadata entry's name is itself invalid and already reported).
    """

    if not isinstance(raw, str) or raw != raw.strip():
        raise InventoryError("model URL must be a non-empty, trimmed string")
    try:
        parsed = urlsplit(raw)
    except ValueError as exc:
        raise InventoryError(f"model URL is not parseable: {raw!r}") from exc
    if parsed.scheme.casefold() != "https" or not parsed.hostname:
        raise InventoryError(f"model URL must use HTTPS: {raw!r}")
    if parsed.username or parsed.password or parsed.fragment:
        raise InventoryError(f"model URL contains credentials or a fragment: {raw!r}")
    try:
        port = parsed.port
    except ValueError as exc:
        raise InventoryError(f"model URL has an invalid port: {raw!r}") from exc
    if port not in {None, 443}:
        raise InventoryError(f"model URL uses a non-HTTPS port: {raw!r}")
    host = parsed.hostname.rstrip(".").casefold()
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise InventoryError(f"IP-address model URLs are not allowed: {raw!r}")
    if host not in ALLOWED_HOSTS:
        raise InventoryError(f"model URL host is not allowlisted: {host}")

    if parsed.query:
        for pair in parsed.query.split("&"):
            key = unquote(pair.split("=", 1)[0])
            if _SENSITIVE_QUERY_KEYS.search(key):
                raise InventoryError("model URL query appears to contain a credential")

    path_parts = [unquote(part) for part in parsed.path.split("/") if part]
    if host == "huggingface.co":
        try:
            resolve_index = path_parts.index("resolve")
            revision = path_parts[resolve_index + 1]
            remote_filename = path_parts[-1]
        except (ValueError, IndexError) as exc:
            raise InventoryError(
                "Hugging Face URL must be a /resolve/<commit>/ file URL"
            ) from exc
        if resolve_index != 2 or len(path_parts) < 5:
            raise InventoryError(
                "Hugging Face URL must identify /<owner>/<repo>/resolve/<commit>/<file>"
            )
        if not _HF_REVISION.fullmatch(revision):
            if not allow_mutable_hf_revision:
                raise InventoryError(
                    "Hugging Face URL must pin a full commit revision unless a "
                    "reviewed SHA-256 binds the expected bytes"
                )
            if not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", revision):
                raise InventoryError("Hugging Face URL contains an unsafe revision")
            # Dot segments (including percent-encoded forms, already decoded by
            # unquote above) must never name a revision.
            if any(
                segment in {".", ".."}
                for segment in revision.replace("\\", "/").split("/")
            ):
                raise InventoryError("Hugging Face URL contains an unsafe revision")
        if filename is not None and remote_filename != filename:
            raise InventoryError(
                "Hugging Face URL filename does not match the manifest filename"
            )
    else:
        if (
            len(path_parts) != 4
            or path_parts[:3] != ["api", "download", "models"]
            or not path_parts[3].isdigit()
        ):
            raise InventoryError(
                "Civitai URL must be /api/download/models/<numeric-version-id>"
            )
    return raw


def _metadata_issues(entry: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    filename = _model_filename(entry.get("name"))
    if filename is None:
        issues.append("invalid_or_missing_name")
    raw_url = entry.get("url")
    if not isinstance(raw_url, str) or not raw_url.strip():
        issues.append("missing_url")
    else:
        try:
            _validate_url(
                raw_url,
                filename,
                allow_mutable_hf_revision=_metadata_has_sha256(entry),
            )
        except InventoryError:
            issues.append("unsafe_url")
    if not isinstance(entry.get("directory"), str) or not entry["directory"].strip():
        issues.append("missing_directory")
    raw_hash = entry.get("hash")
    raw_hash_type = entry.get("hash_type", entry.get("hashType"))
    if raw_hash is not None:
        if not isinstance(raw_hash, str) or not re.fullmatch(
            r"(?:sha256:)?[0-9a-fA-F]{64}", raw_hash, re.IGNORECASE
        ):
            issues.append("invalid_hash")
        else:
            self_describing = raw_hash.casefold().startswith("sha256:")
            valid_type = (
                isinstance(raw_hash_type, str)
                and raw_hash_type.strip().casefold() in {"sha256", "sha-256"}
            )
            if not self_describing and raw_hash_type is None:
                issues.append("missing_hash_type")
            elif not valid_type and raw_hash_type is not None:
                issues.append("invalid_hash_type")
    elif raw_hash_type is not None:
        issues.append("hash_type_without_hash")
    return issues


def _iter_model_arrays(
    value: Any,
    node_by_path: dict[tuple[Any, ...], tuple[str, str, str]],
    path: tuple[Any, ...] = (),
) -> Iterator[
    tuple[
        dict[str, Any],
        tuple[Any, ...],
        str,
        str | None,
        str | None,
        str | None,
    ]
]:
    if isinstance(value, list):
        for index, child in enumerate(value):
            yield from _iter_model_arrays(child, node_by_path, path + (index,))
        return
    if not isinstance(value, dict):
        return

    models = value.get("models")
    if isinstance(models, list):
        node_path = path[:-1] if path and path[-1] == "properties" else None
        node_info = node_by_path.get(node_path) if node_path is not None else None
        scope = "node" if node_info else "root"
        for index, entry in enumerate(models):
            if isinstance(entry, dict):
                yield (
                    entry,
                    path + ("models", index),
                    scope,
                    node_info[0] if node_info else None,
                    node_info[1] if node_info else None,
                    node_info[2] if node_info else None,
                )

    for key, child in value.items():
        yield from _iter_model_arrays(child, node_by_path, path + (key,))


def _detect_format(node_kinds: set[str]) -> str:
    if node_kinds == {"ui"}:
        return "ui"
    if node_kinds == {"api"}:
        return "api"
    if node_kinds == {"ui", "api"}:
        return "hybrid"
    return "unknown"


def _directory_hint_groups(hints: set[str]) -> set[str]:
    aliases = {
        "clip": "text_encoders",
        "text_encoders": "text_encoders",
        "diffusion_models": "diffusion_models",
        "unet": "diffusion_models",
    }
    return {aliases.get(hint.casefold(), hint.casefold()) for hint in hints}


def build_inventory(document: Any, source_name: str | None = None) -> dict[str, Any]:
    if not isinstance(document, dict):
        raise InventoryError("workflow JSON root must be an object")

    nodes = list(_iter_nodes(document))
    node_by_path = {
        path: (node_id, node_type, kind)
        for _, path, kind, node_id, node_type in nodes
    }
    node_kinds = {kind for _, _, kind, _, _ in nodes}
    requirements: dict[str, dict[str, Any]] = {}
    metadata: list[dict[str, Any]] = []
    warnings: list[dict[str, str]] = []

    def add_requirement(
        requirement_key: str,
        filename: str,
        hints: set[str],
        occurrence: dict[str, Any],
        metadata_entry: dict[str, Any] | None = None,
    ) -> None:
        record = requirements.setdefault(
            requirement_key,
            {
                "filenames": set(),
                "directory_hints": set(),
                "occurrences": [],
                "metadata_entries": [],
            },
        )
        record["filenames"].add(filename)
        record["directory_hints"].update(hints)
        record["occurrences"].append(occurrence)
        if metadata_entry is not None:
            record["metadata_entries"].append(metadata_entry)

    for node, node_path, kind, node_id, node_type in nodes:
        sources: list[tuple[str, Any, tuple[Any, ...]]] = []
        if "inputs" in node:
            sources.append(("input", node.get("inputs"), node_path + ("inputs",)))
        if "widgets_values" in node:
            sources.append(
                ("widget", node.get("widgets_values"), node_path + ("widgets_values",))
            )
        for source, values, base_path in sources:
            for raw_value, relative_path, field in _iter_strings(values):
                filename = _model_filename(raw_value)
                unsupported_filename = _unsupported_model_filename(raw_value)
                if not filename and not unsupported_filename:
                    continue
                field_hints = _hints_from_field(field)
                node_hints = _hints_from_node_type(node_type)
                hints = field_hints or node_hints
                value_path = base_path + relative_path
                value_pointer = _pointer(value_path)
                qualified = bool(hints) or _field_may_reference_model(
                    field
                ) or _node_may_reference_model(node_type)
                if not qualified:
                    warnings.append(
                        {
                            "code": "unqualified_model_like_string",
                            "message": (
                                f"ignored {filename or unsupported_filename!r}: node/field "
                                "context does not identify a model consumer"
                            ),
                            "path": value_pointer,
                        }
                    )
                    continue
                if unsupported_filename:
                    warnings.append(
                        {
                            "code": "unsupported_runpoddirect_extension",
                            "message": (
                                f"{unsupported_filename!r} looks like a model, but its "
                                "extension is outside the current RunpodDirect scanner contract"
                            ),
                            "path": value_pointer,
                        }
                    )
                    continue
                add_requirement(
                    "consumer|"
                    + _pointer(node_path)
                    + "|"
                    + value_pointer
                    + "|"
                    + filename.casefold(),
                    filename,
                    hints,
                    {
                        "directory_hints": sorted(hints),
                        "field": field,
                        "node_id": node_id,
                        "node_kind": kind,
                        "node_path": _pointer(node_path),
                        "node_type": node_type,
                        "path": value_pointer,
                        "selected_value": raw_value,
                        "source": source,
                        "subfoldered": _is_subfoldered_selection(raw_value),
                    },
                )

    for entry, entry_path, scope, node_id, node_type, node_kind in _iter_model_arrays(
        document, node_by_path
    ):
        issues = _metadata_issues(entry)
        filename = _model_filename(entry.get("name"))
        normalized = {
            "directory": (
                entry.get("directory")
                if isinstance(entry.get("directory"), str)
                else None
            ),
            "hash": entry.get("hash") if isinstance(entry.get("hash"), str) else None,
            "hash_type": (
                entry.get("hash_type")
                if isinstance(entry.get("hash_type"), str)
                else entry.get("hashType")
                if isinstance(entry.get("hashType"), str)
                else None
            ),
            "issues": issues,
            "name": entry.get("name") if isinstance(entry.get("name"), str) else None,
            "node_id": node_id,
            "node_type": node_type,
            "path": _pointer(entry_path),
            "scope": scope,
            "url": entry.get("url") if isinstance(entry.get("url"), str) else None,
        }
        metadata.append(normalized)
        if filename:
            raw_directory = entry.get("directory")
            hints = (
                {raw_directory.strip()}
                if isinstance(raw_directory, str)
                and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", raw_directory.strip())
                else set()
            )
            metadata_node_path = _pointer(entry_path[:-3]) if node_id is not None else None
            def matching_consumers(*, exact: bool) -> list[str]:
                matches: list[str] = []
                for candidate_key, candidate in requirements.items():
                    candidate_names = set(candidate["filenames"])
                    name_matches = (
                        filename in candidate_names
                        if exact
                        else any(
                            filename.casefold() == candidate_name.casefold()
                            for candidate_name in candidate_names
                        )
                    )
                    if not name_matches:
                        continue
                    candidate_node_paths = {
                        occurrence.get("node_path")
                        for occurrence in candidate["occurrences"]
                        if occurrence.get("source") != "metadata"
                    }
                    if not candidate_node_paths:
                        continue
                    if node_id is None or metadata_node_path in candidate_node_paths:
                        matches.append(candidate_key)
                return matches

            matches = matching_consumers(exact=True)
            case_mismatch = False
            if not matches:
                matches = matching_consumers(exact=False)
                case_mismatch = bool(matches)

            occurrence = {
                "directory_hints": sorted(hints),
                "field": "models",
                "node_id": node_id,
                "node_kind": node_kind,
                "node_path": metadata_node_path,
                "node_type": node_type,
                "path": _pointer(entry_path),
                "selected_value": entry.get("name"),
                "source": "metadata",
                "subfoldered": _is_subfoldered_selection(entry.get("name")),
            }
            if len(matches) == 1:
                candidate = requirements[matches[0]]
                expected_filename = sorted(
                    candidate["filenames"], key=lambda item: (item.casefold(), item)
                )[0]
                if case_mismatch:
                    issues.append("name_mismatch_with_loader")

                candidate_hints = set(candidate["directory_hints"])
                metadata_hints = hints
                if candidate_hints and hints:
                    if _directory_hint_groups(candidate_hints).isdisjoint(
                        _directory_hint_groups(hints)
                    ):
                        issues.append("directory_mismatch_with_loader")
                    # Loader-derived hints remain authoritative. Avoid making a
                    # repair impossible by folding a conflicting metadata folder
                    # back into the requirement's accepted directory set.
                    metadata_hints = set()
                add_requirement(
                    matches[0],
                    expected_filename,
                    metadata_hints,
                    occurrence,
                    normalized,
                )
            elif not matches:
                add_requirement(
                    "metadata|" + _pointer(entry_path) + "|" + filename.casefold(),
                    filename,
                    hints,
                    occurrence,
                    normalized,
                )
            else:
                warnings.append(
                    {
                        "code": "ambiguous_model_metadata_scope",
                        "message": (
                            "metadata basename matches multiple consuming fields and was not "
                            "used to satisfy any one requirement"
                        ),
                        "path": _pointer(entry_path),
                    }
                )
        if issues:
            warnings.append(
                {
                    "code": "incomplete_model_metadata",
                    "message": ", ".join(issues),
                    "path": _pointer(entry_path),
                }
            )

    output_requirements: list[dict[str, Any]] = []
    for requirement_key, raw_record in requirements.items():
        filenames = sorted(raw_record["filenames"], key=lambda item: (item.casefold(), item))
        occurrences = sorted(
            raw_record["occurrences"],
            key=lambda item: (
                item.get("path") or "",
                item.get("source") or "",
                item.get("node_id") or "",
            ),
        )
        unique_occurrences = []
        seen_occurrences: set[str] = set()
        for occurrence in occurrences:
            signature = _canonical_json(occurrence)
            if signature not in seen_occurrences:
                seen_occurrences.add(signature)
                unique_occurrences.append(occurrence)

        metadata_entries = raw_record["metadata_entries"]
        if metadata_entries and any(not item["issues"] for item in metadata_entries):
            metadata_status = "complete"
        elif metadata_entries:
            metadata_status = "partial"
        else:
            metadata_status = "missing"
        output_requirements.append(
            {
                "directory_ambiguous": len(
                    _directory_hint_groups(raw_record["directory_hints"])
                )
                > 1,
                "directory_hints": sorted(raw_record["directory_hints"]),
                "filename": filenames[0],
                "metadata_status": metadata_status,
                "occurrences": unique_occurrences,
                "selection_mismatch": any(
                    occurrence.get("selected_value") != filenames[0]
                    for occurrence in unique_occurrences
                    if occurrence.get("source") != "metadata"
                ),
                "subfoldered": any(
                    occurrence.get("subfoldered") is True
                    for occurrence in unique_occurrences
                    if occurrence.get("source") != "metadata"
                ),
                "requirement_id": "model-"
                + hashlib.sha256(requirement_key.encode("utf-8")).hexdigest()[:16],
            }
        )

    output_requirements.sort(
        key=lambda item: (
            item["filename"].casefold(),
            item["filename"],
            item["requirement_id"],
        )
    )
    metadata.sort(key=lambda item: (item["path"], item.get("name") or ""))
    warnings.sort(key=lambda item: (item["path"], item["code"], item["message"]))

    result = {
        "existing_metadata": metadata,
        "requirements": output_requirements,
        "schema_version": SCHEMA_VERSION,
        "summary": {
            "complete_metadata": sum(
                item["metadata_status"] == "complete" for item in output_requirements
            ),
            "model_requirements": len(output_requirements),
            "nodes_scanned": len(nodes),
            "unresolved_requirements": sum(
                item["metadata_status"] != "complete" for item in output_requirements
            ),
        },
        "warnings": warnings,
        "workflow_format": _detect_format(node_kinds),
        "workflow_sha256": workflow_sha256(document),
    }
    if source_name:
        result["source_name"] = source_name
    return result


def load_json(path: Path) -> Any:
    def reject_constant(value: str) -> Any:
        raise InventoryError(f"invalid JSON in {path}: non-finite number {value!r}")

    def finite_float(value: str) -> float:
        parsed = float(value)
        if not math.isfinite(parsed):
            reject_constant(value)
        return parsed

    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            return json.load(
                handle,
                parse_constant=reject_constant,
                parse_float=finite_float,
            )
    except OSError as exc:
        raise InventoryError(f"cannot read {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise InventoryError(f"invalid JSON in {path}: {exc}") from exc


def _write_report(report: dict[str, Any], output: Path | None) -> None:
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if output is None:
        sys.stdout.write(rendered)
        return
    if output.exists():
        raise InventoryError(f"refusing to overwrite existing report: {output}")
    if not output.parent.exists():
        raise InventoryError(f"output directory does not exist: {output.parent}")
    try:
        with output.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(rendered)
    except (OSError, UnicodeError) as exc:
        raise InventoryError(f"cannot write {output}: {exc}") from exc


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inventory conservative model requirements in a ComfyUI workflow."
    )
    parser.add_argument("workflow", type=Path, help="ComfyUI workflow JSON")
    parser.add_argument("--output", "-o", type=Path, help="write a new report file")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        if args.output and os.path.normcase(str(args.workflow.resolve())) == os.path.normcase(
            str(args.output.resolve())
        ):
            raise InventoryError("report output must not overwrite the workflow")
        document = load_json(args.workflow)
        report = build_inventory(document, source_name=args.workflow.name)
        _write_report(report, args.output)
    except InventoryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
