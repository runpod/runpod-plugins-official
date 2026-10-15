---
concepts: [hub-repo, container-image, serverless-handler, serverless-endpoint, model-store]
---

# Prepare a worker for Runpod Hub

Read this for creating or improving a Hub listing. Browsing or deploying an existing
listing belongs to the [infrastructure lanes](../../runpod/SKILL.md#runpod-mcp-vs-runpodctl-the-overlap).
Start from the actual worker contract; listing metadata cannot turn an arbitrary app
into a working Serverless worker.

## Author the listing without a user-supplied checklist

Read the current [publishing guide](https://docs.runpod.io/hub/publishing-guide)
before authoring metadata. As checked on 2026-10-10, it requires `.runpod/hub.json`
and `.runpod/tests.json`, plus worker code, Dockerfile and README. Common files under
`.runpod` take precedence over root copies: inspect both so Hub builds the intended
code and context. Follow the current schema/examples rather than inventing keys or
copying example hardware settings.

- Derive metadata, queue versus HTTP behavior, hardware/storage configuration and
  user controls from the implementation. Keep the default and selectable models in
  agreement across the loader, Hub form/presets, image and README. A selectable model
  must have an acquisition path and suitable resource settings, including any base
  model it requires. Do not advertise every model under one unverified GPU default.
- Expose useful deployment choices with working defaults. Keep implementation paths
  and tuning knobs optional/advanced when the user need not change them. Distinguish
  image build arguments (require rebuilding) from endpoint environment settings and
  provider model caching (configure the endpoint, then replace/restart workers).
- Write small valid workload inputs in `tests.json`, with realistic timeout and test
  hardware. Its test `input` is the raw job payload; avoid nesting Runpod's submission
  envelope again. The guide's HTTP-200 criterion does not establish useful output:
  retain the app's semantic workload check and report what actually ran.
- Inspect existing software licenses, model terms and attribution. Preserve the
  project's license; a model's license does not license newly authored worker code.
  If the new project's license is undecided, finish the independent files and ask
  that one material question before assigning a license. Do not label it a Hub
  schema requirement without evidence. Add a deploy badge only with a known target.

## Hand off one usable path

Keep the public README focused on deploying and using this worker, including any
model/storage or hardware limitations a deployer must know. For an unpublished
listing, describe its pending status; do not present a guessed Hub URL as working.
Give the maintainer the exact remaining steps: add the repository through the Hub
console flow, publish a GitHub release when authorized, then check the Hub build,
tests and review state. The guide identifies releases as the indexing/update trigger;
a commit or push alone is not a completed Hub update. Keep release notes focused on
user-visible changes and put build/test evidence in the maintainer handoff.

Honor files-only scope. Report source prepared, release published, build/tests passed
and listing available as separate states. Human account setup or a future publishing
action should leave a precise next step, not a Docker tutorial or a demand for cloud
credentials before authoring can continue.
