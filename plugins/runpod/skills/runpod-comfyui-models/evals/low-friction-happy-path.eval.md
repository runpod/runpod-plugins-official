# Repair an exact public model without conversational friction

## Prompt

Here is a ComfyUI output PNG from an older community workflow. Find the missing models,
repair the metadata, and check which ones my live Runpod ComfyUI Pod still needs. Do not
download anything yet.

## Expected behavior

The agent treats the supplied artifact and repair request as authorization for read-only
inspection, deterministic extraction/inventory, provider lookup, live presence checks,
and writing a new repaired workflow copy. It does not pause for those ordinary steps.

It resolves all requirements together, uses publisher/workflow context first, batches
independent provider and live checks, and prefers structured connectors/MCP/built-in web
access over a user-visible sequence of shell `curl` calls. When an official publisher
record provides an exact compatible path, pinned revision, and trusted matching hash, it
marks that item verified and stops; it does not research mirrors merely for completeness.

It keeps extraction, inventory, and its resolution manifest in one task-specific
temporary directory. It writes the verified metadata to a new workflow copy,
re-inventories it, cleans the temporary directory, and returns one concise result with
exactly one full absolute file path/link: the repaired JSON. A compact in-chat model
summary, live missing state, and the fact that no download was started are not extra artifacts. It
does not end by requiring the user to answer an optional next-step question.

## Assertions

- Asks zero user questions when every model has one verified public ungated identity.
- Makes no per-model confirmation loop and performs one batch missing-model check.
- Does not add `--help`, separate PNG inspection, empty capability probes, `/object_info`,
  or a post-annotation live rescan when the direct operation already provides the evidence.
- Avoids shell `curl` when connected or built-in HTTP/provider tooling can do the work.
- Stops resolution at the first verified official/publisher artifact.
- Reuses one canonical provider response instead of separately fetching repository,
  commit, file, access, and license evidence or querying unrelated candidates.
- Preserves the original PNG/workflow and leaves only one new persistent file: the
  repaired JSON.
- Reports the repaired JSON's full absolute path.
- Does not attach, link, or leave beside the input a normalized/extracted JSON, inventory,
  or manifest.
- Does not download, install, restart, overwrite, or queue because those were not requested.
- Reports the completed repair and optional next action without turning it into a blocker.
