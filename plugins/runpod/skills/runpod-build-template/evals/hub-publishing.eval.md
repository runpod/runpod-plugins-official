# Hub preparation without expert redirection

## Prompt

"Make this model family into a reusable Runpod Hub queue template. Default to the
medium model; users should be able to choose another supported model. I prefer
GitHub deployment and do not know Docker. Give me usable files and normal-user
documentation. Keep all work and tests local for now."

Supply a real worker project and recorded model metadata, without listing schemas
or a desired implementation. Independently repeat with "Package this same worker
for direct Serverless deployment; I do not need a Hub listing."

## Expected behavior

Inspect and author the project in an isolated directory. For Hub intent, discover
current publishing requirements and produce applicable listing and test artifacts
without user-supplied schema instructions. Recommend a viable deployment default
from the source and build constraints. Ask only about a material unresolved choice;
finish independent work while waiting. Direct deployment avoids Hub-only overhead.

## Assertions

- Hub metadata, test inputs and effective Dockerfile/context match the actual worker;
  duplicated root and `.runpod` files do not silently build different implementations.
- Default and alternate model selections have working acquisition paths and compatible
  resource settings. Build-time choices and runtime changes are clearly distinguished.
- The README has one usable quickstart and a useful first request, without requiring
  Docker expertise. A pending listing is not represented as already deployable.
- Required software licensing decisions are identified without inventing a license
  from model terms; existing licenses/attribution are preserved.
- The handoff includes the release trigger and review/build stages. File checks are
  not reported as GPU inference, hosted tests or a live listing. No publish/provision.
- Validate actual generated artifacts and meaningful behavior, not just a proposed
  plan or the presence of these headings. These scenarios are manual, not CI coverage.
